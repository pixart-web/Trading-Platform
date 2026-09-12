from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.intelligence.technical.models import FeatureSnapshot, FeatureValue

D = Decimal
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Efficiency = Annotated[Decimal, Field(ge=-1, le=1)]
Magnitude = Annotated[Decimal, Field(ge=0, le=100)]
Variance = Annotated[Decimal, Field(gt=0, le=10000)]
Vector = tuple[Efficiency, Magnitude, Magnitude]


class RegimeLabel(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


class VolatilityRegime(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class RegimeSpec(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    period: int = Field(default=14, ge=2, le=500, strict=True)
    baseline_period: int = Field(default=50, ge=2, le=500, strict=True)
    range_efficiency: Decimal = Field(default=D("0.3"), ge=0, lt=1)
    trend_efficiency: Decimal = Field(default=D("0.6"), gt=0, le=1)
    low_volatility_ratio: Decimal = Field(default=D("0.67"), gt=0, lt=1)
    high_volatility_ratio: Decimal = Field(default=D("1.5"), gt=1, le=100)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.range_efficiency >= self.trend_efficiency:
            raise ValueError("range efficiency must be below trend efficiency")
        return self


class TrendReason(StrEnum):
    WARMUP = "WARMUP"
    FLAT_CLOSES = "FLAT_CLOSES"
    EFFICIENT_MOVE = "EFFICIENT_MOVE"
    LOW_EFFICIENCY = "LOW_EFFICIENCY"
    MIXED_PATH = "MIXED_PATH"


class RegimeObservation(DomainModel):
    engine_version: Literal["regimes-1.0.0"] = "regimes-1.0.0"
    spec: RegimeSpec
    technical: FeatureSnapshot
    signed_efficiency: FeatureValue
    volatility_ratio: FeatureValue
    trend: RegimeLabel | None
    trend_reason: TrendReason
    volatility: VolatilityRegime | None
    # Ordered vector: signed efficiency, RMS log return, log(1 + relative volume).
    vector: Vector | None


class SamplePartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"


class TrainingExample(DomainModel):
    partition: SamplePartition = SamplePartition.TRAIN
    observation: RegimeObservation
    label: RegimeLabel
    label_available_at: UTCDateTime

    @model_validator(mode="after")
    def usable(self) -> Self:
        if self.observation.vector is None:
            raise ValueError("training requires all model features")
        if self.label_available_at < self.observation.technical.available_at:
            raise ValueError("label cannot predate observation availability")
        return self


class FitSpec(DomainModel):
    version: Literal["gaussian-nb-1.0.0"] = "gaussian-nb-1.0.0"
    minimum_per_class: int = Field(default=10, ge=2, le=2500, strict=True)
    variance_floor: Decimal = Field(default=D("1e-12"), ge=D("1e-18"), le=1)


class GaussianClass(DomainModel):
    label: RegimeLabel
    count: int = Field(ge=2, le=10000, strict=True)
    mean: Vector
    variance: tuple[Variance, Variance, Variance]


class RegimeModel(DomainModel):
    model_version: Literal["gaussian-nb-1.0.0"] = "gaussian-nb-1.0.0"
    stage: Literal["RESEARCH"] = "RESEARCH"
    calibration: Literal["UNCALIBRATED"] = "UNCALIBRATED"
    feature_spec: RegimeSpec
    fit_spec: FitSpec
    label_policy: Identifier
    market_id: Identifier
    timeframe: Timeframe
    source: Identifier
    trained_through: UTCDateTime
    training_available_at: UTCDateTime
    fitted_at: UTCDateTime
    dataset_hash: Hash
    classes: tuple[GaussianClass, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(c.label for c in self.classes) != tuple(RegimeLabel):
            raise ValueError("all classes are required in canonical order")
        if not self.trained_through <= self.training_available_at <= self.fitted_at:
            raise ValueError("model availability must follow training observations and labels")
        if sum(c.count for c in self.classes) > 10000:
            raise ValueError("maximum 10000 training observations")
        if any(c.count < self.fit_spec.minimum_per_class for c in self.classes):
            raise ValueError("insufficient observations per class")
        if any(v < self.fit_spec.variance_floor for c in self.classes for v in c.variance):
            raise ValueError("variance cannot be below configured floor")
        return self


class RegimeProbability(DomainModel):
    label: RegimeLabel
    probability: Decimal = Field(ge=0, le=1)


class ProbabilityResult(DomainModel):
    status: Literal["RESEARCH", "UNAVAILABLE"]
    reason: (
        Literal["NO_MODEL", "FEATURES_UNAVAILABLE", "MODEL_NOT_AVAILABLE", "TRAINING_OVERLAP"]
        | None
    )
    calibration: Literal["UNCALIBRATED"] = "UNCALIBRATED"
    model_hash: Hash | None = None
    probabilities: tuple[RegimeProbability, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == "UNAVAILABLE":
            if self.reason is None or self.probabilities:
                raise ValueError("unavailable probabilities require a reason and no values")
        else:
            if self.reason is not None or self.model_hash is None:
                raise ValueError("research probabilities require an identified model")
            if tuple(p.label for p in self.probabilities) != tuple(RegimeLabel):
                raise ValueError("probabilities require every class in canonical order")
            with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
                if sum((p.probability for p in self.probabilities), D(0)) != 1:
                    raise ValueError("probabilities must sum to one")
        return self


class RegimeSnapshot(DomainModel):
    observation: RegimeObservation
    probability: ProbabilityResult


class ClassSupport(DomainModel):
    label: RegimeLabel
    count: int = Field(ge=0, le=10000)


class RegimeEvaluation(DomainModel):
    version: Literal["regime-evaluation-1.0.0"] = "regime-evaluation-1.0.0"
    model_hash: Hash
    dataset_hash: Hash
    partition: Literal[SamplePartition.VALIDATION, SamplePartition.FINAL_HOLDOUT]
    evaluated_at: UTCDateTime
    sample_count: int = Field(ge=1, le=10000)
    class_support: tuple[ClassSupport, ...]
    accuracy: Decimal = Field(ge=0, le=1)
    multiclass_brier: Decimal = Field(ge=0, le=2)
    calibration: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
