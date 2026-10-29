from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "data"
    timezone: str = "Asia/Kolkata"
    port: int = 8000
    public_url: str = "http://localhost:8000"
    dashboard_dir: str = "../frontend/out"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_confirmation_template: str = ""
    whatsapp_template_language: str = "en"
    whatsapp_reminder_template: str = ""
    reminder_hours: int = 3

    cloudflare_tunnel_token: str = ""
    cloudflared_path: str = "cloudflared"
    backups_to_keep: int = 14

    plivo_webhook_key: str = ""
    plivo_voice: str = "Polly.Aditi"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def config() -> Config:
    return Config()
