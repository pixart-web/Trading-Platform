from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, Timeframe
from pocket_alpha.forecasts.models import EvidenceSnapshot

D = Decimal
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ScoreValue = Annotated[Decimal, Field(ge=0, le=100, max_digits=38, decimal_places=30)]
Weight = Annotated[Decimal, Field(gt=0, le=1000, max_digits=38, decimal_places=30)]
TotalWeight = Annotated[Decimal, Field(gt=0, le=16000, max_digits=38, decimal_places=30)]
Coverage = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=30)]


class PocketScoreStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ComponentStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PocketScoreComponentDefinition(DomainModel):
    component: Identifier
    label: str = Field(min_length=1, max_length=80)
    weight: Weight
    required: bool = True


class PocketScoreSpec(DomainModel):
    schema_version: Literal["pocket-score-spec-1.0.0"] = "pocket-score-spec-1.0.0"
    score_version: Identifier
    components: tuple[PocketScoreComponentDefinition, ...] = Field(min_length=1, max_length=16)
    minimum_coverage: Coverage = D(1)

    @model_validator(mode="after")
    def unique_components(self) -> Self:
        identities = tuple(item.component for item in self.components)
        if len(set(identities)) != len(identities):
            raise ValueError("Pocket Score component identities must be unique")
        return self


class PocketScoreComponentInput(DomainModel):
    component: Identifier
    status: ComponentStatus
    value: ScoreValue | None = None
    normalization_version: Identifier
    available_at: UTCDateTime | None = None
    unavailable_reason: Identifier | None = None
    evidence: tuple[EvidenceSnapshot, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == ComponentStatus.UNAVAILABLE:
            if (
                self.value is not None
                or self.available_at is not None
                or self.unavailable_reason is None
                or self.evidence
            ):
                raise ValueError("unavailable score component requires only an explicit reason")
            return self
        if (
            self.value is None
            or self.available_at is None
            or self.unavailable_reason is not None
            or not self.evidence
        ):
            raise ValueError("available score component requires value, availability and evidence")
        if any(item.available_at > self.available_at for item in self.evidence):
            raise ValueError("component evidence cannot arrive after component availability")
        return self


class PocketScoreRequest(DomainModel):
    score_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    as_of: UTCDateTime
    spec: PocketScoreSpec
    inputs: tuple[PocketScoreComponentInput, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def declared_inputs(self) -> Self:
        declared = tuple(item.component for item in self.spec.components)
        supplied = tuple(item.component for item in self.inputs)
        if supplied != declared:
            raise ValueError("Pocket Score inputs must match configured component order exactly")
        return self


class PocketScoreComponentExplanation(DomainModel):
    component: Identifier
    label: str = Field(min_length=1, max_length=80)
    status: ComponentStatus
    required: bool
    configured_weight: Weight
    effective_weight: Coverage | None = None
    raw_value: ScoreValue | None = None
    contribution: ScoreValue | None = None
    normalization_version: Identifier
    available_at: UTCDateTime | None = None
    unavailable_reason: Identifier | None = None
    evidence: tuple[EvidenceSnapshot, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == ComponentStatus.AVAILABLE:
            if self.raw_value is None or self.available_at is None:
                raise ValueError("available explanation requires value and availability")
            if self.unavailable_reason is not None or not self.evidence:
                raise ValueError("available explanation requires evidence and no failure reason")
            if (self.effective_weight is None) != (self.contribution is None):
                raise ValueError("effective weight and contribution must be provided together")
            if any(item.available_at > self.available_at for item in self.evidence):
                raise ValueError("explanation evidence cannot arrive after component availability")
            return self
        values = (
            self.effective_weight,
            self.raw_value,
            self.contribution,
            self.available_at,
        )
        if any(value is not None for value in values) or self.unavailable_reason is None:
            raise ValueError("unavailable explanation cannot contain calculated values")
        if self.evidence:
            raise ValueError("unavailable explanation cannot contain evidence")
        return self


class PocketScore(DomainModel):
    schema_version: Literal["pocket-score-1.0.0"] = "pocket-score-1.0.0"
    score_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    as_of: UTCDateTime
    generated_at: UTCDateTime
    status: PocketScoreStatus
    score_version: Identifier
    config_hash: Hash
    input_hash: Hash
    coverage: Coverage
    total_weight: TotalWeight
    available_weight: Annotated[Decimal, Field(ge=0, le=16000, max_digits=38, decimal_places=30)]
    score: ScoreValue | None = None
    unavailable_reason: Identifier | None = None
    components: tuple[PocketScoreComponentExplanation, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("Pocket Score cannot be generated before its as-of time")
        if len({item.component for item in self.components}) != len(self.components):
            raise ValueError("Pocket Score explanations must have unique components")
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            expected_total = sum((item.configured_weight for item in self.components), D(0))
            expected_available = sum(
                (
                    item.configured_weight
                    for item in self.components
                    if item.status == ComponentStatus.AVAILABLE
                ),
                D(0),
            )
            if self.total_weight != expected_total or self.available_weight != expected_available:
                raise ValueError("Pocket Score weight totals must match component explanations")
            expected_coverage = (self.available_weight / self.total_weight).quantize(D("1e-30"))
            if self.coverage != expected_coverage:
                raise ValueError("Pocket Score coverage must match available configured weight")
            if self.status == PocketScoreStatus.UNAVAILABLE:
                if self.score is not None or self.unavailable_reason is None:
                    raise ValueError("unavailable Pocket Score requires only an explicit reason")
                if any(
                    item.effective_weight is not None or item.contribution is not None
                    for item in self.components
                ):
                    raise ValueError(
                        "unavailable Pocket Score cannot publish partial contributions"
                    )
                return self
            if self.score is None or self.unavailable_reason is not None:
                raise ValueError("available Pocket Score requires a score and no failure reason")
            available = tuple(
                item for item in self.components if item.status == ComponentStatus.AVAILABLE
            )
            if not available:
                raise ValueError("available Pocket Score requires available components")
            effective_total = sum(
                (item.effective_weight for item in available if item.effective_weight is not None),
                D(0),
            )
            if effective_total != 1:
                raise ValueError("effective Pocket Score weights must sum exactly to one")
            for item in available:
                assert item.raw_value is not None
                assert item.effective_weight is not None
                assert item.contribution is not None
                expected_weight = (item.configured_weight / self.available_weight).quantize(
                    D("1e-30")
                )
                if abs(item.effective_weight - expected_weight) > D("1e-29"):
                    raise ValueError("effective component weight exceeds the rounding tolerance")
                expected_contribution = (
                    item.raw_value * item.configured_weight / self.available_weight
                ).quantize(D("1e-30"))
                if abs(item.contribution - expected_contribution) > D("1e-28"):
                    raise ValueError("component contribution exceeds the rounding tolerance")
            contribution_total = sum(
                (item.contribution for item in available if item.contribution is not None), D(0)
            )
            if self.score != contribution_total:
                raise ValueError("Pocket Score must equal the sum of explained contributions")
        return self
