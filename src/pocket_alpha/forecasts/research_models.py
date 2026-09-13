from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, Price, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import EvidenceSnapshot, ForecastDirection

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FiniteDecimal = Annotated[Decimal, Field(max_digits=38, decimal_places=36)]
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=36)]
Return = Annotated[Decimal, Field(ge=-1, max_digits=38, decimal_places=36)]


class ForecastPartition(StrEnum):
    TRAIN = "TRAIN"
    CALIBRATION = "CALIBRATION"
    VALIDATION = "VALIDATION"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"


class BaselineSpec(DomainModel):
    version: Literal["gaussian-return-baseline-1.0.0"] = "gaussian-return-baseline-1.0.0"
    feature_names: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    direction_threshold: NonNegative
    minimum_per_class: int = Field(default=10, ge=2, le=1000)
    variance_floor: Decimal = Field(default=Decimal("1e-12"), ge=Decimal("1e-18"), le=1)
    lower_quantile: Decimal = Field(default=Decimal("0.1"), gt=0, lt=Decimal("0.5"))
    upper_quantile: Decimal = Field(default=Decimal("0.9"), gt=Decimal("0.5"), lt=1)

    @model_validator(mode="after")
    def unique_features(self) -> Self:
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature names must be unique")
        if self.lower_quantile >= self.upper_quantile:
            raise ValueError("quantile bounds must be ordered")
        return self


class ForecastObservation(DomainModel):
    observation_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    input_start: UTCDateTime
    generated_at: UTCDateTime
    expires_at: UTCDateTime
    reference_price: Price
    feature_version: Identifier
    feature_values: tuple[FiniteDecimal, ...] = Field(min_length=1, max_length=16)
    evidence: tuple[EvidenceSnapshot, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def temporal_contract(self) -> Self:
        if self.input_start > self.generated_at:
            raise ValueError("input window cannot start after forecast generation")
        if self.expires_at != expires_at(self.generated_at, self.horizon):
            raise ValueError("observation expiry must match the horizon convention")
        if any(item.available_at > self.generated_at for item in self.evidence):
            raise ValueError("observation evidence cannot arrive after generation")
        return self


class LabeledForecastExample(DomainModel):
    observation: ForecastObservation
    actual_return: Return
    outcome_available_at: UTCDateTime
    outcome_hash: Hash
    partition: ForecastPartition

    @model_validator(mode="after")
    def outcome_after_target(self) -> Self:
        if self.outcome_available_at < self.observation.expires_at:
            raise ValueError("outcome cannot be available before forecast expiry")
        return self


class GaussianDirectionClass(DomainModel):
    direction: ForecastDirection
    count: int = Field(ge=2, le=10000)
    feature_mean: tuple[FiniteDecimal, ...] = Field(min_length=1, max_length=16)
    feature_variance: tuple[NonNegative, ...] = Field(min_length=1, max_length=16)
    return_mean: Return
    absolute_return_mean: NonNegative
    return_lower: Return
    return_upper: FiniteDecimal

    @model_validator(mode="after")
    def coherent(self) -> Self:
        lengths = {len(self.feature_mean), len(self.feature_variance)}
        if len(lengths) != 1:
            raise ValueError("class feature vectors must have equal length")
        if not self.return_lower <= self.return_mean <= self.return_upper:
            raise ValueError("class return interval must contain its mean")
        return self


class BaselineForecastModel(DomainModel):
    schema_version: Literal["baseline-forecast-model-1.0.0"] = "baseline-forecast-model-1.0.0"
    model_version: Identifier
    code_version: Identifier
    environment_version: Identifier
    random_seed: None = None
    spec: BaselineSpec
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    feature_version: Identifier
    trained_through: UTCDateTime
    training_available_at: UTCDateTime
    fitted_at: UTCDateTime
    dataset_hash: Hash
    classes: tuple[GaussianDirectionClass, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(item.direction for item in self.classes) != tuple(ForecastDirection):
            raise ValueError("model classes must use canonical direction order")
        width = len(self.spec.feature_names)
        if any(len(item.feature_mean) != width for item in self.classes):
            raise ValueError("model class vectors must match feature specification")
        if self.training_available_at > self.fitted_at:
            raise ValueError("model cannot be fitted before training outcomes are available")
        return self


class TemperatureCalibration(DomainModel):
    schema_version: Literal["temperature-calibration-1.0.0"] = "temperature-calibration-1.0.0"
    calibration_version: Identifier
    model_hash: Hash
    temperature: Decimal = Field(gt=0, max_digits=38, decimal_places=36)
    candidates: tuple[Decimal, ...] = Field(min_length=2, max_length=32)
    raw_brier: Decimal = Field(ge=0, le=2)
    calibrated_brier: Decimal = Field(ge=0, le=2)
    sample_count: int = Field(ge=1, le=10000)
    calibrated_through: UTCDateTime
    calibration_available_at: UTCDateTime
    fitted_at: UTCDateTime
    dataset_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(sorted(set(self.candidates))) != self.candidates:
            raise ValueError("temperature candidates must be unique and ordered")
        if any(item <= 0 for item in self.candidates) or self.temperature not in self.candidates:
            raise ValueError("selected temperature must be a positive declared candidate")
        if self.calibrated_brier > self.raw_brier:
            raise ValueError("calibration cannot worsen its fitting Brier score")
        if self.calibration_available_at > self.fitted_at:
            raise ValueError("calibration cannot precede outcome availability")
        return self


class EconomicCostSpec(DomainModel):
    version: Identifier
    round_trip_fee_bps: Decimal = Field(ge=0, le=10000)
    round_trip_spread_bps: Decimal = Field(ge=0, le=10000)
    round_trip_slippage_bps: Decimal = Field(ge=0, le=10000)
    latency_bps: Decimal = Field(ge=0, le=10000)

    @property
    def total_rate(self) -> Decimal:
        return (
            self.round_trip_fee_bps
            + self.round_trip_spread_bps
            + self.round_trip_slippage_bps
            + self.latency_bps
        ) / Decimal(10000)


class BaselineEvaluation(DomainModel):
    schema_version: Literal["baseline-forecast-evaluation-1.0.0"] = (
        "baseline-forecast-evaluation-1.0.0"
    )
    model_hash: Hash
    calibration_hash: Hash | None
    dataset_hash: Hash
    cost_spec: EconomicCostSpec
    partition: Literal[ForecastPartition.VALIDATION, ForecastPartition.FINAL_HOLDOUT]
    evaluated_at: UTCDateTime
    sample_count: int = Field(ge=1, le=10000)
    brier_score: Decimal = Field(ge=0, le=2)
    return_mae: NonNegative
    return_rmse: NonNegative
    directional_accuracy: Decimal = Field(ge=0, le=1)
    gross_expectancy: FiniteDecimal
    net_expectancy: FiniteDecimal
    compounded_net_return: FiniteDecimal
    maximum_drawdown: Decimal = Field(ge=0, le=1)
    profit_factor: NonNegative | None
    sharpe: FiniteDecimal | None
    sortino: FiniteDecimal | None
    calmar: FiniteDecimal | None
    active_fraction: Decimal = Field(ge=0, le=1)
    turnover: Decimal = Field(ge=0, le=2)
    total_cost: NonNegative
    ruin_observed: bool
    losing_periods: int = Field(ge=0)


def observed_direction(value: Decimal, threshold: Decimal) -> ForecastDirection:
    if value > threshold:
        return ForecastDirection.UP
    if value < -threshold:
        return ForecastDirection.DOWN
    return ForecastDirection.RANGE
