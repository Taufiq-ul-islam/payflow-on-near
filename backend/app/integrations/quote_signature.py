import hashlib
import json

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


ONE_CLICK_PUBLIC_KEY = (
    "ed25519:reYaWhvwu8Jzo3WUM3zhn6VrhuMEF4eADL17qtRVifc"
)

BASE58_ALPHABET = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def base58_encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = ""

    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded

    leading_zeros = len(data) - len(data.lstrip(b"\x00"))

    return (
        BASE58_ALPHABET[0] * leading_zeros
        + encoded
    )


def base58_decode(value: str) -> bytes:
    number = 0

    for char in value:
        try:
            digit = BASE58_ALPHABET.index(char)
        except ValueError as exc:
            raise ValueError("Invalid Base58 value") from exc

        number = number * 58 + digit

    leading_zeros = len(value) - len(value.lstrip("1"))

    decoded = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )

    return b"\x00" * leading_zeros + decoded


def decode_ed25519(value: str) -> bytes:
    if value.startswith("ed25519:"):
        value = value[len("ed25519:"):]

    return base58_decode(value)


def verify_quote_signature(
    quote_request: dict,
    quote: dict,
    timestamp: str,
    signature: str,
) -> bool:
    try:
        if not isinstance(quote_request, dict):
            return False

        if not isinstance(quote, dict):
            return False

        if not isinstance(timestamp, str):
            return False

        if not isinstance(signature, str):
            return False

        signed_payload = {
            **quote_request,
            **quote,
            "timestamp": timestamp,
        }

        canonical_json = json.dumps(
            signed_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

        digest = hashlib.sha256(
            canonical_json.encode("utf-8")
        ).digest()

        message = base58_encode(digest).encode("utf-8")

        public_key = decode_ed25519(ONE_CLICK_PUBLIC_KEY)
        signature_bytes = decode_ed25519(signature)

        if len(public_key) != 32 or len(signature_bytes) != 64:
            return False

        VerifyKey(public_key).verify(message, signature_bytes)

        return True

    except (
        KeyError,
        TypeError,
        ValueError,
        BadSignatureError,
    ):
        return False
