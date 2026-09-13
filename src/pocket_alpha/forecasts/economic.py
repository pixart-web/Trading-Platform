from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.forecasts.baseline import fingerprint, predict
from pocket_alpha.forecasts.models import ForecastDirection, ForecastStatus
from pocket_alpha.forecasts.research_models import (
    BaselineEvaluation,
    BaselineForecastModel,
    EconomicCostSpec,
    ForecastPartition,
    LabeledForecastExample,
    TemperatureCalibration,
    observed_direction,
)

D = Decimal
RESOLUTION = D("1e-30")


def _published(value: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return value.quantize(RESOLUTION)


class BaselineForecastEvaluator:
    """Temporal statistical and one-unit economic diagnostics after explicit costs."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def evaluate(
        self,
        model: BaselineForecastModel,
        calibration: TemperatureCalibration | None,
        examples: tuple[LabeledForecastExample, ...],
        *,
        costs: EconomicCostSpec,
        evaluated_at: datetime,
    ) -> BaselineEvaluation:
        if not 1 <= len(examples) <= 10000:
            raise ValueError("evaluation requires 1..10000 examples")
        partition = examples[0].partition
        if partition not in (ForecastPartition.VALIDATION, ForecastPartition.FINAL_HOLDOUT):
            raise ValueError("evaluation requires VALIDATION or FINAL_HOLDOUT examples")
        if any(item.partition != partition for item in examples):
            raise ValueError("evaluation cannot mix temporal partitions")
        evaluated_at = utc(evaluated_at)
        if evaluated_at > utc(self.clock.now()):
            raise ValueError("evaluation cannot be performed in the future")
        ordered = tuple(sorted(examples, key=lambda item: item.observation.generated_at))
        if len({item.observation.observation_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate evaluation observation")
        cutoff = (
            calibration.calibrated_through if calibration is not None else model.trained_through
        )
        previous_expiry = None
        for item in ordered:
            observation = item.observation
            if observation.input_start < cutoff:
                raise ValueError("evaluation input window overlaps fitted targets")
            if item.outcome_available_at > evaluated_at:
                raise ValueError("evaluation outcome is not yet available")
            if previous_expiry is not None and observation.generated_at < previous_expiry:
                raise ValueError("economic compounding requires non-overlapping forecast periods")
            previous_expiry = observation.expires_at

        brier = absolute_error = squared_error = D(0)
        gross_returns: list[Decimal] = []
        net_returns: list[Decimal] = []
        correct = active = 0
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            for item in ordered:
                forecast = predict(
                    uuid5(
                        NAMESPACE_URL,
                        f"{fingerprint(model.model_dump())}:{item.observation.observation_id}",
                    ),
                    item.observation,
                    model,
                    calibration=calibration,
                )
                if forecast.status != ForecastStatus.AVAILABLE:
                    raise ValueError("ambiguous baseline forecast cannot enter evaluation")
                actual = observed_direction(item.actual_return, model.spec.direction_threshold)
                brier += sum(
                    (
                        (probability.probability - int(probability.direction == actual)) ** 2
                        for probability in forecast.probabilities
                    ),
                    D(0),
                )
                assert forecast.expected_return is not None
                error = forecast.expected_return - item.actual_return
                absolute_error += abs(error)
                squared_error += error * error
                correct += forecast.direction == actual
                if forecast.direction == ForecastDirection.UP:
                    gross = item.actual_return
                elif forecast.direction == ForecastDirection.DOWN:
                    gross = -item.actual_return
                else:
                    gross = D(0)
                is_active = forecast.direction != ForecastDirection.RANGE
                active += is_active
                gross_returns.append(gross)
                net_returns.append(gross - costs.total_rate if is_active else D(0))

            count = len(ordered)
            gross_expectancy = sum(gross_returns, D(0)) / count
            net_expectancy = sum(net_returns, D(0)) / count
            mean = net_expectancy
            variance = sum(((value - mean) ** 2 for value in net_returns), D(0)) / count
            deviation = variance.sqrt()
            downside = (sum((min(value, D(0)) ** 2 for value in net_returns), D(0)) / count).sqrt()
            gains = sum((max(value, D(0)) for value in net_returns), D(0))
            losses = sum((-min(value, D(0)) for value in net_returns), D(0))

            equity = peak = D(1)
            maximum_drawdown = D(0)
            ruin = False
            for value in net_returns:
                if ruin or value <= -1:
                    equity = D(0)
                    ruin = True
                else:
                    equity *= 1 + value
                peak = max(peak, equity)
                maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak)
            compounded = equity - 1
            return BaselineEvaluation(
                model_hash=fingerprint(model.model_dump()),
                calibration_hash=(
                    fingerprint(calibration.model_dump()) if calibration is not None else None
                ),
                dataset_hash=fingerprint([item.model_dump() for item in ordered]),
                cost_spec=costs,
                partition=partition,
                evaluated_at=evaluated_at,
                sample_count=count,
                brier_score=_published(brier / count),
                return_mae=_published(absolute_error / count),
                return_rmse=_published((squared_error / count).sqrt()),
                directional_accuracy=_published(D(correct) / count),
                gross_expectancy=_published(gross_expectancy),
                net_expectancy=_published(net_expectancy),
                compounded_net_return=_published(compounded),
                maximum_drawdown=_published(maximum_drawdown),
                profit_factor=_published(gains / losses) if losses else None,
                sharpe=_published(mean / deviation) if deviation else None,
                sortino=_published(mean / downside) if downside else None,
                calmar=_published(compounded / maximum_drawdown) if maximum_drawdown else None,
                active_fraction=_published(D(active) / count),
                turnover=_published(D(2 * active) / count),
                total_cost=_published(costs.total_rate * active),
                ruin_observed=ruin,
                losing_periods=sum(value < 0 for value in net_returns),
            )
