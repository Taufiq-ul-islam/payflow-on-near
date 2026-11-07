import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.integrations.near_relayer import near_relayer, NearRelayerError

router = APIRouter(prefix="/relayer", tags=["NEAR Relayer"])


class SignedDelegateActionRequest(BaseModel):
    delegate_action: dict
    signature: str = Field(min_length=1)


def verify_internal_key(provided_key: str | None):
    expected = settings.internal_api_key

    if not expected:
        raise HTTPException(
            503, "Internal relayer authentication is not configured",
        )

    if not provided_key or not secrets.compare_digest(provided_key, expected):
        raise HTTPException(401, "Invalid internal API key")


def validate_delegate_action(delegate_action: dict):
    admin_id = settings.payflow_contract_admin_id

    if not admin_id:
        raise HTTPException(
            503, "PAYFLOW_CONTRACT_ADMIN_ID is not configured",
        )

    if delegate_action.get("sender_id") != admin_id:
        raise HTTPException(
            403, "Only the configured PayFlow admin can submit this action",
        )

    if delegate_action.get("receiver_id") != (
        settings.payflow_contract_id
    ):
        raise HTTPException(
            403, "Delegate action receiver is not the PayFlow contract",
        )

    actions = delegate_action.get("actions", [])

    if len(actions) != 1:
        raise HTTPException(
            400, "Exactly one delegated action is allowed",
        )

    action = actions[0]

    function_call = (
        action.get("FunctionCall")
        or action.get("function_call")
    )

    if not function_call:
        raise HTTPException(
            400, "Only function-call actions are accepted",
        )

    if function_call.get("method_name") != "record_settlement":
        raise HTTPException(
            403, "This contract method is not allowlisted",
        )

    if str(function_call.get("deposit", "0")) != "0":
        raise HTTPException(
            400, "Attached deposit is not allowed",
        )

    try:
        gas = int(function_call.get("gas", "0"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid gas value")

    if gas <= 0 or gas > settings.relayer_max_gas:
        raise HTTPException(
            400, "Gas exceeds the configured relayer limit",
        )


@router.post("/submit")
async def submit_delegate_action(
    data: SignedDelegateActionRequest,
    internal_api_key: str | None = Header(
        default=None,
        alias="X-Internal-API-Key",
    ),
):
    verify_internal_key(internal_api_key)
    validate_delegate_action(data.delegate_action)

    try:
        result = await near_relayer.submit_signed_delegate_action(
            delegate_action=data.delegate_action,
            signature=data.signature,
        )

        return {
            "submitted": True,
            "relayer_response": result,
        }

    except NearRelayerError as exc:
        raise HTTPException(502, str(exc))