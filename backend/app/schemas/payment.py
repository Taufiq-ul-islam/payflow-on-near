from pydantic import BaseModel, Field

class DepositSubmitRequest(BaseModel):
    tx_hash: str = Field(min_length=1, max_length=255)
    near_sender_account: str | None = Field(default=None, max_length=128)


class PaymentAttemptResponse(BaseModel):
    payment_attempt_id: str
    status: str
    deposit_address: str
    deposit_memo: str | None = None
    expected_amount: str
    destination_asset: str