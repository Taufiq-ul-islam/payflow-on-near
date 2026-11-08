from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.database import get_db
from app.integrations.near_intents import near_intents, NearIntentsError
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction
from app.schemas.payment import DepositSubmitRequest
from app.services.payment_service import create_payment_quote, convert_usdc_to_units
from app.services.reconciliation import reconcile_payment, reconcile_direct_near_payment, NearRPCError
from app.core.config import settings


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



@router.get("/")
def list_payment_attempts(
    freelancer_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    attempts = (
        db.query(PaymentAttempt)
        .join(Invoice, PaymentAttempt.invoice_id == Invoice.id)
        .options(
            joinedload(PaymentAttempt.invoice),
            selectinload(PaymentAttempt.transactions),
        )
        .filter(Invoice.freelancer_id == freelancer_id)
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


@router.get("/tokens")
async def supported_tokens():
    try:
        return await near_intents.get_tokens()
    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))


@router.post("/quote/{invoice_id}")
async def request_quote(
    invoice_id: UUID,
    source_asset: str,
    refund_address: str,
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    try:
        return await create_payment_quote(
            invoice,
            source_asset,
            refund_address,
            dry=True,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))


@router.post("/direct/{invoice_id}")
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
    # Idempotent retry.
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

    active_attempt = (
        db.query(PaymentAttempt)
        .filter(
            PaymentAttempt.invoice_id == invoice_id,
            PaymentAttempt.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )

    if active_attempt:
        db.rollback()
        raise HTTPException(
            409,
            "An active payment attempt already exists",
        )

    try:
        amount_units = convert_usdc_to_units(invoice.total)

        attempt_id = uuid4()

        # Synthetic unique internal address because the existing
        # database column is non-nullable and unique.
        # The actual recipient is stored in quoteRequest.recipient.
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


@router.post("/commit/{invoice_id}")
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
    # A retry with the same key returns the original attempt.
    existing = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.idempotency_key == idempotency_key)
        .first()
    )

    if existing:
        if existing.invoice_id != invoice_id:
            raise HTTPException(
                409, "Idempotency key was already used for another invoice",
            )
        
        if (
            existing.source_asset != source_asset
            or existing.refund_address != refund_address
        ):
            raise HTTPException(
                409, "Idempotency key was reused with different payment details",
            )

        return {
            **serialize_attempt(existing),
            "quote": existing.quote_response,
        }

    # Lock the invoice row to serialize concurrent commit requests.
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

    active_attempt = (
        db.query(PaymentAttempt)
        .filter(
            PaymentAttempt.invoice_id == invoice_id,
            PaymentAttempt.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )

    if active_attempt:
        db.rollback()
        raise HTTPException(
            409, "An active payment attempt already exists",
        )

    try:
        # Keep the row lock until the quote is persisted.
        quote_response = await create_payment_quote(
            invoice, source_asset, refund_address, dry=False,
        )

        quote = quote_response.get("quote") or {}
        quote_request = quote_response.get("quoteRequest") or {}

        deposit_address = quote.get("depositAddress")
        expected_amount = quote.get("amountOut")

        if not deposit_address or not expected_amount:
            raise ValueError("Tidepool returned an incomplete live quote")

        attempt = PaymentAttempt(
            invoice_id=invoice.id,
            idempotency_key=idempotency_key,

            quote_id=quote_response.get("correlationId"),
            quote_signature=quote_response.get("signature"),
            quote_response=quote_response,

            deposit_address=deposit_address,
            deposit_memo=quote.get("depositMemo"),

            source_asset=source_asset,
            destination_asset=quote_request.get("destinationAsset"),

            expected_input_amount=quote.get("amountIn"),
            expected_amount=expected_amount,

            refund_address=refund_address,
            provider_correlation_id=quote_response.get("correlationId"),

            status="PENDING_DEPOSIT",
        )

        if not quote_request.get("destinationAsset"):
            raise ValueError("Quote has no destination asset")

        if quote_request.get("recipient") != invoice.freelancer_id:
            raise ValueError("Quote recipient does not match invoice")

        if not attempt.destination_asset:
            raise ValueError("Quote has no destination asset")

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


@router.post("/{attempt_id}/deposit-submit")
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

    duplicate = (
        db.query(Transaction)
        .filter(Transaction.tx_hash == data.tx_hash)
        .first()
    )

    if duplicate:
        if duplicate.payment_attempt_id == attempt.id:
            return {"status": "already_submitted"}

        raise HTTPException(
            409,
            "Transaction hash is already associated with another payment",
        )

    # Direct NEAR USDC payment: do not submit anything to Tidepool.
    if (
        (attempt.quote_response or {}).get("payment_mode") == "DIRECT_NEAR"
    ):
        sender_account = (data.near_sender_account or "").strip()

        if not sender_account:
            raise HTTPException(
                400, "Payer NEAR account ID is required for direct payment",
            )

        transaction = Transaction(
            payment_attempt_id=attempt.id,
            chain="NEAR",
            tx_hash=data.tx_hash,
            transaction_type="DIRECT_PAYMENT",
            amount=attempt.expected_amount,
            explorer_url=(f"https://testnet.nearblocks.io/txns/{data.tx_hash}"),
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
    
    try:
        result = await near_intents.submit_deposit(
            deposit_address=attempt.deposit_address,
            tx_hash=data.tx_hash,
            memo=attempt.deposit_memo,
            near_sender_account=data.near_sender_account,
        )

        transaction = Transaction(
            payment_attempt_id=attempt.id,
            chain="ORIGIN",
            tx_hash=data.tx_hash,
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


@router.get("/{attempt_id}/status")
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
        if ((attempt.quote_response or {}).get("payment_mode") == "DIRECT_NEAR"):
            return await reconcile_direct_near_payment(db, attempt)
        
        return await reconcile_payment(db, attempt)

    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))
    except NearRPCError as exc:
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))