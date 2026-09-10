from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

AssetId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Symbol = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S+$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z0-9]{2,12}$")]


class AssetType(StrEnum):
    CRYPTO = "CRYPTO"
    STOCK = "STOCK"
    ETF = "ETF"
    INDEX = "INDEX"
    FOREX = "FOREX"
    COMMODITY = "COMMODITY"
    BOND = "BOND"
    OPTION = "OPTION"
    FUTURE = "FUTURE"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

    @property
    def duration(self) -> timedelta:
        return timedelta(
            seconds={
                "1m": 60,
                "5m": 300,
                "15m": 900,
                "30m": 1800,
                "1h": 3600,
                "4h": 14400,
                "1d": 86400,
                "1w": 604800,
            }[self.value]
        )


class ForecastHorizon(StrEnum):
    H1 = "1H"
    H4 = "4H"
    H8 = "8H"
    H12 = "12H"
    H24 = "24H"
    D2 = "2D"
    D3 = "3D"
    D7 = "7D"
    D14 = "14D"
    D30 = "30D"
    D90 = "90D"
    M6 = "6M"
    M12 = "12M"


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Asset(DomainModel):
    asset_id: AssetId
    symbol: Symbol
    name: str = Field(min_length=1, max_length=256)
    asset_type: AssetType


class Money(DomainModel):
    amount: Decimal
    currency: Currency


class TimestampedModel(DomainModel):
    observed_at: AwareDatetime

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        from datetime import UTC

        return value.astimezone(UTC)
