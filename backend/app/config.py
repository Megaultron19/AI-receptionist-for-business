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

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def config() -> Config:
    return Config()
