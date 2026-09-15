from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Number = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]
Ratio = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=18)]


class IntelligenceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UnavailableReason(StrEnum):
    PORTFOLIO_VALUATION_INCOMPLETE = "PORTFOLIO_VALUATION_INCOMPLETE"
    NO_OPEN_POSITIONS = "NO_OPEN_POSITIONS"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ZERO_VARIANCE = "ZERO_VARIANCE"
    STALE_VALUATION = "STALE_VALUATION"
    BENCHMARK_NOT_CONFIGURED = "BENCHMARK_NOT_CONFIGURED"
    SECTOR_DATA_UNAVAILABLE = "SECTOR_DATA_UNAVAILABLE"
    LIQUIDITY_DATA_UNAVAILABLE = "LIQUIDITY_DATA_UNAVAILABLE"
    NAV_HISTORY_UNAVAILABLE = "NAV_HISTORY_UNAVAILABLE"
    REGIME_ATTRIBUTION_UNAVAILABLE = "REGIME_ATTRIBUTION_UNAVAILABLE"
    HORIZON_ATTRIBUTION_UNAVAILABLE = "HORIZON_ATTRIBUTION_UNAVAILABLE"


class Metric(DomainModel):
    status: MetricStatus
    value: Number | None = None
    reason: UnavailableReason | None = None
    explanation: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == MetricStatus.AVAILABLE:
            if self.value is None or self.reason is not None:
                raise ValueError("available metric requires a value and no unavailable reason")
        elif self.value is not None or self.reason is None:
            raise ValueError("unavailable metric requires a reason and no value")
        return self


class PortfolioIntelligencePolicy(DomainModel):
    schema_version: Literal["portfolio-intelligence-policy-1.0.0"] = (
        "portfolio-intelligence-policy-1.0.0"
    )
    policy_version: Literal["portfolio-intelligence-1.0.0"] = "portfolio-intelligence-1.0.0"
    lookback_bars: int = Field(default=60, ge=20, le=500)
    minimum_observations: int = Field(default=20, ge=3, le=499)
    maximum_price_age_bars: int = Field(default=3, ge=1, le=100)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.minimum_observations >= self.lookback_bars:
            raise ValueError("minimum observations must be below lookback bars")
        return self


class AllocationDimension(StrEnum):
    CASH = "CASH"
    MARKET = "MARKET"
    ASSET_CLASS = "ASSET_CLASS"
    CURRENCY = "CURRENCY"
    VENUE = "VENUE"
    DIRECTION = "DIRECTION"


class AllocationBucket(DomainModel):
    dimension: AllocationDimension
    key: str = Field(min_length=1, max_length=128)
    value: NonNegative
    portfolio_weight: Ratio


class Concentration(DomainModel):
    dimension: AllocationDimension
    hhi: Metric
    largest_weight: Metric
    effective_count: Metric


class MarketRisk(DomainModel):
    market_id: Identifier
    observations: int = Field(ge=0, le=500)
    per_bar_volatility: Metric
    beta: Metric


class Correlation(DomainModel):
    left_market_id: Identifier
    right_market_id: Identifier
    observations: int = Field(ge=0, le=500)
    correlation: Metric

    @model_validator(mode="after")
    def canonical_pair(self) -> Self:
        if self.left_market_id >= self.right_market_id:
            raise ValueError("correlation pair must use canonical market order")
        return self


class RiskContribution(DomainModel):
    market_id: Identifier
    contribution_fraction: Metric


class ObservationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"


class PortfolioObservation(DomainModel):
    code: Identifier
    severity: ObservationSeverity
    message: str = Field(min_length=1, max_length=400)
    evidence: tuple[str, ...] = Field(default=(), max_length=20)


class PortfolioIntelligenceReport(DomainModel):
    schema_version: Literal["portfolio-intelligence-report-1.0.0"] = (
        "portfolio-intelligence-report-1.0.0"
    )
    analysis_id: UUID
    portfolio_id: UUID
    portfolio_revision: int = Field(ge=1)
    ledger_sequence: int = Field(ge=0)
    timeframe: Timeframe
    benchmark_market_id: Identifier | None = None
    as_of: UTCDateTime
    generated_at: UTCDateTime
    status: IntelligenceStatus
    policy: PortfolioIntelligencePolicy
    policy_hash: Hash
    portfolio_input_hash: Hash
    equity: NonNegative | None
    allocations: tuple[AllocationBucket, ...] = Field(max_length=1000)
    concentrations: tuple[Concentration, ...] = Field(max_length=10)
    market_risk: tuple[MarketRisk, ...] = Field(max_length=250)
    correlations: tuple[Correlation, ...] = Field(max_length=31125)
    portfolio_per_bar_volatility: Metric
    portfolio_beta: Metric
    risk_contributions: tuple[RiskContribution, ...] = Field(max_length=250)
    sector_concentration: Metric
    drawdown: Metric
    liquidity: Metric
    regime_exposure: Metric
    horizon_exposure: Metric
    observations: tuple[PortfolioObservation, ...] = Field(max_length=100)
    input_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("portfolio intelligence cannot precede its as-of time")
        allocation_keys = tuple((item.dimension.value, item.key) for item in self.allocations)
        if allocation_keys != tuple(sorted(allocation_keys)) or len(set(allocation_keys)) != len(
            allocation_keys
        ):
            raise ValueError("allocations must be unique and canonically ordered")
        market_ids = tuple(item.market_id for item in self.market_risk)
        if market_ids != tuple(sorted(market_ids)) or len(set(market_ids)) != len(market_ids):
            raise ValueError("market risk must be unique and canonically ordered")
        contribution_ids = tuple(item.market_id for item in self.risk_contributions)
        if contribution_ids != tuple(sorted(contribution_ids)):
            raise ValueError("risk contributions must use canonical market order")
        return self
