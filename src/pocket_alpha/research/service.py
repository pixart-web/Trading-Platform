import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.inputs import ResearchStrategy
from pocket_alpha.backtesting.models import RunConfig, digest
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.forecasts.models import Forecast, ForecastOutcome
from pocket_alpha.forecasts.storage import ForecastRepository
from pocket_alpha.market_data.datasets import DatasetRepository, MarketDataset, MarketDatasetRecord
from pocket_alpha.research.diagnostics import calibration, drift, resample
from pocket_alpha.research.models import ResearchReport, StudyPlan, Trial, Variant, Window
from pocket_alpha.research.storage import HoldoutRecord, ResearchRepository
from pocket_alpha.research.temporal import economic_key, subset


class ResearchFactory(Protocol):
    def fit(self, training: MarketDataset, variant: Variant) -> str:
        """Return canonical JSON using training data only; no final/test data is supplied."""
        ...

    def materialize(self, artifact_json: str, variant: Variant) -> ResearchStrategy:
        """Create a fresh independent callback instance for each evaluation window."""
        ...


class HoldoutConsumed(Exception):
    pass


def close_returns(data: MarketDataset) -> tuple[Decimal, ...]:
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return tuple(
            b.close / a.close - 1
            for a, b in zip(data.inputs.candles, data.inputs.candles[1:], strict=False)
        )


class ResearchService:
    def __init__(self, repository: ResearchRepository, clock: Clock) -> None:
        self.repository, self.clock = repository, clock

    def run(self, plan: StudyPlan, factory: ResearchFactory) -> ResearchReport:
        with self.repository.session.begin_nested():
            plan = self.repository.put_plan(plan)
            return self._evaluate(plan, factory, None)

    def _evaluate(
        self, plan: StudyPlan, factory: ResearchFactory, selected: str | None
    ) -> ResearchReport:
        session = self.repository.session
        trials: list[Trial] = []
        origin = None
        for source in plan.sources:
            dataset = DatasetRepository(session).get(source.dataset_id)
            assert dataset is not None
            origin = dataset.inputs.origin
            variants = tuple(v for v in plan.variants if selected is None or v.name == selected)
            evaluation_folds = plan.folds if selected is None else (plan.folds[-1],)
            for fold in evaluation_folds:
                training = subset(dataset, fold.train)
                for variant in variants:
                    # Numeric changes in fitting/materialization cannot alter research accounting.
                    if selected is None:
                        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                            artifact = factory.fit(training, variant)
                    else:
                        experiments_id = uuid5(
                            NAMESPACE_URL,
                            "pocket-alpha-research:"
                            + digest(
                                dict(
                                    study_id=str(plan.study_id), stage="EXPERIMENTS", selected=None
                                )
                            ),
                        )
                        experiments = self.repository.get(experiments_id)
                        assert experiments is not None
                        frozen = next(
                            t
                            for t in experiments.trials
                            if t.source_id == source.dataset_id
                            and t.fold == fold.name
                            and t.variant == selected
                            and t.partition == "TEST"
                        )
                        if frozen.train_hash != training.content_hash:
                            raise ValueError(
                                "final training identity differs from sealed experiments"
                            )
                        artifact = frozen.fitted_artifact_json
                    if not isinstance(artifact, str) or not 2 <= len(artifact) <= 65536:
                        raise ValueError("fitted research artifact must be bounded JSON")
                    parsed = json.loads(artifact)
                    if (
                        not isinstance(parsed, dict)
                        or json.dumps(
                            parsed, sort_keys=True, separators=(",", ":"), allow_nan=False
                        )
                        != artifact
                    ):
                        raise ValueError("fitted research artifact must be a canonical JSON object")
                    if selected is not None:
                        windows: list[
                            tuple[
                                Literal["VALIDATION", "TEST", "REGIME", "FINAL_HOLDOUT"],
                                str | None,
                                Window,
                            ]
                        ] = [("FINAL_HOLDOUT", None, plan.final_holdout)]
                    else:
                        windows = [("VALIDATION", None, fold.validation), ("TEST", None, fold.test)]
                        windows.extend(
                            ("REGIME", segment.name, segment.window)
                            for segment in plan.segments
                            if fold.test.start <= segment.window.start
                            and segment.window.end <= fold.test.end
                        )
                    for partition, regime, window in windows:
                        trials.append(
                            self._trial(
                                dataset,
                                training,
                                variant,
                                fold.name,
                                partition,
                                regime,
                                window,
                                artifact,
                                factory,
                                plan,
                                selected is not None,
                            )
                        )
        assert origin is not None
        stage = "EXPERIMENTS" if selected is None else "FINAL_HOLDOUT"
        report_id = uuid5(
            NAMESPACE_URL,
            "pocket-alpha-research:"
            + digest(dict(study_id=str(plan.study_id), stage=stage, selected=selected)),
        )
        calibration_inputs: list[tuple[Forecast, ForecastOutcome]] = []
        if selected is None:
            ledger = ForecastRepository(session)
            for forecast_id in plan.calibration_forecast_ids:
                forecast = ledger.forecast(forecast_id)
                outcome = ledger.outcome(forecast_id)
                if outcome is None:
                    raise LookupError("calibration outcome missing; research is not ready")
                calibration_inputs.append((forecast, outcome))
        generated_at = utc(self.clock.now())
        draft = ResearchReport.model_construct(
            report_id=report_id,
            study_id=plan.study_id,
            plan_hash=digest(plan),
            stage=stage,
            selected_variant=selected,
            generated_at=generated_at,
            calibration_inputs=tuple(calibration_inputs),
            calibration_diagnostics=calibration(tuple(calibration_inputs), generated_at),
            trials=tuple(trials),
            declared_trials=len(plan.sources)
            * len(plan.variants)
            * (2 * len(plan.folds) + len(plan.segments)),
            origin=origin,
            warnings=(
                "MULTIPLE_TESTING_NO_CORRECTED_SIGNIFICANCE",
                "RESAMPLING_IS_DESCRIPTIVE_NOT_RUIN_PROBABILITY",
                "UNIVERSE_SELECTION_BIAS_UNASSESSED",
                "NO_AUTOMATIC_PROMOTION",
                "INDEPENDENT_FLAT_START_WINDOWS",
                "MODELED_EXECUTION_COSTS_UNVALIDATED",
            ),
            content_hash="0" * 64,
        )
        payload = draft.model_dump(mode="json")
        payload["content_hash"] = digest(
            draft.model_dump(mode="json", exclude={"content_hash", "generated_at"})
        )
        return self.repository.put(ResearchReport.model_validate(payload))

    def _trial(
        self,
        dataset: MarketDataset,
        training: MarketDataset,
        variant: Variant,
        fold: str,
        partition: Literal["VALIDATION", "TEST", "REGIME", "FINAL_HOLDOUT"],
        regime: str | None,
        window: Window,
        artifact: str,
        factory: ResearchFactory,
        plan: StudyPlan,
        final: bool,
    ) -> Trial:
        evaluation = subset(dataset, window)
        session = self.repository.session
        existing = session.get(MarketDatasetRecord, evaluation.dataset_id)
        if existing is None:
            session.add(
                MarketDatasetRecord(
                    dataset_id=evaluation.dataset_id, payload=evaluation.model_dump_json()
                )
            )
            session.flush()
        elif existing.payload != evaluation.model_dump_json():
            raise ValueError("derived research dataset identity conflict")
        config = RunConfig.model_validate(
            variant.config.model_dump()
            | dict(evaluation_split="FINAL_HOLDOUT" if final else "VALIDATION")
        )
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            strategy = factory.materialize(artifact, variant)
        report = Backtester(self.clock)._run(
            evaluation, config, strategy, (), final_authorized=final
        )
        report = BacktestRepository(session).put(report)
        analysis = resample(report, plan.analysis) + drift(
            close_returns(training), close_returns(evaluation)
        )
        return Trial(
            source_id=dataset.dataset_id,
            asset_id=dataset.inputs.asset.asset_id,
            fold=fold,
            variant=variant.name,
            partition=partition,
            horizon=variant.horizon,
            regime=regime,
            train_hash=training.content_hash,
            fitted_artifact_json=artifact,
            fitted_artifact_hash=digest(json.loads(artifact)),
            backtest_id=report.run_id,
            backtest_hash=report.content_hash,
            diagnostics=analysis,
        )


def consume_final(
    engine: Engine, study_id: UUID, selected: str, factory: ResearchFactory, clock: Clock
) -> ResearchReport:
    # This operation owns durable transactions. A claim commits before any callback sees final data.
    with Session(engine) as session:
        repository = ResearchRepository(session)
        plan = repository.plan(study_id)
        if plan is None or selected not in {v.name for v in plan.variants}:
            raise LookupError("sealed study/selection not found")
        experiments_id = uuid5(
            NAMESPACE_URL,
            "pocket-alpha-research:"
            + digest(dict(study_id=str(study_id), stage="EXPERIMENTS", selected=None)),
        )
        experiments = repository.get(experiments_id)
        if experiments is None:
            raise ValueError("complete experiments must be committed before final consumption")
        selection_hash = digest(dict(plan_hash=digest(plan), selected=selected))
        payload = json.dumps(
            dict(
                plan_hash=digest(plan),
                selected=selected,
                experiments_hash=experiments.content_hash,
                consumed_at=utc(clock.now()).isoformat(),
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        for source in plan.sources:
            dataset = DatasetRepository(session).get(source.dataset_id)
            assert dataset is not None
            session.add(
                HoldoutRecord(
                    asset_id=economic_key(dataset),
                    study_id=study_id,
                    selection_hash=selection_hash,
                    payload=payload,
                )
            )
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HoldoutConsumed(
                "asset final holdout already consumed; retries/tuning forbidden"
            ) from error
    with Session(engine) as session:
        repository = ResearchRepository(session)
        report = ResearchService(repository, clock)._evaluate(plan, factory, selected)
        session.commit()
        return report
