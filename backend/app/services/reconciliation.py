import asyncio
import base64
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.near_intents import near_intents
from app.integrations.near_relayer import near_relayer, NearRelayerError
from app.integrations.quote_signature import verify_quote_signature
from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt, Transaction


FINAL_STATUSES = {
    "SUCCESS",
    "REFUNDED",
    "FAILED",
    "DUPLICATE_SETTLEMENT",
    "SETTLEMENT_REVIEW",
}

ACTIVE_PROVIDER_STATUSES = {
    "PENDING_DEPOSIT",
    "KNOWN_DEPOSIT_TX",
    "INCOMPLETE_DEPOSIT",
    "PROCESSING",
}

ALLOWED_PROVIDER_STATUSES = ACTIVE_PROVIDER_STATUSES | {
    "SUCCESS",
    "REFUNDED",
    "FAILED",
}


class NearRPCError(Exception):
    pass


@asynccontextmanager
async def _relayer_advisory_lock(db: Session):
    """
    Acquire a PostgreSQL session-level advisory lock for the
    configured function-call public key.

    A dedicated connection keeps the lock alive across commits
    performed by the reconciliation session.
    """

    public_key = settings.payflow_admin_function_call_public_key

    if not public_key:
        raise NearRelayerError(
            "Function-call public key is not configured"
        )

    lock_id = int.from_bytes(
        hashlib.sha256(
            public_key.encode("utf-8")
        ).digest()[:8],
        byteorder="big",
        signed=True,
    )

    connection = db.get_bind().connect()
    acquired = False

    try:
        # Wait up to 60 seconds for another worker.
        for _ in range(600):
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": lock_id},
                ).scalar()
            )
            connection.commit()

            if acquired:
                break

            await asyncio.sleep(0.1)

        if not acquired:
            raise NearRelayerError(
                "Timed out waiting for the NEAR relayer signing lock"
            )

        yield

    finally:
        if acquired:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
                connection.commit()
            except Exception:
                connection.invalidate()

        connection.close()


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

    if invoice.paid_payment_attempt_id == attempt.id:
        attempt.status = "SUCCESS"
        return "SUCCESS"

    if invoice.status == "PAID":
        attempt.status = "DUPLICATE_SETTLEMENT"
        return "DUPLICATE_SETTLEMENT"

    attempt.status = "SETTLEMENT_REVIEW"
    return "SETTLEMENT_REVIEW"


def _verify_stored_received_amount(
    attempt: PaymentAttempt,
) -> bool:
    """
    Confirm the stored received amount matches the exact-output
    amount expected by the original quote.
    """

    if attempt.received_amount is None:
        return False

    return (
        str(attempt.received_amount)
        == str(attempt.expected_amount)
    )


def _recover_received_amount(
    attempt: PaymentAttempt,
) -> bool:
    """
    Recover the received amount from the saved provider response
    when an earlier reconciliation stored SUCCESS without it.
    """

    provider_response = attempt.provider_response or {}
    swap_details = provider_response.get("swapDetails") or {}
    recovered_amount = swap_details.get("amountOut")

    if recovered_amount is None:
        return False

    if str(recovered_amount) != str(attempt.expected_amount):
        raise ValueError(
            "Stored settlement amount does not match expected amount"
        )

    attempt.received_amount = str(recovered_amount)
    return True


async def record_onchain_settlement(
    db: Session,
    invoice: Invoice,
    attempt: PaymentAttempt,
) -> dict:
    """
    Serialize settlement signing and submission across backend workers.

    The attempt and invoice are refreshed after acquiring the lock
    because another worker may have completed the operation while
    this worker was waiting.
    """

    async with _relayer_advisory_lock(db):
        db.refresh(attempt)
        db.refresh(invoice)

        return await _record_onchain_settlement_locked(
            db,
            invoice,
            attempt,
        )


async def _record_onchain_settlement_locked(
    db: Session,
    invoice: Invoice,
    attempt: PaymentAttempt,
) -> dict:
    """
    Record an already-verified payment in the PayFlow NEAR contract.

    The contract is checked before submission. An uncertain relayer
    submission is never blindly submitted a second time.

    This function must only be called while holding the advisory lock.
    """

    if attempt.status != "SUCCESS":
        return {
            "status": "SKIPPED",
            "reason": "Payment is not canonical SUCCESS",
        }

    if not _verify_stored_received_amount(attempt):
        recording = {
            "status": "FAILED",
            "error": "Verified received amount is missing or incorrect",
        }

        provider_response = dict(attempt.provider_response or {})
        provider_response["_payflow_contract"] = recording
        attempt.provider_response = provider_response
        db.commit()

        return recording

    provider_response = dict(attempt.provider_response or {})
    previous = dict(
        provider_response.get("_payflow_contract") or {}
    )
    previous_status = previous.get("status")

    expected = {
        "invoice_id": str(invoice.id),
        "freelancer": str(invoice.freelancer_id),
        "amount": str(attempt.received_amount),
        "token": str(settings.usdc_asset_id),
        "settlement_reference": str(attempt.id),
    }

    payload = {
        "jsonrpc": "2.0",
        "id": "payflow-settlement-check",
        "method": "query",
        "params": {
            "request_type": "call_function",
            "finality": "final",
            "account_id": settings.payflow_contract_id,
            "method_name": "get_settlement",
            "args_base64": base64.b64encode(
                json.dumps(
                    {"invoice_id": str(invoice.id)}
                ).encode("utf-8")
            ).decode("ascii"),
        },
    }

    # Always inspect the contract before considering submission.
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                settings.near_rpc_url,
                json=payload,
            )
            response.raise_for_status()
            rpc_data = response.json()

        if not isinstance(rpc_data, dict):
            raise NearRPCError("Invalid NEAR RPC response")

        if rpc_data.get("error"):
            raise NearRPCError(
                json.dumps(rpc_data["error"])
            )

        raw_result = (
            (rpc_data.get("result") or {}).get("result")
        )

        if not isinstance(raw_result, list):
            raise NearRPCError(
                "NEAR RPC returned no contract view result"
            )

        try:
            onchain_settlement = json.loads(
                bytes(raw_result).decode("utf-8")
            )
        except (ValueError, TypeError) as exc:
            raise NearRPCError(
                "Could not decode contract settlement result"
            ) from exc

        if (
            onchain_settlement is not None
            and not isinstance(onchain_settlement, dict)
        ):
            raise NearRPCError(
                "Contract returned an invalid settlement record"
            )

    except (httpx.HTTPError, ValueError, NearRPCError) as exc:
        recording = {
            "status": "PENDING_CONFIRMATION",
            "settlement_reference": str(attempt.id),
            "error": f"Could not check contract state: {exc}",
        }

        provider_response["_payflow_contract"] = recording
        attempt.provider_response = provider_response
        db.commit()

        return recording

    # A record already exists: it must match this exact payment.
    if onchain_settlement is not None:
        matches = all(
            str(onchain_settlement.get(key)) == value
            for key, value in expected.items()
        )

        if matches:
            recording = {
                "status": "CONFIRMED",
                "settlement_reference": str(attempt.id),
                "onchain_settlement": onchain_settlement,
            }
        else:
            recording = {
                "status": "CONFLICT",
                "settlement_reference": str(attempt.id),
                "error": (
                    "A different settlement is already recorded "
                    "for this invoice"
                ),
                "onchain_settlement": onchain_settlement,
            }

        provider_response["_payflow_contract"] = recording
        attempt.provider_response = provider_response
        db.commit()

        return recording

    # An earlier submission may have reached the relayer.
    # Do not automatically submit again while its outcome is uncertain.
    if previous_status in {
        "SUBMITTING",
        "SUBMITTED",
        "PENDING_CONFIRMATION",
    }:
        recording = {
            **previous,
            "status": "PENDING_CONFIRMATION",
            "message": (
                "No on-chain record is visible yet; "
                "not resubmitting automatically"
            ),
        }

        provider_response["_payflow_contract"] = recording
        attempt.provider_response = provider_response
        db.commit()

        return recording

    # Signing alone cannot submit a transaction.
    try:
        signed = await near_relayer.create_signed_settlement_action(
            invoice_id=expected["invoice_id"],
            freelancer=expected["freelancer"],
            amount=expected["amount"],
            token=expected["token"],
            settlement_reference=expected["settlement_reference"],
        )

        if (
            not isinstance(signed, dict)
            or not signed.get("delegate_action")
            or not signed.get("signature")
        ):
            raise NearRelayerError(
                "Relayer returned an invalid signed action"
            )

    except Exception as exc:
        recording = {
            "status": "FAILED",
            "settlement_reference": str(attempt.id),
            "error": f"Could not sign settlement action: {exc}",
        }

        provider_response["_payflow_contract"] = recording
        attempt.provider_response = provider_response
        db.commit()

        return recording

    # Persist before submitting. If submission becomes uncertain,
    # subsequent reconciliation checks the contract instead.
    recording = {
        "status": "SUBMITTING",
        "settlement_reference": str(attempt.id),
    }

    provider_response["_payflow_contract"] = recording
    attempt.provider_response = provider_response
    db.commit()

    try:
        result = await near_relayer.submit_signed_delegate_action(
            delegate_action=signed["delegate_action"],
            signature=signed["signature"],
        )

        recording = {
            "status": "SUBMITTED",
            "settlement_reference": str(attempt.id),
            "relayer_response": result,
        }

    except NearRelayerError as exc:
        recording = {
            "status": (
                "PENDING_CONFIRMATION"
                if exc.outcome_uncertain
                else "FAILED"
            ),
            "settlement_reference": str(attempt.id),
            "error": str(exc),
        }

    except Exception as exc:
        # Unknown exceptions are conservatively treated as uncertain.
        recording = {
            "status": "PENDING_CONFIRMATION",
            "settlement_reference": str(attempt.id),
            "error": str(exc),
        }

    provider_response = dict(attempt.provider_response or {})
    provider_response["_payflow_contract"] = recording
    attempt.provider_response = provider_response
    db.commit()

    return recording


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

    # Recover or repair already-final attempts.
    if attempt.status in FINAL_STATUSES:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == attempt.invoice_id)
            .with_for_update()
            .one()
        )

        status_data = attempt.provider_response or {}

        if attempt.status == "SUCCESS":
            if (
                not attempt.received_amount
                and not _recover_received_amount(attempt)
            ):
                attempt.status = "SETTLEMENT_REVIEW"
                db.commit()

            elif not _verify_stored_received_amount(attempt):
                raise ValueError(
                    "Stored received amount does not match expected amount"
                )

            else:
                mark_invoice_settled(db, invoice, attempt)
                db.commit()

        db.refresh(attempt)
        db.refresh(invoice)

        response = {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": (
                status_data.get("status") or attempt.status
            ),
            "invoice_status": invoice.status,
            "received_amount": attempt.received_amount,
            "swap_details": status_data.get("swapDetails"),
            "payment_attempt_status": attempt.status,
            "contract_recording": None,
        }

        if attempt.status == "SUCCESS":
            response["contract_recording"] = (
                await record_onchain_settlement(
                    db,
                    invoice,
                    attempt,
                )
            )

        return response

    if not attempt.deposit_address:
        raise ValueError("Payment attempt has no deposit address")

    status_data = await near_intents.get_status(
        deposit_address=attempt.deposit_address,
        deposit_memo=attempt.deposit_memo,
    )

    if not isinstance(status_data, dict):
        raise ValueError(
            "Invalid NEAR Intents status response"
        )

    status_quote = status_data.get("quoteResponse")

    if not isinstance(status_quote, dict):
        raise ValueError(
            "NEAR Intents status response is missing the original quote"
        )

    status_quote_request = status_quote.get("quoteRequest")
    status_quote_details = status_quote.get("quote")

    if not isinstance(status_quote_request, dict):
        raise ValueError(
            "Status quote is missing quoteRequest"
        )

    if not isinstance(status_quote_details, dict):
        raise ValueError(
            "Status quote is missing quote details"
        )

    # Verify the signature returned with the status response.
    if not verify_quote_signature(
        status_quote_request,
        status_quote_details,
        status_quote.get("timestamp"),
        status_quote.get("signature"),
    ):
        raise ValueError(
            "NEAR Intents original quote signature verification failed"
        )

    # Verify the quote persisted when the payment was committed.
    original_quote = attempt.quote_response or {}

    if not verify_quote_signature(
        original_quote.get("quoteRequest") or {},
        original_quote.get("quote") or {},
        original_quote.get("timestamp"),
        original_quote.get("signature"),
    ):
        raise ValueError(
            "Stored payment quote signature verification failed"
        )

    correlation_id = attempt.provider_correlation_id

    if not correlation_id:
        raise ValueError(
            "Payment attempt has no provider correlation ID"
        )

    if status_data.get("correlationId") != correlation_id:
        raise ValueError(
            "NEAR Intents status correlation ID mismatch"
        )

    if status_quote.get("correlationId") != correlation_id:
        raise ValueError(
            "NEAR Intents quote correlation ID mismatch"
        )

    if (
        status_quote.get("signature")
        != original_quote.get("signature")
    ):
        raise ValueError(
            "NEAR Intents quote signature does not match original quote"
        )

    provider_status = status_data.get("status")

    if provider_status not in ALLOWED_PROVIDER_STATUSES:
        raise ValueError(
            f"Unexpected NEAR Intents payment status: {provider_status}"
        )

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == attempt.invoice_id)
        .with_for_update()
        .one()
    )

    settlement_result = None

    if provider_status == "SUCCESS":
        original_request = original_quote.get("quoteRequest") or {}
        swap_details = status_data.get("swapDetails") or {}

        expected_quote_fields = {
            "originAsset": attempt.source_asset,
            "destinationAsset": settings.usdc_asset_id,
            "amount": str(attempt.expected_amount),
            "refundTo": attempt.refund_address,
            "recipient": invoice.freelancer_id,
            "swapType": "EXACT_OUTPUT",
            "depositMode": "SIMPLE",
            "depositType": "ORIGIN_CHAIN",
            "refundType": "ORIGIN_CHAIN",
            "recipientType": "DESTINATION_CHAIN",
        }

        # Validate the quote returned by the provider.
        for field, expected in expected_quote_fields.items():
            if str(status_quote_request.get(field)) != str(expected):
                raise ValueError(
                    f"NEAR Intents status quote has unexpected {field}"
                )

        # Validate the original quote saved at commit time.
        for field, expected in expected_quote_fields.items():
            if str(original_request.get(field)) != str(expected):
                raise ValueError(
                    f"Stored quote has unexpected {field}"
                )

        if (
            status_quote_details.get("depositAddress")
            != attempt.deposit_address
        ):
            raise ValueError(
                "Status response deposit address mismatch"
            )

        if (
            str(status_quote_details.get("amountOut"))
            != str(attempt.expected_amount)
        ):
            raise ValueError(
                "NEAR Intents quoted output amount mismatch"
            )

        if (
            str(status_quote_details.get("amountIn"))
            != str(attempt.expected_input_amount)
        ):
            raise ValueError(
                "NEAR Intents quoted input amount mismatch"
            )

        received_amount = swap_details.get("amountOut")

        if received_amount is None:
            raise ValueError(
                "Missing actual output amount"
            )

        if str(received_amount) != str(attempt.expected_amount):
            raise ValueError(
                "Received amount does not match the exact-output quote"
            )

        destination_transactions = (
            swap_details.get("destinationChainTxHashes") or []
        )

        if not isinstance(destination_transactions, list):
            raise ValueError(
                "Invalid destination transaction list"
            )

        if not destination_transactions:
            raise ValueError(
                "SUCCESS response has no destination transaction hash"
            )

        primary_transaction = destination_transactions[0]

        if not isinstance(primary_transaction, dict):
            raise ValueError(
                "Invalid destination transaction entry"
            )

        tx_hash = primary_transaction.get("hash")

        if not isinstance(tx_hash, str) or not tx_hash.strip():
            raise ValueError(
                "Missing destination transaction hash"
            )

        attempt.received_amount = str(received_amount)

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
                    amount=str(received_amount),
                    explorer_url=primary_transaction.get("explorerUrl"),
                )
            )

        # The provider payment is verified. Now atomically claim invoice.
        settlement_result = mark_invoice_settled(
            db,
            invoice,
            attempt,
        )

    elif provider_status == "REFUNDED":
        attempt.status = "REFUNDED"

        if invoice.status != "PAID":
            invoice.status = "PENDING"

    elif provider_status == "FAILED":
        attempt.status = "FAILED"

        if invoice.status != "PAID":
            invoice.status = "PENDING"

    else:
        attempt.status = provider_status

    # Save provider evidence and payment state together.
    attempt.provider_response = status_data

    db.commit()
    db.refresh(attempt)
    db.refresh(invoice)

    contract_recording = None

    if (
        provider_status == "SUCCESS"
        and settlement_result == "SUCCESS"
    ):
        contract_recording = await record_onchain_settlement(
            db,
            invoice,
            attempt,
        )

    return {
        "payment_attempt_id": str(attempt.id),
        "invoice_id": str(invoice.id),
        "provider_status": provider_status,
        "invoice_status": invoice.status,
        "received_amount": attempt.received_amount,
        "swap_details": status_data.get("swapDetails"),
        "payment_attempt_status": attempt.status,
        "contract_recording": contract_recording,
    }


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

    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == attempt.invoice_id)
        .with_for_update()
        .one()
    )

    # Direct payments need the same final-state recovery behavior
    # as cross-chain payments.
    if attempt.status in FINAL_STATUSES:
        contract_recording = None

        if attempt.status == "SUCCESS":
            if (
                not attempt.received_amount
                or str(attempt.received_amount)
                != str(attempt.expected_amount)
            ):
                attempt.status = "SETTLEMENT_REVIEW"
                db.commit()

            else:
                mark_invoice_settled(db, invoice, attempt)
                db.commit()

                if attempt.status == "SUCCESS":
                    contract_recording = await record_onchain_settlement(
                        db,
                        invoice,
                        attempt,
                    )

        db.refresh(attempt)
        db.refresh(invoice)

        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": attempt.status,
            "invoice_status": invoice.status,
            "received_amount": attempt.received_amount,
            "contract_recording": contract_recording,
        }

    transaction_record = (
        db.query(Transaction)
        .filter(
            Transaction.payment_attempt_id == attempt.id,
            Transaction.transaction_type == "DIRECT_PAYMENT",
        )
        .first()
    )

    if not transaction_record:
        raise ValueError(
            "Direct payment transaction has not been submitted"
        )

    sender_account = (
        (attempt.provider_response or {}).get(
            "direct_sender_account"
        )
    )

    if not sender_account:
        raise ValueError(
            "Payer NEAR account ID is missing"
        )

    prefix, separator, token_contract = (
        settings.usdc_asset_id.partition(":")
    )

    if prefix != "nep141" or not separator or not token_contract:
        raise ValueError(
            "Configured USDC asset is not a NEAR NEP-141 asset"
        )

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

    if not isinstance(rpc_data, dict):
        raise NearRPCError(
            "NEAR RPC returned an invalid response"
        )

    if rpc_data.get("error"):
        error_text = json.dumps(rpc_data["error"])

        if "UNKNOWN_TRANSACTION" in error_text:
            return {
                "payment_attempt_id": str(attempt.id),
                "invoice_id": str(invoice.id),
                "provider_status": "PROCESSING",
                "invoice_status": invoice.status,
                "message": (
                    "Transaction is not yet available on NEAR RPC"
                ),
            }

        raise NearRPCError(
            f"NEAR RPC error: {error_text}"
        )

    result = rpc_data.get("result")

    if not isinstance(result, dict):
        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": "PROCESSING",
            "invoice_status": invoice.status,
        }

    transaction = result.get("transaction") or {}

    if not isinstance(transaction, dict):
        raise NearRPCError(
            "NEAR RPC returned an invalid transaction"
        )

    # Verify the actual signer, receiver and transaction hash.
    if transaction.get("signer_id") != sender_account:
        raise ValueError(
            "Transaction signer does not match payer account"
        )

    if transaction.get("receiver_id") != token_contract:
        raise ValueError(
            "Transaction was not sent to the configured USDC contract"
        )

    if transaction.get("hash") != tx_hash:
        raise ValueError(
            "NEAR transaction hash mismatch"
        )

    # Require exactly one action and require that action to be ft_transfer.
    actions = transaction.get("actions")

    if not isinstance(actions, list) or len(actions) != 1:
        raise ValueError(
            "Direct payment must contain exactly one transfer action"
        )

    action = actions[0]

    if (
        not isinstance(action, dict)
        or set(action.keys()) != {"FunctionCall"}
    ):
        raise ValueError(
            "Direct payment contains an unexpected transaction action"
        )

    function_call = action["FunctionCall"]

    if not isinstance(function_call, dict):
        raise ValueError(
            "Invalid NEAR function-call action"
        )

    if function_call.get("method_name") != "ft_transfer":
        raise ValueError(
            "Expected a standard ft_transfer transaction"
        )

    args = function_call.get("args")

    if not isinstance(args, str):
        raise ValueError(
            "NEAR transfer arguments are missing"
        )

    try:
        action_args = json.loads(
            base64.b64decode(
                args,
                validate=True,
            ).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(
            "Could not decode NEAR transfer arguments"
        ) from exc

    if not isinstance(action_args, dict):
        raise ValueError(
            "Invalid NEAR transfer arguments"
        )

    if action_args.get("receiver_id") != invoice.freelancer_id:
        raise ValueError(
            "Transfer recipient does not match freelancer"
        )

    if str(action_args.get("amount")) != str(attempt.expected_amount):
        raise ValueError(
            "Transfer amount does not match invoice"
        )

    execution_status = result.get("status") or {}

    if not isinstance(execution_status, dict):
        raise NearRPCError(
            "NEAR RPC returned an invalid execution status"
        )

    if "Failure" in execution_status:
        attempt.status = "FAILED"

        if invoice.status != "PAID":
            invoice.status = "PENDING"

        db.commit()

        return {
            "payment_attempt_id": str(attempt.id),
            "invoice_id": str(invoice.id),
            "provider_status": "FAILED",
            "invoice_status": invoice.status,
        }

    if not (
        "SuccessValue" in execution_status
        or "SuccessReceiptId" in execution_status
    ):
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
        if not isinstance(item, dict):
            continue

        outcome = item.get("outcome") or {}

        if isinstance(outcome, dict):
            logs.extend(outcome.get("logs") or [])

    # Verify the actual NEP-141 transfer event.
    verified_transfer = False

    for log in logs:
        if not isinstance(log, str) or "EVENT_JSON:" not in log:
            continue

        raw_event = log.split("EVENT_JSON:", 1)[1]

        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict):
            continue

        if (
            event.get("standard") != "nep141"
            or event.get("event") != "ft_transfer"
        ):
            continue

        for transfer in event.get("data") or []:
            if not isinstance(transfer, dict):
                continue

            if (
                transfer.get("old_owner_id") == sender_account
                and transfer.get("new_owner_id") == invoice.freelancer_id
                and str(transfer.get("amount"))
                == str(attempt.expected_amount)
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
    attempt.received_amount = str(attempt.expected_amount)

    settlement_result = mark_invoice_settled(
        db,
        invoice,
        attempt,
    )

    attempt.provider_response = {
        **(attempt.provider_response or {}),
        "near_rpc_verified": True,
        "verified_transaction_hash": tx_hash,
    }

    transaction_record.amount = str(attempt.expected_amount)

    explorer_base = (
        "https://nearblocks.io"
        if settings.near_network == "mainnet"
        else "https://testnet.nearblocks.io"
    )

    transaction_record.explorer_url = (
        f"{explorer_base}/txns/{tx_hash}"
    )

    db.commit()
    db.refresh(attempt)
    db.refresh(invoice)

    contract_recording = None

    if settlement_result == "SUCCESS":
        contract_recording = await record_onchain_settlement(
            db,
            invoice,
            attempt,
        )

    return {
        "payment_attempt_id": str(attempt.id),
        "invoice_id": str(invoice.id),
        "provider_status": attempt.status,
        "invoice_status": invoice.status,
        "received_amount": attempt.received_amount,
        "verification": "NEAR_RPC_NEP141_EVENT",
        "contract_recording": contract_recording,
    }
