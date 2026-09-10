from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


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
    asset_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    asset_type: AssetType


class Money(DomainModel):
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z0-9]{2,12}$")


class TimestampedModel(DomainModel):
    observed_at: AwareDatetime

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        from datetime import UTC

        return value.astimezone(UTC)
