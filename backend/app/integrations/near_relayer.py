import base64
import json

import httpx
from py_near.account import Account
from py_near_primitives import FunctionCallAction

from app.core.config import settings


class NearRelayerError(Exception):
    pass


class NearRelayer:
    def __init__(self):
        self.base_url = settings.relayer_url.rstrip("/")
        self.timeout = httpx.Timeout(60.0)

    async def create_signed_settlement_action(
        self,
        invoice_id: str,
        freelancer: str,
        amount: str,
        token: str,
        settlement_reference: str,
    ) -> dict:
        """
        Build and sign a NEP-366 DelegateAction for record_settlement.

        This method only creates the signed payload.
        It does NOT submit a transaction.
        """

        admin_id = settings.payflow_contract_admin_id
        contract_id = settings.payflow_contract_id

        public_key = settings.payflow_admin_function_call_public_key
        private_key = settings.payflow_admin_function_call_private_key

        if not admin_id or not contract_id:
            raise NearRelayerError(
                "PayFlow contract/admin configuration is missing"
            )

        if not public_key or not private_key:
            raise NearRelayerError(
                "Function-call signing key is not configured"
            )

        if not all([
            invoice_id,
            freelancer,
            amount,
            token,
            settlement_reference,
        ]):
            raise NearRelayerError(
                "Settlement arguments must not be empty"
            )

        if not public_key.startswith("ed25519:"):
            raise NearRelayerError(
                "Expected an ed25519 function-call public key"
            )

        if not private_key.startswith("ed25519:"):
            raise NearRelayerError(
                "Expected an ed25519 function-call private key"
            )

        try:
            public_key_b58 = public_key.split(":", 1)[1]

            account = Account(
                account_id=admin_id,
                private_key=private_key,
                rpc_addr=settings.near_rpc_url,
            )

            # The account fetches the nonce for this exact signing key
            # and obtains the current block height.
            function_call = FunctionCallAction(
                method_name="record_settlement",
                args=json.dumps(
                    {
                        "invoice_id": invoice_id,
                        "freelancer": freelancer,
                        "amount": amount,
                        "token": token,
                        "settlement_reference": settlement_reference,
                    },
                    separators=(",", ":"),
                ).encode("utf-8"),
                gas=settings.relayer_max_gas,
                deposit=0,
            )

            delegate = await account.create_delegate_action(
                actions=[function_call],
                receiver_id=contract_id,
                public_key=public_key_b58,
            )

            signature = account.sign_delegate_transaction(delegate)

            # Convert the py-near model into NEAR RPC-compatible JSON.
            serialized_actions = []

            for action in delegate.actions:
                if not isinstance(action, FunctionCallAction):
                    raise NearRelayerError(
                        "Unexpected action type in DelegateAction"
                    )

                serialized_actions.append({
                    "FunctionCall": {
                        "method_name": action.method_name,
                        "args": base64.b64encode(bytes(action.args)).decode("ascii"),
                        "gas": int(action.gas),
                        "deposit": int(action.deposit),
                    }
                })

            delegate_json = {
                "sender_id": delegate.sender_id,
                "receiver_id": delegate.receiver_id,
                "actions": serialized_actions,
                "nonce": delegate.nonce,
                "max_block_height": delegate.max_block_height,
                "public_key": public_key,
            }

            return {
                "delegate_action": delegate_json,
                "signature": f"ed25519:{signature}",
            }


        except NearRelayerError:
            raise

        except Exception as exc:
            raise NearRelayerError(
                f"Could not create signed settlement action: {exc}"
            ) from exc

    async def submit_signed_delegate_action(
        self,
        delegate_action: dict,
        signature: str,
    ):
        if not self.base_url:
            raise NearRelayerError(
                "RELAYER_URL is not configured"
            )

        payload = {
            "delegate_action": delegate_action,
            "signature": signature,
        }

        headers = {}

        if settings.relayer_api_key:
            headers["Authorization"] = (
                f"Bearer {settings.relayer_api_key}"
            )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    f"{self.base_url}/send_meta_tx",
                    json=payload,
                    headers=headers,
                )

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as exc:
            raise NearRelayerError(
                f"Relayer returned HTTP "
                f"{exc.response.status_code}: {exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise NearRelayerError(
                f"Could not connect to NEAR relayer: {exc}"
            ) from exc


near_relayer = NearRelayer()