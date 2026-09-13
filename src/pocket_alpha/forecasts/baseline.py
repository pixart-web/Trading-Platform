import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import UUID

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    Forecast,
    ForecastDirection,
    ForecastStatus,
    ModelStage,
    ProbabilityValue,
)
from pocket_alpha.forecasts.research_models import (
    BaselineForecastModel,
    BaselineSpec,
    ForecastObservation,
    ForecastPartition,
    GaussianDirectionClass,
    LabeledForecastExample,
    TemperatureCalibration,
    observed_direction,
)
from pocket_alpha.intelligence.provenance import canonical

D = Decimal
RESOLUTION = D("1e-30")


def fingerprint(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(canonical(payload), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _published(value: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return value.quantize(RESOLUTION)


def _quantile(values: list[Decimal], quantile: Decimal) -> Decimal:
    ordered = sorted(values)
    index = int((len(ordered) - 1) * quantile)
    return ordered[index]


class BaselineForecastTrainer:
    """Fit an explicit Gaussian direction baseline from TRAIN outcomes only."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def fit(
        self,
        examples: tuple[LabeledForecastExample, ...],
        *,
        fitted_at: datetime,
        model_version: str,
        code_version: str,
        environment_version: str,
        spec: BaselineSpec,
    ) -> BaselineForecastModel:
        minimum = spec.minimum_per_class * len(ForecastDirection)
        if not minimum <= len(examples) <= 10000:
            raise ValueError("training size must satisfy every class minimum and the 10000 bound")
        if any(item.partition != ForecastPartition.TRAIN for item in examples):
            raise ValueError("only TRAIN examples can fit a forecast model")
        fitted_at = utc(fitted_at)
        if fitted_at > utc(self.clock.now()):
            raise ValueError("forecast model fitted_at cannot be in the future")
        ordered = tuple(sorted(examples, key=lambda item: item.observation.generated_at))
        first = ordered[0].observation
        identity = (
            first.market_id,
            first.asset_id,
            first.candle_timeframe,
            first.horizon,
            first.feature_version,
        )
        if len({item.observation.observation_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate forecast training observation")
        for item in ordered:
            observation = item.observation
            if (
                observation.market_id,
                observation.asset_id,
                observation.candle_timeframe,
                observation.horizon,
                observation.feature_version,
            ) != identity:
                raise ValueError(
                    "training requires one market, horizon, timeframe and feature version"
                )
            if len(observation.feature_values) != len(spec.feature_names):
                raise ValueError("training vector does not match the feature specification")
            if item.outcome_available_at > fitted_at:
                raise ValueError("training outcome is not yet available")
        classes = []
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            for direction in ForecastDirection:
                selected = [
                    item
                    for item in ordered
                    if observed_direction(item.actual_return, spec.direction_threshold) == direction
                ]
                if len(selected) < spec.minimum_per_class:
                    raise ValueError("insufficient forecast examples per direction class")
                width = len(spec.feature_names)
                means = tuple(
                    sum((item.observation.feature_values[j] for item in selected), D(0))
                    / len(selected)
                    for j in range(width)
                )
                variances = tuple(
                    max(
                        spec.variance_floor,
                        sum(
                            (
                                (item.observation.feature_values[j] - means[j]) ** 2
                                for item in selected
                            ),
                            D(0),
                        )
                        / len(selected),
                    )
                    for j in range(width)
                )
                returns = [item.actual_return for item in selected]
                return_mean = sum(returns, D(0)) / len(returns)
                lower = min(_quantile(returns, spec.lower_quantile), return_mean)
                upper = max(_quantile(returns, spec.upper_quantile), return_mean)
                classes.append(
                    GaussianDirectionClass(
                        direction=direction,
                        count=len(selected),
                        feature_mean=tuple(_published(value) for value in means),
                        feature_variance=tuple(_published(value) for value in variances),
                        return_mean=_published(return_mean),
                        absolute_return_mean=_published(
                            sum((abs(value) for value in returns), D(0)) / len(returns)
                        ),
                        return_lower=lower,
                        return_upper=upper,
                    )
                )
        return BaselineForecastModel(
            model_version=model_version,
            code_version=code_version,
            environment_version=environment_version,
            spec=spec,
            market_id=first.market_id,
            asset_id=first.asset_id,
            candle_timeframe=first.candle_timeframe,
            horizon=first.horizon,
            feature_version=first.feature_version,
            trained_through=max(item.observation.expires_at for item in ordered),
            training_available_at=max(item.outcome_available_at for item in ordered),
            fitted_at=fitted_at,
            dataset_hash=fingerprint([item.model_dump() for item in ordered]),
            classes=tuple(classes),
        )


def raw_probabilities(
    observation: ForecastObservation, model: BaselineForecastModel
) -> tuple[ProbabilityValue, ...]:
    if (
        observation.market_id,
        observation.asset_id,
        observation.candle_timeframe,
        observation.horizon,
        observation.feature_version,
    ) != (
        model.market_id,
        model.asset_id,
        model.candle_timeframe,
        model.horizon,
        model.feature_version,
    ):
        raise ValueError("forecast model is incompatible with observation identity")
    if len(observation.feature_values) != len(model.spec.feature_names):
        raise ValueError("observation vector does not match the model feature specification")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        total_count = sum(item.count for item in model.classes)
        scores = [
            (D(item.count) / total_count).ln()
            - sum(
                (
                    variance.ln() + (value - mean) ** 2 / variance
                    for value, mean, variance in zip(
                        observation.feature_values,
                        item.feature_mean,
                        item.feature_variance,
                        strict=True,
                    )
                ),
                D(0),
            )
            / 2
            for item in model.classes
        ]
        maximum = max(scores)
        weights = [
            (score - maximum).exp() if score - maximum >= -1000 else D(0) for score in scores
        ]
        total = sum(weights, D(0))
        values = [(weight / total).quantize(RESOLUTION) for weight in weights]
        values[scores.index(maximum)] += 1 - sum(values, D(0))
        return tuple(
            ProbabilityValue(direction=item.direction, probability=value)
            for item, value in zip(model.classes, values, strict=True)
        )


def apply_temperature(
    probabilities: tuple[ProbabilityValue, ...], temperature: Decimal
) -> tuple[ProbabilityValue, ...]:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        weights = [
            D(0) if item.probability == 0 else (item.probability.ln() / temperature).exp()
            for item in probabilities
        ]
        total = sum(weights, D(0))
        values = [(weight / total).quantize(RESOLUTION) for weight in weights]
        winner = max(range(len(values)), key=values.__getitem__)
        values[winner] += 1 - sum(values, D(0))
        return tuple(
            ProbabilityValue(direction=item.direction, probability=value)
            for item, value in zip(probabilities, values, strict=True)
        )


def predict(
    forecast_id: UUID,
    observation: ForecastObservation,
    model: BaselineForecastModel,
    *,
    calibration: TemperatureCalibration | None = None,
) -> Forecast:
    if observation.generated_at < model.fitted_at:
        raise ValueError("forecast model was not available at observation generation")
    probabilities = raw_probabilities(observation, model)
    calibration_status = CalibrationStatus.UNCALIBRATED
    if calibration is not None:
        if calibration.model_hash != fingerprint(model.model_dump()):
            raise ValueError("calibration does not belong to forecast model")
        if observation.generated_at < calibration.fitted_at:
            raise ValueError("calibration was not available at observation generation")
        probabilities = apply_temperature(probabilities, calibration.temperature)
        calibration_status = CalibrationStatus.CALIBRATED
    winners = tuple(
        item
        for item in probabilities
        if item.probability == max(p.probability for p in probabilities)
    )
    common = {
        "forecast_id": forecast_id,
        "market_id": observation.market_id,
        "asset_id": observation.asset_id,
        "candle_timeframe": observation.candle_timeframe,
        "horizon": observation.horizon,
        "generated_at": observation.generated_at,
        "expires_at": observation.expires_at,
        "reference_price": observation.reference_price,
        "model_version": model.model_version,
        "model_stage": ModelStage.RESEARCH,
        "feature_version": observation.feature_version,
        "dataset_hash": model.dataset_hash,
        "evidence": observation.evidence,
    }
    if len(winners) != 1:
        return Forecast.model_validate(
            {
                **common,
                "status": ForecastStatus.UNAVAILABLE,
                "unavailable_reason": "AMBIGUOUS_DIRECTION",
            }
        )
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        expected_return = sum(
            (
                probability.probability * item.return_mean
                for probability, item in zip(probabilities, model.classes, strict=True)
            ),
            D(0),
        )
        expected_move = sum(
            (
                probability.probability * item.absolute_return_mean
                for probability, item in zip(probabilities, model.classes, strict=True)
            ),
            D(0),
        )
        expected_low = sum(
            (
                probability.probability * item.return_lower
                for probability, item in zip(probabilities, model.classes, strict=True)
            ),
            D(0),
        )
        expected_high = sum(
            (
                probability.probability * item.return_upper
                for probability, item in zip(probabilities, model.classes, strict=True)
            ),
            D(0),
        )
    winner = winners[0]
    return Forecast.model_validate(
        {
            **common,
            "status": ForecastStatus.AVAILABLE,
            "direction": winner.direction,
            "probabilities": probabilities,
            "expected_return": _published(expected_return),
            "expected_move": _published(expected_move),
            "range_threshold": model.spec.direction_threshold,
            "expected_low_return": _published(expected_low),
            "expected_high_return": _published(expected_high),
            "confidence": winner.probability,
            "probability_calibration": calibration_status,
        }
    )
