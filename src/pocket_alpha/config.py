from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://pocket_alpha:local_only@localhost:5432/pocket_alpha"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    database_url_file: Path | None = Field(default=None, repr=False)
    redis_url_file: Path | None = Field(default=None, repr=False)
    control_proxy_token: SecretStr = Field(default=SecretStr(""), repr=False)
    control_proxy_token_file: Path | None = Field(default=None, repr=False)
    # Deployment gates never authorize an order by themselves. The persistent control plane,
    # qualification evidence and independent risk engine must also approve execution.
    live_trading_enabled: bool = False
    derivative_execution_enabled: bool = False

    @field_validator("live_trading_enabled", "derivative_execution_enabled", mode="before")
    @classmethod
    def parse_boolean_flag(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return value

    @model_validator(mode="after")
    def load_file_secrets(self) -> "Settings":
        """Prefer Docker secret files without ever including their contents in errors."""
        for path, field in (
            (self.database_url_file, "database_url"),
            (self.redis_url_file, "redis_url"),
            (self.control_proxy_token_file, "control_proxy_token"),
        ):
            if path is None:
                continue
            try:
                if not path.is_file() or path.stat().st_size > 4096:
                    raise ValueError
                value = path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError, ValueError) as exc:
                raise ValueError(f"invalid {field} secret file") from exc
            if not value:
                raise ValueError(f"empty {field} secret file")
            object.__setattr__(self, field, SecretStr(value))
        if (
            self.environment == "production"
            and len(self.control_proxy_token.get_secret_value()) < 32
        ):
            raise ValueError("production control proxy token must contain at least 32 characters")
        if self.derivative_execution_enabled and not self.live_trading_enabled:
            raise ValueError("derivative deployment gate requires live trading deployment gate")
        return self
