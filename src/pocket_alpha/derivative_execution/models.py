"""Fail-closed contracts for synthetic derivative execution qualification."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Hash, digest
from pocket_alpha.derivatives.models import DerivativeContract
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import Currency, DomainModel
from pocket_alpha.leverage.models import LeverageAssessment

Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18, allow_inf_nan=False)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18, allow_inf_nan=False)]
Fraction = Annotated[
    Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=18, allow_inf_nan=False)
]
Signed = Annotated[Decimal, Field(max_digits=38, decimal_places=18, allow_inf_nan=False)]
Origin = Literal["REAL", "SYNTHETIC"]


class DerivativeExecutionPolicy(DomainModel):
    schema_version: Literal["derivative-execution-policy-1.0.0"] = (
        "derivative-execution-policy-1.0.0"
    )
    version: Identifier
    mode: Literal["DISABLED", "SYNTHETIC_QUALIFICATION"] = "DISABLED"
    global_enable: bool = False
    derivative_enable: bool = False
    manual_enable: bool = False
    account_identity_hash: Hash
    contract_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    strategy_hashes: tuple[Hash, ...] = Field(min_length=1, max_length=20)
    collateral_currency: Currency
    capital_limit: Positive
    order_notional_limit: Positive
    total_gross_notional_limit: Positive
    total_net_notional_limit: Positive
    position_notional_limit: Positive
    collateral_limit: Positive
    daily_loss_limit: Positive
    maximum_drawdown: Fraction
    maximum_collateral_fraction: Fraction
    maximum_leverage: Annotated[Decimal, Field(ge=1, le=100, max_digits=38, decimal_places=18)]
    minimum_liquidation_buffer_fraction: Fraction
    maximum_initial_margin_rate: Fraction
    maximum_maintenance_margin_rate: Fraction
    maximum_fee_fraction: Fraction
    maximum_funding_fraction: Fraction
    maximum_spread_fraction: Fraction
    maximum_mark_index_deviation_fraction: Fraction
    maximum_basis_fraction: Fraction
    maximum_price_deviation_fraction: Fraction
    maximum_modeled_loss_fraction: Fraction
    maximum_positions: int = Field(ge=1, le=20, strict=True)
    maximum_orders_per_minute: int = Field(ge=1, le=60, strict=True)
    maximum_orders_per_day: int = Field(ge=1, le=1000, strict=True)
    maximum_data_age_seconds: int = Field(ge=1, le=300, strict=True)
    minimum_expiry_buffer_seconds: int = Field(ge=0, le=31_536_000, strict=True)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(set(self.contract_ids)) != len(self.contract_ids) or len(
            set(self.strategy_hashes)
        ) != len(self.strategy_hashes):
            raise ValueError("duplicate derivative policy allowlist")
        if not (
            self.order_notional_limit
            <= self.position_notional_limit
            <= self.total_gross_notional_limit
            <= self.capital_limit
        ):
            raise ValueError("inconsistent derivative notional limits")
        if self.total_net_notional_limit > self.total_gross_notional_limit:
            raise ValueError("net notional limit exceeds gross limit")
        if self.collateral_limit > self.capital_limit:
            raise ValueError("collateral limit exceeds capital limit")
        return self


class DerivativeStrategyEvidence(DomainModel):
    """Immutable strategy output reference; this module does not invent signals."""

    schema_version: Literal["derivative-strategy-evidence-1.0.0"] = (
        "derivative-strategy-evidence-1.0.0"
    )
    strategy_id: UUID
    strategy_version: Identifier
    definition_hash: Hash
    proposal_hash: Hash
    leverage_position_hash: Hash
    stage: Literal["SHADOW"] = "SHADOW"
    origin: Literal["SYNTHETIC"] = "SYNTHETIC"
    evaluated_at: UTCDateTime
    valid_until: UTCDateTime
    evidence_hash: Hash
    content_hash: Hash

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.valid_until <= self.evaluated_at:
            raise ValueError("strategy evidence validity must follow evaluation")
        if self.content_hash != digest(self.model_dump(mode="json", exclude={"content_hash"})):
            raise ValueError("strategy evidence hash mismatch")
        return self


class DerivativeOrderIntent(DomainModel):
    schema_version: Literal["derivative-order-intent-1.0.0"] = "derivative-order-intent-1.0.0"
    intent_id: UUID
    contract_id: Identifier
    position_side: Literal["LONG", "SHORT"]
    order_side: Literal["BUY", "SELL"]
    effect: Literal["OPEN", "CLOSE"]
    order_type: Literal["LIMIT"] = "LIMIT"
    time_in_force: Literal["GTC"] = "GTC"
    contracts: Positive
    limit_price: Positive
    reduce_only: bool
    position_mode: Literal["ONE_WAY"] = "ONE_WAY"
    margin_mode: Literal["ISOLATED"] = "ISOLATED"
    created_at: UTCDateTime
    expires_at: UTCDateTime
    strategy_proposal_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("intent expiry must follow creation")
        expected = "BUY" if self.position_side == "LONG" else "SELL"
        if self.effect == "CLOSE":
            expected = "SELL" if self.position_side == "LONG" else "BUY"
        if self.order_side != expected:
            raise ValueError("order side contradicts position side and effect")
        if self.reduce_only != (self.effect == "CLOSE"):
            raise ValueError("close orders must be reduce-only and opens must not")
        return self


class DerivativeMarketState(DomainModel):
    schema_version: Literal["derivative-market-state-1.0.0"] = "derivative-market-state-1.0.0"
    origin: Origin
    contract: DerivativeContract
    observed_at: UTCDateTime
    available_at: UTCDateTime
    mark_price: Positive
    index_price: Positive
    bid: Positive
    ask: Positive
    funding_rate: Signed | None = None
    next_funding_at: UTCDateTime | None = None
    initial_margin_rate: Fraction
    maintenance_margin_rate: Fraction
    quantity_step: Positive
    price_tick: Positive
    minimum_contracts: Positive
    maximum_contracts: Positive
    minimum_notional: Positive
    maximum_notional: Positive
    rules_reference: str = Field(min_length=1, max_length=512)
    provenance_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.available_at < self.observed_at:
            raise ValueError("market state available before observation")
        if self.ask < self.bid:
            raise ValueError("crossed derivative quote")
        if self.maintenance_margin_rate > self.initial_margin_rate:
            raise ValueError("maintenance margin exceeds initial margin")
        if self.minimum_contracts > self.maximum_contracts:
            raise ValueError("contract quantity bounds reversed")
        if self.minimum_notional > self.maximum_notional:
            raise ValueError("notional bounds reversed")
        if (self.funding_rate is None) != (self.next_funding_at is None):
            raise ValueError("funding rate and schedule must be supplied together")
        return self


class DerivativePositionState(DomainModel):
    contract_id: Identifier
    contract_hash: Hash
    side: Literal["LONG", "SHORT"]
    contracts: Positive
    entry_price: Positive
    mark_price: Positive
    notional: Positive
    initial_margin: Nonnegative
    maintenance_margin: Nonnegative
    unrealized_pnl: Signed
    liquidation_price: Positive | None = None
    margin_mode: Literal["ISOLATED"] = "ISOLATED"


class DerivativeAccountState(DomainModel):
    schema_version: Literal["derivative-account-state-1.0.0"] = "derivative-account-state-1.0.0"
    origin: Origin
    account_identity_hash: Hash
    observed_at: UTCDateTime
    completed_at: UTCDateTime
    collateral_currency: Currency
    equity: Positive
    available_collateral: Nonnegative
    wallet_balance: Positive
    positions: tuple[DerivativePositionState, ...] = Field(max_length=100)
    open_order_client_ids: tuple[Identifier, ...] = Field(max_length=100)
    position_mode: Literal["ONE_WAY"] = "ONE_WAY"
    margin_mode: Literal["ISOLATED"] = "ISOLATED"
    trading_permission: bool
    withdrawal_permission: Literal[False] = False
    provenance_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.completed_at < self.observed_at:
            raise ValueError("account completion precedes observation")
        if self.available_collateral > self.equity:
            raise ValueError("available collateral exceeds equity")
        identities = [(p.contract_id, p.side) for p in self.positions]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate derivative position identity")
        if len(set(self.open_order_client_ids)) != len(self.open_order_client_ids):
            raise ValueError("duplicate open order client id")
        return self


class DerivativeLocalState(DomainModel):
    schema_version: Literal["derivative-local-state-1.0.0"] = "derivative-local-state-1.0.0"
    account_identity_hash: Hash
    revision: int = Field(ge=0, strict=True)
    recorded_at: UTCDateTime
    account_state_hash: Hash
    independently_reconciled: bool


class DerivativeExecutionRequest(DomainModel):
    schema_version: Literal["derivative-execution-request-1.0.0"] = (
        "derivative-execution-request-1.0.0"
    )
    strategy: DerivativeStrategyEvidence
    intent: DerivativeOrderIntent
    leverage: LeverageAssessment
    market: DerivativeMarketState
    account: DerivativeAccountState
    local_state: DerivativeLocalState
    daily_start_equity: Positive
    daily_net_flows: Signed
    high_water_equity: Positive
    loss_context_at: UTCDateTime
    health_ready: bool
    independent_qualification: bool = False


class DerivativeRiskDecision(DomainModel):
    schema_version: Literal["derivative-risk-decision-1.0.0"] = "derivative-risk-decision-1.0.0"
    request_hash: Hash
    policy_hash: Hash
    assessed_at: UTCDateTime
    submission_permitted: bool
    reasons: tuple[Identifier, ...]
    order_notional: Nonnegative
    reserved_collateral: Nonnegative
    projected_gross_notional: Nonnegative
    projected_net_notional: Signed
    live_trading_enabled: Literal[False] = False
    derivative_execution_enabled: Literal[False] = False
    execution_authorized: Literal[False] = False


class DerivativeCommission(DomainModel):
    currency: Currency
    amount: Nonnegative


class DerivativeBrokerReport(DomainModel):
    schema_version: Literal["derivative-broker-report-1.0.0"] = "derivative-broker-report-1.0.0"
    client_id: Identifier
    contract_id: Identifier
    position_side: Literal["LONG", "SHORT"]
    order_side: Literal["BUY", "SELL"]
    effect: Literal["OPEN", "CLOSE"]
    reduce_only: bool
    order_id: str = Field(min_length=1, max_length=128)
    status: Literal["NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELLED", "EXPIRED"]
    original_contracts: Positive
    limit_price: Positive
    executed_contracts: Nonnegative
    cumulative_settlement_value: Nonnegative
    commissions: tuple[DerivativeCommission, ...]
    realized_pnl: Signed
    funding_paid: Signed
    at: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.executed_contracts > self.original_contracts:
            raise ValueError("derivative order overfill")
        if self.status in {"NEW", "REJECTED"} and self.executed_contracts != 0:
            raise ValueError("derivative report status contradicts quantity")
        if self.status == "PARTIALLY_FILLED" and not (
            0 < self.executed_contracts < self.original_contracts
        ):
            raise ValueError("invalid derivative partial fill")
        if self.status == "FILLED" and self.executed_contracts != self.original_contracts:
            raise ValueError("incomplete derivative filled report")
        if (self.executed_contracts == 0) != (self.cumulative_settlement_value == 0):
            raise ValueError("executed contracts and settlement value disagree")
        if len({fee.currency for fee in self.commissions}) != len(self.commissions):
            raise ValueError("duplicate cumulative derivative commission currency")
        return self
