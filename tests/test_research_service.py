from decimal import Decimal
from uuid import uuid4

import pytest

from pocket_alpha.backtesting.models import digest
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.market_data.datasets import MarketDataset
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.research.models import ResearchReport, StudyPlan, Variant
from pocket_alpha.research.service import ResearchService
from pocket_alpha.research.storage import ConflictingResearch, ResearchRecord, ResearchRepository
from tests.research_fixtures import CLOCK, Factory, plan, seed


def test_complete_matrix_losing_trials_fresh_callbacks_and_reproducibility(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    data = seed(storage)
    study = plan(data)
    factory = Factory()
    first = ResearchService(storage, CLOCK).run(study, factory)
    assert first.declared_trials == 15 and len(first.trials) == 15
    assert len(factory.training) == 6 and len(factory.callbacks) == 15
    assert len({id(c) for c in factory.callbacks}) == 15
    assert all(d.inputs.query.end < study.final_holdout.start for d in factory.training)
    assert all(t.partition != "FINAL_HOLDOUT" for t in first.trials)
    assert {t.variant for t in first.trials} == {"baseline", "quantity", "stress"}
    assert {t.regime for t in first.trials} == {None, "declared-regime"}
    for trial in first.trials:
        backtest = BacktestRepository(repository.session).get(trial.backtest_id)
        assert backtest is not None
        assert all(f.risk_id for f in backtest.fills)
        if trial.partition != "REGIME":
            net = next(m.value for m in backtest.metrics if m.name == "net_return")
            assert net is not None and net < Decimal(0)
    assert not first.profitability_claim and not first.live_ready
    assert storage.get(first.report_id) == first
    assert ResearchService(storage, CLOCK).run(study, Factory()) == first
    assert storage.get(uuid4()) is None


def test_artifact_and_index_corruption_cannot_be_research_evidence(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    report = ResearchService(storage, CLOCK).run(plan(seed(storage)), Factory())
    payload = report.model_dump(mode="json")
    payload["trials"][0]["fitted_artifact_json"] = "{}"
    with pytest.raises(ValueError):
        ResearchReport.model_validate(payload)
    row = repository.session.get(ResearchRecord, report.report_id)
    assert row is not None
    row.content_hash = "0" * 64
    repository.session.flush()
    with pytest.raises(ValueError, match="index"):
        storage.get(report.report_id)


def test_incomplete_matrix_even_with_rehashed_payload_is_rejected(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    report = ResearchService(storage, CLOCK).run(plan(seed(storage)), Factory())
    payload = report.model_dump(mode="json")
    payload["trials"] = payload["trials"][:-1]
    payload["content_hash"] = digest(
        {k: v for k, v in payload.items() if k not in {"content_hash", "generated_at"}}
    )
    altered = ResearchReport.model_validate(payload)
    with pytest.raises(ValueError, match="matrix"):
        storage.put(altered)
    assert storage.get(report.report_id) == report


def test_distinct_result_same_manifest_is_not_silently_replaced(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    study = plan(seed(storage))
    first = ResearchService(storage, CLOCK).run(study, Factory())
    payload = first.model_dump(mode="json")
    payload["warnings"].append("DIFFERENT_RESULT")
    payload["content_hash"] = digest(
        {k: v for k, v in payload.items() if k not in {"content_hash", "generated_at"}}
    )
    with pytest.raises(ConflictingResearch):
        storage.put(ResearchReport.model_validate(payload))
    assert storage.get(first.report_id) == first


def test_future_training_failure_rolls_back_artifacts(repository: MarketRepository) -> None:
    storage = ResearchRepository(repository.session)
    study = plan(seed(storage))

    class Failing(Factory):
        def fit(self, training: MarketDataset, variant: Variant) -> str:
            raise RuntimeError("research dependency failed")

    with pytest.raises(RuntimeError):
        ResearchService(storage, CLOCK).run(study, Failing())
    assert storage.plan(study.study_id) is None


def test_calibration_artifacts_are_persisted_from_matching_oos_ledger(
    repository: MarketRepository,
) -> None:
    from datetime import timedelta

    from pocket_alpha.forecasts.service import ForecastLedger
    from pocket_alpha.forecasts.storage import ForecastRepository
    from tests.market_fixtures import START
    from tests.test_forecasts import forecast, outcome

    storage = ResearchRepository(repository.session)
    data = seed(storage)
    generated = START + timedelta(hours=19)
    f = forecast(
        market_id=data.inputs.market.market_id,
        asset_id=data.inputs.asset.asset_id,
        model_version="synthetic-model-1",
        generated_at=generated,
        expires_at=generated + timedelta(hours=1),
    )
    o = outcome(
        end_price_at=generated + timedelta(hours=1),
        observation_available_at=generated + timedelta(hours=2),
        recorded_at=generated + timedelta(hours=3),
    )
    ledger = ForecastLedger(ForecastRepository(repository.session), CLOCK)
    ledger.append_forecast(f)
    ledger.append_outcome(o)
    study = StudyPlan.model_validate(
        plan(data).model_dump() | dict(calibration_forecast_ids=(f.forecast_id,))
    )
    report = ResearchService(storage, CLOCK).run(study, Factory())
    assert report.calibration_inputs == ((f, o),)
    assert report.calibration_diagnostics[0].value == Decimal("0.14")
    assert storage.get(report.report_id) == report


def test_cross_asset_and_horizon_matrix_is_explicit(repository: MarketRepository) -> None:
    from datetime import timedelta
    from uuid import UUID

    from pocket_alpha.domain.models import ForecastHorizon
    from pocket_alpha.market_data.datasets import DatasetInputs, MarketDatasetRecord
    from pocket_alpha.research.models import Source, Variant, Window
    from pocket_alpha.research.temporal import folds
    from tests.market_fixtures import START

    storage = ResearchRepository(repository.session)
    first = seed(storage)
    values = first.inputs.model_dump(mode="json")
    for name in ("mapping", "market", "query"):
        values[name]["market_id"] = "simulation:ETH-USD"
    values["market"].update(asset_id="synthetic:ETH", symbol="ETH-USD")
    values["asset"].update(asset_id="synthetic:ETH", symbol="ETH", name="Synthetic Ethereum")
    values["mapping"]["instrument_id"] = "synthetic-eth-product"
    for candle in values["candles"]:
        candle["market_id"] = "simulation:ETH-USD"
    inputs = DatasetInputs.model_validate(values)
    second = MarketDataset(dataset_id=UUID(int=2202), inputs=inputs, content_hash=inputs.digest())
    repository.session.add(
        MarketDatasetRecord(dataset_id=second.dataset_id, payload=second.model_dump_json())
    )
    repository.session.flush()
    base = plan(first)
    variant = Variant.model_validate(
        base.variants[1].model_dump() | dict(horizon=ForecastHorizon.H4)
    )
    study = StudyPlan.model_validate(
        base.model_dump()
        | dict(
            sources=(
                *base.sources,
                Source(dataset_id=second.dataset_id, dataset_hash=second.content_hash),
            ),
            folds=folds(START, 8 * 3600, 8 * 3600, 4 * 3600, 1, "WALK_FORWARD"),
            variants=(base.variants[0], variant, base.variants[2]),
            segments=(),
            label_horizon_seconds=4 * 3600,
            final_holdout=Window(
                start=START + timedelta(hours=36), end=START + timedelta(hours=64)
            ),
        )
    )
    report = ResearchService(storage, CLOCK).run(study, Factory())
    assert len(report.trials) == 12
    assert {t.asset_id for t in report.trials} == {"synthetic:BTC", "synthetic:ETH"}
    assert {t.horizon for t in report.trials} == {ForecastHorizon.H1, ForecastHorizon.H4}
    assert storage.get(report.report_id) == report
