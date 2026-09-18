import json
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.backtesting.models import digest
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.common.clock import utc
from pocket_alpha.database import Base
from pocket_alpha.market_data.datasets import DatasetRepository
from pocket_alpha.research.models import ResearchReport, StudyPlan
from pocket_alpha.research.temporal import economic_key, subset


class StudyRecord(Base):
    __tablename__ = "research_studies"
    study_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    plan_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ResearchRecord(Base):
    __tablename__ = "research_reports"
    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("research_studies.study_id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class HoldoutRecord(Base):
    __tablename__ = "research_holdout_consumption"
    asset_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("research_studies.study_id"))
    selection_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ConflictingResearch(Exception):
    pass


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _insert(
        self, table: type[StudyRecord] | type[ResearchRecord], values: dict[str, object], key: str
    ) -> None:
        dialect = self.session.get_bind().dialect.name
        if dialect not in {"sqlite", "postgresql"}:
            raise ValueError("unsupported research storage dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        self.session.execute(
            insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
        )
        self.session.flush()

    def plan(self, study_id: UUID) -> StudyPlan | None:
        row = self.session.get(StudyRecord, study_id)
        if row is None:
            return None
        plan = StudyPlan.model_validate_json(row.payload)
        if row.study_id != plan.study_id or row.plan_hash != digest(plan):
            raise ValueError("research plan index mismatch")
        origins = set()
        assets = set()
        for source in plan.sources:
            dataset = DatasetRepository(self.session).get(source.dataset_id)
            if dataset is None or dataset.content_hash != source.dataset_hash:
                raise ValueError("research source missing or corrupted")
            origins.add(dataset.inputs.origin)
            assets.add(economic_key(dataset))
        if len(origins) != 1 or len(assets) != len(plan.sources):
            raise ValueError("study requires one origin and distinct assets")
        return plan

    def put_plan(self, plan: StudyPlan) -> StudyPlan:
        plan = StudyPlan.model_validate_json(plan.model_dump_json())
        with self.session.begin_nested():
            self._insert(
                StudyRecord,
                dict(
                    study_id=plan.study_id, plan_hash=digest(plan), payload=plan.model_dump_json()
                ),
                "study_id",
            )
            stored = self.plan(plan.study_id)
            assert stored is not None
            if stored != plan:
                raise ConflictingResearch("study identity already has different parameters")
            return stored

    def get(self, report_id: UUID) -> ResearchReport | None:
        row = self.session.get(ResearchRecord, report_id)
        if row is None:
            return None
        report = ResearchReport.model_validate_json(row.payload)
        if (report.report_id, report.study_id, report.content_hash) != (
            row.report_id,
            row.study_id,
            row.content_hash,
        ):
            raise ValueError("research report index mismatch")
        self._check(report)
        return report

    def _check(self, report: ResearchReport) -> None:
        plan = self.plan(report.study_id)
        if plan is None or report.plan_hash != digest(plan):
            raise ValueError("research report plan missing or corrupted")
        ids = tuple(f.forecast_id for f, _ in report.calibration_inputs)
        if ids != (plan.calibration_forecast_ids if report.stage == "EXPERIMENTS" else ()):
            raise ValueError("calibration inputs do not match sealed plan")
        from pocket_alpha.forecasts.storage import ForecastRepository

        ledger = ForecastRepository(self.session)
        for forecast, outcome in report.calibration_inputs:
            if (
                ledger.forecast(forecast.forecast_id) != forecast
                or ledger.outcome(forecast.forecast_id) != outcome
            ):
                raise ValueError("calibration ledger artifact mismatch")
            sources = [DatasetRepository(self.session).get(s.dataset_id) for s in plan.sources]
            if not any(
                d is not None
                and (forecast.market_id, forecast.asset_id)
                == (d.inputs.market.market_id, d.inputs.asset.asset_id)
                for d in sources
            ):
                raise ValueError("calibration asset does not match study")
            if not any(
                f.validation.start <= forecast.generated_at < f.validation.end
                or f.test.start <= forecast.generated_at < f.test.end
                for f in plan.folds
            ):
                raise ValueError("calibration requires out-of-sample forecasts")
            if not any(
                (forecast.model_version, forecast.horizon)
                == (v.config.strategy.model_version, v.horizon)
                for v in plan.variants
            ):
                raise ValueError("calibration model/horizon does not match study")
            if (
                max(outcome.observation_available_at, outcome.recorded_at)
                >= plan.final_holdout.start
            ):
                raise ValueError("calibration outcomes cannot consume final holdout")
        expected: set[tuple[UUID, str, str, str, str | None]] = set()
        for source in plan.sources:
            for variant in plan.variants:
                if report.stage == "FINAL_HOLDOUT":
                    if variant.name == report.selected_variant:
                        expected.add(
                            (
                                source.dataset_id,
                                plan.folds[-1].name,
                                variant.name,
                                "FINAL_HOLDOUT",
                                None,
                            )
                        )
                else:
                    for fold in plan.folds:
                        for partition in ("VALIDATION", "TEST"):
                            expected.add(
                                (source.dataset_id, fold.name, variant.name, partition, None)
                            )
                        for segment in plan.segments:
                            if (
                                fold.test.start <= segment.window.start
                                and segment.window.end <= fold.test.end
                            ):
                                expected.add(
                                    (
                                        source.dataset_id,
                                        fold.name,
                                        variant.name,
                                        "REGIME",
                                        segment.name,
                                    )
                                )
        actual = {(t.source_id, t.fold, t.variant, t.partition, t.regime) for t in report.trials}
        if actual != expected or report.declared_trials != len(plan.sources) * len(
            plan.variants
        ) * (2 * len(plan.folds) + len(plan.segments)):
            raise ValueError("research matrix incomplete or trial accounting incorrect")
        for trial in report.trials:
            backtest = BacktestRepository(self.session).get(trial.backtest_id)
            source_data = DatasetRepository(self.session).get(trial.source_id)
            if (
                source_data is None
                or backtest is None
                or backtest.content_hash != trial.backtest_hash
            ):
                raise ValueError("research trial source/backtest missing or corrupted")
            fold = next(f for f in plan.folds if f.name == trial.fold)
            variant = next(v for v in plan.variants if v.name == trial.variant)
            window = (
                plan.final_holdout
                if trial.partition == "FINAL_HOLDOUT"
                else fold.validation
                if trial.partition == "VALIDATION"
                else fold.test
                if trial.partition == "TEST"
                else next(s.window for s in plan.segments if s.name == trial.regime)
            )
            evaluation = subset(source_data, window)
            training = subset(source_data, fold.train)
            expected_config = variant.config.model_dump() | dict(
                evaluation_split="FINAL_HOLDOUT"
                if trial.partition == "FINAL_HOLDOUT"
                else "VALIDATION"
            )
            if (
                backtest.dataset_id != evaluation.dataset_id
                or trial.train_hash != training.content_hash
                or trial.asset_id != source_data.inputs.asset.asset_id
                or trial.horizon != variant.horizon
                or backtest.config.model_dump() != expected_config
                or report.origin != source_data.inputs.origin
                or backtest.generated_at > report.generated_at
            ):
                raise ValueError("research trial does not match sealed plan")
            from pocket_alpha.research.diagnostics import drift, resample
            from pocket_alpha.research.service import close_returns

            expected_diagnostics = resample(backtest, plan.analysis) + drift(
                close_returns(training), close_returns(evaluation)
            )
            if trial.diagnostics != expected_diagnostics:
                raise ValueError("research diagnostics do not match immutable trial inputs")
        if report.stage == "FINAL_HOLDOUT":
            for trial in report.trials:
                final_source = DatasetRepository(self.session).get(trial.source_id)
                assert final_source is not None
                claim = self.session.get(HoldoutRecord, economic_key(final_source))
                if (
                    claim is None
                    or claim.study_id != report.study_id
                    or claim.selection_hash
                    != digest(dict(plan_hash=report.plan_hash, selected=report.selected_variant))
                ):
                    raise ValueError("final research lacks persisted holdout consumption")
                experiments_id = uuid5(
                    NAMESPACE_URL,
                    "pocket-alpha-research:"
                    + digest(
                        dict(study_id=str(report.study_id), stage="EXPERIMENTS", selected=None)
                    ),
                )
                experiments = self.get(experiments_id)
                if experiments is None:
                    raise ValueError("final research lacks sealed experiments")
                frozen = next(
                    t
                    for t in experiments.trials
                    if t.source_id == trial.source_id
                    and t.fold == trial.fold
                    and t.variant == trial.variant
                    and t.partition == "TEST"
                )
                consumption = json.loads(claim.payload)
                if (
                    not isinstance(consumption, dict)
                    or set(consumption)
                    != {"plan_hash", "selected", "experiments_hash", "consumed_at"}
                    or not isinstance(consumption["consumed_at"], str)
                ):
                    raise ValueError("holdout consumption payload malformed")
                if (
                    trial.fitted_artifact_json != frozen.fitted_artifact_json
                    or consumption.get("plan_hash") != report.plan_hash
                    or consumption.get("selected") != report.selected_variant
                    or consumption.get("experiments_hash") != experiments.content_hash
                    or utc(datetime.fromisoformat(consumption["consumed_at"])) > report.generated_at
                ):
                    raise ValueError("final selection/artifact/consumption evidence changed")

    def put(self, report: ResearchReport) -> ResearchReport:
        report = ResearchReport.model_validate_json(report.model_dump_json())
        self._check(report)
        with self.session.begin_nested():
            self._insert(
                ResearchRecord,
                dict(
                    report_id=report.report_id,
                    study_id=report.study_id,
                    content_hash=report.content_hash,
                    payload=report.model_dump_json(),
                ),
                "report_id",
            )
            stored = self.get(report.report_id)
            assert stored is not None
            if stored.content_hash != report.content_hash:
                raise ConflictingResearch("same research plan produced different results")
            return stored
