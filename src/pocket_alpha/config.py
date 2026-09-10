from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://pocket_alpha:local_only@localhost:5432/pocket_alpha"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    # Live execution is unavailable in Foundation, even with environment overrides.
    live_trading_enabled: Literal[False] = False
