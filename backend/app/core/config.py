from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    near_intents_base_url: str
    near_intents_api_key: str

    near_network: str 
    near_rpc_url: str 

    payflow_contract_id: str
    payflow_contract_admin_id: str

    payflow_admin_function_call_public_key: str
    payflow_admin_function_call_private_key: str

    relayer_url: str
    relayer_api_key: str
    relayer_max_gas: int
    internal_api_key: str

    usdc_asset_id: str
    usdc_decimals: int

    frontend_url: str = "http://localhost:3000"

    # Wallet authentication
    auth_cookie_secure: bool = True
    auth_session_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()