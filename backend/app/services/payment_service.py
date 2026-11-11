from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import settings
from app.integrations.near_intents import near_intents


def convert_usdc_to_units(amount: Decimal) -> str:
    amount = Decimal(str(amount))

    if amount <= 0:
        raise ValueError("Invoice amount must be positive")

    scale = Decimal(10) ** settings.usdc_decimals
    units = amount * scale

    if units != units.to_integral_value():
        raise ValueError(
            f"Invoice supports at most {settings.usdc_decimals} "
            "decimal places"
        )

    return str(int(units))


def build_quote_payload(
    invoice,
    source_asset: str,
    refund_address: str,
    dry: bool,
):
    if invoice.status != "PENDING":
        raise ValueError("Invoice is not payable")

    if invoice.due_date:
        due_date = invoice.due_date

        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)

        if due_date < datetime.now(timezone.utc):
            raise ValueError("Invoice has expired")

    if not settings.usdc_asset_id:
        raise ValueError("USDC asset ID is not configured")

    if not invoice.freelancer_id:
        raise ValueError("Freelancer NEAR account is missing")

    if not source_asset:
        raise ValueError("Source asset is required")

    if not refund_address:
        raise ValueError("Refund address is required")

    return {
        "dry": dry,
        "depositMode": "SIMPLE",
        "swapType": "EXACT_OUTPUT",
        "slippageTolerance": 100,

        "originAsset": source_asset,
        "destinationAsset": settings.usdc_asset_id,

        "amount": convert_usdc_to_units(invoice.total),

        "depositType": "ORIGIN_CHAIN",

        "refundTo": refund_address,
        "refundType": "ORIGIN_CHAIN",

        "recipient": invoice.freelancer_id,
        "recipientType": "DESTINATION_CHAIN",

        "deadline": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
    }


async def create_payment_quote(
    invoice,
    source_asset: str,
    refund_address: str,
    dry: bool = True,
):
    payload = build_quote_payload(
        invoice=invoice,
        source_asset=source_asset,
        refund_address=refund_address,
        dry=dry,
    )

    return await near_intents.get_quote(payload)