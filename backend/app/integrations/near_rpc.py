import httpx

from app.core.config import settings

class NearRpcError(Exception):
    pass


class NearRpc:
    def __init__(self):
        self.rpc_url = settings.near_rpc_url.rstrip("/")
        self.timeout = httpx.Timeout(30.0)

    async def get_transaction(
        self,
        tx_hash: str,
        sender_account: str,
    ):
        payload = {
            "jsonrpc": "2.0",
            "id": "payflow-refund-verification",
            "method": "EXPERIMENTAL_tx_status",
            "params": [
                tx_hash,
                sender_account,
            ],
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    self.rpc_url,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            if not isinstance(result, dict):
                raise NearRpcError("Invalid NEAR RPC response.")
            
            if result.get("error"):
                raise NearRpcError(
                    f"NEAR RPC error: {result['error']}"
                )

            transaction_result = result.get("result")

            if not isinstance(transaction_result, dict):
                raise NearRpcError("NEAR RPC returned no transaction result.")

            return transaction_result

        except httpx.HTTPStatusError as exc:
            raise NearRpcError(
                f"NEAR RPC HTTP {exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise NearRpcError(f"Could not connect to NEAR RPC: {exc}") from exc

        except ValueError as exc:
            raise NearRpcError("NEAR RPC returned invalid JSON.") from exc


    async def get_transaction_status(
        self,
        tx_hash: str,
        sender_account: str,
    ):
        return await self.get_transaction(tx_hash, sender_account)


near_rpc = NearRpc()