from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload
from redis_fastapi import rate_limit

from app.core.database import get_db
from app.integrations.near_intents import near_intents, NearIntentsError
from app.integrations.quote_signature import verify_quote_signature
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction
from app.schemas.payment import DepositSubmitRequest
from app.services.payment_service import create_payment_quote, convert_usdc_to_units
from app.services.reconciliation import reconcile_payment, reconcile_direct_near_payment, NearRPCError
from app.core.config import settings
from app.models.user import User
from app.api.auth import current_user


router = APIRouter(prefix="/payments", tags=["Payments"])


ACTIVE_STATUSES = {
    "PENDING_DEPOSIT",
    "KNOWN_DEPOSIT_TX",
    "INCOMPLETE_DEPOSIT",
    "PROCESSING",
}


def serialize_attempt(attempt):
    return {
        "payment_attempt_id": str(attempt.id),
        "status": attempt.status,
        "deposit_address": attempt.deposit_address,
        "deposit_memo": attempt.deposit_memo,
        "expected_amount": attempt.expected_amount,
        "destination_asset": attempt.destination_asset,
        "payment_mode": (
            (attempt.quote_response or {}).get("payment_mode", "INTENTS")
        ),
    }


def verify_provider_quote(quote_response):
    """Verify the signature on a NEAR Intents 1Click quote."""

    if not isinstance(quote_response, dict):
        return False

    return verify_quote_signature(
        quote_response.get("quoteRequest"),
        quote_response.get("quote"),
        quote_response.get("timestamp"),
        quote_response.get("signature"),
    )


@router.get("/")
def list_payment_attempts(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    attempts = (
        db.query(PaymentAttempt)
        .join(Invoice, PaymentAttempt.invoice_id == Invoice.id)
        .options(
            joinedload(PaymentAttempt.invoice),
            selectinload(PaymentAttempt.transactions),
        )
        .filter(Invoice.freelancer_id == user.near_account_id)
        .order_by(PaymentAttempt.created_at.desc())
        .all()
    )

    return [
        {
            "id": str(attempt.id),
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(attempt.invoice_id),
            "invoice_number": attempt.invoice.invoice_number,
            "client_name": attempt.invoice.client_name,
            "status": attempt.status,
            "deposit_address": attempt.deposit_address,
            "deposit_memo": attempt.deposit_memo,
            "source_asset": attempt.source_asset,
            "destination_asset": attempt.destination_asset,
            "expected_amount": attempt.expected_amount,
            "received_amount": attempt.received_amount,
            "created_at": attempt.created_at,
            "payer_address": attempt.payer_address,
            "payer_network": attempt.payer_network,
            "payer_asset": attempt.payer_asset,
            "payer_asset_decimals": attempt.payer_asset_decimals,
            "transactions": [
                {
                    "id": str(transaction.id),
                    "chain": transaction.chain,
                    "tx_hash": transaction.tx_hash,
                    "transaction_type": transaction.transaction_type,
                    "amount": transaction.amount,
                    "explorer_url": transaction.explorer_url,
                    "created_at": transaction.created_at,
                }
                for transaction in attempt.transactions
            ],
        }
        for attempt in attempts
    ]


@router.get(
    "/tokens",
    dependencies=[Depends(rate_limit("30/minute"))],
)
async def supported_tokens():
    try:
        return await near_intents.get_tokens()
    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))


@router.post(
    "/quote/{invoice_id}",
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def request_quote(
    invoice_id: UUID,
    source_asset: str,
    refund_address: str,
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    try:
        quote_response = await create_payment_quote(
            invoice,
            source_asset,
            refund_address,
            dry=True,
        )

        if not verify_provider_quote(quote_response):
            raise HTTPException(
                502,
                "NEAR Intents quote signature verification failed",
            )

        return quote_response

    except ValueError as exc:
        raise HTTPException(400, str(exc))

    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))


@router.post(
    "/direct/{invoice_id}",
    dependencies=[Depends(rate_limit("5/minute"))],
)
def create_direct_payment(
    invoice_id: UUID,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.idempotency_key == idempotency_key)
        .first()
    )

    if existing:
        if existing.invoice_id != invoice_id:
            raise HTTPException(
                409,
                "Idempotency key was already used for another invoice",
            )

        if (
            (existing.quote_response or {}).get("payment_mode")
            != "DIRECT_NEAR"
        ):
            raise HTTPException(
                409,
                "Idempotency key belongs to a different payment method",
            )

        return {
            **serialize_attempt(existing),
            "quote": existing.quote_response,
        }

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )

    if not invoice:
        db.rollback()
        raise HTTPException(404, "Invoice not found")

    if invoice.status != "PENDING":
        db.rollback()
        raise HTTPException(409, "Invoice is not payable")

    if not invoice.freelancer_id:
        db.rollback()
        raise HTTPException(400, "Freelancer NEAR account is missing")

    if not settings.usdc_asset_id.startswith("nep141:"):
        db.rollback()
        raise HTTPException(
            400,
            "Direct payment requires a NEAR NEP-141 USDC asset",
        )

    if invoice.due_date:
        due_date = invoice.due_date

        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)

        if due_date < datetime.now(timezone.utc):
            db.rollback()
            raise HTTPException(400, "Invoice has expired")

    try:
        amount_units = convert_usdc_to_units(invoice.total)
        attempt_id = uuid4()

        quote_response = {
            "payment_mode": "DIRECT_NEAR",
            "quoteRequest": {
                "originAsset": settings.usdc_asset_id,
                "destinationAsset": settings.usdc_asset_id,
                "recipient": invoice.freelancer_id,
                "amount": amount_units,
            },
            "quote": {
                "amountIn": amount_units,
                "amountOut": amount_units,
            },
        }

        attempt = PaymentAttempt(
            id=attempt_id,
            invoice_id=invoice.id,
            idempotency_key=idempotency_key,
            quote_response=quote_response,
            deposit_address=f"direct-near:{attempt_id}",
            deposit_memo=None,
            source_asset=settings.usdc_asset_id,
            destination_asset=settings.usdc_asset_id,
            expected_input_amount=amount_units,
            expected_amount=amount_units,
            refund_address=None,
            status="PENDING_DEPOSIT",
        )

        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        return {
            **serialize_attempt(attempt),
            "quote": quote_response,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post(
    "/commit/{invoice_id}",
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def commit_payment(
    invoice_id: UUID,
    source_asset: str,
    refund_address: str,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.idempotency_key == idempotency_key)
        .first()
    )

    if existing:
        if existing.invoice_id != invoice_id:
            raise HTTPException(
                409,
                "Idempotency key was already used for another invoice",
            )

        if (
            existing.source_asset != source_asset
            or existing.refund_address != refund_address
        ):
            raise HTTPException(
                409,
                "Idempotency key was reused with different payment details",
            )

        return {
            **serialize_attempt(existing),
            "quote": existing.quote_response,
        }

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )

    if not invoice:
        db.rollback()
        raise HTTPException(404, "Invoice not found")

    if invoice.status != "PENDING":
        db.rollback()
        raise HTTPException(409, "Invoice is not payable")

    try:
        quote_response = await create_payment_quote(
            invoice,
            source_asset,
            refund_address,
            dry=False,
        )

        if not isinstance(quote_response, dict):
            raise ValueError("Invalid NEAR Intents quote response")

        quote = quote_response.get("quote")
        quote_request = quote_response.get("quoteRequest")

        if not isinstance(quote, dict) or not isinstance(
            quote_request, dict
        ):
            raise ValueError(
                "NEAR Intents returned an incomplete quote"
            )

        if not verify_provider_quote(quote_response):
            raise ValueError(
                "NEAR Intents 1Click quote signature verification failed"
            )

        correlation_id = quote_response.get("correlationId")

        if not isinstance(correlation_id, str) or not correlation_id:
            raise ValueError(
                "NEAR Intents quote has no correlation ID"
            )

        expected_quote_fields = {
            "originAsset": source_asset,
            "destinationAsset": settings.usdc_asset_id,
            "amount": convert_usdc_to_units(invoice.total),
            "refundTo": refund_address,
            "recipient": invoice.freelancer_id,
            "swapType": "EXACT_OUTPUT",
            "depositMode": "SIMPLE",
            "depositType": "ORIGIN_CHAIN",
            "refundType": "ORIGIN_CHAIN",
            "recipientType": "DESTINATION_CHAIN",
        }

        for field, expected in expected_quote_fields.items():
            if quote_request.get(field) != expected:
                raise ValueError(
                    f"NEAR Intents quote has an unexpected {field}"
                )

        deposit_address = quote.get("depositAddress")
        expected_amount = quote.get("amountOut")
        expected_input_amount = quote.get("amountIn")

        if (
            not isinstance(deposit_address, str)
            or not deposit_address
            or expected_amount is None
            or expected_input_amount is None
        ):
            raise ValueError(
                "NEAR Intents 1Click returned an incomplete live quote"
            )

        if str(expected_amount) != convert_usdc_to_units(invoice.total):
            raise ValueError(
                "NEAR Intents quote output does not match the invoice amount"
            )

        try:
            if int(str(expected_input_amount)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(
                "NEAR Intents returned an invalid input amount"
            )

        attempt = PaymentAttempt(
            invoice_id=invoice.id,
            idempotency_key=idempotency_key,
            quote_id=correlation_id,
            quote_signature=quote_response.get("signature"),
            quote_response=quote_response,
            deposit_address=deposit_address,
            deposit_memo=quote.get("depositMemo"),
            source_asset=source_asset,
            destination_asset=settings.usdc_asset_id,
            expected_input_amount=expected_input_amount,
            expected_amount=expected_amount,
            refund_address=refund_address,
            provider_correlation_id=correlation_id,
            status="PENDING_DEPOSIT",
        )

        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        return {
            **serialize_attempt(attempt),
            "quote": quote_response,
        }

    except NearIntentsError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))

    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.post(
    "/{attempt_id}/deposit-submit",
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def submit_deposit(
    attempt_id: UUID,
    data: DepositSubmitRequest,
    db: Session = Depends(get_db),
):
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt_id)
        .with_for_update()
        .first()
    )

    if not attempt:
        raise HTTPException(404, "Payment attempt not found")

    if attempt.status not in ACTIVE_STATUSES:
        raise HTTPException(
            409,
            f"Cannot submit a deposit for status {attempt.status}",
        )

    quote_response = attempt.quote_response or {}

    is_direct_near = (
        quote_response.get("payment_mode") == "DIRECT_NEAR"
    )

    tx_hash = data.tx_hash.strip()
    payer_address = (data.payer_address or "").strip()
    payer_network = (data.payer_network or "").strip().lower()
    payer_asset = (data.payer_asset or "").strip()

    duplicate = (
        db.query(Transaction)
        .filter(Transaction.tx_hash == tx_hash)
        .first()
    )

    if duplicate:
        if duplicate.payment_attempt_id == attempt.id:
            return {"status": "already_submitted"}

        raise HTTPException(
            409,
            "Transaction hash is already associated with another payment",
        )

    # Direct NEAR payment: no 1Click correlation ID is required.
    if is_direct_near:
        sender_account = (
            data.near_sender_account or ""
        ).strip()

        if not sender_account:
            raise HTTPException(
                400,
                "Payer NEAR account ID is required for direct payment",
            )

        if not payer_address or payer_address != sender_account:
            raise HTTPException(
                400,
                "Payer address must match the NEAR sender account",
            )

        if payer_network != "near":
            raise HTTPException(
                400,
                "Direct payment network must be NEAR",
            )

        if (
            attempt.source_asset != settings.usdc_asset_id
            or payer_asset != settings.usdc_asset_id
            or data.payer_asset_decimals != settings.usdc_decimals
        ):
            raise HTTPException(
                400,
                "Direct payment must use the configured NEAR USDC asset",
            )

        attempt.payer_address = sender_account
        attempt.payer_network = "near"
        attempt.payer_asset = settings.usdc_asset_id
        attempt.payer_asset_decimals = settings.usdc_decimals

        transaction = Transaction(
            payment_attempt_id=attempt.id,
            chain="NEAR",
            tx_hash=tx_hash,
            transaction_type="DIRECT_PAYMENT",
            amount=attempt.expected_amount,
            explorer_url=(
                f"https://{'nearblocks.io' if settings.near_network == 'mainnet' else 'testnet.nearblocks.io'}/txns/{tx_hash}"
            ),
        )

        attempt.provider_response = {
            "direct_sender_account": sender_account,
        }
        attempt.status = "PROCESSING"

        db.add(transaction)
        db.commit()

        return {
            "status": attempt.status,
            "payment_mode": "DIRECT_NEAR",
            "message": "Transaction submitted for NEAR verification",
        }

    # Cross-chain payment: require the original 1Click correlation ID.
    if not attempt.provider_correlation_id:
        raise HTTPException(
            409,
            "Payment attempt has no provider correlation ID",
        )

    if (
        quote_response.get("correlationId")
        != attempt.provider_correlation_id
    ):
        raise HTTPException(
            409,
            "Payment quote correlation ID mismatch",
        )

    if not payer_address or not payer_network or not payer_asset:
        raise HTTPException(
            400,
            "Payer address, network, and asset are required",
        )

    if (
        not attempt.refund_address
        or payer_address != attempt.refund_address
    ):
        raise HTTPException(
            400,
            "Payer address does not match the original payment quote",
        )

    if payer_asset != attempt.source_asset:
        raise HTTPException(
            400,
            "Payer asset does not match the original payment quote",
        )

    try:
        token_response = await near_intents.get_tokens()

        if isinstance(token_response, list):
            tokens = token_response

        elif isinstance(token_response, dict):
            tokens = (
                token_response.get("tokens")
                or token_response.get("data")
            )

            if isinstance(tokens, dict):
                tokens = tokens.get("tokens")

        else:
            tokens = None

        if not isinstance(tokens, list):
            raise HTTPException(
                502,
                "Unexpected NEAR Intents 1Click token registry response",
            )

        source_token = next(
            (
                token
                for token in tokens
                if isinstance(token, dict)
                and token.get("assetId") == attempt.source_asset
            ),
            None,
        )

        if not source_token:
            raise HTTPException(
                400,
                "Original payment asset is not in NEAR Intents 1Click's token registry",
            )

        registry_network = str(
            source_token.get("blockchain") or ""
        ).lower()

        try:
            registry_decimals = int(source_token["decimals"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                502,
                "NEAR Intents 1Click token registry has invalid asset decimals",
            )

        if payer_network != registry_network:
            raise HTTPException(
                400,
                "Payer network does not match the original payment asset",
            )

        if data.payer_asset_decimals != registry_decimals:
            raise HTTPException(
                400,
                "Payer asset decimals do not match NEAR Intents 1Click's token registry",
            )

        attempt.payer_address = payer_address
        attempt.payer_network = payer_network
        attempt.payer_asset = payer_asset
        attempt.payer_asset_decimals = registry_decimals

        result = await near_intents.submit_deposit(
            deposit_address=attempt.deposit_address,
            tx_hash=tx_hash,
            memo=attempt.deposit_memo,
            near_sender_account=data.near_sender_account,
        )

        if not isinstance(result, dict):
            raise NearIntentsError(
                "NEAR Intents returned an invalid deposit submission response"
            )

        transaction = Transaction(
            payment_attempt_id=attempt.id,
            chain="ORIGIN",
            tx_hash=tx_hash,
            transaction_type="DEPOSIT",
        )

        db.add(transaction)
        attempt.provider_response = result

        if result.get("status"):
            attempt.status = result["status"]

        db.commit()

        return {
            "status": attempt.status,
            "provider_response": result,
        }

    except NearIntentsError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))


@router.get(
    "/{attempt_id}/status",
    dependencies=[Depends(rate_limit("30/minute"))],
)
async def payment_status(
    attempt_id: UUID,
    db: Session = Depends(get_db),
):
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt_id)
        .first()
    )

    if not attempt:
        raise HTTPException(404, "Payment attempt not found")

    try:
        if (
            (attempt.quote_response or {}).get("payment_mode")
            == "DIRECT_NEAR"
        ):
            return await reconcile_direct_near_payment(db, attempt)

        return await reconcile_payment(db, attempt)

    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))

    except NearRPCError as exc:
        raise HTTPException(502, str(exc))

    except ValueError as exc:
        raise HTTPException(409, str(exc))
