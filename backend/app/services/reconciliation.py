from sqlalchemy.orm import Session

from app.integrations.near_intents import near_intents
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction


FINAL_STATUSES = {"SUCCESS", "REFUNDED", "FAILED"}


async def reconcile_payment(
    db: Session,
    attempt: PaymentAttempt,
):
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt.id)
        .with_for_update()
        .one()
    )

    if not attempt.deposit_address:
        raise ValueError("Payment attempt has no deposit address")

    status_data = await near_intents.get_status(
        deposit_address=attempt.deposit_address,
        deposit_memo=attempt.deposit_memo,
    )

    provider_status = status_data.get("status")

    if not provider_status:
        raise ValueError("Tidepool returned no execution status")

    attempt.provider_response = status_data
    attempt.status = provider_status

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == attempt.invoice_id)
        .with_for_update()
        .one()
    )

    if provider_status == "SUCCESS":
        original_quote = attempt.quote_response
        status_quote = status_data.get("quoteResponse") or {}

        original_request = original_quote.get("quoteRequest") or {}
        status_request = status_quote.get("quoteRequest") or {}

        status_quote_details = status_quote.get("quote") or {}
        swap_details = status_data.get("swapDetails") or {}

        # Ensure the status response refers to our original quote.
        if (
            status_quote_details.get("depositAddress")
            != attempt.deposit_address
        ):
            raise ValueError("Status response deposit address mismatch")

        if (
            status_request.get("destinationAsset")
            != attempt.destination_asset
        ):
            raise ValueError("Destination asset mismatch")

        if status_request.get("recipient") != invoice.freelancer_id:
            raise ValueError("Settlement recipient mismatch")

        if (
            original_request.get("destinationAsset")
            != status_request.get("destinationAsset")
        ):
            raise ValueError("Quote destination changed")

        if (
            original_request.get("recipient")
            != status_request.get("recipient")
        ):
            raise ValueError("Quote recipient changed")

        received_amount = swap_details.get("amountOut")

        if not received_amount:
            raise ValueError("Missing actual output amount")

        if received_amount != attempt.expected_amount:
            raise ValueError(
                "Received amount does not match the exact-output quote"
            )

        destination_transactions = (
            swap_details.get("destinationChainTxHashes") or []
        )

        if not destination_transactions:
            raise ValueError("SUCCESS response has no destination transaction hash")

        attempt.received_amount = received_amount

        for item in destination_transactions:
            tx_hash = item.get("hash")

            if not tx_hash:
                continue

            exists = (
                db.query(Transaction)
                .filter(Transaction.tx_hash == tx_hash)
                .first()
            )

            if not exists:
                db.add(
                    Transaction(
                        payment_attempt_id=attempt.id,
                        chain="NEAR",
                        tx_hash=tx_hash,
                        transaction_type="SETTLEMENT",
                        amount=received_amount,
                        explorer_url=item.get("explorerUrl"),
                    )
                )

        # This is provider-reported settlement confirmation.
        # It is not yet an independent NEAR RPC verification.
        if invoice.status != "PAID":
            invoice.status = "PAID"

    elif provider_status == "REFUNDED":
        # A refunded attempt does not mean the invoice was paid.
        if invoice.status != "PAID":
            invoice.status = "PENDING"

    elif provider_status == "FAILED":
        if invoice.status != "PAID":
            invoice.status = "PENDING"

    db.commit()

    return {
        "payment_attempt_id": str(attempt.id),
        "invoice_id": str(invoice.id),
        "provider_status": provider_status,
        "invoice_status": invoice.status,
        "received_amount": attempt.received_amount,
        "swap_details": status_data.get("swapDetails"),
    }