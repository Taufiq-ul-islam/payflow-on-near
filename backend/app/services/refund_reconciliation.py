from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.near_intents import near_intents
from app.integrations.near_rpc import NearRpcError
from app.models.refund import Refund, RefundTransaction
from app.services.refund_service import verify_refund_transfer, get_usdc_token, amount_to_units


PENDING_PROVIDER_STATUSES = {
    "PENDING_DEPOSIT",
    "KNOWN_DEPOSIT_TX",
    "INCOMPLETE_DEPOSIT",
    "PROCESSING",
}

FINAL_REFUND_STATUSES = {"SUCCESS", "FAILED", "REVIEW"}


def _refund_response(refund):
    return {
        "refund_id": str(refund.id),
        "status": refund.status,
        "received_amount": (
            str(refund.received_amount)
            if refund.received_amount is not None
            else None
        ),
    }


def _get_quote_details(refund):
    response = refund.quote_response or {}
    quote = response.get("quote", response)

    return response, quote


def _mark_review(refund, db, status_data, reason):
    refund.status = "REVIEW"
    refund.provider_response = {
        **(refund.provider_response or {}),
        "latest_status": status_data,
        "review_reason": reason,
    }
    db.commit()
    return _refund_response(refund)


async def reconcile_direct_near_refund(
    db: Session,
    refund_id,
    freelancer_near_account: str,
):
    refund = (
        db.query(Refund)
        .filter(Refund.id == refund_id)
        .with_for_update()
        .one_or_none()
    )

    if not refund:
        raise ValueError("Refund not found.")

    if refund.destination_network != "near":
        raise ValueError("This is not a direct NEAR refund.")

    if refund.status == "SUCCESS":
        return _refund_response(refund)

    if refund.status not in ["PENDING", "PROCESSING"]:
        raise ValueError(
            f"Cannot reconcile refund in status {refund.status}."
        )

    transaction = (
        db.query(RefundTransaction)
        .filter(
            RefundTransaction.refund_id == refund.id,
            RefundTransaction.transaction_type == "DIRECT_NEAR_REFUND",
        )
        .first()
    )

    if not transaction:
        raise ValueError("Direct NEAR refund transaction was not found.")

    verification = await verify_refund_transfer(
        refund=refund,
        tx_hash=transaction.tx_hash,
        sender_account=freelancer_near_account,
    )

    expected_units = amount_to_units(
        Decimal(str(refund.expected_amount)),
        settings.usdc_decimals,
    )

    if verification["amount"] != expected_units:
        raise ValueError("Verified refund amount does not match expected amount.")

    expected_amount = Decimal(str(refund.expected_amount))

    refund.received_amount = expected_amount
    refund.status = "SUCCESS"
    refund.completed_at = datetime.now(timezone.utc)

    refund.provider_response = {
        **(refund.provider_response or {}),
        "direct_near_refund_verification": verification,
        "reconciliation_status": "SUCCESS",
    }

    transaction.amount = expected_amount
    transaction.explorer_url = (
        f"https://testnet.nearblocks.io/txns/{transaction.tx_hash}"
    )

    db.commit()

    return {
        **_refund_response(refund),
        "transaction_hash": transaction.tx_hash,
        "message": "Direct NEAR refund successfully verified.",
    }


async def reconcile_cross_chain_refund(
    db: Session,
    refund_id,
):
    refund = (
        db.query(Refund)
        .filter(Refund.id == refund_id)
        .with_for_update()
        .one_or_none()
    )

    if not refund:
        raise ValueError("Refund not found.")

    if refund.destination_network == "near":
        raise ValueError("This is not a cross-chain refund.")

    if refund.status in FINAL_REFUND_STATUSES:
        return _refund_response(refund)

    if refund.status not in ["PENDING", "PROCESSING"]:
        raise ValueError(f"Cannot reconcile refund in status {refund.status}.")

    if not refund.deposit_address:
        raise ValueError("Refund has no Tidepool deposit address.")

    status_data = await near_intents.get_status(
        deposit_address=refund.deposit_address,
        deposit_memo=refund.deposit_memo,
    )

    provider_status = status_data.get("status")

    if not provider_status:
        raise ValueError("Tidepool returned no refund execution status.")

    if provider_status in PENDING_PROVIDER_STATUSES:
        refund.provider_response = {
            **(refund.provider_response or {}),
            "latest_status": status_data,
        }
        db.commit()

        return {
            **_refund_response(refund),
            "provider_status": provider_status,
            "message": "Refund is still processing.",
        }

    if provider_status == "FAILED":
        refund.status = "FAILED"
        refund.provider_response = {
            **(refund.provider_response or {}),
            "latest_status": status_data,
        }
        db.commit()
        return _refund_response(refund)

    if provider_status != "SUCCESS":
        return _mark_review(
            refund,
            db,
            status_data,
            f"Unexpected Tidepool refund status: {provider_status}",
        )

    original_response, original_quote = _get_quote_details(refund)

    status_quote = status_data.get("quoteResponse") or {}
    status_quote_details = status_quote.get("quote") or {}
    status_request = status_quote.get("quoteRequest") or {}

    original_request = original_response.get("quoteRequest") or {}

    # Validate correlation ID against both original and status quotes.
    correlation_id = status_data.get("correlationId")

    if not correlation_id:
        return _mark_review(
            refund, db, status_data, "Missing Tidepool correlation ID."
        )

    if correlation_id != status_quote.get("correlationId"):
        return _mark_review(
            refund, db, status_data, "Tidepool status correlation ID mismatch."
        )

    if correlation_id != original_response.get("correlationId"):
        return _mark_review(
            refund, db, status_data, "Status does not match original refund quote."
        )

    # Validate the original quote signature.
    original_signature = (
        refund.quote_signature
        or original_quote.get("signature")
    )

    if not original_signature:
        return _mark_review(
            refund, db, status_data, "Original refund quote signature is missing."
        )

    if status_quote.get("signature") != original_signature:
        return _mark_review(
            refund, db, status_data, "Tidepool refund quote signature mismatch."
        )

    if status_quote_details.get("depositAddress") != refund.deposit_address:
        return _mark_review(
            refund, db, status_data, "Refund deposit address mismatch."
        )

    # Validate destination asset and recipient.
    if status_request.get("destinationAsset") != refund.destination_asset:
        return _mark_review(
            refund, db, status_data, "Refund destination asset mismatch."
        )

    if status_request.get("recipient") != refund.destination_address:
        return _mark_review(
            refund, db, status_data, "Refund recipient mismatch."
        )

    if original_request.get("destinationAsset") != status_request.get("destinationAsset"):
        return _mark_review(
            refund, db, status_data, "Refund destination asset changed."
        )

    if original_request.get("recipient") != status_request.get("recipient"):
        return _mark_review(
            refund, db, status_data, "Refund recipient changed."
        )

    if status_request.get("amount") != original_request.get("amount"):
        return _mark_review(
            refund, db, status_data, "Refund requested amount changed."
        )

    if status_quote_details.get("amountOut") != original_quote.get("amountOut"):
        return _mark_review(
            refund, db, status_data, "Refund quoted output amount mismatch."
        )

    # Retrieve actual destination token precision from Tidepool.
    try:
        token = await get_usdc_token(
            refund.destination_network,
            refund.destination_asset,
        )
        destination_decimals = int(token["decimals"])
    except (ValueError, KeyError, TypeError) as exc:
        return _mark_review(
            refund,
            db,
            status_data,
            f"Could not verify destination token metadata: {exc}",
        )

    swap_details = status_data.get("swapDetails") or {}
    received_units = swap_details.get("amountOut")

    if received_units is None:
        return _mark_review(
            refund, db, status_data, "Missing actual refund output amount."
        )

    quoted_units = original_quote.get("amountOut")

    if quoted_units is None or str(received_units) != str(quoted_units):
        return _mark_review(
            refund,
            db,
            status_data,
            "Actual refund amount does not match exact-output quote.",
        )

    # Independently ensure the quote represents the amount stored in our DB.
    expected_units = amount_to_units(
        Decimal(str(refund.expected_amount)),
        destination_decimals,
    )

    if str(received_units) != expected_units:
        return _mark_review(
            refund,
            db,
            status_data,
            "Tidepool output does not match the stored expected amount.",
        )

    destination_transactions = (
        swap_details.get("destinationChainTxHashes") or []
    )

    if not destination_transactions:
        return _mark_review(
            refund,
            db,
            status_data,
            "Successful refund has no destination transaction hash.",
        )

    primary_transaction = next(
        (
            tx for tx in destination_transactions
            if isinstance(tx, dict)
            and isinstance(tx.get("hash"), str)
            and tx["hash"].strip()
        ),
        None,
    )

    if primary_transaction is None:
        return _mark_review(
            refund,
            db,
            status_data,
            "Missing destination payout transaction.",
        )

    if not isinstance(primary_transaction, dict):
        return _mark_review(
            refund, db, status_data, "Invalid destination transaction entry."
        )

    tx_hash = primary_transaction.get("hash")

    if not isinstance(tx_hash, str) or not tx_hash.strip():
        return _mark_review(
            refund, db, status_data, "Missing destination transaction hash."
        )

    existing_transaction = (
        db.query(RefundTransaction)
        .filter(RefundTransaction.tx_hash == tx_hash)
        .first()
    )

    if existing_transaction:
        if existing_transaction.refund_id != refund.id:
            return _mark_review(
                refund,
                db,
                status_data,
                "Destination transaction belongs to another refund.",
            )
    else:
        db.add(
            RefundTransaction(
                id=uuid4(),
                refund_id=refund.id,
                chain=refund.destination_network.upper(),
                tx_hash=tx_hash,
                transaction_type="CROSS_CHAIN_SETTLEMENT",
                asset=refund.destination_asset,
                amount=Decimal(str(refund.expected_amount)),
                explorer_url=primary_transaction.get("explorerUrl"),
            )
        )

    refund.received_amount = (
        Decimal(str(received_units))
        / (Decimal(10) ** destination_decimals)
    )

    refund.status = "SUCCESS"
    refund.completed_at = datetime.now(timezone.utc)

    refund.provider_response = {
        **(refund.provider_response or {}),
        "latest_status": status_data,
        "reconciliation_status": "SUCCESS",
        "destination_transaction_hash": tx_hash,
    }

    db.commit()

    return {
        **_refund_response(refund),
        "transaction_hash": tx_hash,
        "message": "Cross-chain refund successfully reconciled.",
    }
