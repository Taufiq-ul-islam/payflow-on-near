import httpx

from app.core.config import settings

class NearIntentsError(Exception):
    pass

class NearIntents:
    def __init__(self):
        self.base_url = settings.near_intents_base_url.rstrip("/")
        self.timeout = httpx.Timeout(30.0)

        self.headers = {}

        if settings.near_intents_api_key:
            self.headers["Authorization"] = (f"Bearer {settings.near_intents_api_key}")

    async def _request(self, method: str, path: str, **kwargs):
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self.headers,
            ) as client:
                response = await client.request(method, path, **kwargs)

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()
            except ValueError:
                detail = exc.response.text

            raise NearIntentsError(
                f"NEAR Intents 1Click HTTP {exc.response.status_code}: {detail}"
            ) from exc

        except httpx.RequestError as exc:
            raise NearIntentsError(
                f"NEAR Intents 1Click connection failed: {exc}"
            ) from exc

        except ValueError as exc:
            raise NearIntentsError(
                "NEAR Intents 1Click returned an invalid JSON response."
            ) from exc

    async def get_tokens(self):
        return await self._request("GET", "/v0/tokens")

    async def get_quote(self, payload: dict):
        return await self._request("POST", "/v0/quote", json=payload)

    async def submit_deposit(
        self,
        deposit_address: str,
        tx_hash: str,
        memo: str | None = None,
        near_sender_account: str | None = None,
    ):
        payload = {
            "depositAddress": deposit_address,
            "txHash": tx_hash,
        }

        if memo:
            payload["memo"] = memo

        if near_sender_account:
            payload["nearSenderAccount"] = near_sender_account

        return await self._request("POST", "/v0/deposit/submit", json=payload)

    async def get_status(
        self,
        deposit_address: str,
        deposit_memo: str | None = None,
    ):
        params = {"depositAddress": deposit_address}

        if deposit_memo:
            params["depositMemo"] = deposit_memo

        return await self._request("GET", "/v0/status", params=params)


near_intents = NearIntents()