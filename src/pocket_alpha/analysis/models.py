from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.directional.models import DirectionalAnalysis, DirectionalDecision
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.models import CalibrationStatus, Forecast, ForecastStatus
from pocket_alpha.opportunities.models import OpportunityScore, OpportunityStatus
from pocket_alpha.scoring.models import PocketScore, PocketScoreStatus


class AnalyzeStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class HorizonConclusion(StrEnum):
    ELIGIBLE_LONG = "ELIGIBLE_LONG"
    ELIGIBLE_SHORT = "ELIGIBLE_SHORT"
    INELIGIBLE_LONG = "INELIGIBLE_LONG"
    INELIGIBLE_SHORT = "INELIGIBLE_SHORT"
    NO_TRADE = "NO_TRADE"
    UNAVAILABLE = "UNAVAILABLE"


class AnalyzeIssue(StrEnum):
    POCKET_SCORE_NOT_PRODUCED = "POCKET_SCORE_NOT_PRODUCED"
    POCKET_SCORE_UNAVAILABLE = "POCKET_SCORE_UNAVAILABLE"


class HorizonIssue(StrEnum):
    FORECAST_NOT_PRODUCED = "FORECAST_NOT_PRODUCED"
    FORECAST_UNAVAILABLE = "FORECAST_UNAVAILABLE"
    FORECAST_EXPIRED = "FORECAST_EXPIRED"
    FORECAST_UNCALIBRATED = "FORECAST_UNCALIBRATED"
    DIRECTIONAL_NOT_PRODUCED = "DIRECTIONAL_NOT_PRODUCED"
    DIRECTIONAL_NO_TRADE = "DIRECTIONAL_NO_TRADE"
    OPPORTUNITY_NOT_PRODUCED = "OPPORTUNITY_NOT_PRODUCED"
    OPPORTUNITY_UNAVAILABLE = "OPPORTUNITY_UNAVAILABLE"
    OPPORTUNITY_INELIGIBLE = "OPPORTUNITY_INELIGIBLE"


class AnalyzeResponseStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


def _artifact_or_reason(value: object | None, reason: str | None, label: str) -> None:
    if (value is None) == (reason is None):
        raise ValueError(f"{label} requires exactly one artifact or unavailable reason")


class AnalyzeHorizonInput(DomainModel):
    horizon: ForecastHorizon
    forecast: Forecast | None = None
    forecast_unavailable_reason: Identifier | None = None
    directional: DirectionalAnalysis | None = None
    directional_unavailable_reason: Identifier | None = None
    opportunity: OpportunityScore | None = None
    opportunity_unavailable_reason: Identifier | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _artifact_or_reason(self.forecast, self.forecast_unavailable_reason, "forecast")
        _artifact_or_reason(self.directional, self.directional_unavailable_reason, "directional")
        _artifact_or_reason(self.opportunity, self.opportunity_unavailable_reason, "opportunity")
        for artifact in (self.forecast, self.directional, self.opportunity):
            if artifact is not None and artifact.horizon != self.horizon:
                raise ValueError("Analyze horizon must match every supplied artifact")
        if self.opportunity is not None:
            if self.forecast is None or self.directional is None:
                raise ValueError("opportunity requires its forecast and directional artifacts")
            if (
                self.opportunity.forecast_id != self.forecast.forecast_id
                or self.opportunity.analysis_id != self.directional.analysis_id
            ):
                raise ValueError("opportunity must reference the supplied upstream artifacts")
            if (
                self.opportunity.status == OpportunityStatus.AVAILABLE
                and self.directional.decision.value != self.opportunity.direction
            ):
                raise ValueError("opportunity direction must match directional analysis")
        return self


class AnalyzeHorizon(DomainModel):
    horizon: ForecastHorizon
    status: AnalyzeStatus
    conclusion: HorizonConclusion
    issues: tuple[HorizonIssue, ...]
    forecast: Forecast | None = None
    forecast_unavailable_reason: Identifier | None = None
    directional: DirectionalAnalysis | None = None
    directional_unavailable_reason: Identifier | None = None
    opportunity: OpportunityScore | None = None
    opportunity_unavailable_reason: Identifier | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        AnalyzeHorizonInput.model_validate(
            {
                "horizon": self.horizon,
                "forecast": self.forecast,
                "forecast_unavailable_reason": self.forecast_unavailable_reason,
                "directional": self.directional,
                "directional_unavailable_reason": self.directional_unavailable_reason,
                "opportunity": self.opportunity,
                "opportunity_unavailable_reason": self.opportunity_unavailable_reason,
            }
        )
        return self


class AnalyzeRequest(DomainModel):
    report_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    as_of: UTCDateTime
    report_version: Identifier
    pocket_score: PocketScore | None = None
    pocket_score_unavailable_reason: Identifier | None = None
    horizons: tuple[AnalyzeHorizonInput, ...] = Field(min_length=13, max_length=13)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _artifact_or_reason(self.pocket_score, self.pocket_score_unavailable_reason, "Pocket Score")
        if tuple(item.horizon for item in self.horizons) != tuple(ForecastHorizon):
            raise ValueError("Analyze requires every forecast horizon in canonical order")
        return self


class AnalyzeReport(DomainModel):
    schema_version: Literal["analyze-report-1.0.0"] = "analyze-report-1.0.0"
    report_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    as_of: UTCDateTime
    generated_at: UTCDateTime
    status: AnalyzeStatus
    report_version: Identifier
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[AnalyzeIssue, ...]
    pocket_score: PocketScore | None = None
    pocket_score_unavailable_reason: Identifier | None = None
    horizons: tuple[AnalyzeHorizon, ...] = Field(min_length=13, max_length=13)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _artifact_or_reason(self.pocket_score, self.pocket_score_unavailable_reason, "Pocket Score")
        if self.generated_at < self.as_of:
            raise ValueError("Analyze report cannot be generated before its as-of time")
        if tuple(item.horizon for item in self.horizons) != tuple(ForecastHorizon):
            raise ValueError("Analyze report requires canonical forecast horizons")
        if self.pocket_score is not None:
            identity = (
                self.pocket_score.market_id,
                self.pocket_score.asset_id,
                self.pocket_score.candle_timeframe,
                self.pocket_score.as_of,
            )
            if identity != (
                self.market_id,
                self.asset_id,
                self.candle_timeframe,
                self.as_of,
            ):
                raise ValueError("Pocket Score identity must match Analyze report")
            if self.pocket_score.generated_at > self.generated_at:
                raise ValueError("Pocket Score was unavailable at report generation")
        identifiers = (
            (
                "forecast",
                tuple(item.forecast.forecast_id for item in self.horizons if item.forecast),
            ),
            (
                "directional",
                tuple(item.directional.analysis_id for item in self.horizons if item.directional),
            ),
            (
                "opportunity",
                tuple(
                    item.opportunity.opportunity_id for item in self.horizons if item.opportunity
                ),
            ),
        )
        if any(len(set(values)) != len(values) for _, values in identifiers):
            raise ValueError("Analyze artifacts must have unique identities across horizons")
        for item in self.horizons:
            self._validate_horizon(item)
            status, conclusion, issues = derive_horizon(item, self.as_of)
            if (item.status, item.conclusion, item.issues) != (status, conclusion, issues):
                raise ValueError("Analyze horizon summary must match supplied artifacts")
        expected_issues = (
            (AnalyzeIssue.POCKET_SCORE_NOT_PRODUCED,)
            if self.pocket_score is None
            else (AnalyzeIssue.POCKET_SCORE_UNAVAILABLE,)
            if self.pocket_score.status == PocketScoreStatus.UNAVAILABLE
            else ()
        )
        if self.issues != expected_issues:
            raise ValueError("Analyze report issues must match Pocket Score state")
        present = int(self.pocket_score is not None) + sum(
            artifact is not None
            for item in self.horizons
            for artifact in (item.forecast, item.directional, item.opportunity)
        )
        total = 1 + len(self.horizons) * 3
        expected_status = (
            AnalyzeStatus.UNAVAILABLE
            if present == 0
            else AnalyzeStatus.COMPLETE
            if present == total
            else AnalyzeStatus.PARTIAL
        )
        if self.status != expected_status:
            raise ValueError("Analyze status must match artifact coverage")
        return self

    def _validate_horizon(self, item: AnalyzeHorizon) -> None:
        common = (self.market_id, self.asset_id, self.candle_timeframe, item.horizon)
        if item.forecast is not None:
            forecast_identity = (
                item.forecast.market_id,
                item.forecast.asset_id,
                item.forecast.candle_timeframe,
                item.forecast.horizon,
            )
            if forecast_identity != common:
                raise ValueError("forecast identity must match Analyze report")
            if item.forecast.generated_at > self.as_of:
                raise ValueError("forecast was unavailable at the Analyze as-of time")
        if item.directional is not None:
            directional_identity = (
                item.directional.market_id,
                item.directional.asset_id,
                item.directional.candle_timeframe,
                item.directional.horizon,
            )
            if directional_identity != common or item.directional.as_of != self.as_of:
                raise ValueError("directional identity must match Analyze report")
            if item.directional.generated_at > self.generated_at:
                raise ValueError("directional analysis was unavailable at report generation")
        if item.opportunity is not None:
            opportunity_identity = (
                item.opportunity.market_id,
                item.opportunity.asset_id,
                item.opportunity.candle_timeframe,
                item.opportunity.horizon,
            )
            if opportunity_identity != common or item.opportunity.as_of != self.as_of:
                raise ValueError("opportunity identity must match Analyze report")
            if item.opportunity.generated_at > self.generated_at:
                raise ValueError("opportunity was unavailable at report generation")


class AnalyzeSnapshotResponse(DomainModel):
    schema_version: Literal["analyze-response-1.0.0"] = "analyze-response-1.0.0"
    market_id: Identifier
    candle_timeframe: Timeframe
    requested_as_of: UTCDateTime
    status: AnalyzeResponseStatus
    report: AnalyzeReport | None = None
    unavailable_reason: Identifier | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == AnalyzeResponseStatus.UNAVAILABLE:
            if self.report is not None or self.unavailable_reason is None:
                raise ValueError("unavailable Analyze response requires only a reason")
            return self
        if self.report is None or self.unavailable_reason is not None:
            raise ValueError("available Analyze response requires only a report")
        if (
            self.report.market_id != self.market_id
            or self.report.candle_timeframe != self.candle_timeframe
            or self.report.as_of != self.requested_as_of
        ):
            raise ValueError("Analyze response identity must match its report")
        return self


def derive_horizon(
    item: AnalyzeHorizon | AnalyzeHorizonInput, as_of: UTCDateTime
) -> tuple[AnalyzeStatus, HorizonConclusion, tuple[HorizonIssue, ...]]:
    artifacts = (item.forecast, item.directional, item.opportunity)
    present = sum(value is not None for value in artifacts)
    status = (
        AnalyzeStatus.UNAVAILABLE
        if present == 0
        else AnalyzeStatus.COMPLETE
        if present == len(artifacts)
        else AnalyzeStatus.PARTIAL
    )
    issues: list[HorizonIssue] = []
    if item.forecast is None:
        issues.append(HorizonIssue.FORECAST_NOT_PRODUCED)
    elif item.forecast.status == ForecastStatus.UNAVAILABLE:
        issues.append(HorizonIssue.FORECAST_UNAVAILABLE)
    else:
        if item.forecast.expires_at <= as_of:
            issues.append(HorizonIssue.FORECAST_EXPIRED)
        if item.forecast.probability_calibration != CalibrationStatus.CALIBRATED:
            issues.append(HorizonIssue.FORECAST_UNCALIBRATED)
    if item.directional is None:
        issues.append(HorizonIssue.DIRECTIONAL_NOT_PRODUCED)
    elif item.directional.decision == DirectionalDecision.NO_TRADE:
        issues.append(HorizonIssue.DIRECTIONAL_NO_TRADE)
    if item.opportunity is None:
        issues.append(HorizonIssue.OPPORTUNITY_NOT_PRODUCED)
    elif item.opportunity.status == OpportunityStatus.UNAVAILABLE:
        issues.append(HorizonIssue.OPPORTUNITY_UNAVAILABLE)
    elif not item.opportunity.eligible:
        issues.append(HorizonIssue.OPPORTUNITY_INELIGIBLE)

    if item.directional is not None and item.directional.decision == DirectionalDecision.NO_TRADE:
        conclusion = HorizonConclusion.NO_TRADE
    elif item.opportunity is not None and item.opportunity.status == OpportunityStatus.AVAILABLE:
        assert item.opportunity.direction is not None
        if item.opportunity.eligible:
            conclusion = HorizonConclusion(f"ELIGIBLE_{item.opportunity.direction.value}")
        else:
            conclusion = HorizonConclusion(f"INELIGIBLE_{item.opportunity.direction.value}")
    else:
        conclusion = HorizonConclusion.UNAVAILABLE
    return status, conclusion, tuple(issues)
