from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.models import ForecastHorizon
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    Forecast,
    ForecastDirection,
    ForecastEvaluation,
    ForecastOutcome,
)
from pocket_alpha.forecasts.service import validate_outcome

D = Decimal


def evaluate_forecasts(
    pairs: tuple[tuple[Forecast, ForecastOutcome], ...], clock: Clock
) -> tuple[ForecastEvaluation, ...]:
    if not 1 <= len(pairs) <= 10000:
        raise ValueError("evaluation requires 1..10000 forecast outcomes")
    grouped: dict[tuple[str, ForecastHorizon], list[tuple[Forecast, ForecastOutcome]]] = (
        defaultdict(list)
    )
    for forecast, outcome in pairs:
        if forecast.forecast_id != outcome.forecast_id or forecast.status != "AVAILABLE":
            raise ValueError("evaluation requires matching available forecasts and outcomes")
        validate_outcome(forecast, outcome, clock)
        grouped[(forecast.model_version, forecast.horizon)].append((forecast, outcome))
    reports = []
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        for (model, horizon), values in sorted(grouped.items(), key=lambda item: item[0]):
            brier = errors = squared = D(0)
            correct = 0
            calibrated = True
            for forecast, outcome in values:
                assert forecast.range_threshold is not None
                actual = (
                    ForecastDirection.UP
                    if outcome.actual_return > forecast.range_threshold
                    else ForecastDirection.DOWN
                    if outcome.actual_return < -forecast.range_threshold
                    else ForecastDirection.RANGE
                )
                brier += sum(
                    (p.probability - int(p.direction == actual)) ** 2
                    for p in forecast.probabilities
                )
                assert forecast.expected_return is not None
                error = forecast.expected_return - outcome.actual_return
                errors += abs(error)
                squared += error * error
                correct += forecast.direction == actual
                calibrated &= forecast.probability_calibration == CalibrationStatus.CALIBRATED
            count = len(values)
            reports.append(
                ForecastEvaluation(
                    model_version=model,
                    horizon=horizon,
                    evaluated_at=utc(clock.now()),
                    sample_count=count,
                    brier_score=brier / count,
                    return_mae=errors / count,
                    return_rmse=(squared / count).sqrt(),
                    directional_accuracy=D(correct) / count,
                    calibration_status=(
                        CalibrationStatus.CALIBRATED
                        if calibrated
                        else CalibrationStatus.UNCALIBRATED
                    ),
                )
            )
    return tuple(reports)
