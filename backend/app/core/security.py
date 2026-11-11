import base64
import hashlib
import re
import struct
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import settings


ACCOUNT_ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$"
)

NEP413_TAG = 2**31 + 413


def _borsh_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def nep413_signing_hash(
    message: str,
    nonce: bytes,
    recipient: str,
    callback_url: str | None = None,
) -> bytes:
    if len(nonce) != 32:
        raise ValueError("NEP-413 nonce must be 32 bytes")

    payload = (
        struct.pack("<I", NEP413_TAG)
        + _borsh_string(message)
        + nonce
        + _borsh_string(recipient)
        + (
            b"\x00"
            if callback_url is None
            else b"\x01" + _borsh_string(callback_url)
        )
    )

    return hashlib.sha256(payload).digest()


def _b58decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

    number = 0

    for char in value:
        if char not in alphabet:
            raise ValueError("Invalid base58 value")

        number = number * 58 + alphabet.index(char)

    raw = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )

    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def verify_nep413_signature(
    public_key: str,
    signature: str,
    message: str,
    nonce_b64: str,
    recipient: str,
    callback_url: str,
) -> bool:
    try:
        key_type, encoded_key = public_key.split(":", 1)

        if key_type != "ed25519":
            return False

        key_bytes = _b58decode(encoded_key)
        signature_bytes = base64.b64decode(signature, validate=True)
        nonce = base64.b64decode(nonce_b64, validate=True)

        if (
            len(key_bytes) != 32
            or len(signature_bytes) != 64
            or len(nonce) != 32
        ):
            return False

        digest = nep413_signing_hash(
            message,
            nonce,
            recipient,
            callback_url,
        )

        Ed25519PublicKey.from_public_bytes(key_bytes).verify(
            signature_bytes,
            digest,
        )

        return True

    except (
        ValueError,
        InvalidSignature,
        TypeError,
    ):
        return False


def auth_recipient() -> str:
    parsed = urlparse(settings.frontend_url)

    if not parsed.netloc:
        raise RuntimeError("FRONTEND_URL must be an absolute URL")

    return parsed.netloc.lower()


def auth_callback_url() -> str:
    return settings.frontend_url.rstrip("/") + "/login"


async def is_full_access_key(
    account_id: str,
    public_key: str,
) -> bool:
    payload = {
        "jsonrpc": "2.0",
        "id": "payflow-auth",
        "method": "query",
        "params": {
            "request_type": "view_access_key_list",
            "finality": "final",
            "account_id": account_id,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                settings.near_rpc_url,
                json=payload,
            )
            response.raise_for_status()

            result = response.json().get("result", {})

        for entry in result.get("keys", []):
            if (
                entry.get("public_key") == public_key
                and entry.get("access_key", {}).get("permission")
                == "FullAccess"
            ):
                return True

        return False

    except (httpx.HTTPError, ValueError, TypeError):
        return False