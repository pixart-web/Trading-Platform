from datetime import datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pocket_alpha.backtesting.execution import capacity, estimate, stepped
from pocket_alpha.backtesting.models import (
    EquityPoint,
    Intent,
    OrderEvent,
    RoundTrip,
    RunConfig,
    SimulatedFill,
)
from pocket_alpha.backtesting.risk import (
    Book,
    PendingOrder,
    authorize,
    halt,
    reserve_unit,
    snapshot,
)
from pocket_alpha.domain.market import Candle

D = Decimal


class StrategyError(Exception):
    pass


class SimulatedExecution:
    def __init__(self, run_id: UUID, config: RunConfig) -> None:
        self.run_id, self.config = run_id, config
        self.book = Book(
            cash=config.initial_cash,
            high_water=config.initial_cash,
            daily_start_equity=config.initial_cash,
        )
        self.pending: list[PendingOrder] = []
        self.events: list[OrderEvent] = []
        self.fills: list[SimulatedFill] = []
        self.points: list[EquityPoint] = []
        self.trades: list[RoundTrip] = []
        self.intentions: dict[str, Intent] = {}
        self.halted: str | None = None
        self.cohort_opened: datetime | None = None
        self.cohort_quantity = self.cohort_pnl = D(0)

    def event(
        self,
        client_id: str,
        at: datetime,
        state: str,
        reason: str,
        quantity: Decimal,
        risk_id: UUID | None = None,
    ) -> None:
        self.events.append(
            OrderEvent.model_validate(
                dict(
                    sequence=len(self.events) + 1,
                    client_id=client_id,
                    at=at,
                    state=state,
                    reason=reason,
                    remaining_quantity=quantity,
                    risk_id=risk_id,
                )
            )
        )
        if len(self.events) > 100000:
            raise ValueError("backtest event budget exceeded")

    def terminal(self, order: PendingOrder, at: datetime, state: str, reason: str) -> None:
        self.event(order.intent.client_id, at, state, reason, order.remaining, order.risk_id)
        self.pending.remove(order)

    def timers(self, now: datetime) -> None:
        timers = sorted(
            (instant, priority, o.intent.client_id, o)
            for o in self.pending
            for instant, priority in ((o.ready_at, 0), (o.expires_at, 1))
            if instant <= now and (priority == 1 or not o.acknowledged)
        )
        for instant, priority, _, order in timers:
            if order not in self.pending:
                continue
            if priority == 0:
                order.acknowledged = True
                self.event(
                    order.intent.client_id,
                    instant,
                    "ACKNOWLEDGED",
                    "SIMULATED_ACK",
                    order.remaining,
                    order.risk_id,
                )
            else:
                self.terminal(order, instant, "EXPIRED", "ORDER_LIFETIME")

    def observe_risk(self, mark: Decimal) -> None:
        self.book.high_water = max(self.book.high_water, self.book.cash + self.book.quantity * mark)
        self.halted = self.halted or halt(self.book, mark, self.config)

    def submit(self, intent: Intent, now: datetime, quote: Candle, feature_close: datetime) -> None:
        previous = self.intentions.get(intent.client_id)
        if previous is not None:
            if previous != intent:
                raise StrategyError("client intention identity reused with conflicting payload")
            return
        if len(self.intentions) >= self.config.maximum_intents:
            raise StrategyError("backtest intention budget exceeded")
        self.intentions[intent.client_id] = intent
        if intent.action == "CANCEL":
            target = next(
                (o for o in self.pending if o.intent.client_id == intent.cancel_client_id), None
            )
            if target:
                self.terminal(target, now, "CANCELLED", "STRATEGY_CANCEL")
            else:
                self.event(intent.client_id, now, "REJECTED", "CANCEL_TARGET_NOT_PENDING", D(0))
            return
        reason = self.halted or authorize(
            intent,
            self.book,
            self.pending,
            quote.close,
            min(quote.close_time, feature_close),
            now,
            self.config,
        )
        quantity = intent.quantity
        assert quantity is not None
        if reason:
            self.event(intent.client_id, now, "REJECTED", reason, quantity)
            return
        risk_id = uuid5(NAMESPACE_URL, f"{self.run_id}:risk:{intent.client_id}")
        costs = self.config.costs
        order = PendingOrder(
            intent=intent,
            risk_id=risk_id,
            created_at=now,
            ready_at=now + timedelta(seconds=costs.latency_seconds),
            expires_at=now + timedelta(seconds=costs.order_lifetime_seconds),
            reference_price=quote.close,
            reserved_unit_cash=reserve_unit(quote.close, self.config),
            remaining=quantity,
        )
        self.pending.append(order)
        self.event(intent.client_id, now, "APPROVED", "SIMULATION_RISK_APPROVED", quantity, risk_id)
        if costs.latency_seconds == 0:
            order.acknowledged = True
            self.event(intent.client_id, now, "ACKNOWLEDGED", "SIMULATED_ACK", quantity, risk_id)

    def execute(self, candle: Candle, mark: Decimal) -> None:
        available = capacity(candle, self.config.costs)
        for order in list(self.pending):
            if self.halted:
                self.terminal(order, candle.received_at, "CANCELLED", self.halted)
                continue
            if not order.acknowledged or candle.open_time <= order.ready_at:
                continue
            costs = self.config.costs
            if (
                candle.received_at - candle.close_time
            ).total_seconds() > self.config.risk.maximum_data_age_seconds:
                self.terminal(order, candle.received_at, "REJECTED", "STALE_EXECUTION_DATA")
                continue
            collar = costs.maximum_price_deviation_fraction
            if (
                not order.reference_price * (1 - collar)
                <= candle.close
                <= order.reference_price * (1 + collar)
            ):
                self.terminal(order, candle.received_at, "REJECTED", "PRICE_COLLAR")
                continue
            quantity = stepped(min(order.remaining, available), costs.quantity_step)
            if (
                quantity < costs.minimum_quantity
                or quantity * candle.close < costs.minimum_notional
            ):
                continue
            fill = estimate(
                order, candle, quantity, capacity(candle, costs) - available, costs, self.run_id
            )
            other_orders = [o for o in self.pending if o is not order]
            state = snapshot(self.book, other_orders, mark)
            if order.intent.action == "BUY":
                debit = quantity * fill.price + fill.fee
                if (
                    debit > state.cash - state.reserved_cash
                    or (
                        self.book.quantity
                        + order.remaining
                        + sum((o.remaining for o in other_orders if o.intent.action == "BUY"), D(0))
                    )
                    * mark
                    > (self.book.cash - debit + (self.book.quantity + quantity) * mark)
                    * self.config.risk.maximum_exposure_fraction
                ):
                    self.terminal(order, candle.received_at, "REJECTED", "FILL_RISK_OR_CASH_LIMIT")
                    continue
                if self.book.quantity == 0:
                    self.cohort_opened = fill.at
                self.cohort_quantity += quantity
                self.book.cash -= debit
                self.book.quantity += quantity
                self.book.cost_basis += debit
            else:
                if quantity > state.quantity - state.reserved_quantity:
                    self.terminal(order, candle.received_at, "REJECTED", "FILL_POSITION_LIMIT")
                    continue
                allocated = (
                    self.book.cost_basis
                    if quantity == self.book.quantity
                    else self.book.cost_basis * quantity / self.book.quantity
                )
                proceeds = quantity * fill.price - fill.fee
                pnl = proceeds - allocated
                fill = fill.model_copy(update={"realized_pnl": pnl})
                self.book.cash += proceeds
                self.book.quantity -= quantity
                self.book.cost_basis -= allocated
                self.cohort_pnl += pnl
                if self.book.quantity == 0:
                    assert self.cohort_opened is not None
                    self.trades.append(
                        RoundTrip(
                            opened_at=self.cohort_opened,
                            closed_at=fill.at,
                            quantity=self.cohort_quantity,
                            net_pnl=self.cohort_pnl,
                        )
                    )
                    self.cohort_opened = None
                    self.cohort_quantity = self.cohort_pnl = D(0)
            self.fills.append(fill)
            if len(self.fills) > 100000:
                raise ValueError("backtest fill budget exceeded")
            available -= quantity
            order.remaining -= quantity
            if order.remaining == 0:
                self.terminal(order, fill.at, "FILLED", "SIMULATED_COMPLETE")
            else:
                self.event(
                    order.intent.client_id,
                    fill.at,
                    "PARTIALLY_FILLED",
                    "LIQUIDITY_LIMIT",
                    order.remaining,
                    order.risk_id,
                )
            self.observe_risk(mark)

    def point(self, at: datetime, mark: Decimal) -> None:
        equity = self.book.cash + self.book.quantity * mark
        self.points.append(
            EquityPoint(
                at=at,
                cash=self.book.cash,
                quantity=self.book.quantity,
                mark=mark,
                equity=equity,
                high_water=self.book.high_water,
                drawdown=(self.book.high_water - equity) / self.book.high_water,
            )
        )
