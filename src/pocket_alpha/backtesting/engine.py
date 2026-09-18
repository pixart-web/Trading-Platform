from bisect import bisect_right
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import NAMESPACE_URL, UUID, uuid5

from pocket_alpha.backtesting.execution import capacity, estimate, stepped
from pocket_alpha.backtesting.inputs import (
    ResearchStrategy,
    current_code_hash,
    current_environment_hash,
    prepare,
)
from pocket_alpha.backtesting.metrics import calculate_metrics
from pocket_alpha.backtesting.models import (
    BacktestReport,
    EquityPoint,
    Intent,
    OrderEvent,
    RoundTrip,
    RunConfig,
    SimulatedFill,
    StrategyView,
    digest,
)
from pocket_alpha.backtesting.risk import (
    Book,
    PendingOrder,
    authorize,
    halt,
    reserve_unit,
    snapshot,
)
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.market import Candle
from pocket_alpha.forecasts.models import Forecast, ForecastStatus
from pocket_alpha.market_data.datasets import MarketDataset

D = Decimal


class StrategyError(Exception):
    pass


class Backtester:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def run(
        self,
        dataset: MarketDataset,
        config: RunConfig,
        strategy: ResearchStrategy,
        forecasts: tuple[Forecast, ...] = (),
    ) -> BacktestReport:
        return self._run(dataset, config, strategy, forecasts, final_authorized=False)

    def _run(
        self,
        dataset: MarketDataset,
        config: RunConfig,
        strategy: ResearchStrategy,
        forecasts: tuple[Forecast, ...],
        *,
        final_authorized: bool,
    ) -> BacktestReport:
        # Internal research-only entry: persisted holdout consumption precedes authorization.
        dataset = MarketDataset.model_validate_json(dataset.model_dump_json())
        config = RunConfig.model_validate_json(config.model_dump_json())
        if config.evaluation_split == "FINAL_HOLDOUT" and not final_authorized:
            raise ValueError(
                "final holdout consumption requires protected research authorization; "
                "use the protected research factory"
            )
        if strategy.identity != config.strategy:
            raise ValueError("strategy implementation identity does not match run configuration")
        if config.code_tree_hash != current_code_hash():
            raise ValueError("run code identity does not match current Python source tree")
        if config.environment_hash != current_environment_hash():
            raise ValueError("run environment identity does not match installed runtime")
        now = utc(self.clock.now())
        if now < dataset.inputs.captured_at:
            raise ValueError("cannot run a dataset captured in the future")
        prepared = prepare(dataset, config, forecasts)
        forecast_hash = digest([f.model_dump(mode="json") for f in prepared.forecasts])
        input_hash = digest(
            dict(
                dataset_id=str(dataset.dataset_id),
                dataset_hash=dataset.content_hash,
                config=config.model_dump(mode="json"),
                forecast_inputs=[f.model_dump(mode="json") for f in prepared.forecasts],
                forecast_input_hash=forecast_hash,
            )
        )
        run_id = uuid5(NAMESPACE_URL, "pocket-alpha-backtest:" + input_hash)
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            simulation = _Simulation(run_id, config)
            prefix_times = tuple(f.available_at for f in prepared.technical)
            latest: Candle | None = None
            previous_day = None
            for instant, bars in prepared.arrivals:
                simulation.timers(instant)
                latest = max((*bars, latest) if latest else bars, key=lambda c: c.close_time)
                if previous_day != instant.date():
                    simulation.book.daily_start_equity = (
                        simulation.points[-1].equity if simulation.points else config.initial_cash
                    )
                    previous_day = instant.date()
                simulation.observe_risk(latest.close)
                for candle in bars:
                    simulation.execute(candle, latest.close)
                simulation.observe_risk(latest.close)
                count = bisect_right(prefix_times, instant)
                if count:
                    technical = prepared.technical[count - 1]
                    view = StrategyView(
                        as_of=instant,
                        history=dataset.inputs.candles[
                            max(0, count - config.maximum_history_bars) : count
                        ],
                        technical=technical,
                        forecasts=tuple(
                            f
                            for f in prepared.forecasts
                            if f.status == ForecastStatus.AVAILABLE
                            and f.generated_at <= instant < f.expires_at
                        ),
                        portfolio=snapshot(simulation.book, simulation.pending, latest.close),
                    )
                    try:
                        # Strategy-local numeric changes must not mutate accounting precision.
                        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                            if strategy.identity != config.strategy:
                                raise StrategyError("strategy identity changed during simulation")
                            intents = strategy.on_event(view)
                    except Exception as error:
                        raise StrategyError(
                            "research strategy failed; no completed report"
                        ) from error
                    if not isinstance(intents, tuple) or len(intents) > 10:
                        raise StrategyError(
                            "strategy must emit a bounded tuple of at most 10 intentions"
                        )
                    for intent in intents:
                        simulation.submit(
                            Intent.model_validate_json(intent.model_dump_json()),
                            instant,
                            latest,
                            technical.bar_close,
                        )
                simulation.point(instant, latest.close)
            assert latest is not None
            final_at = simulation.points[-1].at
            for order in list(simulation.pending):
                simulation.terminal(order, final_at, "CANCELLED", "END_OF_DATA")
            final = snapshot(simulation.book, simulation.pending, latest.close)
            warnings = [
                "SINGLE_MARKET_SELECTION_BIAS_NOT_ASSESSED",
                "MODELED_BAR_CLOSE_EXECUTION",
                "CLOSE_MARKS_DO_NOT_ESTIMATE_INTRABAR_DRAWDOWN",
                "SPOT_LONG_NO_BORROW_FUNDING",
                "NO_PROFITABILITY_CLAIM",
            ]
            if dataset.inputs.origin == "SYNTHETIC":
                warnings.append("SYNTHETIC_TEST_ECONOMICS_ONLY")
            if not any(c.open_time > prepared.arrivals[0][0] for c in dataset.inputs.candles):
                warnings.append("INSUFFICIENT_CAUSAL_EXECUTION_WINDOW")
            if simulation.halted:
                warnings.append("RISK_HALT_NO_FORCED_FILL")
            metrics = calculate_metrics(
                tuple(simulation.points), tuple(simulation.fills), tuple(simulation.trades), config
            )
            finished_at = utc(self.clock.now())
            if finished_at < now:
                raise ValueError("clock moved backwards during simulation")
            draft = BacktestReport.model_construct(
                run_id=run_id,
                generated_at=finished_at,
                dataset_id=dataset.dataset_id,
                market_id=dataset.inputs.market.market_id,
                asset_id=dataset.inputs.asset.asset_id,
                venue_id=dataset.inputs.venue.venue_id,
                quote_currency=dataset.inputs.market.quote_currency,
                dataset_hash=dataset.content_hash,
                origin=dataset.inputs.origin,
                config=config,
                forecast_inputs=prepared.forecasts,
                forecast_input_hash=forecast_hash,
                input_hash=input_hash,
                content_hash="0" * 64,
                orders=tuple(simulation.events),
                fills=tuple(simulation.fills),
                equity=tuple(simulation.points),
                round_trips=tuple(simulation.trades),
                metrics=metrics,
                final_portfolio=final,
                warnings=tuple(warnings),
            )
            return BacktestReport.model_validate(
                draft.model_dump()
                | {
                    "content_hash": digest(
                        draft.model_dump(mode="json", exclude={"content_hash", "generated_at"})
                    )
                }
            )


class _Simulation:
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
