from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from redis_fastapi import rate_limit

from app.core.config import settings
from app.core.database import get_db
from app.api.auth import current_user

from app.models.user import User
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt
from app.models.refund import Refund, RefundTransaction

from app.schemas.refund import RefundQuoteRequest, RefundResponse, RefundDepositSubmitRequest
from app.services.refund_service import (
    create_refund_quote,
    verify_refund_transfer,
    amount_to_units,
    get_usdc_token_for_network,
    normalize_network,
)
from app.services.refund_reconciliation import reconcile_direct_near_refund, reconcile_cross_chain_refund
from app.integrations.near_intents import near_intents, NearIntentsError
from app.integrations.near_rpc import NearRpcError
from app.integrations.quote_signature import verify_quote_signature


router = APIRouter(prefix="/refunds", tags=["Refunds"])


def serialize_refund(refund: Refund) -> dict:
    return {
        "refund_id": str(refund.id),
        "payment_attempt_id": str(refund.payment_attempt_id),
        "status": refund.status,
        "destination_network": refund.destination_network,
        "destination_asset": refund.destination_asset,
        "destination_address": refund.destination_address,
        "requested_amount": str(refund.requested_amount),
        "source_amount": str(refund.source_amount),
        "expected_amount": str(refund.expected_amount),
        "fee_details": refund.fee_details,
    }


def get_owned_refund_query(db: Session, user: User):
    return (
        db.query(Refund)
        .join(
            PaymentAttempt,
            Refund.payment_attempt_id == PaymentAttempt.id,
        )
        .join(
            Invoice,
            PaymentAttempt.invoice_id == Invoice.id,
        )
        .filter(Invoice.freelancer_id == user.near_account_id)
    )


def parse_refund_id(refund_id: str) -> UUID:
    try:
        return UUID(refund_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid refund ID.",
        )



@router.post(
    "/quote/{payment_attempt_id}",
    response_model=RefundResponse,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def request_refund_quote(
    payment_attempt_id: str,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=255,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        attempt_id = UUID(payment_attempt_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment attempt ID.",
        )

    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt_id)
        .with_for_update()
        .first()
    )

    if not attempt:
        raise HTTPException(404, "Payment attempt not found.")

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == attempt.invoice_id,
            Invoice.freelancer_id == user.near_account_id,
        )
        .first()
    )

    if not invoice:
        raise HTTPException(404, "Payment attempt not found.")

    # Idempotent retry: return the existing quote for this payment.
    if idempotency_key:
        existing = (
            get_owned_refund_query(db, user)
            .filter(Refund.idempotency_key == idempotency_key)
            .first()
        )

        if existing:
            if existing.payment_attempt_id != attempt.id:
                raise HTTPException(
                    409,
                    "Idempotency key was already used for another refund.",
                )
            return serialize_refund(existing)

        key_exists = (
            db.query(Refund.id)
            .filter(Refund.idempotency_key == idempotency_key)
            .first()
        )

        if key_exists:
            raise HTTPException(
                409,
                "Idempotency key is already in use.",
            )

    if attempt.status not in {"SUCCESS", "DUPLICATE_SETTLEMENT"}:
        raise HTTPException(409, "Only successful or duplicate settlements can be refunded.")

    # Use the payer details saved and validated during payment submission.
    destination_network = normalize_network(attempt.payer_network)
    destination_address = (attempt.payer_address or "").strip()
    payer_asset = (attempt.payer_asset or "").strip()

    if not destination_network or not destination_address or not payer_asset:
        raise HTTPException(
            409,
            "Original payer wallet details are missing. "
            "This payment cannot use automatic refunds.",
        )

    if attempt.payer_asset_decimals is None:
        raise HTTPException(409, "Original payer asset decimals are missing.")

    if (
        attempt.received_amount is None
        or Decimal(str(attempt.received_amount)) <= 0
    ):
        raise HTTPException(409, "No refundable received amount is recorded.")

    
    # Resolve USDC on the original payer's network using the shared registry parser.
    try:
        destination_token = await get_usdc_token_for_network(destination_network)

        destination_asset = destination_token["assetId"]

    except NearIntentsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # PaymentAttempt.received_amount is stored in USDC base units.
    
    # Enforce one active refund per payment attempt.
    existing_refunds = (
        db.query(Refund)
        .filter(Refund.payment_attempt_id == attempt.id)
        .all()
    )

    for existing_refund in existing_refunds:
        if existing_refund.status != "FAILED":
            raise HTTPException(
                409,
                "A refund already exists for this payment attempt. "
                "Only one full refund is allowed.",
            )

        recorded_transaction = (
            db.query(RefundTransaction.id)
            .filter(
                RefundTransaction.refund_id == existing_refund.id
            )
            .first()
        )

        if recorded_transaction:
            raise HTTPException(
                409,
                "A failed refund has a recorded transfer. "
                "It must be reconciled before another refund.",
            )

    # Refund the entire received USDC balance.
    requested_amount = (
        Decimal(str(attempt.received_amount))
        / (Decimal(10) ** settings.usdc_decimals)
    )

    try:
        result = await create_refund_quote(
            destination_network=destination_network,
            destination_asset=destination_asset,
            destination_address=destination_address,
            requested_amount=requested_amount,
            freelancer_near_account=user.near_account_id,
        )

    except ValueError as exc:
        raise HTTPException(400, str(exc))

    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))

    source_amount = Decimal(str(result["source_amount"]))
    expected_amount = Decimal(str(result["expected_amount"]))

    if source_amount != requested_amount:
        raise HTTPException(
            400,
            detail="The quote does not cover the entire refundable balance.",
        )

    quote_response = result.get("quote_response") or {}
    quote = quote_response.get("quote") or {}

    provider_correlation_id = quote_response.get("correlationId")
    quote_signature = quote_response.get("signature")

    if destination_network != "near":
        if not quote_signature or not provider_correlation_id:
            raise HTTPException(
                status_code=502,
                detail="NEAR Intents 1Click quote is missing its signature or correlation ID.",
            )

    refund = Refund(
        id=uuid4(),
        payment_attempt_id=attempt.id,
        idempotency_key=idempotency_key,
        destination_network=destination_network,
        destination_asset=destination_asset,
        destination_address=destination_address,
        requested_amount=requested_amount,
        source_asset=settings.usdc_asset_id,
        source_amount=source_amount,
        expected_amount=expected_amount,
        quote_id=provider_correlation_id,
        quote_signature=quote_signature,
        provider_correlation_id=provider_correlation_id,
        quote_response=quote_response,
        fee_details=result.get("fee_details"),
        deposit_address=quote.get("depositAddress"),
        deposit_memo=quote.get("depositMemo"),
        status="AWAITING_APPROVAL",
    )

    db.add(refund)

    try:
        db.commit()
        db.refresh(refund)

    except Exception:
        db.rollback()
        raise HTTPException(
            409,
            "Could not save refund request. The idempotency key may already be in use.",
        )

    return serialize_refund(refund)




@router.post("/{refund_id}/approve", dependencies=[Depends(rate_limit("10/minute"))])
def approve_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    refund_uuid = parse_refund_id(refund_id)

    refund = (
        get_owned_refund_query(db, user)
        .filter(Refund.id == refund_uuid)
        .with_for_update()
        .first()
    )

    if not refund:
        raise HTTPException(404, "Refund not found.")

    if refund.status not in {"AWAITING_APPROVAL", "PENDING"}:
        raise HTTPException(
            409,
            "Refund is no longer eligible for approval.",
        )

    # A PENDING refund can only be retried if no transfer was recorded.
    if refund.status == "PENDING":
        existing_transaction = (
            db.query(RefundTransaction)
            .filter(RefundTransaction.refund_id == refund.id)
            .first()
        )

        if existing_transaction:
            raise HTTPException(
                409,
                "A refund transfer has already been recorded. "
                "Reconcile it instead of sending another transfer.",
            )

    # Cross-chain refunds require a valid, unexpired signed quote.
    if refund.destination_network != "near":
        quote_response = refund.quote_response

        if not isinstance(quote_response, dict):
            raise HTTPException(
                409,
                "Refund quote data is invalid. Request a new quote.",
            )

        quote = quote_response.get("quote")
        quote_request = quote_response.get("quoteRequest")

        if not isinstance(quote, dict) or not isinstance(quote_request, dict):
            raise HTTPException(
                409,
                "Refund quote is incomplete. Request a new quote.",
            )

        signature = quote_response.get("signature")
        timestamp = quote_response.get("timestamp")
        correlation_id = quote_response.get("correlationId")

        if (
            not signature
            or signature != refund.quote_signature
            or not correlation_id
            or correlation_id != refund.provider_correlation_id
        ):
            raise HTTPException(
                409,
                "Refund quote signature or correlation ID is invalid.",
            )

        if not verify_quote_signature(
            quote_request,
            quote,
            timestamp,
            signature,
        ):
            raise HTTPException(
                409,
                "Refund quote signature verification failed. "
                "Request a new quote.",
            )

        # Verify that the signed quote matches the persisted refund.
        expected_quote_fields = {
            "originAsset": refund.source_asset,
            "destinationAsset": refund.destination_asset,
            "amount": amount_to_units(
                Decimal(str(refund.source_amount)),
                settings.usdc_decimals,
            ),
            "refundTo": user.near_account_id,
            "recipient": refund.destination_address,
            "swapType": "EXACT_INPUT",
            "depositMode": "SIMPLE",
            "depositType": "ORIGIN_CHAIN",
            "refundType": "ORIGIN_CHAIN",
            "recipientType": "DESTINATION_CHAIN",
        }

        for field, expected in expected_quote_fields.items():
            if quote_request.get(field) != expected:
                raise HTTPException(
                    409,
                    f"Refund quote {field} does not match the refund record.",
                )

        if quote.get("depositAddress") != refund.deposit_address:
            raise HTTPException(
                409,
                "Refund deposit address does not match the signed quote.",
            )

        if quote.get("depositMemo") != refund.deposit_memo:
            raise HTTPException(
                409,
                "Refund deposit memo does not match the signed quote.",
            )

        if str(quote.get("amountIn")) != expected_quote_fields["amount"]:
            raise HTTPException(
                409,
                "Refund quote input amount does not match the refundable balance.",
            )

        deadline = quote_request.get("deadline")

        if not isinstance(deadline, str) or not deadline:
            raise HTTPException(409, "Refund quote has no deadline. Request a new quote.")

        try:
            expires_at = datetime.fromisoformat(
                deadline.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(
                409,
                "Refund quote has an invalid deadline. Request a new quote.",
            )

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                409,
                "Refund quote expired. Request a new quote.",
            )

    # Only after validation succeeds do we approve the refund.
    if refund.status == "AWAITING_APPROVAL":
        refund.approved_at = datetime.now(timezone.utc)

    refund.status = "PENDING"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            409,
            "Could not approve the refund. Please retry.",
        )

    return {
        "refund_id": str(refund.id),
        "status": refund.status,
        "payment_mode": (
            "DIRECT_NEAR_REFUND"
            if refund.destination_network == "near"
            else "CROSS_CHAIN"
        ),
        "source_asset": refund.source_asset,
        "destination_network": refund.destination_network,
        "destination_asset": refund.destination_asset,
        "destination_address": refund.destination_address,
        "requested_amount": str(refund.requested_amount),
        "source_amount": str(refund.source_amount),
        "expected_amount": str(refund.expected_amount),
        "deposit_address": refund.deposit_address,
        "deposit_memo": refund.deposit_memo,
        "message": "Refund approved. Awaiting wallet transfer.",
    }



@router.post("/{refund_id}/deposit-submit", dependencies=[Depends(rate_limit("10/minute"))])
async def submit_refund_deposit(
    refund_id: str,
    payload: RefundDepositSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    refund_uuid = parse_refund_id(refund_id)

    refund = (
        get_owned_refund_query(db, user)
        .filter(Refund.id == refund_uuid)
        .with_for_update()
        .first()
    )

    if not refund:
        raise HTTPException(
            status_code=404,
            detail="Refund not found.",
        )

    if payload.near_sender_account != user.near_account_id:
        raise HTTPException(
            status_code=403,
            detail="Transaction sender must match the authenticated freelancer.",
        )

    tx_hash = payload.tx_hash.strip()

    if not tx_hash:
        raise HTTPException(
            status_code=400,
            detail="Transaction hash is required.",
        )

    is_direct_near = refund.destination_network == "near"

    # Check the hash before checking the refund status.
    # This allows retries after the original submission was recorded.
    existing_transaction = (
        db.query(RefundTransaction)
        .filter(RefundTransaction.tx_hash == tx_hash)
        .first()
    )

    if existing_transaction:
        if existing_transaction.refund_id != refund.id:
            raise HTTPException(
                status_code=409,
                detail="Transaction hash is already associated with another refund.",
            )

        if refund.status != "PROCESSING":
            raise HTTPException(
                status_code=409,
                detail=f"Refund is in unexpected status {refund.status}.",
            )

        if is_direct_near:
            return {
                "refund_id": str(refund.id),
                "status": refund.status,
                "transaction_hash": tx_hash,
                "message": "NEAR refund transaction is already recorded.",
            }

        # Provider submission may have failed or its response may
        # have been lost. Retry using the SAME transaction hash.
        provider_status = (
            (refund.provider_response or {}).get(
                "deposit_submission_status"
            )
        )

        if provider_status == "SUBMITTED":
            return {
                "refund_id": str(refund.id),
                "status": refund.status,
                "transaction_hash": tx_hash,
                "message": "Transaction has already been submitted to NEAR Intents 1Click.",
            }

        if not refund.deposit_address:
            raise HTTPException(
                status_code=409,
                detail="Refund has no NEAR Intents 1Click deposit address.",
            )

        try:
            provider_response = await near_intents.submit_deposit(
                deposit_address=refund.deposit_address,
                tx_hash=tx_hash,
                memo=refund.deposit_memo,
                near_sender_account=payload.near_sender_account,
            )

        except NearIntentsError as exc:
            refund.provider_response = {
                **(refund.provider_response or {}),
                "deposit_submission_status": "RETRY_REQUIRED",
                "deposit_submission_error": str(exc),
            }

            try:
                db.commit()
            except Exception:
                db.rollback()
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Provider submission failed, and the retry state "
                        "could not be saved. Reconcile before retrying."
                    ),
                )

            raise HTTPException(
                status_code=502,
                detail=(
                    "The transaction is recorded, but NEAR Intents 1Click submission "
                    "failed. Retry submission using the same transaction hash."
                ),
            )

        refund.provider_response = {
            **(refund.provider_response or {}),
            "deposit_submit": provider_response,
            "deposit_submission_status": "SUBMITTED",
            "deposit_submission_error": None,
        }

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "NEAR Intents 1Click submission was attempted, but its response "
                    "could not be saved. Retry using the same transaction hash."
                ),
            )

        return {
            "refund_id": str(refund.id),
            "status": refund.status,
            "transaction_hash": tx_hash,
            "message": "Transaction submitted to NEAR Intents 1Click. Awaiting refund completion.",
        }

    # New transaction submissions are accepted only while PENDING.
    if refund.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Refund cannot accept a transaction in status {refund.status}.",
        )

    if not is_direct_near and not refund.deposit_address:
        raise HTTPException(
            status_code=409,
            detail="Refund has no NEAR Intents 1Click deposit address.",
        )

    # Verify the actual source NEP-141 transfer before recording it.
    try:
        verification = await verify_refund_transfer(
            refund=refund,
            tx_hash=tx_hash,
            sender_account=payload.near_sender_account,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except NearRpcError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    transaction_type = (
        "DIRECT_NEAR_REFUND"
        if is_direct_near
        else "REFUND_DEPOSIT"
    )

    # Persist the verified transaction BEFORE calling NEAR Intents 1Click.
    refund.provider_response = {
        **(refund.provider_response or {}),
        "source_transfer_verification": verification,
        "deposit_submission_status": (
            "NOT_REQUIRED" if is_direct_near else "SUBMISSION_PENDING"
        ),
    }

    db.add(
        RefundTransaction(
            id=uuid4(),
            refund_id=refund.id,
            chain="NEAR",
            tx_hash=tx_hash,
            transaction_type=transaction_type,
            asset=refund.source_asset,
            amount=refund.source_amount,
        )
    )

    refund.status = "PROCESSING"

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not record the verified refund transaction.",
        )

    # Direct NEAR refunds need no NEAR Intents 1Click submission.
    if is_direct_near:
        return {
            "refund_id": str(refund.id),
            "status": refund.status,
            "transaction_hash": tx_hash,
            "payment_mode": "DIRECT_NEAR_USDC",
            "message": "NEAR refund transaction recorded. Awaiting verification.",
        }

    # Cross-chain: submit the already-recorded transaction to NEAR Intents 1Click.
    try:
        provider_response = await near_intents.submit_deposit(
            deposit_address=refund.deposit_address,
            tx_hash=tx_hash,
            memo=refund.deposit_memo,
            near_sender_account=payload.near_sender_account,
        )

    except NearIntentsError as exc:
        refund.provider_response = {
            **(refund.provider_response or {}),
            "deposit_submission_status": "RETRY_REQUIRED",
            "deposit_submission_error": str(exc),
        }

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=(
                    "Provider submission failed, and the retry state "
                    "could not be saved. Reconcile before retrying."
                ),
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "The transaction is recorded, but NEAR Intents 1Click submission "
                "failed. Retry submission using the same transaction hash."
            ),
        )

    refund.provider_response = {
        **(refund.provider_response or {}),
        "deposit_submit": provider_response,
        "deposit_submission_status": "SUBMITTED",
        "deposit_submission_error": None,
    }

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "NEAR Intents 1Click submission was attempted, but its response "
                "could not be saved. Retry using the same transaction hash."
            ),
        )

    return {
        "refund_id": str(refund.id),
        "status": refund.status,
        "transaction_hash": tx_hash,
        "payment_mode": "CROSS_CHAIN",
        "message": "Transaction submitted to NEAR Intents 1Click. Awaiting refund completion.",
    }


@router.post("/{refund_id}/reconcile", dependencies=[Depends(rate_limit("20/minute"))])
async def reconcile_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    refund_uuid = parse_refund_id(refund_id)

    refund = (
        get_owned_refund_query(db, user)
        .filter(Refund.id == refund_uuid)
        .first()
    )

    if not refund:
        raise HTTPException(
            status_code=404,
            detail="Refund not found.",
        )

    try:
        if refund.destination_network == "near":
            return await reconcile_direct_near_refund(
                db=db,
                refund_id=refund_uuid,
                freelancer_near_account=user.near_account_id,
            )

        return await reconcile_cross_chain_refund(
            db=db,
            refund_id=refund_uuid,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except NearRpcError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except NearIntentsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/{refund_id}")
def get_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    refund_uuid = parse_refund_id(refund_id)

    refund = (
        get_owned_refund_query(db, user)
        .filter(Refund.id == refund_uuid)
        .first()
    )

    if not refund:
        raise HTTPException(
            status_code=404,
            detail="Refund not found.",
        )

    result = serialize_refund(refund)

    result.update({
        "source_asset": refund.source_asset,
        "deposit_address": refund.deposit_address,
        "deposit_memo": refund.deposit_memo,
        "received_amount": (
            str(refund.received_amount)
            if refund.received_amount is not None
            else None
        ),
        "provider_response": refund.provider_response,
        "created_at": refund.created_at.isoformat(),
        "approved_at": (
            refund.approved_at.isoformat()
            if refund.approved_at else None
        ),
        "completed_at": (
            refund.completed_at.isoformat()
            if refund.completed_at else None
        ),
        "transactions": [
            {
                "chain": transaction.chain,
                "tx_hash": transaction.tx_hash,
                "transaction_type": transaction.transaction_type,
                "asset": transaction.asset,
                "amount": (
                    str(transaction.amount)
                    if transaction.amount is not None
                    else None
                ),
                "explorer_url": transaction.explorer_url,
            }
            for transaction in refund.transactions
        ],
    })

    return result


@router.get("")
def list_refunds(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    refunds = (
        get_owned_refund_query(db, user)
        .order_by(Refund.created_at.desc())
        .all()
    )

    return [serialize_refund(refund) for refund in refunds]
