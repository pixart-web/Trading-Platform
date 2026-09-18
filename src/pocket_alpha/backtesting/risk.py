"""Research-only risk gate; these policies never grant live authorization."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pocket_alpha.backtesting.models import Intent, PortfolioState, RunConfig

D = Decimal


@dataclass
class Book:
    cash: Decimal
    quantity: Decimal = D(0)
    cost_basis: Decimal = D(0)
    high_water: Decimal = D(0)
    daily_start_equity: Decimal = D(0)


@dataclass
class PendingOrder:
    intent: Intent
    risk_id: UUID
    created_at: datetime
    ready_at: datetime
    expires_at: datetime
    reference_price: Decimal
    reserved_unit_cash: Decimal
    remaining: Decimal
    acknowledged: bool = False


def snapshot(book: Book, orders: list[PendingOrder], mark: Decimal) -> PortfolioState:
    return PortfolioState(
        cash=book.cash,
        quantity=book.quantity,
        cost_basis=book.cost_basis,
        reserved_cash=sum(
            (o.remaining * o.reserved_unit_cash for o in orders if o.intent.action == "BUY"), D(0)
        ),
        reserved_quantity=sum((o.remaining for o in orders if o.intent.action == "SELL"), D(0)),
        equity=book.cash + book.quantity * mark,
    )


def reserve_unit(price: Decimal, config: RunConfig) -> Decimal:
    costs = config.costs
    adverse = (costs.spread_bps / 2 + costs.slippage_bps + costs.impact_bps_at_capacity) / 10000
    return (
        price
        * (1 + costs.maximum_price_deviation_fraction)
        * (1 + adverse)
        * (1 + costs.fee_bps / 10000)
    )


def halt(book: Book, mark: Decimal, config: RunConfig) -> str | None:
    equity = book.cash + book.quantity * mark
    if config.risk.kill_switch:
        return "KILL_SWITCH"
    if equity <= 0:
        return "BANKRUPTCY"
    if (
        book.high_water
        and (book.high_water - equity) / book.high_water >= config.risk.maximum_drawdown
    ):
        return "DRAWDOWN_LIMIT"
    if (
        book.daily_start_equity
        and (book.daily_start_equity - equity) / book.daily_start_equity
        >= config.risk.maximum_daily_loss
    ):
        return "DAILY_LOSS_LIMIT"
    return None


def authorize(
    intent: Intent,
    book: Book,
    orders: list[PendingOrder],
    mark: Decimal,
    quote_close: datetime,
    now: datetime,
    config: RunConfig,
) -> str | None:
    reason = halt(book, mark, config)
    if reason:
        return reason
    if (now - quote_close).total_seconds() > config.risk.maximum_data_age_seconds:
        return "STALE_DATA"
    if config.costs.spread_bps > config.risk.maximum_spread_bps:
        return "SPREAD_LIMIT"
    if len(orders) >= config.risk.maximum_pending_orders:
        return "PENDING_ORDER_LIMIT"
    quantity = intent.quantity
    if (
        quantity is None
        or quantity < config.costs.minimum_quantity
        or quantity % config.costs.quantity_step
    ):
        return "INVALID_QUANTITY"
    notional = quantity * reserve_unit(mark, config)
    if quantity * mark < config.costs.minimum_notional:
        return "MINIMUM_NOTIONAL"
    if notional > config.risk.maximum_order_notional:
        return "ORDER_NOTIONAL_LIMIT"
    state = snapshot(book, orders, mark)
    if intent.action == "BUY":
        if quantity * reserve_unit(mark, config) > state.cash - state.reserved_cash:
            return "INSUFFICIENT_UNRESERVED_CASH"
        pending_quantity = sum((o.remaining for o in orders if o.intent.action == "BUY"), D(0))
        worst_mark = mark * (1 + config.costs.maximum_price_deviation_fraction)
        if (
            book.quantity + pending_quantity + quantity
        ) * worst_mark > state.equity * config.risk.maximum_exposure_fraction:
            return "EXPOSURE_LIMIT"
    elif quantity > state.quantity - state.reserved_quantity:
        return "SHORT_NOT_SUPPORTED"
    return None
