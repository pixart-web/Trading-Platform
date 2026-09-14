from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.models import EvidenceSnapshot

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MetricValue = Annotated[
    Decimal,
    Field(ge=Decimal("-1000000000"), le=Decimal("1000000000"), max_digits=38, decimal_places=24),
]


class DirectionalSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class DirectionalDecision(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class ComparisonOperator(StrEnum):
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CaseStatus(StrEnum):
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class DirectionalReason(StrEnum):
    LONG_CASE_ONLY = "LONG_CASE_ONLY"
    SHORT_CASE_ONLY = "SHORT_CASE_ONLY"
    CONFLICTING_CASES = "CONFLICTING_CASES"
    NO_CASE_PASSED = "NO_CASE_PASSED"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


class DirectionalCriterionDefinition(DomainModel):
    criterion: Identifier
    label: str = Field(min_length=1, max_length=80)
    operator: ComparisonOperator
    threshold: MetricValue
    rule_version: Identifier


class DirectionalCasePolicy(DomainModel):
    side: DirectionalSide
    criteria: tuple[DirectionalCriterionDefinition, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_criteria(self) -> Self:
        identities = tuple(item.criterion for item in self.criteria)
        if len(set(identities)) != len(identities):
            raise ValueError("directional criterion identities must be unique within a side")
        return self


class DirectionalPolicy(DomainModel):
    schema_version: Literal["directional-policy-1.0.0"] = "directional-policy-1.0.0"
    policy_version: Identifier
    long_case: DirectionalCasePolicy
    short_case: DirectionalCasePolicy

    @model_validator(mode="after")
    def canonical_sides(self) -> Self:
        if (
            self.long_case.side != DirectionalSide.LONG
            or self.short_case.side != DirectionalSide.SHORT
        ):
            raise ValueError("directional policy requires canonical LONG and SHORT cases")
        return self


class DirectionalMetric(DomainModel):
    criterion: Identifier
    status: MetricStatus
    value: MetricValue | None = None
    source_version: Identifier
    available_at: UTCDateTime | None = None
    unavailable_reason: Identifier | None = None
    evidence: tuple[EvidenceSnapshot, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == MetricStatus.UNAVAILABLE:
            if (
                self.value is not None
                or self.available_at is not None
                or self.unavailable_reason is None
                or self.evidence
            ):
                raise ValueError("unavailable directional metric requires only an explicit reason")
            return self
        if (
            self.value is None
            or self.available_at is None
            or self.unavailable_reason is not None
            or not self.evidence
        ):
            raise ValueError(
                "available directional metric requires value, availability and evidence"
            )
        if any(item.available_at > self.available_at for item in self.evidence):
            raise ValueError("directional evidence cannot arrive after metric availability")
        return self


class DirectionalCaseInput(DomainModel):
    side: DirectionalSide
    metrics: tuple[DirectionalMetric, ...] = Field(min_length=1, max_length=16)


class DirectionalAnalysisRequest(DomainModel):
    analysis_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    as_of: UTCDateTime
    policy: DirectionalPolicy
    long_case: DirectionalCaseInput
    short_case: DirectionalCaseInput

    @model_validator(mode="after")
    def matches_policy(self) -> Self:
        pairs = (
            (self.policy.long_case, self.long_case, DirectionalSide.LONG),
            (self.policy.short_case, self.short_case, DirectionalSide.SHORT),
        )
        for policy, case, side in pairs:
            if case.side != side:
                raise ValueError("directional request requires canonical LONG and SHORT cases")
            declared = tuple(item.criterion for item in policy.criteria)
            supplied = tuple(item.criterion for item in case.metrics)
            if supplied != declared:
                raise ValueError("directional metrics must match policy criterion order exactly")
        return self


class DirectionalCriterionResult(DomainModel):
    criterion: Identifier
    label: str = Field(min_length=1, max_length=80)
    operator: ComparisonOperator
    threshold: MetricValue
    rule_version: Identifier
    status: MetricStatus
    value: MetricValue | None = None
    passed: bool | None = None
    source_version: Identifier
    available_at: UTCDateTime | None = None
    unavailable_reason: Identifier | None = None
    evidence: tuple[EvidenceSnapshot, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        calculated = (self.value, self.passed, self.available_at)
        if self.status == MetricStatus.UNAVAILABLE:
            if any(item is not None for item in calculated) or self.unavailable_reason is None:
                raise ValueError("unavailable criterion result requires only an explicit reason")
            if self.evidence:
                raise ValueError("unavailable criterion result cannot contain evidence")
            return self
        if any(item is None for item in calculated):
            raise ValueError("available criterion result requires value, result and availability")
        if self.unavailable_reason is not None or not self.evidence:
            raise ValueError("available criterion result requires evidence and no failure reason")
        assert self.value is not None
        expected = (
            self.value >= self.threshold
            if self.operator == ComparisonOperator.GREATER_THAN_OR_EQUAL
            else self.value <= self.threshold
        )
        if self.passed != expected:
            raise ValueError("criterion result must match its configured comparison")
        assert self.available_at is not None
        if any(item.available_at > self.available_at for item in self.evidence):
            raise ValueError("criterion evidence cannot arrive after result availability")
        return self


class DirectionalCaseAnalysis(DomainModel):
    side: DirectionalSide
    status: CaseStatus
    qualifies: bool | None
    results: tuple[DirectionalCriterionResult, ...] = Field(min_length=1, max_length=16)
    failed_criteria: tuple[Identifier, ...]
    unavailable_criteria: tuple[Identifier, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len({item.criterion for item in self.results}) != len(self.results):
            raise ValueError("directional case results must use unique criteria")
        failed = tuple(
            item.criterion
            for item in self.results
            if item.status == MetricStatus.AVAILABLE and item.passed is False
        )
        unavailable = tuple(
            item.criterion for item in self.results if item.status == MetricStatus.UNAVAILABLE
        )
        if self.failed_criteria != failed or self.unavailable_criteria != unavailable:
            raise ValueError("directional case reason lists must match criterion results")
        if unavailable:
            if self.status != CaseStatus.UNAVAILABLE or self.qualifies is not None:
                raise ValueError("case with unavailable evidence cannot publish qualification")
            return self
        expected = not failed
        if self.status != CaseStatus.COMPLETE or self.qualifies != expected:
            raise ValueError("complete case qualification must match all criterion results")
        return self


class DirectionalAnalysis(DomainModel):
    schema_version: Literal["directional-analysis-1.0.0"] = "directional-analysis-1.0.0"
    analysis_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    as_of: UTCDateTime
    generated_at: UTCDateTime
    policy_version: Identifier
    policy_hash: Hash
    input_hash: Hash
    decision: DirectionalDecision
    reason: DirectionalReason
    long_case: DirectionalCaseAnalysis
    short_case: DirectionalCaseAnalysis

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("directional analysis cannot be generated before its as-of time")
        if (
            self.long_case.side != DirectionalSide.LONG
            or self.short_case.side != DirectionalSide.SHORT
        ):
            raise ValueError("directional analysis requires canonical LONG and SHORT cases")
        if (
            self.long_case.status == CaseStatus.UNAVAILABLE
            or self.short_case.status == CaseStatus.UNAVAILABLE
        ):
            expected = (DirectionalDecision.NO_TRADE, DirectionalReason.INCOMPLETE_EVIDENCE)
        elif self.long_case.qualifies and self.short_case.qualifies:
            expected = (DirectionalDecision.NO_TRADE, DirectionalReason.CONFLICTING_CASES)
        elif self.long_case.qualifies:
            expected = (DirectionalDecision.LONG, DirectionalReason.LONG_CASE_ONLY)
        elif self.short_case.qualifies:
            expected = (DirectionalDecision.SHORT, DirectionalReason.SHORT_CASE_ONLY)
        else:
            expected = (DirectionalDecision.NO_TRADE, DirectionalReason.NO_CASE_PASSED)
        if (self.decision, self.reason) != expected:
            raise ValueError("directional decision must match independent case results")
        return self
