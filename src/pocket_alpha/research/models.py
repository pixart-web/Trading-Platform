from decimal import Decimal
from typing import Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Hash, RunConfig, digest
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, ForecastHorizon
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import Forecast, ForecastOutcome


class Window(DomainModel):
    start: UTCDateTime
    end: UTCDateTime

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start >= self.end:
            raise ValueError("research window must be nonempty")
        return self


class Fold(DomainModel):
    name: Identifier
    train: Window
    validation: Window
    test: Window
    embargo_seconds: int = Field(ge=0, le=31622400, strict=True)

    @model_validator(mode="after")
    def isolated(self) -> Self:
        if (self.validation.start - self.train.end).total_seconds() < self.embargo_seconds or (
            self.test.start - self.validation.end
        ).total_seconds() < self.embargo_seconds:
            raise ValueError("train/validation/test must be ordered with declared embargo")
        return self


class Source(DomainModel):
    dataset_id: UUID
    dataset_hash: Hash


class Variant(DomainModel):
    name: Identifier
    role: Literal["BASELINE", "PARAMETER", "COST_STRESS"]
    config: RunConfig
    horizon: ForecastHorizon


class Segment(DomainModel):
    name: Identifier
    window: Window
    evidence_hash: Hash
    available_at: UTCDateTime
    provenance: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def causal(self) -> Self:
        if self.available_at > self.window.start:
            raise ValueError("regime segment evidence must be known before segment start")
        return self


class AnalysisPolicy(DomainModel):
    version: Identifier
    seed: int = Field(ge=0, le=2147483647, strict=True)
    simulations: int = Field(ge=20, le=1000, strict=True)
    block_length: int = Field(ge=1, le=100, strict=True)
    minimum_returns: int = Field(ge=3, le=10000, strict=True)
    lower_quantile: Decimal = Field(gt=0, lt=Decimal("0.5"), allow_inf_nan=False)
    upper_quantile: Decimal = Field(gt=Decimal("0.5"), lt=1, allow_inf_nan=False)


class StudyPlan(DomainModel):
    schema_version: Literal["research-plan-1.0.0"] = "research-plan-1.0.0"
    version: Identifier
    rationale: str = Field(min_length=1, max_length=1024)
    mode: Literal["WALK_FORWARD", "ROLLING"]
    sources: tuple[Source, ...] = Field(min_length=1, max_length=16)
    folds: tuple[Fold, ...] = Field(min_length=1, max_length=16)
    variants: tuple[Variant, ...] = Field(min_length=1, max_length=16)
    segments: tuple[Segment, ...] = Field(max_length=16)
    final_holdout: Window
    label_horizon_seconds: int = Field(ge=1, le=31622400, strict=True)
    analysis: AnalysisPolicy
    calibration_forecast_ids: tuple[UUID, ...] = Field(default=(), max_length=1000)
    selection_bias: Literal["UNASSESSED_NO_UNIVERSE_CLAIM"] = "UNASSESSED_NO_UNIVERSE_CLAIM"
    maximum_runs: int = Field(ge=1, le=256, strict=True)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        for values in [
            self.calibration_forecast_ids,
            tuple(s.dataset_id for s in self.sources),
            tuple(f.name for f in self.folds),
            tuple(v.name for v in self.variants),
            tuple(s.name for s in self.segments),
        ]:
            if len(set(values)) != len(values):
                raise ValueError("plan identities must be unique")
        if sum(v.role == "BASELINE" for v in self.variants) != 1:
            raise ValueError("exactly one declared interpretable baseline is required")
        if any(v.config.evaluation_split != "RESEARCH" for v in self.variants):
            raise ValueError("variant config must be a research template")
        baseline = next(v for v in self.variants if v.role == "BASELINE")
        for v in self.variants:
            if (
                v.config.code_tree_hash,
                v.config.environment_hash,
                v.config.initial_cash,
                v.config.risk,
            ) != (
                baseline.config.code_tree_hash,
                baseline.config.environment_hash,
                baseline.config.initial_cash,
                baseline.config.risk,
            ):
                raise ValueError("variants must share code/environment/capital/risk")
            if v.role == "COST_STRESS":
                if (v.config.strategy, v.horizon, v.config.feature_specs) != (
                    baseline.config.strategy,
                    baseline.horizon,
                    baseline.config.feature_specs,
                ):
                    raise ValueError("cost stress must preserve baseline strategy/features/horizon")
                a, b = v.config.costs, baseline.config.costs
                if (
                    any(
                        getattr(a, n) < getattr(b, n)
                        for n in (
                            "fee_bps",
                            "spread_bps",
                            "slippage_bps",
                            "impact_bps_at_capacity",
                            "latency_seconds",
                        )
                    )
                    or a.participation > b.participation
                ):
                    raise ValueError("stress cannot improve costs, latency or liquidity")
                if a.model_dump(exclude={"version"}) == b.model_dump(exclude={"version"}):
                    raise ValueError("cost stress must change declared assumptions")
        for variant in self.variants:
            cutoffs = [f.train.end for f in self.folds] + [self.final_holdout.start]
            if any(
                (expires_at(at, variant.horizon) - at).total_seconds() > self.label_horizon_seconds
                for at in cutoffs
            ):
                raise ValueError("declared maximum label horizon does not cover variant horizons")
        for i, f in enumerate(self.folds):
            if f.embargo_seconds < self.label_horizon_seconds:
                raise ValueError("embargo must cover declared maximum label horizon")
            if i:
                previous = self.folds[i - 1]
                if f.test.start < previous.test.end or f.train.end <= previous.train.end:
                    raise ValueError("fold tests must not overlap and training must advance")
                if self.mode == "WALK_FORWARD" and f.train.start != previous.train.start:
                    raise ValueError("walk-forward training must expand from a fixed start")
                if self.mode == "ROLLING" and (
                    f.train.end - f.train.start != previous.train.end - previous.train.start
                    or f.train.start <= previous.train.start
                ):
                    raise ValueError("rolling training must advance with fixed width")
        if any(
            (self.final_holdout.start - f.test.end).total_seconds() < self.label_horizon_seconds
            for f in self.folds
        ):
            raise ValueError("final holdout must follow every test with an embargo")
        for s in self.segments:
            if not any(
                f.test.start <= s.window.start < s.window.end <= f.test.end for f in self.folds
            ):
                raise ValueError("regime segments must lie inside a declared test")
        runs = len(self.sources) * len(self.variants) * (2 * len(self.folds) + len(self.segments))
        if runs > self.maximum_runs:
            raise ValueError("declared matrix exceeds run budget")
        return self

    @property
    def study_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, "pocket-alpha-study:" + digest(self))


class Diagnostic(DomainModel):
    name: Identifier
    value: Decimal | None = Field(allow_inf_nan=False)
    reason: Identifier | None = None

    @model_validator(mode="after")
    def availability(self) -> Self:
        if (self.value is None) != (self.reason is not None):
            raise ValueError("unavailable diagnostic needs an explicit reason")
        return self


class Trial(DomainModel):
    source_id: UUID
    asset_id: Identifier
    fold: Identifier
    variant: Identifier
    partition: Literal["VALIDATION", "TEST", "REGIME", "FINAL_HOLDOUT"]
    horizon: ForecastHorizon
    regime: Identifier | None = None
    train_hash: Hash
    fitted_artifact_hash: Hash
    fitted_artifact_json: str = Field(min_length=2, max_length=65536)
    backtest_id: UUID
    backtest_hash: Hash
    diagnostics: tuple[Diagnostic, ...]


class ResearchReport(DomainModel):
    schema_version: Literal["research-report-1.0.0"] = "research-report-1.0.0"
    report_id: UUID
    study_id: UUID
    plan_hash: Hash
    stage: Literal["EXPERIMENTS", "FINAL_HOLDOUT"]
    selected_variant: Identifier | None
    generated_at: UTCDateTime
    trials: tuple[Trial, ...] = Field(min_length=1, max_length=256)
    declared_trials: int = Field(ge=1)
    origin: Literal["REAL", "SYNTHETIC"]
    warnings: tuple[Identifier, ...]
    content_hash: Hash
    calibration_inputs: tuple[tuple[Forecast, ForecastOutcome], ...] = Field(
        default=(), max_length=1000
    )
    calibration_diagnostics: tuple[Diagnostic, ...]
    profitability_claim: Literal[False] = False
    live_ready: Literal[False] = False

    @model_validator(mode="after")
    def intact(self) -> Self:
        import json

        for trial in self.trials:
            artifact = json.loads(trial.fitted_artifact_json)
            canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if (
                not isinstance(artifact, dict)
                or canonical != trial.fitted_artifact_json
                or digest(artifact) != trial.fitted_artifact_hash
            ):
                raise ValueError("fitted artifact must be canonical and match its hash")
        expected = uuid5(
            NAMESPACE_URL,
            "pocket-alpha-research:"
            + digest(
                dict(study_id=str(self.study_id), stage=self.stage, selected=self.selected_variant)
            ),
        )
        if self.report_id != expected or self.content_hash != digest(
            self.model_dump(mode="json", exclude={"content_hash", "generated_at"})
        ):
            raise ValueError("research report identity/content hash mismatch")
        from pocket_alpha.research.diagnostics import calibration

        if self.calibration_diagnostics != calibration(self.calibration_inputs, self.generated_at):
            raise ValueError("calibration diagnostics do not match immutable outcomes")
        keys = [(t.source_id, t.fold, t.variant, t.partition, t.regime) for t in self.trials]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate research trial")
        if self.stage == "FINAL_HOLDOUT":
            if self.selected_variant is None or any(
                t.partition != "FINAL_HOLDOUT" or t.variant != self.selected_variant
                for t in self.trials
            ):
                raise ValueError("final report must use one frozen selection")
        elif self.selected_variant is not None or any(
            t.partition == "FINAL_HOLDOUT" for t in self.trials
        ):
            raise ValueError("experiments cannot consume final holdout")
        return self
