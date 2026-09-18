"""Immutable read-only account observations and explicit local reconciliation state."""

import hashlib
from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.domain.market import UTCDateTime
from pocket_alpha.domain.models import DomainModel

Amount = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]
Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
Code = Annotated[str, Field(pattern=r"^[A-Z0-9]{1,24}$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def digest(model: DomainModel) -> str:
    return hashlib.sha256(model.model_dump_json().encode()).hexdigest()


def account_hash(uid: str) -> str:
    return hashlib.sha256(("binance-spot:" + uid).encode()).hexdigest()


class InstrumentBinding(DomainModel):
    symbol: Code
    market_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    base_asset: Code
    quote_asset: Code


class Instrument(InstrumentBinding):
    price_tick: Positive
    quantity_step: Positive
    quote_asset_precision: int = Field(ge=0, le=18, strict=True)
    metadata_hash: Hash
    status: Literal["TRADING"]


class Balance(DomainModel):
    asset: Code
    free: Amount
    locked: Amount

    @property
    def spot_position_quantity(self) -> Decimal:
        with localcontext() as context:
            context.prec = 80
            return self.free + self.locked


class OpenOrder(DomainModel):
    symbol: Code
    order_id: int = Field(ge=0, strict=True)
    client_order_id: str = Field(min_length=1, max_length=128)
    side: Literal["BUY", "SELL"]
    order_type: Literal[
        "LIMIT",
        "LIMIT_MAKER",
        "MARKET",
        "STOP_LOSS",
        "STOP_LOSS_LIMIT",
        "TAKE_PROFIT",
        "TAKE_PROFIT_LIMIT",
    ]
    status: Literal["NEW", "PARTIALLY_FILLED"]
    quantity: Positive
    executed_quantity: Amount
    price: Amount
    # Preserve all remaining venue fields for exact reconciliation, including stop/OCO parameters.
    venue_payload_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.executed_quantity >= self.quantity:
            raise ValueError("open order cannot be fully executed")
        if (self.status == "NEW" and self.executed_quantity != 0) or (
            self.status == "PARTIALLY_FILLED" and self.executed_quantity == 0
        ):
            raise ValueError("open order status and quantity disagree")
        if (
            self.order_type in {"LIMIT", "LIMIT_MAKER", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"}
            and self.price == 0
        ):
            raise ValueError("limit order requires a positive price")
        return self


class Trade(DomainModel):
    symbol: Code
    trade_id: int = Field(ge=0, strict=True)
    order_id: int = Field(ge=0, strict=True)
    side: Literal["BUY", "SELL"]
    quantity: Positive
    price: Positive
    quote_quantity: Positive
    commission: Amount
    commission_asset: Code
    occurred_at: UTCDateTime
    venue_payload_hash: Hash


class HistoryScope(DomainModel):
    symbol: Code
    from_id: int = Field(ge=0, strict=True)


class ObservationRequest(DomainModel):
    instruments: tuple[InstrumentBinding, ...] = Field(min_length=1, max_length=10)
    history_scope: tuple[HistoryScope, ...]


class AccountState(DomainModel):
    schema_version: Literal["broker-state-1.0.0"] = "broker-state-1.0.0"
    venue: Literal["BINANCE_SPOT"] = "BINANCE_SPOT"
    origin: Literal["REAL", "SYNTHETIC"]
    account_identity_hash: Hash
    instruments: tuple[Instrument, ...] = Field(min_length=1, max_length=10)
    balances: tuple[Balance, ...]
    open_orders: tuple[OpenOrder, ...]
    trades: tuple[Trade, ...]
    history_scope: tuple[HistoryScope, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        symbols = [x.symbol for x in self.instruments]
        if len(set(symbols)) != len(symbols):
            raise ValueError("duplicate instrument")
        if len({x.market_id for x in self.instruments}) != len(symbols):
            raise ValueError("duplicate market binding")
        if len({x.asset for x in self.balances}) != len(self.balances):
            raise ValueError("duplicate balance")
        if len({(x.symbol, x.order_id) for x in self.open_orders}) != len(self.open_orders):
            raise ValueError("duplicate open order")
        if len({(x.symbol, x.trade_id) for x in self.trades}) != len(self.trades):
            raise ValueError("duplicate trade")
        scopes = {x.symbol: x.from_id for x in self.history_scope}
        if len(scopes) != len(self.history_scope) or set(scopes) != set(symbols):
            raise ValueError("explicit history scope required for every instrument")
        if any(x.symbol not in symbols for x in self.open_orders):
            raise ValueError("open order outside instrument scope")
        if any(x.symbol not in scopes or x.trade_id < scopes[x.symbol] for x in self.trades):
            raise ValueError("trade outside history scope")
        return self

    def canonical(self) -> "AccountState":
        return self.model_copy(
            update={
                "instruments": tuple(sorted(self.instruments, key=lambda x: x.symbol)),
                "balances": tuple(sorted(self.balances, key=lambda x: x.asset)),
                "open_orders": tuple(
                    sorted(self.open_orders, key=lambda x: (x.symbol, x.order_id))
                ),
                "trades": tuple(sorted(self.trades, key=lambda x: (x.symbol, x.trade_id))),
                "history_scope": tuple(sorted(self.history_scope, key=lambda x: x.symbol)),
            }
        )


class LocalState(DomainModel):
    state: AccountState
    revision: int = Field(ge=1, strict=True)
    recorded_at: UTCDateTime
    # Caller attestation, not a cryptographic proof or automatic bootstrap from an observation.
    independently_verified: Literal[True]


class Observation(DomainModel):
    schema_version: Literal["broker-observation-1.0.0"] = "broker-observation-1.0.0"
    state: AccountState
    started_at: UTCDateTime
    completed_at: UTCDateTime
    permissions_hash: Hash
    execution_authorized: Literal[False] = False
    live_trading_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("observation clock moved backwards")
        if any(x.occurred_at > self.completed_at for x in self.state.trades):
            raise ValueError("future trade")
        return self


class Reconciliation(DomainModel):
    schema_version: Literal["broker-reconciliation-1.0.0"] = "broker-reconciliation-1.0.0"
    observation_hash: Hash
    local_state_hash: Hash | None
    assessed_at: UTCDateTime
    status: Literal["MATCHED", "BLOCKED"]
    reasons: tuple[str, ...]
    read_only_ready: bool
    execution_authorized: Literal[False] = False
    live_trading_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.read_only_ready != (self.status == "MATCHED" and not self.reasons):
            raise ValueError("inconsistent reconciliation readiness")
        if self.status == "MATCHED" and self.local_state_hash is None:
            raise ValueError("missing local state")
        return self


def reconcile(
    observation: Observation,
    local: LocalState | None,
    *,
    now: UTCDateTime,
    maximum_age_seconds: int = 30,
) -> Reconciliation:
    if not 1 <= maximum_age_seconds <= 300:
        raise ValueError("invalid observation age bound")
    reasons: list[str] = []
    if observation.state.origin != "REAL":
        reasons.append("NON_REAL_OBSERVATION")
    age = (now - observation.completed_at).total_seconds()
    if age < 0 or age > maximum_age_seconds:
        reasons.append("OBSERVATION_NOT_CURRENT")
    if (observation.completed_at - observation.started_at).total_seconds() > maximum_age_seconds:
        reasons.append("OBSERVATION_SPAN_EXCEEDED")
    if local is None:
        reasons.append("LOCAL_STATE_MISSING")
    else:
        if local.recorded_at > observation.started_at:
            reasons.append("LOCAL_STATE_NOT_CAUSAL")
        for name in (
            "origin",
            "account_identity_hash",
            "instruments",
            "balances",
            "open_orders",
            "trades",
            "history_scope",
        ):
            if getattr(observation.state.canonical(), name) != getattr(
                local.state.canonical(), name
            ):
                reasons.append(name.upper() + "_MISMATCH")
    return Reconciliation(
        observation_hash=digest(observation),
        local_state_hash=digest(local) if local else None,
        assessed_at=now,
        status="BLOCKED" if reasons else "MATCHED",
        reasons=tuple(reasons),
        read_only_ready=not reasons,
    )
