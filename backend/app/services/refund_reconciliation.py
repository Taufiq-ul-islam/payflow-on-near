from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.near_intents import near_intents
from app.models.refund import Refund, RefundTransaction
from app.services.refund_service import (
    verify_refund_transfer,
    get_usdc_token,
    amount_to_units,
)
from app.integrations.quote_signature import verify_quote_signature


PENDING_PROVIDER_STATUSES = {
    "PENDING_DEPOSIT",
    "KNOWN_DEPOSIT_TX",
    # "INCOMPLETE_DEPOSIT",
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
    quote = response.get("quote", {})

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


def _verify_refund_quote(refund, response):
    if not isinstance(response, dict):
        return None, None, "Quote response is invalid."

    quote = response.get("quote")
    quote_request = response.get("quoteRequest")

    if not isinstance(quote, dict) or not isinstance(quote_request, dict):
        return None, None, "Quote or quote request is missing."

    signature = response.get("signature")

    if not signature:
        return None, None, "Quote signature is missing."

    if not verify_quote_signature(
        quote_request,
        quote,
        response.get("timestamp"),
        signature,
    ):
        return None, None, "Quote signature verification failed."

    if signature != refund.quote_signature:
        return None, None, "Quote signature does not match the stored refund."

    correlation_id = response.get("correlationId")

    if (
        not correlation_id
        or correlation_id != refund.provider_correlation_id
    ):
        return None, None, "Quote correlation ID mismatch."

    expected_fields = {
        "originAsset": refund.source_asset,
        "destinationAsset": refund.destination_asset,
        "amount": amount_to_units(
            Decimal(str(refund.source_amount)),
            settings.usdc_decimals,
        ),
        "refundTo": None,
        "recipient": refund.destination_address,
        "swapType": "EXACT_INPUT",
        "depositMode": "SIMPLE",
        "depositType": "ORIGIN_CHAIN",
        "refundType": "ORIGIN_CHAIN",
        "recipientType": "DESTINATION_CHAIN",
    }

    # The refund recipient on the origin chain is the freelancer.
    # The stored signed request is also checked against the original quote
    # when reconciling the provider status below.
    original_response = refund.quote_response or {}
    original_request = original_response.get("quoteRequest") or {}

    expected_fields["refundTo"] = original_request.get("refundTo")

    for field, expected in expected_fields.items():
        if not expected or quote_request.get(field) != expected:
            return None, None, f"Quote {field} does not match the refund."

    if quote.get("depositAddress") != refund.deposit_address:
        return None, None, "Quote deposit address mismatch."

    if quote.get("depositMemo") != refund.deposit_memo:
        return None, None, "Quote deposit memo mismatch."

    if not quote.get("amountIn") or not quote.get("amountOut"):
        return None, None, "Quote is missing input or output amount."

    if str(quote["amountIn"]) != expected_fields["amount"]:
        return None, None, "Quote input amount mismatch."

    return quote, quote_request, None


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

    if refund.status not in {"PENDING", "PROCESSING"}:
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
        raise ValueError(
            "Verified refund amount does not match expected amount."
        )

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

    explorer_base = (
        "https://nearblocks.io"
        if settings.near_network == "mainnet"
        else "https://testnet.nearblocks.io"
    )

    transaction.explorer_url = (
        f"{explorer_base}/txns/{transaction.tx_hash}"
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

    if refund.status not in {"PENDING", "PROCESSING"}:
        raise ValueError(
            f"Cannot reconcile refund in status {refund.status}."
        )

    if not refund.deposit_address:
        raise ValueError("Refund has no 1Click deposit address.")

    original_response, original_quote = _get_quote_details(refund)

    # Verify the original stored quote first.
    original_quote_details, original_request, original_error = (
        _verify_refund_quote(refund, original_response)
    )

    if original_error:
        return _mark_review(
            refund,
            db,
            None,
            f"Original refund quote: {original_error}",
        )

    status_data = await near_intents.get_status(
        deposit_address=refund.deposit_address,
        deposit_memo=refund.deposit_memo,
    )

    if not isinstance(status_data, dict):
        raise ValueError("1Click returned an invalid refund status response.")

    provider_status = status_data.get("status")

    if not provider_status:
        raise ValueError("1Click returned no refund execution status.")

    status_quote = status_data.get("quoteResponse")

    # Verify the signed quote returned with the status response.
    status_quote_details, status_request, status_error = (
        _verify_refund_quote(refund, status_quote)
    )

    if status_error:
        return _mark_review(
            refund,
            db,
            status_data,
            f"Status quote: {status_error}",
        )

    # The status response must refer to the same provider execution.
    if status_data.get("correlationId") != refund.provider_correlation_id:
        return _mark_review(
            refund,
            db,
            status_data,
            "Status correlation ID does not match the original refund.",
        )

    if (
        status_quote.get("correlationId")
        != original_response.get("correlationId")
    ):
        return _mark_review(
            refund,
            db,
            status_data,
            "Status quote does not match the original refund quote.",
        )

    # Ensure the signed request has not changed between quote and status.
    for field, expected in original_request.items():
        if status_request.get(field) != expected:
            return _mark_review(
                refund,
                db,
                status_data,
                f"Status quote request changed field: {field}.",
            )

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
    
    if provider_status == "INCOMPLETE_DEPOSIT":
        return _mark_review(
            refund,
            db,
            status_data,
            (
                "1Click reported an incomplete source deposit. "
                "The refund to the original payer has not been confirmed. "
                "Verify the source funds before taking further action."
            ),
        )

    if provider_status == "REFUNDED":
        return _mark_review(
            refund,
            db,
            status_data,
            (
                "1Click refunded the source USDC to the freelancer. "
                "The refund to the original payer did not complete. "
                "Verify the returned funds before attempting another refund."
            ),
        )

    if provider_status != "SUCCESS":
        return _mark_review(
            refund,
            db,
            status_data,
            f"Unexpected 1Click refund status: {provider_status}",
        )

    # Verify the quoted output against the selected destination token.
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

    swap_details = status_data.get("swapDetails")

    if not isinstance(swap_details, dict):
        return _mark_review(
            refund,
            db,
            status_data,
            "Invalid or missing swap details in the 1Click status response.",
        )

    received_units = swap_details.get("amountOut")

    if received_units is None:
        return _mark_review(
            refund,
            db,
            status_data,
            "Missing actual refund output amount.",
        )

    quoted_units = original_quote.get("amountOut")

    if (
        quoted_units is None
        or str(received_units) != str(quoted_units)
        or str(status_quote_details.get("amountOut")) != str(quoted_units)
    ):
        return _mark_review(
            refund,
            db,
            status_data,
            "Actual refund amount does not match the signed quote.",
        )

    expected_units = amount_to_units(
        Decimal(str(refund.expected_amount)),
        destination_decimals,
    )

    if str(received_units) != expected_units:
        return _mark_review(
            refund,
            db,
            status_data,
            "Refund output does not match the stored expected amount.",
        )

    destination_transactions = swap_details.get("destinationChainTxHashes")

    if not isinstance(destination_transactions, list):
        return _mark_review(
            refund,
            db,
            status_data,
            "Invalid destination transaction list.",
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
            "Successful refund has no destination transaction hash.",
        )

    tx_hash = primary_transaction["hash"].strip()

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
