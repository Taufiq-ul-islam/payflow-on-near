import base64
import json

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import settings
from app.integrations.near_intents import near_intents
from app.integrations.near_rpc import near_rpc


SUPPORTED_NETWORKS = {
    "near",
    "base",
    "arb",
    "eth",
    "bsc",
    "sol",
    "stellar",
    "sui",
}


def amount_to_units(amount: Decimal, decimals: int) -> str:
    amount = Decimal(str(amount))

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Refund amount must be positive.")

    scale = Decimal(10) ** decimals
    units = amount * scale

    if units != units.to_integral_value():
        raise ValueError(
            f"Amount supports at most {decimals} decimal places."
        )

    return str(int(units))


def units_to_amount(units: str, decimals: int) -> Decimal:
    return Decimal(str(units)) / (Decimal(10) ** decimals)


async def get_usdc_token(
    destination_network: str,
    destination_asset: str,
):
    if destination_network not in SUPPORTED_NETWORKS:
        raise ValueError("Unsupported refund destination network.")

    response = await near_intents.get_tokens()

    if isinstance(response, list):
        tokens = response
    elif isinstance(response, dict):
        tokens = response.get("value", response.get("tokens", []))
    else:
        tokens = []

    for token in tokens:
        if (
            token.get("symbol") == "USDC"
            and token.get("blockchain") == destination_network
            and token.get("assetId") == destination_asset
        ):
            return token

    raise ValueError(
        "The selected USDC asset is not supported on this network."
    )


async def create_refund_quote(
    *,
    destination_network: str,
    destination_asset: str,
    destination_address: str,
    requested_amount: Decimal,
    freelancer_near_account: str,
):
    if not destination_address.strip():
        raise ValueError("Refund destination address is required.")

    if not freelancer_near_account:
        raise ValueError("Freelancer NEAR account is missing.")

    requested_amount = Decimal(str(requested_amount))

    if not requested_amount.is_finite() or requested_amount <= 0:
        raise ValueError("Refund amount must be positive.")

    token = await get_usdc_token(
        destination_network,
        destination_asset,
    )
    destination_decimals = int(token["decimals"])

    # Direct NEAR USDC refund: transfer the full amount.
    # Network gas is paid separately in NEAR.
    if destination_network == "near":
        if destination_asset != settings.usdc_asset_id:
            raise ValueError("Unsupported NEAR refund asset.")

        source_units = amount_to_units(
            requested_amount,
            settings.usdc_decimals,
        )
        destination_units = amount_to_units(
            requested_amount,
            destination_decimals,
        )

        return {
            "payment_mode": "DIRECT_NEAR_USDC",
            "token": token,
            "quote_response": None,
            "source_amount": units_to_amount(
                source_units,
                settings.usdc_decimals,
            ),
            "expected_amount": units_to_amount(
                destination_units,
                destination_decimals,
            ),
            "fee_details": {
                "type": "direct_transfer",
                "note": "NEAR network gas is paid separately in NEAR.",
            },
        }

    # Cross-chain refund: EXACT_INPUT spends the entire refundable
    # NEAR USDC amount. The destination receives the net quoted amount.
    source_units = amount_to_units(
        requested_amount,
        settings.usdc_decimals,
    )

    payload = {
        "dry": False,
        "depositMode": "SIMPLE",
        "swapType": "EXACT_INPUT",
        "slippageTolerance": 100,
        "originAsset": settings.usdc_asset_id,
        "destinationAsset": destination_asset,
        "amount": source_units,
        "depositType": "ORIGIN_CHAIN",
        "refundTo": freelancer_near_account,
        "refundType": "ORIGIN_CHAIN",
        "recipient": destination_address,
        "recipientType": "DESTINATION_CHAIN",
        "deadline": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
    }

    response = await near_intents.get_quote(payload)

    if not isinstance(response, dict):
        raise ValueError("Tidepool returned an invalid refund quote.")

    quote = response.get("quote") or {}
    quote_request = response.get("quoteRequest") or {}

    if not quote.get("depositAddress"):
        raise ValueError(
            "Tidepool did not return a refund deposit address."
        )

    if quote_request.get("destinationAsset") != destination_asset:
        raise ValueError(
            "Tidepool returned an unexpected destination asset."
        )

    if quote_request.get("recipient") != destination_address:
        raise ValueError(
            "Tidepool returned an unexpected recipient."
        )

    if quote_request.get("originAsset") != settings.usdc_asset_id:
        raise ValueError(
            "Tidepool returned an unexpected source asset."
        )

    amount_in = quote.get("amountIn")
    amount_out = quote.get("amountOut")

    if amount_in is None or amount_out is None:
        raise ValueError(
            "Tidepool quote is missing its input or output amount."
        )

    # Reject a quote that does not spend the entire refundable balance.
    if str(amount_in) != source_units:
        raise ValueError(
            "Tidepool did not quote the entire refundable source amount."
        )

    return {
        "payment_mode": "CROSS_CHAIN",
        "token": token,
        "quote_response": response,
        "source_amount": units_to_amount(
            amount_in,
            settings.usdc_decimals,
        ),
        "expected_amount": units_to_amount(
            amount_out,
            destination_decimals,
        ),
        "fee_details": {
            "withdrawFee": quote.get("withdrawFee"),
            "refundFee": quote.get("refundFee"),
        },
    }


async def verify_refund_transfer(
    refund,
    tx_hash: str,
    sender_account: str,
):
    result = await near_rpc.get_transaction(
        tx_hash,
        sender_account,
    )

    if not result:
        raise ValueError("NEAR transaction was not found.")

    transaction = result.get("transaction", {})

    # Verify transaction identity and execution.
    if transaction.get("hash") != tx_hash:
        raise ValueError("Transaction hash mismatch.")

    if transaction.get("signer_id") != sender_account:
        raise ValueError("Transaction signer mismatch.")

    if result.get("final_execution_status") != "FINAL":
        raise ValueError("Transaction is not finalized.")

    if "Failure" in result.get("status", {}):
        raise ValueError("NEAR transaction failed.")

    # Derive the NEAR USDC contract from the configured asset ID.
    asset_parts = settings.usdc_asset_id.split(":", 1)

    if len(asset_parts) != 2 or asset_parts[0] != "nep141":
        raise ValueError("Invalid configured NEAR USDC asset ID.")

    token_contract = asset_parts[1]

    if transaction.get("receiver_id") != token_contract:
        raise ValueError(
            "Transaction did not call the NEAR USDC contract."
        )

    actions = transaction.get("actions", [])

    if len(actions) != 1 or "FunctionCall" not in actions[0]:
        raise ValueError(
            "Expected exactly one NEP-141 function call."
        )

    function_call = actions[0]["FunctionCall"]

    if function_call.get("method_name") != "ft_transfer":
        raise ValueError("Transaction is not an ft_transfer.")

    try:
        args = json.loads(
            base64.b64decode(
                function_call["args"]
            ).decode("utf-8")
        )
    except Exception as exc:
        raise ValueError(
            "Could not decode NEP-141 transfer arguments."
        ) from exc

    expected_recipient = (
        refund.deposit_address
        if refund.destination_network != "near"
        else refund.destination_address
    )

    expected_amount = amount_to_units(
        Decimal(str(refund.source_amount)),
        settings.usdc_decimals,
    )

    if args.get("receiver_id") != expected_recipient:
        raise ValueError("NEP-141 transfer recipient mismatch.")

    if str(args.get("amount")) != expected_amount:
        raise ValueError("NEP-141 transfer amount mismatch.")

    # Confirm the actual NEP-141 transfer event.
    matching_events = []

    for receipt in result.get("receipts_outcome", []):
        outcome = receipt.get("outcome", {})

        if outcome.get("executor_id") != token_contract:
            continue

        if "Failure" in outcome.get("status", {}):
            raise ValueError("NEAR transfer receipt failed.")

        for log in outcome.get("logs", []):
            if not log.startswith("EVENT_JSON:"):
                continue

            try:
                event = json.loads(
                    log[len("EVENT_JSON:"):]
                )
            except json.JSONDecodeError:
                continue

            if (
                event.get("standard") != "nep141"
                or event.get("event") != "ft_transfer"
            ):
                continue

            for item in event.get("data", []):
                if (
                    item.get("old_owner_id") == sender_account
                    and item.get("new_owner_id") == expected_recipient
                    and str(item.get("amount")) == expected_amount
                ):
                    matching_events.append(item)

    if not matching_events:
        raise ValueError(
            "Matching NEP-141 transfer event was not found."
        )

    return {
        "verified": True,
        "tx_hash": tx_hash,
        "sender": sender_account,
        "recipient": expected_recipient,
        "amount": expected_amount,
        "token_contract": token_contract,
    }
