from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Self, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator
from sqlalchemy import CursorResult, ForeignKey, String, Text, Uuid, select, update
from sqlalchemy.orm import Mapped, mapped_column

from pocket_alpha.backtesting.models import Hash, digest
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.database import Base
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.forecasts.models import ModelStage
from pocket_alpha.research.models import ResearchReport
from pocket_alpha.research.storage import ResearchRepository


class PromotionPolicy(DomainModel):
    version: Identifier
    minimum_net_return: Decimal = Field(gt=0, allow_inf_nan=False)
    minimum_net_expectancy: Decimal = Field(gt=0, allow_inf_nan=False)
    maximum_drawdown: Decimal = Field(gt=0, lt=1, allow_inf_nan=False)
    minimum_completed_trades: int = Field(ge=1, le=10000, strict=True)
    minimum_assets: int = Field(ge=1, le=16, strict=True)
    minimum_test_folds: int = Field(ge=1, le=16, strict=True)
    minimum_baseline_improvement: Decimal = Field(gt=0, allow_inf_nan=False)
    require_cost_stress: bool


class ModelArtifact(DomainModel):
    artifact_id: UUID
    model_version: Identifier
    experiment_id: UUID
    selected_variant: Identifier
    bundle_hash: Hash
    registered_at: UTCDateTime

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.artifact_id != uuid5(
            NAMESPACE_URL,
            "pocket-alpha-model:"
            + digest(self.model_dump(mode="json", exclude={"artifact_id", "registered_at"})),
        ):
            raise ValueError("model artifact identity mismatch")
        return self


class RegistryEvent(DomainModel):
    artifact_id: UUID
    revision: int = Field(ge=0)
    from_stage: ModelStage | None
    to_stage: ModelStage
    at: UTCDateTime
    reason: str = Field(min_length=1, max_length=1024)
    evidence_id: UUID | None
    evidence_hash: Hash | None
    policy: PromotionPolicy | None
    previous_hash: Hash | None
    content_hash: Hash

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.content_hash != digest(self.model_dump(mode="json", exclude={"content_hash"})):
            raise ValueError("registry evidence hash mismatch")
        return self


class RegistryRecord(Base):
    __tablename__ = "research_model_registry"
    artifact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    revision: Mapped[int] = mapped_column()
    payload: Mapped[str] = mapped_column(Text)


class RegistryEventRecord(Base):
    __tablename__ = "research_model_events"
    artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_model_registry.artifact_id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class RegistryConflict(Exception):
    pass


def bundle(report: ResearchReport, selected: str) -> str:
    return digest(
        [
            dict(
                source_id=str(t.source_id),
                fold=t.fold,
                train_hash=t.train_hash,
                fitted_artifact_hash=t.fitted_artifact_hash,
            )
            for t in report.trials
            if t.variant == selected and t.partition == "TEST"
        ]
    )


class ModelRegistry:
    def __init__(self, repository: ResearchRepository, clock: Clock) -> None:
        self.repository, self.clock = repository, clock

    def get(self, artifact_id: UUID) -> tuple[ModelArtifact, tuple[RegistryEvent, ...]] | None:
        session = self.repository.session
        head = session.get(RegistryRecord, artifact_id)
        if head is None:
            return None
        artifact = ModelArtifact.model_validate_json(head.payload)
        report = self.repository.get(artifact.experiment_id)
        if (
            artifact.artifact_id != artifact_id
            or report is None
            or artifact.bundle_hash != bundle(report, artifact.selected_variant)
        ):
            raise ValueError("registry artifact/evidence corrupted")
        if artifact.registered_at < report.generated_at:
            raise ValueError("registry registration predates its experiment evidence")
        plan = self.repository.plan(report.study_id)
        assert plan is not None
        variant = next((v for v in plan.variants if v.name == artifact.selected_variant), None)
        if variant is None or variant.config.strategy.model_version != artifact.model_version:
            raise ValueError("registry model version differs from sealed experiment")
        rows = session.scalars(
            select(RegistryEventRecord)
            .where(RegistryEventRecord.artifact_id == artifact_id)
            .order_by(RegistryEventRecord.revision)
        ).all()
        events = tuple(RegistryEvent.model_validate_json(row.payload) for row in rows)
        if head.revision < 0 or len(events) != head.revision + 1:
            raise ValueError("registry history incomplete")
        for i, (row, event) in enumerate(zip(rows, events, strict=True)):
            previous = events[i - 1] if i else None
            if (
                event.artifact_id != artifact_id
                or row.revision != i
                or event.revision != i
                or row.content_hash != event.content_hash
                or event.previous_hash != (previous.content_hash if previous else None)
                or event.from_stage != (previous.to_stage if previous else None)
                or (previous is not None and event.at < previous.at)
            ):
                raise ValueError("registry audit chain corrupted")
            if event.evidence_id is not None:
                evidence = self.repository.get(event.evidence_id)
                if (
                    evidence is None
                    or evidence.content_hash != event.evidence_hash
                    or evidence.generated_at > event.at
                ):
                    raise ValueError("registry promotion evidence missing or corrupted")
        if (
            not events
            or events[0].to_stage != ModelStage.RESEARCH
            or events[0].at < artifact.registered_at
        ):
            raise ValueError("registry must start with research registration")
        for event in events[1:]:
            allowed = {
                ModelStage.RESEARCH: {ModelStage.CHALLENGER, ModelStage.RETIRED},
                ModelStage.CHALLENGER: {ModelStage.SHADOW, ModelStage.DEGRADED, ModelStage.RETIRED},
                ModelStage.SHADOW: {ModelStage.DEGRADED, ModelStage.RETIRED},
                ModelStage.DEGRADED: {ModelStage.RETIRED},
                ModelStage.RETIRED: set(),
            }
            if event.from_stage is None or event.to_stage not in allowed.get(
                event.from_stage, set()
            ):
                raise ValueError("stored registry contains an unavailable lifecycle transition")
            if event.to_stage in {ModelStage.CHALLENGER, ModelStage.SHADOW}:
                if event.policy is None or event.evidence_id is None:
                    raise ValueError("stored promotion lacks immutable policy/evidence")
                self._gate(
                    artifact, self.repository.get(event.evidence_id), event.policy, event.to_stage
                )
        return artifact, events

    def register(self, experiment_id: UUID, selected: str) -> ModelArtifact:
        report = self.repository.get(experiment_id)
        if report is None or report.stage != "EXPERIMENTS":
            raise LookupError("complete experiment report required")
        plan = self.repository.plan(report.study_id)
        assert plan is not None
        variant = next((v for v in plan.variants if v.name == selected), None)
        if variant is None:
            raise LookupError("selected variant not found")
        data = dict(
            model_version=variant.config.strategy.model_version,
            experiment_id=experiment_id,
            selected_variant=selected,
            bundle_hash=bundle(report, selected),
        )
        draft = ModelArtifact.model_construct(
            model_version=variant.config.strategy.model_version,
            experiment_id=experiment_id,
            selected_variant=selected,
            bundle_hash=bundle(report, selected),
            artifact_id=UUID(int=0),
            registered_at=utc(self.clock.now()),
        )
        data["artifact_id"] = uuid5(
            NAMESPACE_URL,
            "pocket-alpha-model:"
            + digest(draft.model_dump(mode="json", exclude={"artifact_id", "registered_at"})),
        )
        data["registered_at"] = draft.registered_at
        artifact = ModelArtifact.model_validate(data)
        if artifact.registered_at < report.generated_at:
            raise ValueError("cannot register future experiment evidence")
        stored = self.get(artifact.artifact_id)
        if stored is not None:
            return stored[0]
        session = self.repository.session
        with session.begin_nested():
            session.add(
                RegistryRecord(
                    artifact_id=artifact.artifact_id, revision=0, payload=artifact.model_dump_json()
                )
            )
            session.flush()
            self._event(
                artifact.artifact_id,
                0,
                None,
                ModelStage.RESEARCH,
                "Registered immutable research bundle",
                None,
                None,
                None,
            )
        return artifact

    def transition(
        self,
        artifact_id: UUID,
        expected_revision: int,
        target: ModelStage,
        reason: str,
        evidence_id: UUID | None = None,
        policy: PromotionPolicy | None = None,
    ) -> RegistryEvent:
        stored = self.get(artifact_id)
        if stored is None:
            raise LookupError("model artifact not found")
        artifact, events = stored
        previous = events[-1]
        if previous.revision != expected_revision:
            raise RegistryConflict("registry revision changed")
        allowed = {
            ModelStage.RESEARCH: {ModelStage.CHALLENGER, ModelStage.RETIRED},
            ModelStage.CHALLENGER: {ModelStage.SHADOW, ModelStage.DEGRADED, ModelStage.RETIRED},
            ModelStage.SHADOW: {ModelStage.DEGRADED, ModelStage.RETIRED},
            ModelStage.PRODUCTION: {ModelStage.DEGRADED, ModelStage.RETIRED},
            ModelStage.DEGRADED: {ModelStage.RETIRED},
            ModelStage.RETIRED: set(),
        }
        if target not in allowed[previous.to_stage]:
            raise ValueError("transition unavailable; production promotion is disabled")
        evidence = None
        if target in {ModelStage.CHALLENGER, ModelStage.SHADOW}:
            if policy is None or evidence_id is None:
                raise ValueError("promotion requires explicit policy and immutable OOS evidence")
            policy = PromotionPolicy.model_validate_json(policy.model_dump_json())
            evidence = self.repository.get(evidence_id)
            self._gate(artifact, evidence, policy, target)
        session = self.repository.session
        with session.begin_nested():
            result = session.execute(
                update(RegistryRecord)
                .where(
                    RegistryRecord.artifact_id == artifact_id,
                    RegistryRecord.revision == expected_revision,
                )
                .values(revision=expected_revision + 1)
            )
            if cast(CursorResult[object], result).rowcount != 1:
                raise RegistryConflict("concurrent registry transition")
            return self._event(
                artifact_id,
                expected_revision + 1,
                previous,
                target,
                reason,
                evidence,
                policy,
                evidence_id,
            )

    def _gate(
        self,
        artifact: ModelArtifact,
        evidence: ResearchReport | None,
        policy: PromotionPolicy,
        target: ModelStage,
    ) -> None:
        experiment = self.repository.get(artifact.experiment_id)
        assert experiment is not None
        if (
            evidence is None
            or evidence.origin != "REAL"
            or evidence.study_id != experiment.study_id
        ):
            raise ValueError("promotion requires real evidence from the same sealed study")
        if target == ModelStage.CHALLENGER and evidence.report_id != experiment.report_id:
            raise ValueError("challenger requires sealed out-of-sample experiments")
        if target == ModelStage.SHADOW and (
            evidence.stage != "FINAL_HOLDOUT"
            or evidence.selected_variant != artifact.selected_variant
        ):
            raise ValueError("shadow requires one-shot final holdout for frozen selection")
        trials = [
            t
            for t in evidence.trials
            if t.variant == artifact.selected_variant and t.partition in {"TEST", "FINAL_HOLDOUT"}
        ]
        if len({t.asset_id for t in trials}) < policy.minimum_assets:
            raise ValueError("insufficient cross-asset evidence")
        experiment_tests = [
            t
            for t in experiment.trials
            if t.variant == artifact.selected_variant and t.partition == "TEST"
        ]
        if len({t.fold for t in experiment_tests}) < policy.minimum_test_folds:
            raise ValueError("insufficient temporal OOS folds")
        plan = self.repository.plan(experiment.study_id)
        assert plan is not None
        stress_names = {v.name for v in plan.variants if v.role == "COST_STRESS"}
        if policy.require_cost_stress and not stress_names:
            raise ValueError("cost stress evidence required")
        checked = trials + experiment_tests
        if policy.require_cost_stress:
            checked.extend(
                t for t in experiment.trials if t.variant in stress_names and t.partition == "TEST"
            )
        for trial in checked:
            backtest = BacktestRepository(self.repository.session).get(trial.backtest_id)
            assert backtest is not None
            metrics = {m.name: m.value for m in backtest.metrics}
            economic_gate(metrics, policy)
        baseline = next(v.name for v in plan.variants if v.role == "BASELINE")
        if artifact.selected_variant != baseline:
            for trial in experiment_tests:
                reference = next(
                    t
                    for t in experiment.trials
                    if t.source_id == trial.source_id
                    and t.fold == trial.fold
                    and t.partition == "TEST"
                    and t.variant == baseline
                )
                candidate = BacktestRepository(self.repository.session).get(trial.backtest_id)
                base = BacktestRepository(self.repository.session).get(reference.backtest_id)
                assert candidate is not None and base is not None
                c = next(m.value for m in candidate.metrics if m.name == "net_return")
                b = next(m.value for m in base.metrics if m.name == "net_return")
                assert c is not None and b is not None
                if baseline_improvement(c, b) < policy.minimum_baseline_improvement:
                    raise ValueError("complexity does not improve OOS baseline economics")

    def _event(
        self,
        artifact_id: UUID,
        revision: int,
        previous: RegistryEvent | None,
        target: ModelStage,
        reason: str,
        evidence: ResearchReport | None,
        policy: PromotionPolicy | None,
        evidence_id: UUID | None,
    ) -> RegistryEvent:
        now = utc(self.clock.now())
        if previous and now < previous.at:
            raise ValueError("registry clock moved backwards")
        if evidence is not None and now < evidence.generated_at:
            raise ValueError("promotion evidence cannot come from the future")
        draft = RegistryEvent.model_construct(
            artifact_id=artifact_id,
            revision=revision,
            from_stage=previous.to_stage if previous else None,
            to_stage=target,
            at=now,
            reason=reason,
            evidence_id=evidence.report_id if evidence else None,
            evidence_hash=evidence.content_hash if evidence else None,
            policy=policy,
            previous_hash=previous.content_hash if previous else None,
            content_hash="0" * 64,
        )
        event = RegistryEvent.model_validate(
            draft.model_dump()
            | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
        )
        self.repository.session.add(
            RegistryEventRecord(
                artifact_id=artifact_id,
                revision=revision,
                content_hash=event.content_hash,
                payload=event.model_dump_json(),
            )
        )
        self.repository.session.flush()
        return event


def economic_gate(metrics: dict[str, Decimal | None], policy: PromotionPolicy) -> None:
    policy = PromotionPolicy.model_validate_json(policy.model_dump_json())
    if any(v is not None and not v.is_finite() for v in metrics.values()):
        raise ValueError("economic metrics must be finite")
    thresholds = (
        ("net_return", policy.minimum_net_return),
        ("net_expectancy_per_round_trip", policy.minimum_net_expectancy),
        ("completed_round_trips", Decimal(policy.minimum_completed_trades)),
    )
    for name, limit in thresholds:
        value = metrics.get(name)
        if value is None or value < limit:
            raise ValueError("net OOS economic criteria failed or unavailable")
    dd = metrics.get("maximum_drawdown")
    if dd is None or dd > policy.maximum_drawdown or metrics.get("bankruptcy_events") != 0:
        raise ValueError("drawdown/bankruptcy criteria failed")


def baseline_improvement(candidate: Decimal, reference: Decimal) -> Decimal:
    if not candidate.is_finite() or not reference.is_finite():
        raise ValueError("baseline economics must be finite")
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return candidate - reference
