from bisect import bisect_right
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.backtesting.inputs import (
    ResearchStrategy,
    current_code_hash,
    current_environment_hash,
    prepare,
)
from pocket_alpha.backtesting.metrics import calculate_metrics
from pocket_alpha.backtesting.models import (
    BacktestReport,
    Intent,
    RunConfig,
    StrategyView,
    digest,
)
from pocket_alpha.backtesting.risk import (
    snapshot,
)
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.market import Candle
from pocket_alpha.forecasts.models import Forecast, ForecastStatus
from pocket_alpha.market_data.datasets import MarketDataset
from pocket_alpha.simulation.engine import SimulatedExecution
from pocket_alpha.simulation.engine import StrategyError as StrategyError

D = Decimal


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
            simulation = SimulatedExecution(run_id, config)
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
