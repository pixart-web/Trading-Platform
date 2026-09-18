from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Intent
from pocket_alpha.broker_readonly.models import Hash, LocalState, Observation
from pocket_alpha.domain.market import UTCDateTime
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.portfolio.models import Amount, PortfolioSnapshot, PositiveAmount
from pocket_alpha.strategies.models import StrategyDefinition, StrategyProposal

Positive = PositiveAmount
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]


class SpotPolicy(DomainModel):
    version: str = Field(min_length=1, max_length=64)
    mode: Literal["DISABLED", "SYNTHETIC_QUALIFICATION"] = "DISABLED"
    global_enable: bool = False
    manual_enable: bool = False
    account_identity_hash: Hash
    symbols: tuple[str, ...] = Field(min_length=1, max_length=10)
    strategy_hashes: tuple[Hash, ...] = Field(min_length=1, max_length=20)
    quote_asset: str = Field(pattern=r"^[A-Z0-9]{1,24}$")
    capital_limit: Positive
    order_notional_limit: Positive
    total_exposure_limit: Positive
    position_notional_limit: Positive
    daily_loss_limit: Positive
    maximum_drawdown: Decimal = Field(gt=0, lt=1)
    maximum_positions: int = Field(ge=1, le=10, strict=True)
    maximum_orders_per_minute: int = Field(ge=1, le=60, strict=True)
    maximum_orders_per_day: int = Field(ge=1, le=1000, strict=True)
    maximum_data_age_seconds: int = Field(ge=1, le=300, strict=True)
    maximum_fee_fraction: Decimal = Field(ge=0, le=1, max_digits=38, decimal_places=18)
    maximum_spread_fraction: Decimal = Field(ge=0, le=1)
    maximum_price_deviation_fraction: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(set(self.symbols)) != len(self.symbols) or len(set(self.strategy_hashes)) != len(
            self.strategy_hashes
        ):
            raise ValueError("duplicate policy allowlist")
        if (
            self.order_notional_limit > self.capital_limit
            or self.position_notional_limit > self.total_exposure_limit
            or self.total_exposure_limit > self.capital_limit
        ):
            raise ValueError("inconsistent capital limits")
        return self


class SpotRequest(DomainModel):
    schema_version: Literal["spot-request-1.0.0"] = "spot-request-1.0.0"
    strategy: StrategyDefinition
    proposal: StrategyProposal
    intent: Intent
    symbol: str
    limit_price: Positive
    bid: Positive
    ask: Positive
    quote_at: UTCDateTime
    portfolio: PortfolioSnapshot
    observation: Observation
    local_state: LocalState
    daily_start_equity: Positive
    daily_net_flows: Amount
    high_water_equity: Positive
    loss_context_at: UTCDateTime
    health_ready: bool
    # Explicit caller attestation: no simulated economic outcome constitutes live qualification.
    independent_qualification: bool = False


class SpotDecision(DomainModel):
    schema_version: Literal["spot-risk-1.0.0"] = "spot-risk-1.0.0"
    request_hash: Hash
    policy_hash: Hash
    assessed_at: UTCDateTime
    submission_permitted: bool
    reasons: tuple[str, ...]
    reserved_notional: NonNegative
    live_trading_enabled: Literal[False] = False
    execution_authorized: Literal[False] = False


class Commission(DomainModel):
    asset: str = Field(pattern=r"^[A-Z0-9]{1,24}$")
    amount: NonNegative


class BrokerReport(DomainModel):
    client_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    order_id: str = Field(min_length=1, max_length=128)
    status: Literal["NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELLED", "EXPIRED"]
    original_quantity: Positive
    limit_price: Positive
    executed_quantity: NonNegative
    cumulative_quote: NonNegative
    commissions: tuple[Commission, ...]
    at: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.executed_quantity > self.original_quantity:
            raise ValueError("overfill")
        if self.status in {"NEW", "REJECTED"} and self.executed_quantity != 0:
            raise ValueError("status contradicts quantity")
        if (
            self.status == "PARTIALLY_FILLED"
            and not 0 < self.executed_quantity < self.original_quantity
        ):
            raise ValueError("invalid partial fill")
        if self.status == "FILLED" and self.executed_quantity != self.original_quantity:
            raise ValueError("incomplete filled order")
        if (self.executed_quantity == 0) != (self.cumulative_quote == 0):
            raise ValueError("executed quantity and quote disagree")
        if len({x.asset for x in self.commissions}) != len(self.commissions):
            raise ValueError("duplicate cumulative commission asset")
        return self
