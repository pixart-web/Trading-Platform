from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, AssetType, Currency, DomainModel, Timeframe

AMOUNT_QUANTUM = Decimal("0.000000000000000001")
Amount = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]
PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
NonNegativeAmount = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def accounting_value(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_EVEN)


class PortfolioEntryType(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PortfolioSnapshotStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class Portfolio(DomainModel):
    schema_version: Literal["portfolio-1.0.0"] = "portfolio-1.0.0"
    portfolio_id: UUID
    name: str = Field(min_length=1, max_length=80)
    base_currency: Currency
    accounting_method: Literal["MOVING_AVERAGE_V1"] = "MOVING_AVERAGE_V1"
    valuation_timeframe: Timeframe = Timeframe.H1
    revision: int = Field(ge=1)
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("portfolio update cannot precede creation")
        if self.name != self.name.strip():
            raise ValueError("portfolio name must be trimmed")
        return self


class PortfolioEntry(DomainModel):
    schema_version: Literal["portfolio-entry-1.0.0"] = "portfolio-entry-1.0.0"
    entry_id: UUID
    portfolio_id: UUID
    sequence: int = Field(ge=1)
    entry_type: PortfolioEntryType
    currency: Currency
    cash_amount: PositiveAmount | None = None
    market_id: Identifier | None = None
    asset_id: AssetId | None = None
    quantity: PositiveAmount | None = None
    unit_price: PositiveAmount | None = None
    fee: NonNegativeAmount = Decimal(0)
    gross_value: PositiveAmount
    cash_effect: Amount
    occurred_at: UTCDateTime
    recorded_at: UTCDateTime
    note: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.occurred_at > self.recorded_at:
            raise ValueError("portfolio entry cannot occur after it is recorded")
        if self.note is not None and (not self.note.strip() or self.note != self.note.strip()):
            raise ValueError("portfolio entry note must be non-empty and trimmed")
        cash_entry = self.entry_type in (
            PortfolioEntryType.DEPOSIT,
            PortfolioEntryType.WITHDRAWAL,
        )
        if cash_entry:
            if any(
                value is not None
                for value in (self.market_id, self.asset_id, self.quantity, self.unit_price)
            ):
                raise ValueError("cash entry cannot reference a market or quantity")
            if self.cash_amount is None or self.fee != 0 or self.gross_value != self.cash_amount:
                raise ValueError("cash entry requires one fee-free cash amount")
            expected = (
                self.cash_amount
                if self.entry_type == PortfolioEntryType.DEPOSIT
                else -self.cash_amount
            )
        else:
            if self.cash_amount is not None or any(
                value is None
                for value in (self.market_id, self.asset_id, self.quantity, self.unit_price)
            ):
                raise ValueError("trade entry requires market, asset, quantity and unit price")
            assert self.quantity is not None and self.unit_price is not None
            if self.gross_value != accounting_value(self.quantity * self.unit_price):
                raise ValueError("trade gross value must match quantity and price")
            expected = (
                -(self.gross_value + self.fee)
                if self.entry_type == PortfolioEntryType.BUY
                else self.gross_value - self.fee
            )
        if self.cash_effect != accounting_value(expected):
            raise ValueError("portfolio cash effect is inconsistent")
        return self


class PortfolioMarket(DomainModel):
    market_id: Identifier
    asset_id: AssetId
    symbol: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    asset_type: AssetType
    venue_id: Identifier
    quote_currency: Currency


class PortfolioPosition(DomainModel):
    market: PortfolioMarket
    status: PositionStatus
    quantity: NonNegativeAmount
    average_cost: NonNegativeAmount
    cost_basis: NonNegativeAmount
    realized_pnl: Amount
    last_price: PositiveAmount | None = None
    price_time: UTCDateTime | None = None
    price_available_at: UTCDateTime | None = None
    market_value: NonNegativeAmount | None = None
    unrealized_pnl: Amount | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.cost_basis != accounting_value(self.quantity * self.average_cost):
            raise ValueError("position cost basis is inconsistent")
        valued = (
            self.last_price,
            self.price_time,
            self.price_available_at,
            self.market_value,
            self.unrealized_pnl,
        )
        if self.status == PositionStatus.CLOSED:
            if (
                self.quantity != 0
                or self.cost_basis != 0
                or self.average_cost != 0
                or any(item is not None for item in valued)
            ):
                raise ValueError("closed position cannot expose current valuation")
        else:
            if self.quantity <= 0:
                raise ValueError("open position requires positive quantity")
            if any(item is None for item in valued) and any(item is not None for item in valued):
                raise ValueError("position valuation must be complete or explicitly unavailable")
            if (
                self.price_available_at is not None
                and self.price_time is not None
                and self.price_available_at < self.price_time
            ):
                raise ValueError("price cannot be available before its market time")
        return self


class PortfolioSnapshot(DomainModel):
    schema_version: Literal["portfolio-snapshot-1.0.0"] = "portfolio-snapshot-1.0.0"
    portfolio_id: UUID
    portfolio_revision: int = Field(ge=1)
    ledger_sequence: int = Field(ge=0)
    base_currency: Currency
    accounting_method: Literal["MOVING_AVERAGE_V1"] = "MOVING_AVERAGE_V1"
    valuation_timeframe: Timeframe = Timeframe.H1
    as_of: UTCDateTime
    generated_at: UTCDateTime
    status: PortfolioSnapshotStatus
    cash_balance: NonNegativeAmount
    net_contributions: Amount
    total_fees: NonNegativeAmount
    realized_pnl: Amount
    positions: tuple[PortfolioPosition, ...] = Field(max_length=250)
    total_cost_basis: NonNegativeAmount
    total_market_value: NonNegativeAmount | None = None
    unrealized_pnl: Amount | None = None
    equity: NonNegativeAmount | None = None
    input_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("portfolio snapshot cannot precede its as-of time")
        if tuple(sorted(self.positions, key=lambda item: item.market.market_id)) != self.positions:
            raise ValueError("portfolio positions must use canonical order")
        if len({item.market.market_id for item in self.positions}) != len(self.positions):
            raise ValueError("portfolio positions must be unique")
        open_positions = tuple(
            item for item in self.positions if item.status == PositionStatus.OPEN
        )
        missing = any(item.market_value is None for item in open_positions)
        expected_status = (
            PortfolioSnapshotStatus.PARTIAL if missing else PortfolioSnapshotStatus.COMPLETE
        )
        if self.status != expected_status:
            raise ValueError("portfolio status must match valuation coverage")
        totals = (self.total_market_value, self.unrealized_pnl, self.equity)
        if missing:
            if any(item is not None for item in totals):
                raise ValueError("partial portfolio cannot expose invented totals")
        elif any(item is None for item in totals):
            raise ValueError("complete portfolio requires valuation totals")
        if self.total_cost_basis != accounting_value(
            sum((item.cost_basis for item in self.positions), Decimal(0))
        ) or self.realized_pnl != accounting_value(
            sum((item.realized_pnl for item in self.positions), Decimal(0))
        ):
            raise ValueError("portfolio accounting totals are inconsistent")
        if not missing:
            assert self.total_market_value is not None
            assert self.unrealized_pnl is not None
            assert self.equity is not None
            expected_market_value = accounting_value(
                sum((item.market_value or Decimal(0) for item in self.positions), Decimal(0))
            )
            expected_unrealized = accounting_value(
                sum((item.unrealized_pnl or Decimal(0) for item in self.positions), Decimal(0))
            )
            if (
                self.total_market_value != expected_market_value
                or self.unrealized_pnl != expected_unrealized
                or self.equity != accounting_value(self.cash_balance + self.total_market_value)
            ):
                raise ValueError("portfolio valuation totals are inconsistent")
        return self
