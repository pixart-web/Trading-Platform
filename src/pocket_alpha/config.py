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
    # Live execution stays structurally unavailable, including via environment overrides.
    live_trading_enabled: Literal[False] = False
    # Derivative execution has a separate fail-closed gate.
    derivative_execution_enabled: Literal[False] = False

    @field_validator("live_trading_enabled", "derivative_execution_enabled", mode="before")
    @classmethod
    def parse_disabled_flag(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() == "false":
            return False
        return value

    @model_validator(mode="after")
    def load_file_secrets(self) -> "Settings":
        """Prefer Docker secret files without ever including their contents in errors."""
        for path, field in (
            (self.database_url_file, "database_url"),
            (self.redis_url_file, "redis_url"),
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
        return self
