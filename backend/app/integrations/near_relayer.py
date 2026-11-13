import base64
import json

import httpx
from nacl.signing import SigningKey
from py_near.account import Account
from py_near_primitives import FunctionCallAction

from app.core.config import settings


class NearRelayerError(Exception):
    def __init__(self, message: str, outcome_uncertain: bool = False):
        super().__init__(message)
        self.outcome_uncertain = outcome_uncertain


_BASE58_ALPHABET = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def _base58_decode(value: str) -> bytes:
    number = 0

    for char in value:
        if char not in _BASE58_ALPHABET:
            raise ValueError("Invalid base58 character")
        number = number * 58 + _BASE58_ALPHABET.index(char)

    decoded = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )

    leading_zeroes = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeroes + decoded


def _base58_encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = ""

    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded

    leading_zeroes = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading_zeroes + encoded


def _decode_ed25519_key(value: str, label: str) -> bytes:
    if not isinstance(value, str) or not value.startswith("ed25519:"):
        raise NearRelayerError(
            f"{label} must use the ed25519: prefix"
        )

    try:
        decoded = _base58_decode(value.split(":", 1)[1])
    except ValueError as exc:
        raise NearRelayerError(
            f"{label} is not valid base58"
        ) from exc

    return decoded


def _validate_signing_key_pair(
    public_key: str,
    private_key: str,
) -> str:
    """
    Derive the Ed25519 public key from the configured private key
    and verify that the two configured keys match.

    NEAR ed25519 private keys are commonly 64-byte keypairs.
    A 32-byte seed is also accepted.
    """

    public_bytes = _decode_ed25519_key(
        public_key,
        "Function-call public key",
    )

    private_bytes = _decode_ed25519_key(
        private_key,
        "Function-call private key",
    )

    if len(public_bytes) != 32:
        raise NearRelayerError(
            "Function-call public key must decode to 32 bytes"
        )

    if len(private_bytes) == 64:
        seed = private_bytes[:32]
        embedded_public_key = private_bytes[32:]

    elif len(private_bytes) == 32:
        seed = private_bytes
        embedded_public_key = None

    else:
        raise NearRelayerError(
            "Function-call private key must decode to 32 or 64 bytes"
        )

    try:
        signing_key = SigningKey(seed)
        derived_public_key = signing_key.verify_key.encode()
    except Exception as exc:
        raise NearRelayerError(
            "Could not derive public key from private key"
        ) from exc

    if derived_public_key != public_bytes:
        raise NearRelayerError(
            "Configured function-call public and private keys do not match"
        )

    if (
        embedded_public_key is not None
        and embedded_public_key != derived_public_key
    ):
        raise NearRelayerError(
            "Private key contains an inconsistent public-key component"
        )

    return _base58_encode(derived_public_key)


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

        public_key_b58 = _validate_signing_key_pair(
            public_key,
            private_key,
        )

        try:
            account = Account(
                account_id=admin_id,
                private_key=private_key,
                rpc_addr=settings.near_rpc_url,
            )

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

            # py-near returns a base58-encoded signature.
            signature_b58 = account.sign_delegate_transaction(delegate)

            signature_bytes = _base58_decode(signature_b58)

            if len(signature_bytes) != 64:
                raise NearRelayerError(
                    "py-near returned an invalid Ed25519 signature"
                )

            # Ensure the generated delegate uses the validated key.
            delegate_public_key = delegate.public_key

            if isinstance(delegate_public_key, bytes):
                delegate_public_key = _base58_encode(
                    delegate_public_key
                )

            if isinstance(delegate_public_key, str):
                if delegate_public_key.startswith("ed25519:"):
                    delegate_public_key = delegate_public_key.split(
                        ":", 1
                    )[1]

            if delegate_public_key != public_key_b58:
                raise NearRelayerError(
                    "Generated DelegateAction uses an unexpected public key"
                )

            serialized_actions = []

            for action in delegate.actions:
                if not isinstance(action, FunctionCallAction):
                    raise NearRelayerError(
                        "Unexpected action type in DelegateAction"
                    )

                serialized_actions.append({
                    "FunctionCall": {
                        "method_name": action.method_name,
                        "args": base64.b64encode(
                            bytes(action.args)
                        ).decode("ascii"),
                        "gas": int(action.gas),
                        "deposit": int(action.deposit),
                    }
                })

            delegate_json = {
                "sender_id": delegate.sender_id,
                "receiver_id": delegate.receiver_id,
                "actions": serialized_actions,
                "nonce": int(delegate.nonce),
                "max_block_height": int(delegate.max_block_height),
                "public_key": f"ed25519:{delegate_public_key}",
            }

            return {
                "delegate_action": delegate_json,
                "signature": f"ed25519:{signature_b58}",
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
    ) -> dict:
        """
        Submit an already-signed DelegateAction to the relayer.

        outcome_uncertain=True means the request may have reached
        the relayer, so automatic resubmission is unsafe.
        """

        if not self.base_url:
            raise NearRelayerError(
                "RELAYER_URL is not configured"
            )

        if not isinstance(delegate_action, dict):
            raise NearRelayerError(
                "Invalid DelegateAction payload"
            )

        if not isinstance(signature, str) or not signature.startswith(
            "ed25519:"
        ):
            raise NearRelayerError(
                "Invalid DelegateAction signature"
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

                try:
                    result = response.json()
                except ValueError as exc:
                    raise NearRelayerError(
                        "Relayer returned invalid JSON",
                        outcome_uncertain=True,
                    ) from exc

                if not isinstance(result, dict):
                    raise NearRelayerError(
                        "Relayer returned an invalid response",
                        outcome_uncertain=True,
                    )

                return result

        except NearRelayerError:
            raise

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code

            # A 4xx rejection (apart from timeout-like responses)
            # is treated as a definite request rejection.
            uncertain = (
                status_code in {408, 409, 425, 429}
                or status_code >= 500
            )

            raise NearRelayerError(
                f"Relayer returned HTTP {status_code}: "
                f"{exc.response.text}",
                outcome_uncertain=uncertain,
            ) from exc

        except httpx.RequestError as exc:
            # The connection may have failed after the relayer
            # received the request.
            raise NearRelayerError(
                f"Could not connect to NEAR relayer: {exc}",
                outcome_uncertain=True,
            ) from exc


near_relayer = NearRelayer()
