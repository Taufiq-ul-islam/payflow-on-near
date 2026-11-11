import base64
import json
import httpx

from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.integrations.near_intents import near_intents
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction
from app.core.config import settings


FINAL_STATUSES = {"SUCCESS", "REFUNDED", "FAILED", "DUPLICATE_SETTLEMENT", "SETTLEMENT_REVIEW"}


def mark_invoice_settled(
    db: Session,
    invoice: Invoice,
    attempt: PaymentAttempt,
) -> str:
    """
    Atomically claim an invoice for one verified payment attempt.
    Returns SUCCESS, DUPLICATE_SETTLEMENT, or SETTLEMENT_REVIEW.
    """

    updated = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice.id,
            Invoice.status == "PENDING",
            Invoice.paid_payment_attempt_id.is_(None),
        )
        .update(
            {
                Invoice.status: "PAID",
                Invoice.paid_payment_attempt_id: attempt.id,
                Invoice.paid_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )

    db.refresh(invoice)

    if updated == 1:
        attempt.status = "SUCCESS"
        return "SUCCESS"

    # This exact attempt may already have settled the invoice.
    if invoice.paid_payment_attempt_id == attempt.id:
        attempt.status = "SUCCESS"
        return "SUCCESS"

    # Another attempt already settled it. Preserve this attempt's
    # transaction evidence, but do not overwrite the original payment.
    if invoice.status == "PAID":
        attempt.status = "DUPLICATE_SETTLEMENT"
        return "DUPLICATE_SETTLEMENT"

    # Payment was verified, but the invoice is no longer payable.
    attempt.status = "SETTLEMENT_REVIEW"
    return "SETTLEMENT_REVIEW"


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

    if attempt.status in FINAL_STATUSES:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == attempt.invoice_id)
            .one()
        )

        status_data = attempt.provider_response or {}

        # Repair successful payments whose received amount was not persisted.
        if attempt.status == "SUCCESS" and not attempt.received_amount:
            swap_details = status_data.get("swapDetails") or {}
            recovered_amount = swap_details.get("amountOut")

            if recovered_amount:
                if str(recovered_amount) != str(attempt.expected_amount):
                    raise ValueError("Stored settlement amount does not match expected amount")

                attempt.received_amount = str(recovered_amount)
                db.commit()
                db.refresh(attempt)

        response = {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": status_data.get("status") or attempt.status,
            "invoice_status": invoice.status,
            "received_amount": attempt.received_amount,
            "swap_details": status_data.get("swapDetails"),
            "payment_attempt_status": attempt.status,
        }

        db.commit()
        return response

    if not attempt.deposit_address:
        raise ValueError("Payment attempt has no deposit address")

    status_data = await near_intents.get_status(
        deposit_address=attempt.deposit_address,
        deposit_memo=attempt.deposit_memo,
    )

    provider_status = status_data.get("status")

    if not provider_status:
        raise ValueError("Tidepool returned no execution status")
    
    allowed_provider_statuses = {
        "PENDING_DEPOSIT",
        "KNOWN_DEPOSIT_TX",
        "INCOMPLETE_DEPOSIT",
        "PROCESSING",
        "SUCCESS",
        "REFUNDED",
        "FAILED",
    }

    if provider_status not in allowed_provider_statuses:
        raise ValueError(f"Unexpected Tidepool payment status: {provider_status}")

    attempt.provider_response = status_data

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == attempt.invoice_id)
        .with_for_update()
        .one()
    )

    if provider_status == "SUCCESS":
        original_quote = attempt.quote_response
        status_quote = status_data.get("quoteResponse") or {}

        if status_data.get("correlationId") != status_quote.get("correlationId"):
            raise ValueError("Tidepool correlation ID mismatch")

        if original_quote.get("correlationId") != status_quote.get("correlationId"):
            raise ValueError("Tidepool response does not match original quote")

        original_request = original_quote.get("quoteRequest") or {}
        status_request = status_quote.get("quoteRequest") or {}

        status_quote_details = status_quote.get("quote") or {}
        swap_details = status_data.get("swapDetails") or {}

        # Ensure the status response refers to our original quote.
        if status_quote_details.get("depositAddress") != attempt.deposit_address :
            raise ValueError("Status response deposit address mismatch")

        if status_request.get("destinationAsset") != attempt.destination_asset :
            raise ValueError("Destination asset mismatch")
        
        if attempt.destination_asset != settings.usdc_asset_id:
            raise ValueError("Payment attempt destination is not configured USDC")

        if status_request.get("amount") != attempt.expected_amount:
            raise ValueError("Tidepool requested amount mismatch")

        if status_quote_details.get("amountOut") != attempt.expected_amount:
            raise ValueError("Tidepool quoted output amount mismatch")

        if status_quote.get("signature") != original_quote.get("signature"):
            raise ValueError("Tidepool quote signature mismatch")

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

        # Store one primary settlement transaction with the full
        # received amount. The complete list of destination hashes
        # remains available in attempt.provider_response.
        primary_transaction = destination_transactions[0]

        if not isinstance(primary_transaction, dict):
            raise ValueError("Invalid destination transaction entry")

        tx_hash = primary_transaction.get("hash")

        if not isinstance(tx_hash, str) or not tx_hash.strip():
            raise ValueError("Missing destination transaction hash")

        existing_transaction = (
            db.query(Transaction)
            .filter(Transaction.tx_hash == tx_hash)
            .first()
        )

        if existing_transaction:
            if existing_transaction.payment_attempt_id != attempt.id:
                raise ValueError(
                    "Destination transaction is already associated "
                    "with another payment attempt"
                )
        else:
            db.add(
                Transaction(
                    payment_attempt_id=attempt.id,
                    chain="NEAR",
                    tx_hash=tx_hash,
                    transaction_type="SETTLEMENT",
                    amount=received_amount,
                    explorer_url=primary_transaction.get("explorerUrl"),
                )
            )

        # Tidepool-reported success is not yet independently verified
        # against NEAR RPC. The settlement ownership guard still prevents
        # a second attempt from claiming an already-paid invoice.
        settlement_result = mark_invoice_settled(db, invoice, attempt)

    elif provider_status == "REFUNDED":
        attempt.status = "REFUNDED"
        # A refunded attempt does not mean the invoice was paid.
        if invoice.status != "PAID":
            invoice.status = "PENDING"

    elif provider_status == "FAILED":
        attempt.status = "FAILED"
        if invoice.status != "PAID":
            invoice.status = "PENDING"
    
    else :
        attempt.status = provider_status

    db.commit()

    return {
        "payment_attempt_id": str(attempt.id),
        "invoice_id": str(invoice.id),
        "provider_status": provider_status,
        "invoice_status": invoice.status,
        "received_amount": attempt.received_amount,
        "swap_details": status_data.get("swapDetails"),
        "payment_attempt_status": attempt.status,
    }



class NearRPCError(Exception):
    pass


async def reconcile_direct_near_payment(
    db: Session,
    attempt: PaymentAttempt,
):
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt.id)
        .with_for_update()
        .one()
    )

    if attempt.status in FINAL_STATUSES:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == attempt.invoice_id)
            .one()
        )

        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": attempt.status,
            "invoice_status": invoice.status,
            "received_amount": attempt.received_amount,
        }

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == attempt.invoice_id)
        .with_for_update()
        .one()
    )

    transaction_record = (
        db.query(Transaction)
        .filter(
            Transaction.payment_attempt_id == attempt.id,
            Transaction.transaction_type == "DIRECT_PAYMENT",
        )
        .first()
    )

    if not transaction_record:
        raise ValueError("Direct payment transaction has not been submitted")

    sender_account = (
        (attempt.provider_response or {}).get("direct_sender_account")
    )

    if not sender_account:
        raise ValueError("Payer NEAR account ID is missing")

    prefix, separator, token_contract = (
        settings.usdc_asset_id.partition(":")
    )

    if prefix != "nep141" or not separator or not token_contract:
        raise ValueError("Configured USDC asset is not a NEAR NEP-141 asset")

    tx_hash = transaction_record.tx_hash

    payload = {
        "jsonrpc": "2.0",
        "id": "payflow-direct-payment",
        "method": "tx",
        "params": [tx_hash, sender_account],
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                settings.near_rpc_url,
                json=payload,
            )
            response.raise_for_status()
            rpc_data = response.json()

    except httpx.HTTPError as exc:
        raise NearRPCError(
            f"Could not verify NEAR transaction: {exc}"
        ) from exc

    except ValueError as exc:
        raise NearRPCError(
            "NEAR RPC returned an invalid response"
        ) from exc

    if rpc_data.get("error"):
        error_text = json.dumps(rpc_data["error"])

        if "UNKNOWN_TRANSACTION" in error_text:
            db.commit()
            return {
                "payment_attempt_id": str(attempt.id),
                "invoice_id": str(invoice.id),
                "provider_status": "PROCESSING",
                "invoice_status": invoice.status,
                "message": "Transaction is not yet available on NEAR RPC",
            }

        raise NearRPCError(f"NEAR RPC error: {error_text}")

    result = rpc_data.get("result")

    if not result:
        db.commit()
        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": "PROCESSING",
            "invoice_status": invoice.status,
        }

    transaction = result.get("transaction") or {}

    # Verify the actual signer and destination token contract.
    if transaction.get("signer_id") != sender_account:
        raise ValueError("Transaction signer does not match payer account")

    if transaction.get("receiver_id") != token_contract:
        raise ValueError("Transaction was not sent to the configured USDC contract")

    if transaction.get("hash") != tx_hash:
        raise ValueError("NEAR transaction hash mismatch")

    # Ensure this was a standard ft_transfer call.
    function_call = None

    for action in transaction.get("actions") or []:
        if isinstance(action, dict) and "FunctionCall" in action:
            function_call = action["FunctionCall"]
            break

    if not function_call:
        raise ValueError("Transaction does not contain a fungible-token transfer")

    if function_call.get("method_name") != "ft_transfer":
        raise ValueError("Expected a standard ft_transfer transaction")

    try:
        action_args = json.loads(
            base64.b64decode(function_call["args"]).decode("utf-8")
        )
    except Exception as exc:
        raise ValueError("Could not decode NEAR transfer arguments") from exc

    if action_args.get("receiver_id") != invoice.freelancer_id:
        raise ValueError("Transfer recipient does not match freelancer")

    if str(action_args.get("amount")) != attempt.expected_amount:
        raise ValueError("Transfer amount does not match invoice")

    execution_status = result.get("status") or {}

    if "Failure" in execution_status:
        attempt.status = "FAILED"
        db.commit()

        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": "FAILED",
            "invoice_status": invoice.status,
        }

    # Do not accept a transaction that has not successfully executed.
    if not (
        "SuccessValue" in execution_status
        or "SuccessReceiptId" in execution_status
    ):
        db.commit()

        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": "PROCESSING",
            "invoice_status": invoice.status,
        }

    # Collect execution logs from the transaction and its receipts.
    outcomes = [result.get("transaction_outcome") or {}]
    outcomes.extend(result.get("receipts_outcome") or [])

    logs = []

    for item in outcomes:
        outcome = item.get("outcome") or {}
        logs.extend(outcome.get("logs") or [])

    # Verify the actual NEP-141 transfer event.
    verified_transfer = False

    for log in logs:
        if "EVENT_JSON:" not in log:
            continue

        raw_event = log.split("EVENT_JSON:", 1)[1]

        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            continue

        if (
            event.get("standard") != "nep141"
            or event.get("event") != "ft_transfer"
        ):
            continue

        for transfer in event.get("data") or []:
            if (
                transfer.get("old_owner_id") == sender_account
                and transfer.get("new_owner_id") == invoice.freelancer_id
                and str(transfer.get("amount")) == attempt.expected_amount
            ):
                verified_transfer = True
                break

        if verified_transfer:
            break

    if not verified_transfer:
        raise ValueError(
            "No matching NEP-141 USDC transfer event was found"
        )

    # Only now is the direct payment considered settled.
    attempt.received_amount = attempt.expected_amount
    mark_invoice_settled(db, invoice, attempt)

    attempt.provider_response = {
        **(attempt.provider_response or {}),
        "near_rpc_verified": True,
        "verified_transaction_hash": tx_hash,
    }

    transaction_record.amount = attempt.expected_amount
    transaction_record.explorer_url = (
        f"https://testnet.nearblocks.io/txns/{tx_hash}"
    )

    db.commit()

    return {
        "payment_attempt_id": str(attempt.id),
        "invoice_id": str(invoice.id),
        "provider_status": attempt.status,
        "invoice_status": invoice.status,
        "received_amount": attempt.received_amount,
        "verification": "NEAR_RPC_NEp141_EVENT",
    }