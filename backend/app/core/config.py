from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    near_intents_base_url: str = "https://www.usetidepool.tech"
    near_intents_api_key: str = ""

    near_network: str = "testnet"
    near_rpc_url: str

    payflow_contract_id: str
    payflow_contract_admin_id: str = ""

    relayer_url: str = ""
    relayer_api_key: str = ""
    relayer_max_gas: int = 100_000_000_000_000
    internal_api_key: str = ""

    usdc_asset_id: str = "nep141:usdc.tidepool-sandbox.testnet"
    usdc_decimals: int = 6

    frontend_url: str = "http://localhost:3000"

    # Wallet authentication
    auth_cookie_secure: bool = False
    auth_session_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()