import httpx

from app.core.config import settings

class NearRelayerError(Exception):
    pass

class NearRelayer:
    def __init__(self):
        self.base_url = settings.relayer_url.rstrip("/")
        self.timeout = httpx.Timeout(60.0)

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