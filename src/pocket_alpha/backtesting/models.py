import hashlib
import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Candle, Identifier, UTCDateTime
from pocket_alpha.domain.models import Currency, DomainModel
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.intelligence.technical.models import FeatureSnapshot, IndicatorSpec

D = Decimal
Amount = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]
Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
Fraction = Annotated[Decimal, Field(gt=0, le=1, max_digits=38, decimal_places=18)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def digest(value: object) -> str:
    if isinstance(value, DomainModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Parameter(DomainModel):
    name: Identifier
    value: str = Field(min_length=1, max_length=256)


class StrategyIdentity(DomainModel):
    strategy_version: Identifier
    model_version: Identifier
    parameters: tuple[Parameter, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({p.name for p in self.parameters}) != len(self.parameters):
            raise ValueError("strategy parameter names must be unique")
        return self


class CostPolicy(DomainModel):
    version: Identifier
    execution_model: Literal["next-complete-bar-close-1.0.0"] = "next-complete-bar-close-1.0.0"
    fee_bps: Positive
    spread_bps: Positive
    slippage_bps: Amount = Field(ge=0)
    impact_bps_at_capacity: Amount = Field(ge=0)
    maximum_price_deviation_fraction: Fraction = Field(le=Decimal("0.5"))
    participation: Fraction
    latency_seconds: int = Field(ge=0, le=86400, strict=True)
    order_lifetime_seconds: int = Field(ge=1, le=2592000, strict=True)
    quantity_step: Positive
    minimum_quantity: Positive
    minimum_notional: Positive

    @model_validator(mode="after")
    def bounded(self) -> Self:
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            if (
                self.fee_bps >= 10000
                or self.spread_bps / 2 + self.slippage_bps + self.impact_bps_at_capacity >= 10000
            ):
                raise ValueError("cost assumptions would permit nonpositive sell proceeds")
            if self.minimum_quantity % self.quantity_step != 0:
                raise ValueError("minimum quantity must align with quantity step")
            if self.order_lifetime_seconds <= self.latency_seconds:
                raise ValueError("order lifetime must exceed latency")
        return self


class RiskPolicy(DomainModel):
    version: Identifier
    maximum_order_notional: Positive
    maximum_exposure_fraction: Fraction
    maximum_drawdown: Fraction = Field(lt=1)
    maximum_daily_loss: Fraction = Field(lt=1)
    maximum_data_age_seconds: int = Field(ge=0, le=2592000, strict=True)
    maximum_pending_orders: int = Field(ge=1, le=100, strict=True)
    maximum_spread_bps: Positive
    kill_switch: bool = False


class RunConfig(DomainModel):
    schema_version: Literal["backtest-config-1.0.0"] = "backtest-config-1.0.0"
    strategy: StrategyIdentity
    costs: CostPolicy
    risk: RiskPolicy
    initial_cash: Positive
    code_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    code_tree_hash: Hash
    maximum_intents: int = Field(ge=1, le=10000, strict=True)
    maximum_history_bars: int = Field(ge=1, le=1000, strict=True)
    environment_hash: Hash
    environment_identity: str = Field(min_length=1, max_length=512)
    random_seed: int = Field(ge=0, le=2147483647, strict=True)
    feature_version: Literal["technical-1.0.0"] = "technical-1.0.0"
    feature_specs: tuple[IndicatorSpec, ...] = Field(min_length=1, max_length=32)
    availability_policy: Literal["RECORDED_RECEIPT"] = "RECORDED_RECEIPT"
    universe_scope: Literal["SINGLE_MARKET_NOT_UNIVERSE"] = "SINGLE_MARKET_NOT_UNIVERSE"
    selection_rationale: str = Field(min_length=1, max_length=512)
    selection_bias: Literal["NOT_ASSESSED_NO_UNIVERSE_CLAIM"] = "NOT_ASSESSED_NO_UNIVERSE_CLAIM"
    evaluation_split: Literal["RESEARCH", "TRAIN", "VALIDATION", "FINAL_HOLDOUT"]
    annualization_seconds: int = Field(ge=31536000, le=31622400, strict=True)
    minimum_ratio_returns: int = Field(ge=3, le=10000, strict=True)
    annual_risk_free_rate: Amount = Field(ge=0, lt=1)
    tail_fraction: Fraction = Field(le=Decimal("0.5"))

    @model_validator(mode="after")
    def specifications(self) -> Self:
        if len(set(self.feature_specs)) != len(self.feature_specs):
            raise ValueError("feature specifications must be unique")
        return self


class Intent(DomainModel):
    client_id: Identifier
    action: Literal["BUY", "SELL", "CANCEL"]
    quantity: Positive | None = None
    cancel_client_id: Identifier | None = None

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.action == "CANCEL":
            if self.quantity is not None or self.cancel_client_id is None:
                raise ValueError("cancel requires target and no quantity")
        elif self.quantity is None or self.cancel_client_id is not None:
            raise ValueError("buy/sell intention requires quantity and no cancel target")
        return self


class PortfolioState(DomainModel):
    cash: Decimal = Field(ge=0)
    quantity: Decimal = Field(ge=0)
    cost_basis: Decimal = Field(ge=0)
    reserved_cash: Decimal = Field(ge=0)
    reserved_quantity: Decimal = Field(ge=0)
    equity: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def conserved(self) -> Self:
        if self.reserved_cash > self.cash or self.reserved_quantity > self.quantity:
            raise ValueError("portfolio reservation exceeds available resources")
        return self


class StrategyView(DomainModel):
    as_of: UTCDateTime
    history: tuple[Candle, ...]
    technical: FeatureSnapshot
    forecasts: tuple[Forecast, ...]
    portfolio: PortfolioState

    @model_validator(mode="after")
    def causal(self) -> Self:
        if (
            self.technical.available_at > self.as_of
            or any(c.received_at > self.as_of or c.close_time > self.as_of for c in self.history)
            or any(
                f.generated_at > self.as_of or f.expires_at <= self.as_of for f in self.forecasts
            )
        ):
            raise ValueError("strategy view contains unavailable information")
        return self


class OrderEvent(DomainModel):
    sequence: int = Field(ge=1)
    client_id: Identifier
    at: UTCDateTime
    state: Literal[
        "APPROVED", "REJECTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED"
    ]
    reason: Identifier
    risk_id: UUID | None = None
    remaining_quantity: Decimal = Field(ge=0)


class SimulatedFill(DomainModel):
    fill_id: UUID
    client_id: Identifier
    risk_id: UUID
    at: UTCDateTime
    bar_open: UTCDateTime
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    impact_cost: Decimal = Field(ge=0)
    realized_pnl: Decimal | None = None
    simulation_only: Literal[True] = True


class EquityPoint(DomainModel):
    at: UTCDateTime
    cash: Decimal = Field(ge=0)
    quantity: Decimal = Field(ge=0)
    mark: Decimal = Field(gt=0)
    equity: Decimal = Field(ge=0)
    high_water: Decimal = Field(gt=0)
    drawdown: Decimal = Field(ge=0, le=1)


class RoundTrip(DomainModel):
    opened_at: UTCDateTime
    closed_at: UTCDateTime
    quantity: Decimal = Field(gt=0)
    net_pnl: Decimal


class Metric(DomainModel):
    name: Identifier
    value: Decimal | None
    reason: Identifier | None

    @model_validator(mode="after")
    def honest(self) -> Self:
        if (self.value is None) != (self.reason is not None):
            raise ValueError("metric availability requires matching reason")
        return self


class BacktestReport(DomainModel):
    schema_version: Literal["backtest-report-1.0.0"] = "backtest-report-1.0.0"
    run_id: UUID
    generated_at: UTCDateTime
    dataset_id: UUID
    market_id: Identifier
    asset_id: Identifier
    venue_id: Identifier
    quote_currency: Currency
    dataset_hash: Hash
    origin: Literal["REAL", "SYNTHETIC"]
    config: RunConfig
    forecast_inputs: tuple[Forecast, ...] = Field(max_length=10000)
    forecast_input_hash: Hash
    input_hash: Hash
    content_hash: Hash
    orders: tuple[OrderEvent, ...]
    fills: tuple[SimulatedFill, ...]
    equity: tuple[EquityPoint, ...] = Field(min_length=1, max_length=10000)
    round_trips: tuple[RoundTrip, ...]
    metrics: tuple[Metric, ...]
    final_portfolio: PortfolioState
    warnings: tuple[Identifier, ...]
    profitability_claim: Literal[False] = False
    live_ready: Literal[False] = False

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.content_hash != digest(
            self.model_dump(mode="json", exclude={"content_hash", "generated_at"})
        ):
            raise ValueError("backtest report content hash mismatch")
        if self.forecast_input_hash != digest(
            [f.model_dump(mode="json") for f in self.forecast_inputs]
        ):
            raise ValueError("forecast input hash does not match stored artifacts")
        expected = digest(
            dict(
                dataset_id=str(self.dataset_id),
                dataset_hash=self.dataset_hash,
                config=self.config.model_dump(mode="json"),
                forecast_inputs=[f.model_dump(mode="json") for f in self.forecast_inputs],
                forecast_input_hash=self.forecast_input_hash,
            )
        )
        if self.input_hash != expected or self.run_id != uuid5(
            NAMESPACE_URL, "pocket-alpha-backtest:" + expected
        ):
            raise ValueError("backtest input identity mismatch")
        if len({f.fill_id for f in self.fills}) != len(self.fills):
            raise ValueError("duplicate simulated fill")
        if tuple(p.at for p in self.equity) != tuple(sorted(set(p.at for p in self.equity))):
            raise ValueError("equity timeline must be strictly ordered")
        if tuple(e.sequence for e in self.orders) != tuple(range(1, len(self.orders) + 1)) or tuple(
            e.at for e in self.orders
        ) != tuple(sorted(e.at for e in self.orders)):
            raise ValueError("order audit sequence must be chronological and consecutive")
        if (
            any(f.at > self.generated_at for f in self.fills)
            or any(e.at > self.generated_at for e in self.orders)
            or self.equity[-1].at > self.generated_at
        ):
            raise ValueError("report contains future events")
        approvals = {e.client_id: e for e in self.orders if e.state == "APPROVED"}
        acknowledgements = {e.client_id: e for e in self.orders if e.state == "ACKNOWLEDGED"}
        for fill in self.fills:
            approval, ack = approvals.get(fill.client_id), acknowledgements.get(fill.client_id)
            if (
                approval is None
                or ack is None
                or approval.risk_id != fill.risk_id
                or ack.risk_id != fill.risk_id
                or not approval.at <= ack.at < fill.bar_open < fill.at
            ):
                raise ValueError("fill lacks causal risk approval and acknowledgement")
        if len({m.name for m in self.metrics}) != len(self.metrics):
            raise ValueError("metric names must be unique")
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            cash = self.config.initial_cash
            quantity = Decimal(0)
            for fill in self.fills:
                if fill.side == "BUY":
                    cash -= fill.quantity * fill.price + fill.fee
                    quantity += fill.quantity
                else:
                    cash += fill.quantity * fill.price - fill.fee
                    quantity -= fill.quantity
                if cash < 0 or quantity < 0:
                    raise ValueError("fill ledger violates cash or spot inventory conservation")
            if (
                cash != self.final_portfolio.cash
                or quantity != self.final_portfolio.quantity
                or self.final_portfolio.reserved_cash != 0
                or self.final_portfolio.reserved_quantity != 0
            ):
                raise ValueError("final portfolio does not reconcile with fill ledger")
            last = self.equity[-1]
            if (
                last.cash != cash
                or last.quantity != quantity
                or last.equity != cash + quantity * last.mark
                or self.final_portfolio.equity != last.equity
            ):
                raise ValueError("final marked equity does not reconcile")
        return self
