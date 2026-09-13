import hashlib
import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, Price, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.horizons import expires_at

D = Decimal
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Probability = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=36)]
Return = Annotated[Decimal, Field(ge=-1, max_digits=38, decimal_places=36)]


class ForecastDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"


class ModelStage(StrEnum):
    RESEARCH = "RESEARCH"
    CHALLENGER = "CHALLENGER"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"
    DEGRADED = "DEGRADED"
    RETIRED = "RETIRED"


class CalibrationStatus(StrEnum):
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED = "CALIBRATED"


class ForecastStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ProbabilityValue(DomainModel):
    direction: ForecastDirection
    probability: Probability


class EvidenceSnapshot(DomainModel):
    kind: Identifier
    version: Identifier
    input_hash: Hash
    available_at: UTCDateTime
    canonical_json: str = Field(min_length=2, max_length=1_000_000)
    content_hash: Hash

    @model_validator(mode="after")
    def canonical_content(self) -> Self:
        try:
            content = json.loads(self.canonical_json)
        except json.JSONDecodeError as error:
            raise ValueError("evidence must contain valid JSON") from error
        encoded = json.dumps(content, sort_keys=True, separators=(",", ":"))
        if encoded != self.canonical_json:
            raise ValueError("evidence JSON must use canonical formatting")
        if hashlib.sha256(encoded.encode()).hexdigest() != self.content_hash:
            raise ValueError("evidence content hash mismatch")
        return self


class Forecast(DomainModel):
    schema_version: Literal["forecast-1.0.0"] = "forecast-1.0.0"
    forecast_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    generated_at: UTCDateTime
    expires_at: UTCDateTime
    reference_price: Price
    status: ForecastStatus
    unavailable_reason: Identifier | None = None
    direction: ForecastDirection | None = None
    probabilities: tuple[ProbabilityValue, ...] = ()
    expected_return: Return | None = None
    expected_move: Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=36)] | None = None
    range_threshold: Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=36)] | None = None
    expected_low_return: Return | None = None
    expected_high_return: Annotated[Decimal, Field(max_digits=38, decimal_places=36)] | None = None
    target_return: Return | None = None
    invalidation_return: Return | None = None
    confidence: Probability | None = None
    probability_calibration: CalibrationStatus | None = None
    regime: Identifier | None = None
    model_version: Identifier
    model_stage: ModelStage
    feature_version: Identifier
    dataset_hash: Hash
    evidence: tuple[EvidenceSnapshot, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.expires_at != expires_at(self.generated_at, self.horizon):
            raise ValueError("expiry must match the horizon convention")
        if any(item.available_at > self.generated_at for item in self.evidence):
            raise ValueError("forecast evidence cannot arrive after generation")
        values = (
            self.direction,
            self.expected_return,
            self.expected_move,
            self.range_threshold,
            self.expected_low_return,
            self.expected_high_return,
            self.confidence,
            self.probability_calibration,
        )
        if self.status == ForecastStatus.UNAVAILABLE:
            if (
                self.unavailable_reason is None
                or self.target_return is not None
                or self.invalidation_return is not None
                or self.probabilities
                or any(v is not None for v in values)
            ):
                raise ValueError("unavailable forecast requires only an explicit reason")
            return self
        if self.unavailable_reason is not None or any(v is None for v in values):
            raise ValueError("available forecast requires complete estimates")
        if tuple(p.direction for p in self.probabilities) != tuple(ForecastDirection):
            raise ValueError("probabilities require every direction in canonical order")
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            if sum((p.probability for p in self.probabilities), D(0)) != 1:
                raise ValueError("probabilities must sum exactly to one")
        winning_probability = max(p.probability for p in self.probabilities)
        winners = tuple(p for p in self.probabilities if p.probability == winning_probability)
        if len(winners) != 1:
            raise ValueError("forecast direction requires a unique highest probability")
        if self.direction != winners[0].direction:
            raise ValueError("direction must match the highest probability")
        if self.confidence != winning_probability:
            raise ValueError("confidence must match the declared direction probability")
        assert self.expected_low_return is not None
        assert self.expected_return is not None
        assert self.expected_high_return is not None
        if not self.expected_low_return <= self.expected_return <= self.expected_high_return:
            raise ValueError("expected range must contain expected return")
        if (self.target_return is None) != (self.invalidation_return is None):
            raise ValueError("target and invalidation returns must be provided together")
        if self.target_return is not None and self.invalidation_return is not None:
            assert self.direction is not None
            if self.direction == ForecastDirection.RANGE:
                raise ValueError("range forecasts cannot define directional target levels")
            if self.direction == ForecastDirection.UP and not (
                self.invalidation_return < 0 < self.target_return
            ):
                raise ValueError("up forecast levels must straddle zero directionally")
            if self.direction == ForecastDirection.DOWN and not (
                self.target_return < 0 < self.invalidation_return
            ):
                raise ValueError("down forecast levels must straddle zero directionally")
        return self


class ForecastOutcome(DomainModel):
    schema_version: Literal["forecast-outcome-1.0.0"] = "forecast-outcome-1.0.0"
    outcome_id: UUID
    forecast_id: UUID
    recorded_at: UTCDateTime
    end_price_at: UTCDateTime
    observation_available_at: UTCDateTime
    end_price: Price
    high_price: Price
    low_price: Price
    actual_return: Return
    maximum_favorable_excursion: Annotated[Decimal, Field(ge=0)] | None = None
    maximum_adverse_excursion: Annotated[Decimal, Field(ge=0)] | None = None
    realized_volatility: Annotated[Decimal, Field(ge=0)] | None = None
    target_hit: bool | None = None
    invalidation_hit: bool | None = None
    directional_correct: bool
    outcome_source: Identifier
    observation_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.low_price <= self.end_price <= self.high_price:
            raise ValueError("outcome extrema must contain end price")
        if not self.end_price_at <= self.observation_available_at <= self.recorded_at:
            raise ValueError("outcome timestamps must preserve availability")
        return self


class ForecastEvaluation(DomainModel):
    schema_version: Literal["forecast-evaluation-1.0.0"] = "forecast-evaluation-1.0.0"
    model_version: Identifier
    horizon: ForecastHorizon
    evaluated_at: UTCDateTime
    sample_count: int = Field(ge=1, le=10000)
    brier_score: Decimal = Field(ge=0, le=2)
    return_mae: Decimal = Field(ge=0)
    return_rmse: Decimal = Field(ge=0)
    directional_accuracy: Decimal = Field(ge=0, le=1)
    calibration_status: CalibrationStatus
