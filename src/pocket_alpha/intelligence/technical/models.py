from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.market_data.quality import FreshnessPolicy


class IndicatorKind(StrEnum):
    SMA = "SMA"
    EMA = "EMA"
    WMA = "WMA"
    MACD = "MACD"
    RSI = "RSI"
    STOCHASTIC = "STOCHASTIC"
    ROC = "ROC"
    CCI = "CCI"
    ATR = "ATR"
    BOLLINGER = "BOLLINGER"
    REALIZED_VOLATILITY = "REALIZED_VOLATILITY"
    VOLUME = "VOLUME"
    VWAP = "VWAP"
    PRICE_ACTION = "PRICE_ACTION"
    LINEAR_TREND = "LINEAR_TREND"


class IndicatorSpec(DomainModel):
    kind: IndicatorKind
    version: Literal["1.0.0"] = "1.0.0"
    period: int = Field(default=14, ge=2, le=500, strict=True)
    fast_period: int = Field(default=12, ge=2, le=500, strict=True)
    slow_period: int = Field(default=26, ge=2, le=500, strict=True)
    signal_period: int = Field(default=9, ge=2, le=500, strict=True)
    deviations: Decimal = Field(default=Decimal(2), gt=0, le=10)

    @model_validator(mode="after")
    def parameters(self) -> Self:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        if self.kind != IndicatorKind.MACD and (
            self.fast_period,
            self.slow_period,
            self.signal_period,
        ) != (12, 26, 9):
            raise ValueError("MACD parameters are only valid for MACD")
        if self.kind == IndicatorKind.MACD and self.period != 14:
            raise ValueError("MACD uses fast/slow/signal periods, not period")
        if self.kind != IndicatorKind.BOLLINGER and self.deviations != 2:
            raise ValueError("deviations is only valid for BOLLINGER")
        return self


class FeatureStatus(StrEnum):
    READY = "READY"
    WARMUP = "WARMUP"
    UNDEFINED = "UNDEFINED"


class FeatureValue(DomainModel):
    name: Identifier
    value: Decimal | None
    status: FeatureStatus
    reason: Literal["INSUFFICIENT_HISTORY", "ZERO_DENOMINATOR"] | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.status == FeatureStatus.READY:
            if self.value is None or self.reason is not None:
                raise ValueError("ready features require a finite value and no reason")
        elif (
            self.value is not None
            or self.reason
            != {
                FeatureStatus.WARMUP: "INSUFFICIENT_HISTORY",
                FeatureStatus.UNDEFINED: "ZERO_DENOMINATOR",
            }[self.status]
        ):
            raise ValueError("unavailable features require a matching reason and no value")
        return self


class IndicatorResult(DomainModel):
    spec: IndicatorSpec
    features: tuple[FeatureValue, ...]


class FeatureSnapshot(DomainModel):
    engine_version: Literal["technical-1.0.0"] = "technical-1.0.0"
    numeric_policy: Literal["decimal50-half-even-v1"] = "decimal50-half-even-v1"
    market_id: Identifier
    timeframe: Timeframe
    source: Identifier
    freshness_policy: FreshnessPolicy
    input_start: UTCDateTime
    bar_open: UTCDateTime
    bar_close: UTCDateTime
    available_at: UTCDateTime
    input_count: int = Field(ge=1, le=10000)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    results: tuple[IndicatorResult, ...]
