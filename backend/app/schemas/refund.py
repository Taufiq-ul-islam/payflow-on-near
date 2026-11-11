from decimal import Decimal

from pydantic import BaseModel, Field


class RefundQuoteRequest(BaseModel):
    destination_network: str = Field(min_length=1, max_length=100)
    destination_asset: str = Field(min_length=1, max_length=255)
    destination_address: str = Field(min_length=1, max_length=255)
    requested_amount: Decimal = Field(gt=0)


class RefundResponse(BaseModel):
    refund_id: str
    payment_attempt_id: str
    status: str
    destination_network: str
    destination_asset: str
    destination_address: str
    requested_amount: str
    source_amount: str
    expected_amount: str
    fee_details: dict | None = None

class RefundDepositSubmitRequest(BaseModel):
    tx_hash: str = Field(min_length=1, max_length=255)
    near_sender_account: str = Field(min_length=2, max_length=128)