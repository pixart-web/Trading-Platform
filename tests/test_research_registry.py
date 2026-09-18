from decimal import Decimal

import pytest

from pocket_alpha.backtesting.models import digest
from pocket_alpha.forecasts.models import ModelStage
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.research.registry import (
    ModelRegistry,
    PromotionPolicy,
    RegistryConflict,
    RegistryEventRecord,
    RegistryRecord,
)
from pocket_alpha.research.service import ResearchService
from pocket_alpha.research.storage import ResearchRepository
from tests.research_fixtures import CLOCK, Factory, plan, seed


def policy() -> PromotionPolicy:
    return PromotionPolicy(
        version="synthetic-explicit-gates-1",
        minimum_net_return=Decimal("0.01"),
        minimum_net_expectancy=Decimal("0.01"),
        maximum_drawdown=Decimal("0.2"),
        minimum_completed_trades=1,
        minimum_assets=1,
        minimum_test_folds=2,
        minimum_baseline_improvement=Decimal("0.001"),
        require_cost_stress=True,
    )


def test_registry_requires_oos_real_evidence_and_preserves_audit(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    report = ResearchService(storage, CLOCK).run(plan(seed(storage)), Factory())
    from datetime import timedelta

    from pocket_alpha.common.clock import FrozenClock

    with pytest.raises(ValueError, match="future"):
        ModelRegistry(storage, FrozenClock(CLOCK.now() - timedelta(seconds=1))).register(
            report.report_id, "quantity"
        )
    registry = ModelRegistry(storage, CLOCK)
    artifact = registry.register(report.report_id, "quantity")
    assert registry.register(report.report_id, "quantity") == artifact
    stored = registry.get(artifact.artifact_id)
    assert stored is not None and stored[1][0].to_stage == ModelStage.RESEARCH
    assert artifact.bundle_hash != digest([])
    future = report.model_copy(update={"generated_at": CLOCK.now() + timedelta(seconds=1)})
    with pytest.raises(ValueError, match="future"):
        registry._event(
            artifact.artifact_id,
            1,
            stored[1][0],
            ModelStage.CHALLENGER,
            "Future evidence must fail before persistence",
            future,
            policy(),
            future.report_id,
        )
    with pytest.raises(ValueError, match="real evidence"):
        registry.transition(
            artifact.artifact_id,
            0,
            ModelStage.CHALLENGER,
            "Synthetic is not evidence",
            report.report_id,
            policy(),
        )
    with pytest.raises(ValueError, match="explicit policy"):
        registry.transition(artifact.artifact_id, 0, ModelStage.CHALLENGER, "No thresholds")
    with pytest.raises(ValueError, match="disabled"):
        registry.transition(
            artifact.artifact_id, 0, ModelStage.PRODUCTION, "Cannot jump to production"
        )
    retired = registry.transition(
        artifact.artifact_id, 0, ModelStage.RETIRED, "Losing research retained"
    )
    assert retired.previous_hash == stored[1][0].content_hash
    latest = registry.get(artifact.artifact_id)
    assert latest is not None and latest[1][-1] == retired
    with pytest.raises(RegistryConflict):
        registry.transition(artifact.artifact_id, 0, ModelStage.RETIRED, "Stale revision")
    with pytest.raises(ValueError):
        registry.transition(artifact.artifact_id, 1, ModelStage.RESEARCH, "Cannot restore retired")


def test_registry_chain_corruption_cannot_be_read_as_promoted_model(
    repository: MarketRepository,
) -> None:
    storage = ResearchRepository(repository.session)
    report = ResearchService(storage, CLOCK).run(plan(seed(storage)), Factory())
    registry = ModelRegistry(storage, CLOCK)
    artifact = registry.register(report.report_id, "baseline")
    head = repository.session.get(RegistryRecord, artifact.artifact_id)
    assert head is not None
    head.revision = 1
    repository.session.flush()
    with pytest.raises(ValueError, match="history"):
        registry.get(artifact.artifact_id)
    head.revision = 0
    event = repository.session.get(RegistryEventRecord, (artifact.artifact_id, 0))
    assert event is not None
    event.content_hash = "0" * 64
    repository.session.flush()
    with pytest.raises(ValueError, match="chain"):
        registry.get(artifact.artifact_id)


@pytest.mark.parametrize(
    "change",
    [
        {"net_return": Decimal("-0.1")},
        {"net_expectancy_per_round_trip": None},
        {"completed_round_trips": Decimal(0)},
        {"maximum_drawdown": Decimal("0.3")},
        {"bankruptcy_events": Decimal(1)},
    ],
)
def test_explicit_economic_thresholds_fail_closed(change: dict[str, Decimal | None]) -> None:
    from pocket_alpha.research.registry import economic_gate

    metrics: dict[str, Decimal | None] = {
        "net_return": Decimal("0.02"),
        "net_expectancy_per_round_trip": Decimal(1),
        "completed_round_trips": Decimal(10),
        "maximum_drawdown": Decimal("0.1"),
        "bankruptcy_events": Decimal(0),
    }
    economic_gate(metrics, policy())
    with pytest.raises(ValueError):
        economic_gate(metrics | change, policy())


def test_baseline_comparison_is_independent_of_caller_decimal_precision() -> None:
    from decimal import localcontext

    from pocket_alpha.research.registry import baseline_improvement

    candidate = Decimal("0.1000000000000000000000000000001")
    with localcontext() as context:
        context.prec = 2
        assert baseline_improvement(candidate, Decimal("0.1")) == Decimal("1e-31")
    with pytest.raises(ValueError):
        baseline_improvement(Decimal("Infinity"), Decimal(0))
