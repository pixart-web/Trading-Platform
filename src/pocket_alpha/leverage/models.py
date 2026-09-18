"""Immutable, versioned and explicitly sourced research inputs. No confidence-based leverage."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Hash, digest
from pocket_alpha.derivatives.models import DerivativeContract
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import Currency, DomainModel, ForecastHorizon, Timeframe

Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18, allow_inf_nan=False)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18, allow_inf_nan=False)]
Fraction = Annotated[
    Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=18, allow_inf_nan=False)
]
Result = Annotated[Decimal, Field(allow_inf_nan=False)]
Origin = Literal["REAL", "SYNTHETIC"]


class AssessmentStatus(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    ELEVATED = "ELEVATED"
    HIGH_RISK = "HIGH_RISK"
    REJECTED = "REJECTED"


class StressKind(StrEnum):
    GAP = "GAP"
    VOLATILITY = "VOLATILITY"
    LIQUIDATION = "LIQUIDATION"
    SLIPPAGE = "SLIPPAGE"
    FUNDING = "FUNDING"
    CORRELATED = "CORRELATED"


class ResearchPosition(DomainModel):
    version: Identifier
    contract: DerivativeContract
    side: Literal["LONG", "SHORT"]
    contracts: Positive
    entry: Positive
    stop: Positive
    proposed_leverage: Annotated[Decimal, Field(ge=1, le=1000, max_digits=38, decimal_places=18)]
    timeframe: Timeframe
    horizon: ForecastHorizon
    proposal_at: UTCDateTime
    upstream_hash: Hash


class PortfolioCollateral(DomainModel):
    version: Identifier
    origin: Origin
    at: UTCDateTime
    available_at: UTCDateTime
    currency: Currency
    equity: Positive
    available_collateral: Nonnegative
    provenance_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.available_at < self.at or self.available_collateral > self.equity:
            raise ValueError("portfolio availability/collateral inconsistent")
        return self


class PriorRiskCheck(DomainModel):
    # Caller attestation for offline research, never authenticated order approval.
    version: Identifier
    origin: Origin
    proposal_hash: Hash
    portfolio_hash: Hash
    passed: bool = Field(strict=True)
    assessed_at: UTCDateTime
    valid_until: UTCDateTime
    provenance_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_until <= self.assessed_at:
            raise ValueError("research risk validity must follow assessment")
        return self


class MarginAssumptions(DomainModel):
    model: Literal["LINEAR_ISOLATED_MARK_NOTIONAL_1"] = "LINEAR_ISOLATED_MARK_NOTIONAL_1"
    version: Identifier
    contract_hash: Hash
    available_at: UTCDateTime
    valid_until: UTCDateTime
    initial_margin_rate: Annotated[Decimal, Field(gt=0, le=1, max_digits=38, decimal_places=18)]
    maintenance_margin_rate: Fraction
    liquidation_fee_rate: Fraction
    maximum_mark_notional: Positive
    rules_reference: str = Field(min_length=1, max_length=512)
    provenance_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_until <= self.available_at:
            raise ValueError("margin validity must follow availability")
        if self.maintenance_margin_rate > self.initial_margin_rate:
            raise ValueError("maintenance margin exceeds initial margin")
        return self


class HorizonVolatility(DomainModel):
    contract_hash: Hash
    version: Identifier
    origin: Origin
    convention: Literal["HORIZON_RETURN_FRACTION"] = "HORIZON_RETURN_FRACTION"
    timeframe: Timeframe
    horizon: ForecastHorizon
    observed_at: UTCDateTime
    available_at: UTCDateTime
    value: Fraction
    input_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.available_at < self.observed_at:
            raise ValueError("volatility available before observation")
        return self


class TransactionAssumptions(DomainModel):
    contract_hash: Hash
    version: Identifier
    available_at: UTCDateTime
    horizon: ForecastHorizon
    entry_fee_bps: Annotated[Decimal, Field(ge=0, le=10000, max_digits=38, decimal_places=18)]
    exit_fee_bps: Annotated[Decimal, Field(ge=0, le=10000, max_digits=38, decimal_places=18)]
    spread_bps: Annotated[Decimal, Field(ge=0, le=10000, max_digits=38, decimal_places=18)]
    slippage_bps: Annotated[Decimal, Field(ge=0, le=10000, max_digits=38, decimal_places=18)]
    adverse_funding_fraction: Fraction
    provenance_hash: Hash


class StressScenario(DomainModel):
    name: Identifier
    kind: StressKind
    adverse_gap_fraction: Annotated[Decimal, Field(ge=0, le=100, max_digits=38, decimal_places=18)]
    volatility_multiple: Annotated[Decimal, Field(ge=0, le=100, max_digits=38, decimal_places=18)]
    additional_slippage_bps: Annotated[
        Decimal, Field(ge=0, le=10000, max_digits=38, decimal_places=18)
    ]
    additional_funding_fraction: Fraction
    other_portfolio_loss_fraction: Fraction

    @model_validator(mode="after")
    def exercised(self) -> Self:
        required = {
            StressKind.GAP: self.adverse_gap_fraction,
            StressKind.VOLATILITY: self.volatility_multiple,
            StressKind.SLIPPAGE: self.additional_slippage_bps,
            StressKind.CORRELATED: self.other_portfolio_loss_fraction,
        }
        if self.kind in required and required[self.kind] <= 0:
            raise ValueError("stress must exercise its declared family")
        return self


class LeveragePolicy(DomainModel):
    version: Identifier
    maximum_input_age_seconds: int = Field(ge=0, le=2592000, strict=True)
    maximum_leverage: Annotated[Decimal, Field(ge=1, le=1000, max_digits=38, decimal_places=18)]
    maximum_position_notional: Positive
    maximum_collateral_fraction: Fraction
    elevated_loss_fraction: Fraction
    high_loss_fraction: Fraction
    maximum_loss_fraction: Annotated[Decimal, Field(gt=0, le=1, max_digits=38, decimal_places=18)]
    minimum_liquidation_buffer_fraction: Fraction
    forced_liquidation_overshoot_fraction: Annotated[
        Decimal, Field(gt=0, le=1, max_digits=38, decimal_places=18)
    ]
    reject_standard_liquidation: bool = Field(strict=True)
    reject_collateral_deficit: bool = Field(strict=True)
    scenarios: tuple[StressScenario, ...] = Field(min_length=6, max_length=32)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if not self.elevated_loss_fraction < self.high_loss_fraction < self.maximum_loss_fraction:
            raise ValueError("risk bands must be ordered below the hard loss limit")
        if len({s.name for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("stress names must be unique")
        if {s.kind for s in self.scenarios} != set(StressKind):
            raise ValueError("all six stress families must be declared")
        return self


class LeverageRequest(DomainModel):
    schema_version: Literal["leverage-request-1.0.0"] = "leverage-request-1.0.0"
    origin: Origin
    as_of: UTCDateTime
    position: ResearchPosition
    portfolio: PortfolioCollateral | None
    prior_risk: PriorRiskCheck | None
    margin: MarginAssumptions | None
    volatility: HorizonVolatility | None
    costs: TransactionAssumptions | None
    policy: LeveragePolicy


class StressResult(DomainModel):
    name: Identifier
    kind: StressKind
    adverse_fraction: Result
    exit_mark: Result
    liquidation_price: Result
    liquidated: bool
    transaction_costs: Result
    funding_cost: Result
    modeled_position_loss: Result
    correlated_loss: Result
    combined_portfolio_loss: Result
    portfolio_loss_fraction: Result
    collateral_deficit: Result
    projected_portfolio_equity: Result
    ruin_scenario: bool
    tier_applicable: bool


class LeverageAssessment(DomainModel):
    schema_version: Literal["leverage-assessment-1.0.0"] = "leverage-assessment-1.0.0"
    mode: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    assessment_id: UUID
    generated_at: UTCDateTime
    request: LeverageRequest
    input_hash: Hash
    status: AssessmentStatus
    rejection_reasons: tuple[Identifier, ...]
    warnings: tuple[Identifier, ...]
    base_units: Result | None
    position_notional: Result | None
    required_collateral: Result | None
    stop_distance_fraction: Result | None
    liquidation_price: Result | None
    liquidation_distance_fraction: Result | None
    volatility: Result | None
    expected_transaction_costs: Result | None
    modeled_stop_loss: Result | None
    maximum_modeled_loss: Result | None
    portfolio_risk_fraction: Result | None
    stresses: tuple[StressResult, ...]
    ruin_probability: Literal[None] = None
    execution_authorized: Literal[False] = False
    live_ready: Literal[False] = False
    content_hash: Hash

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.input_hash != digest(self.request) or self.content_hash != digest(
            self.model_dump(mode="json", exclude={"content_hash"})
        ):
            raise ValueError("leverage assessment content/input hash mismatch")
        if self.assessment_id != uuid5(NAMESPACE_URL, "pocket-alpha-leverage:" + self.input_hash):
            raise ValueError("leverage assessment identity mismatch")
        if self.generated_at < self.request.as_of:
            raise ValueError("leverage assessment cannot precede its causal cutoff")
        if (self.status == AssessmentStatus.REJECTED) != bool(self.rejection_reasons):
            raise ValueError("leverage assessment status/rejections inconsistent")
        return self
