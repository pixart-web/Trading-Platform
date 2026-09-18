import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import (
    Hash,
    Intent,
    OrderEvent,
    PortfolioState,
    RunConfig,
    SimulatedFill,
    digest,
)
from pocket_alpha.domain.market import Candle, Identifier, Market, UTCDateTime, Venue
from pocket_alpha.domain.models import Asset, AssetType, DomainModel, Timeframe
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.market_data.providers import ProviderMapping


def canonical_state(value: str) -> str:
    if not 2 <= len(value) <= 65536:
        raise ValueError("strategy checkpoint must be bounded canonical JSON")
    parsed = json.loads(value)
    if (
        not isinstance(parsed, dict)
        or json.dumps(parsed, sort_keys=True, separators=(",", ":"), allow_nan=False) != value
    ):
        raise ValueError("strategy checkpoint must be a canonical finite JSON object")
    return value


class PaperConfig(DomainModel):
    schema_version: Literal["paper-config-1.0.0"] = "paper-config-1.0.0"
    mode: Literal["PAPER"] = "PAPER"
    origin: Literal["REAL", "SYNTHETIC"]
    asset: Asset
    market: Market
    venue: Venue
    mapping: ProviderMapping
    timeframe: Timeframe
    start: UTCDateTime
    run: RunConfig
    maximum_events: int = Field(ge=1, le=10000, strict=True)

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.asset.asset_type != AssetType.CRYPTO or self.run.evaluation_split != "RESEARCH":
            raise ValueError("paper supports crypto spot LONG research only")
        if (
            self.market.asset_id != self.asset.asset_id
            or self.market.venue_id != self.venue.venue_id
            or self.mapping.market_id != self.market.market_id
        ):
            raise ValueError("paper market/asset/venue/mapping mismatch")
        if self.start.microsecond or int(self.start.timestamp()) % int(
            self.timeframe.duration.total_seconds()
        ):
            raise ValueError("paper start must align with native UTC candles")
        if self.origin == "SYNTHETIC" and self.mapping.source == "coinbase-exchange":
            raise ValueError("synthetic paper cannot impersonate the native public feed")
        if self.origin == "REAL" and (
            self.mapping.source != "coinbase-exchange"
            or self.venue.venue_id != "coinbase-exchange"
            or self.mapping.instrument_id != self.market.symbol
            or self.market.symbol != f"{self.asset.symbol}-{self.market.quote_currency}"
        ):
            raise ValueError("REAL paper requires verified native Coinbase base/quote/venue")
        return self


class PaperInput(DomainModel):
    mode: Literal["PAPER"] = "PAPER"
    event_id: UUID
    at: UTCDateTime
    kind: Literal["CANDLE", "HEARTBEAT", "DISCONNECT", "RECONCILE", "KILL", "CLOSE"]
    candle: Candle | None = None
    forecasts: tuple[Forecast, ...] = Field(default=(), max_length=128)
    reason: Identifier | None = None
    reconciliation_hash: Hash | None = None

    @model_validator(mode="after")
    def shaped(self) -> Self:
        if (self.kind == "CANDLE") != (self.candle is not None):
            raise ValueError("only CANDLE input contains a candle")
        if self.kind != "CANDLE" and self.forecasts:
            raise ValueError("forecasts belong to a candle decision only")
        if self.kind == "RECONCILE" and self.reconciliation_hash is None:
            raise ValueError("reconciliation requires the observed ledger state hash")
        return self


class PaperPending(DomainModel):
    client_id: Identifier
    risk_id: UUID
    action: Literal["BUY", "SELL"]
    created_at: UTCDateTime
    ready_at: UTCDateTime
    expires_at: UTCDateTime
    remaining: Decimal = Field(gt=0, allow_inf_nan=False)
    reserved_unit_cash: Decimal = Field(gt=0, allow_inf_nan=False)
    acknowledged: bool


class PaperState(DomainModel):
    schema_version: Literal["paper-state-1.0.0"] = "paper-state-1.0.0"
    mode: Literal["PAPER"] = "PAPER"
    account_id: UUID
    revision: int = Field(ge=0)
    origin: Literal["REAL", "SYNTHETIC"]
    market_id: Identifier
    asset_id: Identifier
    quote_currency: str
    at: UTCDateTime
    status: Literal["WAITING_DATA", "ACTIVE", "SUSPENDED", "HALTED", "CLOSED"]
    reason: Identifier | None
    next_open: UTCDateTime
    last_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    last_close: UTCDateTime | None
    initial_cash: Decimal = Field(gt=0, allow_inf_nan=False)
    portfolio: PortfolioState
    realized_pnl: Decimal = Field(allow_inf_nan=False)
    unrealized_pnl: Decimal | None = Field(allow_inf_nan=False)
    net_return: Decimal | None = Field(allow_inf_nan=False)
    total_fees: Decimal = Field(ge=0, allow_inf_nan=False)
    pending: tuple[PaperPending, ...]
    orders: tuple[OrderEvent, ...]
    fills: tuple[SimulatedFill, ...]
    strategy_checkpoint: str = Field(min_length=2, max_length=65536)
    accounting_hash: Hash
    state_hash: Hash
    live_ready: Literal[False] = False
    profitability_claim: Literal[False] = False

    @model_validator(mode="after")
    def intact(self) -> Self:
        canonical_state(self.strategy_checkpoint)
        if self.state_hash != digest(self.model_dump(mode="json", exclude={"state_hash"})):
            raise ValueError("paper state hash mismatch")
        accounting = dict(
            portfolio=self.portfolio.model_dump(mode="json"),
            pending=[p.model_dump(mode="json") for p in self.pending],
            fills=[f.model_dump(mode="json") for f in self.fills],
        )
        if self.accounting_hash != digest(accounting):
            raise ValueError("paper accounting hash mismatch")
        if (
            tuple(e.sequence for e in self.orders) != tuple(range(1, len(self.orders) + 1))
            or any(e.at > self.at for e in self.orders)
            or any(f.at > self.at for f in self.fills)
        ):
            raise ValueError("paper audit sequence invalid")
        if len({f.fill_id for f in self.fills}) != len(self.fills):
            raise ValueError("duplicate paper fill")
        if len({p.client_id for p in self.pending}) != len(self.pending):
            raise ValueError("duplicate pending paper order")
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            cash, quantity, basis = self.initial_cash, Decimal(0), Decimal(0)
            for fill in self.fills:
                approvals = [
                    o
                    for o in self.orders
                    if o.client_id == fill.client_id
                    and o.state == "APPROVED"
                    and o.risk_id == fill.risk_id
                    and o.at < fill.bar_open
                ]
                if len(approvals) != 1:
                    raise ValueError("paper fill lacks unique prior risk approval")
                if fill.side == "BUY":
                    debit = fill.quantity * fill.price + fill.fee
                    cash -= debit
                    quantity += fill.quantity
                    basis += debit
                    if fill.realized_pnl is not None:
                        raise ValueError("paper purchase cannot realize PnL")
                else:
                    if fill.quantity > quantity:
                        raise ValueError("paper sale exceeds inventory")
                    allocated = (
                        basis if fill.quantity == quantity else basis * fill.quantity / quantity
                    )
                    proceeds = fill.quantity * fill.price - fill.fee
                    if fill.realized_pnl != proceeds - allocated:
                        raise ValueError("paper sale PnL cannot be reconciled")
                    cash += proceeds
                    quantity -= fill.quantity
                    basis -= allocated
                if cash < 0 or quantity < 0 or basis < 0:
                    raise ValueError("paper ledger cannot become negative")
            if (cash, quantity, basis) != (
                self.portfolio.cash,
                self.portfolio.quantity,
                self.portfolio.cost_basis,
            ):
                raise ValueError("paper cash and inventory cannot be reconciled")
            if self.total_fees != sum((f.fee for f in self.fills), Decimal(0)):
                raise ValueError("paper fees do not reconcile")
            if self.realized_pnl != sum(
                (f.realized_pnl or Decimal(0) for f in self.fills), Decimal(0)
            ):
                raise ValueError("paper realized PnL does not reconcile")
            if self.last_price is not None:
                if (
                    self.portfolio.equity
                    != self.portfolio.cash + self.portfolio.quantity * self.last_price
                    or self.unrealized_pnl
                    != self.portfolio.quantity * self.last_price - self.portfolio.cost_basis
                ):
                    raise ValueError("paper marked PnL does not reconcile")
        return self


class PaperJournal(DomainModel):
    mode: Literal["PAPER"] = "PAPER"
    account_id: UUID
    revision: int = Field(ge=1)
    request_hash: Hash
    input: PaperInput
    intents: tuple[Intent, ...] = Field(max_length=10)
    strategy_checkpoint: str
    failure: Identifier | None = None
    previous_hash: Hash
    state_hash: Hash
    content_hash: Hash

    @model_validator(mode="after")
    def intact(self) -> Self:
        canonical_state(self.strategy_checkpoint)
        if self.content_hash != digest(self.model_dump(mode="json", exclude={"content_hash"})):
            raise ValueError("paper journal hash mismatch")
        return self


class PaperView(DomainModel):
    mode: Literal["PAPER"] = "PAPER"
    config: PaperConfig
    state: PaperState
    observed_at: UTCDateTime
    ready: bool
    readiness_reason: Identifier | None
    live_ready: Literal[False] = False


class PaperHeader(DomainModel):
    mode: Literal["PAPER"] = "PAPER"
    account_id: UUID
    config: PaperConfig
    created_at: UTCDateTime
    initial_checkpoint: str

    @model_validator(mode="after")
    def initial(self) -> Self:
        canonical_state(self.initial_checkpoint)
        if (
            not self.config.start
            <= self.created_at
            < self.config.start + self.config.timeframe.duration
        ):
            raise ValueError(
                "paper starts in the current native candle bucket; no historical sessions"
            )
        return self
