import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.portfolio.models import (
    PortfolioEntry,
    PortfolioEntryType,
    PortfolioPosition,
    PortfolioSnapshot,
    PortfolioSnapshotStatus,
    PositionStatus,
    accounting_value,
)
from pocket_alpha.portfolio.storage import ConflictingPortfolio, PortfolioRepository

D = Decimal


class PortfolioEntryRequest(DomainModel):
    entry_id: UUID
    entry_type: PortfolioEntryType
    expected_revision: int = Field(ge=1)
    occurred_at: UTCDateTime
    cash_amount: Decimal | None = None
    market_id: Identifier | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    fee: Decimal = Decimal(0)
    note: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def canonical(self) -> "PortfolioEntryRequest":
        if self.note is not None and (not self.note.strip() or self.note != self.note.strip()):
            raise ValueError("portfolio entry note must be non-empty and trimmed")
        cash = self.entry_type in (PortfolioEntryType.DEPOSIT, PortfolioEntryType.WITHDRAWAL)
        if cash:
            if self.cash_amount is None or self.cash_amount <= 0:
                raise ValueError("cash entry requires a positive cash amount")
            if (
                any(value is not None for value in (self.market_id, self.quantity, self.unit_price))
                or self.fee != 0
            ):
                raise ValueError("cash entry cannot contain trade fields or fees")
        elif (
            self.cash_amount is not None
            or self.market_id is None
            or self.quantity is None
            or self.quantity <= 0
            or self.unit_price is None
            or self.unit_price <= 0
            or self.fee < 0
        ):
            raise ValueError("trade entry requires positive quantity/price and non-negative fee")
        return self


@dataclass
class PositionState:
    quantity: Decimal = Decimal(0)
    average_cost: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)


@dataclass
class LedgerState:
    cash: Decimal
    net_contributions: Decimal
    total_fees: Decimal
    positions: dict[str, PositionState]


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class PortfolioService:
    def __init__(self, repository: PortfolioRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def record(self, portfolio_id: UUID, request: PortfolioEntryRequest) -> PortfolioEntry:
        portfolio = self.repository.get(portfolio_id)
        existing = self.repository.find_entry(request.entry_id)
        if existing is not None:
            if not self._matches(existing, portfolio_id, request):
                raise ConflictingPortfolio(
                    "portfolio entry identity conflicts with persisted content"
                )
            return existing
        recorded_at = utc(self.clock.now())
        if request.occurred_at > recorded_at:
            raise ValueError("portfolio entry cannot occur in the future")
        entries = self.repository.accounting_entries(portfolio_id)
        if entries and request.occurred_at < entries[-1].occurred_at:
            raise ValueError("portfolio entries must be recorded in occurrence order")
        state = self._account(entries)
        market = None
        cash_amount = request.cash_amount
        quantity = request.quantity
        unit_price = request.unit_price
        fee = accounting_value(request.fee)
        if request.entry_type in (PortfolioEntryType.DEPOSIT, PortfolioEntryType.WITHDRAWAL):
            assert cash_amount is not None
            cash_amount = accounting_value(cash_amount)
            gross = cash_amount
            cash_effect = (
                cash_amount if request.entry_type == PortfolioEntryType.DEPOSIT else -cash_amount
            )
        else:
            assert request.market_id is not None
            assert quantity is not None and unit_price is not None
            market = self.repository.market(request.market_id)
            if market.quote_currency != portfolio.base_currency:
                raise ValueError(
                    "market quote currency differs from portfolio base currency; FX is unavailable"
                )
            quantity = accounting_value(quantity)
            unit_price = accounting_value(unit_price)
            gross = accounting_value(quantity * unit_price)
            cash_effect = (
                -(gross + fee) if request.entry_type == PortfolioEntryType.BUY else gross - fee
            )
            if request.entry_type == PortfolioEntryType.SELL and fee > gross:
                raise ValueError("sell fee cannot exceed gross proceeds")
        entry = PortfolioEntry(
            entry_id=request.entry_id,
            portfolio_id=portfolio_id,
            sequence=len(entries) + 1,
            entry_type=request.entry_type,
            currency=portfolio.base_currency,
            cash_amount=cash_amount,
            market_id=market.market_id if market else None,
            asset_id=market.asset_id if market else None,
            quantity=quantity,
            unit_price=unit_price,
            fee=fee,
            gross_value=gross,
            cash_effect=accounting_value(cash_effect),
            occurred_at=request.occurred_at,
            recorded_at=recorded_at,
            note=request.note,
        )
        self._apply(state, entry)
        if len(state.positions) > 250:
            raise ValueError("portfolio market limit reached")
        self.repository.append(entry, request.expected_revision)
        return entry

    def snapshot(self, portfolio_id: UUID, as_of: datetime) -> PortfolioSnapshot:
        portfolio = self.repository.get(portfolio_id)
        cutoff = utc(as_of)
        generated_at = utc(self.clock.now())
        if cutoff > generated_at:
            raise ValueError("portfolio snapshot as-of cannot be in the future")
        if cutoff < portfolio.created_at:
            raise ValueError("portfolio snapshot cannot precede portfolio creation")
        entries = self.repository.accounting_entries(portfolio_id, cutoff)
        state = self._account(entries)
        market_ids = tuple(sorted(state.positions))
        markets = {market_id: self.repository.market(market_id) for market_id in market_ids}
        open_ids = tuple(
            market_id for market_id in market_ids if state.positions[market_id].quantity > 0
        )
        prices = self.repository.latest_prices(open_ids, cutoff, portfolio.valuation_timeframe)
        positions: list[PortfolioPosition] = []
        for market_id in market_ids:
            item = state.positions[market_id]
            cost_basis = accounting_value(item.quantity * item.average_cost)
            price = prices.get(market_id)
            if item.quantity == 0:
                position = PortfolioPosition(
                    market=markets[market_id],
                    status=PositionStatus.CLOSED,
                    quantity=Decimal(0),
                    average_cost=Decimal(0),
                    cost_basis=Decimal(0),
                    realized_pnl=accounting_value(item.realized_pnl),
                )
            elif price is None:
                position = PortfolioPosition(
                    market=markets[market_id],
                    status=PositionStatus.OPEN,
                    quantity=item.quantity,
                    average_cost=item.average_cost,
                    cost_basis=cost_basis,
                    realized_pnl=accounting_value(item.realized_pnl),
                )
            else:
                market_value = accounting_value(item.quantity * price.close)
                position = PortfolioPosition(
                    market=markets[market_id],
                    status=PositionStatus.OPEN,
                    quantity=item.quantity,
                    average_cost=item.average_cost,
                    cost_basis=cost_basis,
                    realized_pnl=accounting_value(item.realized_pnl),
                    last_price=price.close,
                    price_time=price.close_time,
                    price_available_at=price.received_at,
                    market_value=market_value,
                    unrealized_pnl=accounting_value(market_value - cost_basis),
                )
            positions.append(position)
        missing = any(
            item.status == PositionStatus.OPEN and item.market_value is None for item in positions
        )
        total_cost = accounting_value(sum((item.cost_basis for item in positions), D(0)))
        total_market_value: Decimal | None = None
        unrealized = None
        equity = None
        if not missing:
            total_market_value = accounting_value(
                sum((item.market_value or D(0) for item in positions), D(0))
            )
            unrealized = accounting_value(
                sum((item.unrealized_pnl or D(0) for item in positions), D(0))
            )
            equity = accounting_value(state.cash + total_market_value)
        snapshot_portfolio = portfolio.model_copy(
            update={
                "revision": len(entries) + 1,
                "updated_at": entries[-1].recorded_at if entries else portfolio.created_at,
            }
        )
        payload = {
            "portfolio": snapshot_portfolio.model_dump(),
            "entries": [entry.model_dump() for entry in entries],
            "as_of": cutoff,
            "prices": {
                market_id: {
                    "close": price.close,
                    "close_time": price.close_time,
                    "received_at": price.received_at,
                }
                for market_id, price in sorted(prices.items())
            },
        }
        return PortfolioSnapshot(
            portfolio_id=portfolio_id,
            portfolio_revision=snapshot_portfolio.revision,
            ledger_sequence=entries[-1].sequence if entries else 0,
            base_currency=portfolio.base_currency,
            valuation_timeframe=portfolio.valuation_timeframe,
            as_of=cutoff,
            generated_at=generated_at,
            status=(
                PortfolioSnapshotStatus.PARTIAL if missing else PortfolioSnapshotStatus.COMPLETE
            ),
            cash_balance=accounting_value(state.cash),
            net_contributions=accounting_value(state.net_contributions),
            total_fees=accounting_value(state.total_fees),
            realized_pnl=accounting_value(
                sum((item.realized_pnl for item in state.positions.values()), D(0))
            ),
            positions=tuple(positions),
            total_cost_basis=total_cost,
            total_market_value=total_market_value,
            unrealized_pnl=unrealized,
            equity=equity,
            input_hash=fingerprint(payload),
        )

    def _account(self, entries: tuple[PortfolioEntry, ...]) -> LedgerState:
        state = LedgerState(D(0), D(0), D(0), {})
        for entry in entries:
            self._apply(state, entry)
        return state

    def _apply(self, state: LedgerState, entry: PortfolioEntry) -> None:
        next_cash = accounting_value(state.cash + entry.cash_effect)
        if next_cash < 0:
            raise ValueError("portfolio cash cannot become negative")
        state.cash = next_cash
        if entry.entry_type == PortfolioEntryType.DEPOSIT:
            assert entry.cash_amount is not None
            state.net_contributions = accounting_value(state.net_contributions + entry.cash_amount)
            return
        if entry.entry_type == PortfolioEntryType.WITHDRAWAL:
            assert entry.cash_amount is not None
            state.net_contributions = accounting_value(state.net_contributions - entry.cash_amount)
            return
        assert entry.market_id is not None and entry.quantity is not None
        position = state.positions.setdefault(entry.market_id, PositionState())
        state.total_fees = accounting_value(state.total_fees + entry.fee)
        if entry.entry_type == PortfolioEntryType.BUY:
            new_quantity = accounting_value(position.quantity + entry.quantity)
            old_basis = accounting_value(position.quantity * position.average_cost)
            new_basis = accounting_value(old_basis + entry.gross_value + entry.fee)
            position.quantity = new_quantity
            position.average_cost = accounting_value(new_basis / new_quantity)
            return
        if entry.quantity > position.quantity:
            raise ValueError("sell quantity exceeds the open position")
        sold_basis = accounting_value(position.average_cost * entry.quantity)
        position.realized_pnl = accounting_value(
            position.realized_pnl + entry.gross_value - entry.fee - sold_basis
        )
        position.quantity = accounting_value(position.quantity - entry.quantity)
        if position.quantity == 0:
            position.average_cost = D(0)

    @staticmethod
    def _matches(entry: PortfolioEntry, portfolio_id: UUID, request: PortfolioEntryRequest) -> bool:
        return (
            entry.portfolio_id == portfolio_id
            and entry.entry_type == request.entry_type
            and entry.occurred_at == request.occurred_at
            and entry.cash_amount == request.cash_amount
            and entry.market_id == request.market_id
            and entry.quantity == request.quantity
            and entry.unit_price == request.unit_price
            and entry.fee == request.fee
            and entry.note == request.note
        )
