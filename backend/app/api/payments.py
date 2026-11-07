from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.near_intents import (
    near_intents,
    NearIntentsError,
)
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction
from app.schemas.payment import DepositSubmitRequest
from app.services.payment_service import create_payment_quote
from app.services.reconciliation import reconcile_payment


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
    }


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
        result = await reconcile_payment(db, attempt)
        return result
    except NearIntentsError as exc:
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))