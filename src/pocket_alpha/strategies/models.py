from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Hash, Parameter, StrategyIdentity, digest
from pocket_alpha.directional.models import DirectionalAnalysis
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.models import Forecast


class StrategyStage(StrEnum):
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE_SMALL = "LIVE_SMALL"
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class TrendParameters(DomainModel):
    fast_period: int = Field(ge=2, le=499, strict=True)
    slow_period: int = Field(ge=3, le=500, strict=True)
    minimum_trend_fraction: Decimal = Field(gt=0, le=1, max_digits=38, decimal_places=24)
    minimum_expected_return: Decimal = Field(gt=0, le=1, max_digits=38, decimal_places=24)
    invalidation_fraction: Decimal = Field(gt=0, lt=1, max_digits=38, decimal_places=18)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.fast_period >= self.slow_period:
            raise ValueError("trend fast period must precede slow period")
        return self


class AllocationPolicy(DomainModel):
    version: Identifier
    target_exposure_fraction: Decimal = Field(gt=0, le=1, max_digits=38, decimal_places=18)
    cash_buffer_fraction: Decimal = Field(ge=0, lt=1, max_digits=38, decimal_places=18)
    maximum_proposal_notional: Decimal = Field(gt=0, max_digits=38, decimal_places=18)


class StrategyDefinition(DomainModel):
    schema_version: Literal["strategy-definition-1.0.0"] = "strategy-definition-1.0.0"
    family: Literal["SMA_TREND_SPOT_LONG"] = "SMA_TREND_SPOT_LONG"
    version: Identifier
    model_version: Identifier
    market_id: Identifier
    asset_id: Identifier
    source: Identifier
    timeframe: Timeframe
    horizon: ForecastHorizon
    required_data: tuple[Literal["CANDLES", "TECHNICAL", "FORECAST", "DIRECTIONAL"], ...] = (
        "CANDLES",
        "TECHNICAL",
        "FORECAST",
        "DIRECTIONAL",
    )
    feature_version: Literal["technical-1.0.0"] = "technical-1.0.0"
    parameters: TrendParameters
    allocation: AllocationPolicy
    maximum_data_age_seconds: int = Field(ge=0, le=2592000, strict=True)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.required_data != ("CANDLES", "TECHNICAL", "FORECAST", "DIRECTIONAL"):
            raise ValueError("trend requirements cannot omit upstream evidence")
        return self

    def identity(self) -> StrategyIdentity:
        return StrategyIdentity(
            strategy_version=self.version,
            model_version=self.model_version,
            parameters=(Parameter(name="definition_hash", value=digest(self)),),
        )


class StrategyProposal(DomainModel):
    mode: Literal["RESEARCH_PROPOSAL"] = "RESEARCH_PROPOSAL"
    proposal_id: UUID
    definition_hash: Hash
    at: UTCDateTime
    market_id: Identifier
    asset_id: Identifier
    timeframe: Timeframe
    horizon: ForecastHorizon
    action: Literal["ENTER_LONG", "EXIT_LONG", "NO_TRADE"]
    reason: Identifier
    reference_price: Decimal | None = Field(default=None, gt=0)
    invalidation_price: Decimal | None = Field(default=None, gt=0)
    expires_at: UTCDateTime | None = None
    technical_input_hash: Hash | None = None
    directional: DirectionalAnalysis | None = None
    forecast: Forecast | None = None
    input_hash: Hash
    content_hash: Hash
    live_ready: Literal[False] = False

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.content_hash != digest(self.model_dump(mode="json", exclude={"content_hash"})):
            raise ValueError("strategy proposal hash mismatch")
        if self.action != "NO_TRADE" and (
            self.reference_price is None
            or self.invalidation_price is None
            or self.expires_at is None
        ):
            raise ValueError("tradable proposal needs reference, invalidation and expiry")
        if self.expires_at is not None and self.expires_at <= self.at:
            raise ValueError("strategy proposal expiry must follow its observation")
        for evidence in (self.directional, self.forecast):
            if evidence is not None and (
                evidence.market_id != self.market_id
                or evidence.asset_id != self.asset_id
                or evidence.horizon != self.horizon
                or evidence.candle_timeframe != self.timeframe
                or evidence.generated_at > self.at
            ):
                raise ValueError("strategy proposal evidence identity/time mismatch")
        return self


class PositionMemory(DomainModel):
    definition_hash: Hash
    observed_quantity: Decimal = Field(default=Decimal(0), ge=0)
    invalidation_price: Decimal | None = Field(default=None, gt=0)
    holding_until: UTCDateTime | None = None
    entry_client_id: Identifier | None = None
    proposal: StrategyProposal | None = None
