from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.forecasts.baseline import (
    apply_temperature,
    fingerprint,
    raw_probabilities,
)
from pocket_alpha.forecasts.models import ForecastDirection, ProbabilityValue
from pocket_alpha.forecasts.research_models import (
    BaselineForecastModel,
    ForecastPartition,
    LabeledForecastExample,
    TemperatureCalibration,
    observed_direction,
)

D = Decimal


def _brier(
    probabilities: tuple[ProbabilityValue, ...],
    example: LabeledForecastExample,
    model: BaselineForecastModel,
) -> Decimal:
    actual = observed_direction(example.actual_return, model.spec.direction_threshold)
    return sum(
        ((item.probability - int(item.direction == actual)) ** 2 for item in probabilities), D(0)
    )


class TemperatureCalibrator:
    """Fit one temperature on a strictly later CALIBRATION partition."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def fit(
        self,
        model: BaselineForecastModel,
        examples: tuple[LabeledForecastExample, ...],
        *,
        fitted_at: datetime,
        calibration_version: str,
        candidates: tuple[Decimal, ...],
        minimum_samples: int = 30,
    ) -> TemperatureCalibration:
        if not 6 <= minimum_samples <= 10000 or not minimum_samples <= len(examples) <= 10000:
            raise ValueError("calibration requires its explicit minimum sample count")
        if any(item.partition != ForecastPartition.CALIBRATION for item in examples):
            raise ValueError("temperature fitting requires only CALIBRATION examples")
        if tuple(sorted(set(candidates))) != candidates or any(item <= 0 for item in candidates):
            raise ValueError("temperature candidates must be positive, unique and ordered")
        if D(1) not in candidates:
            raise ValueError("temperature candidates must include one as the no-change baseline")
        fitted_at = utc(fitted_at)
        if fitted_at > utc(self.clock.now()):
            raise ValueError("calibration fitted_at cannot be in the future")
        ordered = tuple(sorted(examples, key=lambda item: item.observation.generated_at))
        if len({item.observation.observation_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate calibration observation")
        for item in ordered:
            if item.observation.input_start < model.trained_through:
                raise ValueError("calibration input window overlaps training targets")
            if item.observation.generated_at < model.fitted_at:
                raise ValueError("forecast model was unavailable for calibration observation")
            if item.outcome_available_at > fitted_at:
                raise ValueError("calibration outcome is not yet available")
        directions = {
            observed_direction(item.actual_return, model.spec.direction_threshold)
            for item in ordered
        }
        if directions != set(ForecastDirection):
            raise ValueError("calibration requires every direction class")
        raw = tuple(raw_probabilities(item.observation, model) for item in ordered)
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            scores = {
                candidate: sum(
                    (
                        _brier(apply_temperature(probabilities, candidate), example, model)
                        for probabilities, example in zip(raw, ordered, strict=True)
                    ),
                    D(0),
                )
                / len(ordered)
                for candidate in candidates
            }
        selected = min(candidates, key=lambda item: (scores[item], abs(item - 1), item))
        return TemperatureCalibration(
            calibration_version=calibration_version,
            model_hash=fingerprint(model.model_dump()),
            temperature=selected,
            candidates=candidates,
            raw_brier=scores[D(1)],
            calibrated_brier=scores[selected],
            sample_count=len(ordered),
            calibrated_through=max(item.observation.expires_at for item in ordered),
            calibration_available_at=max(item.outcome_available_at for item in ordered),
            fitted_at=fitted_at,
            dataset_hash=fingerprint([item.model_dump() for item in ordered]),
        )
