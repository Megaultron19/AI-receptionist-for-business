"""Installation settings. Everything secret or deployment-specific comes from the environment;
restaurant business configuration (menu, tables, hours, rules) lives in the database."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/resto"
    secret_key: str = ""
    public_base_url: str = "http://localhost:8000"
    dashboard_url: str = "http://localhost:3000"
    dashboard_dir: str = ""
    cors_origins: str = ""
    log_level: str = "INFO"
    sentry_dsn: str = ""

    anthropic_api_key: str = ""
    llm_provider: str = "anthropic"
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "low"
    llm_timeout_seconds: float = 20.0
    voice_llm_timeout_seconds: float = 9.0

    plivo_auth_id: str = ""
    plivo_auth_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    meta_access_token: str = ""
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_phone_number_id: str = ""
    meta_graph_version: str = "v23.0"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    cost_voice_per_minute_paise: int = 100
    cost_whatsapp_service_msg_paise: int = 0
    cost_whatsapp_template_msg_paise: int = 90
    cost_llm_per_1k_input_tokens_paise: int = 35
    cost_llm_per_1k_output_tokens_paise: int = 170

    session_days: int = 14

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
