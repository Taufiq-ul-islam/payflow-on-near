from pydantic import BaseModel, Field

class DepositSubmitRequest(BaseModel):
    tx_hash: str = Field(min_length=1, max_length=255)
    near_sender_account: str | None = Field(default=None, max_length=128)
    payer_address: str | None = Field(default=None, max_length=255)
    payer_network: str | None = Field(default=None, max_length=50)
    payer_asset: str | None = Field(default=None, max_length=255)
    payer_asset_decimals: int | None = Field(default=None, ge=0, le=24)


class PaymentAttemptResponse(BaseModel):
    payment_attempt_id: str
    status: str
    deposit_address: str
    deposit_memo: str | None = None
    expected_amount: str
    destination_asset: str