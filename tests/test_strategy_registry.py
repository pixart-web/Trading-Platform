"""Synthetic mechanics only; no economic qualification or real orders."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.backtesting.models import Intent
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.strategies.api import router
from pocket_alpha.strategies.models import StrategyStage
from pocket_alpha.strategies.registry import (
    StrategyConflict,
    StrategyEventRecord,
    StrategyRecord,
    StrategyRegistry,
)
from tests.backtest_fixtures import dataset
from tests.market_fixtures import START
from tests.strategy_fixtures import definition
from tests.test_paper_trading import CheckpointPlan, bar, setup


def registry(repository: MarketRepository) -> StrategyRegistry:
    data = dataset().inputs
    repository.register(data.asset, data.venue, data.market, data.mapping)
    return StrategyRegistry(repository.session, FrozenClock(START))


def test_immutable_registration_lifecycle_revision_and_chain(repository: MarketRepository) -> None:
    service = registry(repository)
    artifact = service.register(definition())
    assert service.register(definition()) == artifact
    assert service.ids() == (artifact.strategy_id,)
    changed = definition().model_copy(update={"maximum_data_age_seconds": 61})
    with pytest.raises(StrategyConflict):
        service.register(changed)
    service.clock = FrozenClock(START + timedelta(seconds=1))
    event = service.transition(
        artifact.strategy_id, 0, StrategyStage.SUSPENDED, "MANUAL_SUSPENSION"
    )
    assert event.previous_hash is not None and not artifact.live_ready
    with pytest.raises(StrategyConflict):
        service.transition(artifact.strategy_id, 0, StrategyStage.RETIRED, "STALE")
    service.clock = FrozenClock(START)
    with pytest.raises(ValueError, match="backwards"):
        service.transition(artifact.strategy_id, 1, StrategyStage.RETIRED, "CLOCK")
    service.clock = FrozenClock(START + timedelta(seconds=2))
    service.transition(artifact.strategy_id, 1, StrategyStage.RETIRED, "RETIRED")
    loaded = service.get(artifact.strategy_id)
    assert loaded is not None and len(loaded[1]) == 3
    with pytest.raises(ValueError):
        service.transition(artifact.strategy_id, 2, StrategyStage.RESEARCH, "RESUME")
    paper, state = setup(repository, CheckpointPlan({}))
    paper_loaded = paper.repository.load(state.account_id)
    assert paper_loaded is not None
    assert not service.operational(artifact.strategy_id, state.account_id, paper_loaded[0].config)


@pytest.mark.parametrize(
    "stage",
    [
        StrategyStage.CANDIDATE,
        StrategyStage.PAPER,
        StrategyStage.SHADOW,
        StrategyStage.LIVE_SMALL,
        StrategyStage.LIVE,
    ],
)
def test_unqualified_promotions_and_live_are_closed(
    repository: MarketRepository, stage: StrategyStage
) -> None:
    service = registry(repository)
    artifact = service.register(definition())
    with pytest.raises(ValueError):
        service.transition(artifact.strategy_id, 0, stage, "NO_EVIDENCE")
    loaded = service.get(artifact.strategy_id)
    assert loaded is not None and len(loaded[1]) == 1
    assert service.get(uuid4()) is None
    with pytest.raises(LookupError):
        service.transition(uuid4(), 0, StrategyStage.CANDIDATE, "UNKNOWN")


@pytest.mark.parametrize("case", ["head", "event", "index", "missing"])
def test_corrupted_registry_fails_closed(repository: MarketRepository, case: str) -> None:
    service = registry(repository)
    artifact = service.register(definition())
    head = repository.session.get(StrategyRecord, artifact.strategy_id)
    row = repository.session.get(StrategyEventRecord, (artifact.strategy_id, 0))
    assert head is not None and row is not None
    if case == "head":
        head.payload = head.payload.replace(artifact.definition_hash, "0" * 64)
    elif case == "event":
        row.payload = row.payload.replace("REGISTERED", "TAMPERED")
    elif case == "index":
        row.content_hash = "0" * 64
    else:
        repository.session.delete(row)
    repository.session.flush()
    with pytest.raises(ValueError):
        service.get(artifact.strategy_id)


def test_read_only_strategy_api_and_dependency_failure(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = registry(repository)
    artifact = service.register(definition())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    client = TestClient(app)
    response = client.get("/api/v1/strategies")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()[0][0]["live_ready"] is False
    assert client.get(f"/api/v1/strategies/{artifact.strategy_id}").status_code == 200
    assert client.get(f"/api/v1/strategies/{uuid4()}").status_code == 404
    assert client.post("/api/v1/strategies").status_code == 405

    def broken(self: StrategyRegistry, key: object) -> None:
        raise SQLAlchemyError("secret connection details")

    monkeypatch.setattr(StrategyRegistry, "get", broken)
    failed = client.get(f"/api/v1/strategies/{artifact.strategy_id}")
    assert failed.status_code == 503 and "secret" not in failed.text
    assert client.get("/api/v1/strategies").status_code == 503


def test_lifecycle_guard_cancels_before_pending_fill_and_replays(
    repository: MarketRepository,
) -> None:
    class GuardedPlan(CheckpointPlan):
        ready = True

        def preflight(self, account_id: object, config: object) -> bool:
            return self.ready

    plan = GuardedPlan({1: (Intent(client_id="entry", action="BUY", quantity=Decimal(2)),)})
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan, 0)
    state = bar(paper, state, plan, 1)
    assert state.portfolio.reserved_cash > 0 and not state.fills
    plan.ready = False
    state = bar(paper, state, plan, 2)
    assert state.status == "SUSPENDED" and state.portfolio.reserved_cash == 0
    assert state.fills == () and state.reason == "STRATEGY_NOT_READY"
    plan.ready = True
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None and loaded[1].state() == state


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing",
        "unqualified",
        "future",
        "synthetic",
        "identity",
        "horizon",
        "features",
        "gate",
    ],
)
def test_candidate_reuses_sealed_identity_and_economic_gate_contract(
    repository: MarketRepository,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    # Explicit mocks isolate qualification contracts. They are not real OOS evidence.
    from types import SimpleNamespace as NS

    from pocket_alpha.backtesting.models import digest
    from pocket_alpha.forecasts.models import ModelStage
    from pocket_alpha.research.registry import ModelRegistry
    from pocket_alpha.research.storage import ResearchRepository
    from pocket_alpha.strategies.registry import StrategyEvent
    from tests.strategy_fixtures import run_config
    from tests.test_research_registry import policy

    service = registry(repository)
    artifact = service.register(definition())
    model_id = uuid4()
    sealed = NS(content_hash="a" * 64, at=START, to_stage=ModelStage.CHALLENGER)
    if case == "unqualified":
        sealed.to_stage = ModelStage.RESEARCH
    if case == "future":
        sealed.at = START + timedelta(seconds=1)
    model = NS(experiment_id=uuid4(), selected_variant="mock-contract")
    monkeypatch.setattr(
        ModelRegistry, "get", lambda self, key: None if case == "missing" else (model, (sealed,))
    )
    report = NS(study_id=uuid4(), origin="SYNTHETIC" if case == "synthetic" else "REAL")
    monkeypatch.setattr(ResearchRepository, "get", lambda self, key: report)
    cfg = run_config()
    if case == "identity":
        cfg = cfg.model_copy(
            update={"strategy": cfg.strategy.model_copy(update={"model_version": "other"})}
        )
    if case == "features":
        cfg = cfg.model_copy(update={"feature_specs": ()})
    variant = NS(
        name="mock-contract",
        config=cfg,
        horizon=None if case == "horizon" else definition().horizon,
    )
    monkeypatch.setattr(ResearchRepository, "plan", lambda self, key: NS(variants=(variant,)))
    calls: list[object] = []

    def gate(self: object, model: object, report: object, selected: object, target: object) -> None:
        calls.append(selected)
        if case == "gate":
            raise ValueError("mock net OOS gate rejected")

    monkeypatch.setattr(ModelRegistry, "_gate", gate)
    draft = StrategyEvent.model_construct(
        strategy_id=artifact.strategy_id,
        revision=1,
        from_stage=StrategyStage.RESEARCH,
        to_stage=StrategyStage.CANDIDATE,
        at=START,
        reason="MOCK_CONTRACT",
        model_artifact_id=model_id,
        model_event_hash=sealed.content_hash,
        policy=policy(),
        content_hash="0" * 64,
    )
    event = StrategyEvent.model_validate(
        draft.model_dump()
        | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
    )
    if case == "valid":
        service._evidence(artifact, event, historical=False)
        assert calls == [policy()]
    else:
        with pytest.raises((ValueError, LookupError)):
            service._evidence(artifact, event, historical=False)


@pytest.mark.parametrize(
    "case",
    [
        "paper",
        "shadow",
        "source",
        "costs",
        "checkpoint",
        "future",
        "holdout",
        "empty",
        "return",
        "expectancy",
        "drawdown",
    ],
)
def test_paper_and_shadow_gate_contract_with_explicit_mock_evidence(
    repository: MarketRepository,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    # No fabricated economic DTOs: mocked evidence/runtime exercise only lifecycle mechanisms.
    from types import SimpleNamespace as NS

    from pocket_alpha.backtesting.models import digest
    from pocket_alpha.forecasts.models import ModelStage
    from pocket_alpha.paper_trading.storage import PaperRepository
    from pocket_alpha.research.registry import ModelRegistry
    from pocket_alpha.research.storage import ResearchRepository
    from pocket_alpha.strategies.registry import StrategyEvent
    from tests.strategy_fixtures import run_config
    from tests.test_research_registry import policy

    service = registry(repository)
    artifact = service.register(definition())
    cfg = run_config()
    model_id, paper_id = uuid4(), uuid4()
    model = NS(experiment_id=uuid4(), selected_variant="mock-contract")
    sealed = NS(
        content_hash="a" * 64,
        at=START,
        to_stage=ModelStage.CHALLENGER if case in {"paper", "holdout"} else ModelStage.SHADOW,
        evidence_id=uuid4(),
    )
    monkeypatch.setattr(ModelRegistry, "get", lambda self, key: (model, (sealed,)))
    report = NS(study_id=uuid4(), origin="REAL")
    monkeypatch.setattr(ResearchRepository, "get", lambda self, key: report)
    variant = NS(name="mock-contract", config=cfg, horizon=definition().horizon)
    monkeypatch.setattr(ResearchRepository, "plan", lambda self, key: NS(variants=(variant,)))
    gates: list[object] = []
    monkeypatch.setattr(
        ModelRegistry, "_gate", lambda self, model, report, policy, stage: gates.append(stage)
    )
    paper_cfg = NS(
        origin="REAL",
        market=NS(market_id=definition().market_id),
        asset=NS(asset_id=definition().asset_id),
        mapping=NS(source="other" if case == "source" else definition().source),
        timeframe=definition().timeframe,
        run=cfg.model_copy(update={"initial_cash": Decimal(9999)}) if case == "costs" else cfg,
    )

    class MockRuntime:
        def __init__(self, *args: object) -> None:
            self.revision = 0
            self.sim = NS(
                trades=[]
                if case == "empty"
                else [NS(net_pnl=Decimal("-1") if case == "expectancy" else Decimal(2))],
                book=NS(high_water=Decimal(100)),
            )

        def market(self, event: object) -> None:
            pass

        def decisions(self, *args: object) -> None:
            self.revision += 1

        def state(self) -> object:
            return NS(
                state_hash=("b" if self.revision == 0 else "c" if self.revision == 1 else "d") * 64,
                at=START + timedelta(seconds=1) if case == "future" else START,
                status="ACTIVE",
                net_return=Decimal("-0.1") if case == "return" else Decimal("0.1"),
                portfolio=NS(
                    equity=Decimal(50)
                    if case == "drawdown" and self.revision == 1
                    else Decimal(100)
                ),
            )

    current = MockRuntime()
    current.revision = 1
    header = NS(config=paper_cfg, created_at=START, account_id=paper_id, initial_checkpoint="{}")
    journal: tuple[NS, ...] = (
        NS(
            state_hash="c" * 64,
            revision=1,
            input=object(),
            intents=(),
            strategy_checkpoint="{}",
            failure=None,
        ),
    )
    if case == "drawdown":
        # Terminal equity recovers; the earlier drawdown must still prevent SHADOW.
        current.revision = 2
        journal += (
            NS(
                state_hash="d" * 64,
                revision=2,
                input=object(),
                intents=(),
                strategy_checkpoint="{}",
                failure=None,
            ),
        )
    monkeypatch.setattr(PaperRepository, "load", lambda self, key: (header, current, journal))
    target = StrategyStage.PAPER if case == "paper" else StrategyStage.SHADOW
    draft = StrategyEvent.model_construct(
        strategy_id=artifact.strategy_id,
        revision=1,
        from_stage=StrategyStage.CANDIDATE,
        to_stage=target,
        at=START,
        reason="MOCK_CONTRACT",
        model_artifact_id=model_id,
        model_event_hash=sealed.content_hash,
        paper_account_id=paper_id,
        paper_state_hash=("e" if case == "checkpoint" else "d" if case == "drawdown" else "c") * 64,
        policy=policy(),
        content_hash="0" * 64,
    )
    event = StrategyEvent.model_validate(
        draft.model_dump()
        | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
    )
    if case in {"paper", "shadow"}:
        service._evidence(artifact, event, historical=False)
        assert gates == (
            [ModelStage.CHALLENGER]
            if case == "paper"
            else [ModelStage.CHALLENGER, ModelStage.SHADOW]
        )
    else:
        with pytest.raises(ValueError):
            service._evidence(artifact, event, historical=False)


def test_registered_adapter_rejects_research_before_any_fill(repository: MarketRepository) -> None:
    from pocket_alpha.paper_trading.models import PaperConfig, PaperInput
    from pocket_alpha.paper_trading.service import PaperService
    from pocket_alpha.paper_trading.storage import PaperRepository
    from pocket_alpha.strategies.registry import RegisteredStrategyAdapter
    from tests.strategy_fixtures import run_config

    service = registry(repository)
    artifact = service.register(definition())
    data = dataset().inputs
    cfg = PaperConfig(
        origin="SYNTHETIC",
        asset=data.asset,
        market=data.market,
        venue=data.venue,
        mapping=data.mapping,
        timeframe=data.query.timeframe,
        start=START,
        run=run_config(),
        maximum_events=100,
    )
    adapter = RegisteredStrategyAdapter(service, artifact.strategy_id, cfg)
    paper = PaperService(
        PaperRepository(repository.session), FrozenClock(START + timedelta(minutes=1))
    )
    state = paper.create(cfg, adapter)
    assert not adapter.preflight(state.account_id, cfg)
    assert not adapter.preflight(state.account_id, cfg.model_copy(update={"maximum_events": 101}))
    with pytest.raises(LookupError):
        RegisteredStrategyAdapter(service, uuid4(), cfg)
    candle = data.candles[0]
    paper.clock = FrozenClock(candle.received_at)
    state = paper.process(
        state.account_id,
        PaperInput(event_id=uuid4(), at=paper.clock.now(), kind="CANDLE", candle=candle),
        adapter,
        state.revision,
    )
    assert state.status == "SUSPENDED" and state.reason == "STRATEGY_NOT_READY"
    assert not state.fills and not state.orders and not state.live_ready


def test_lifecycle_bindings_and_operational_model_with_mock_qualification(
    repository: MarketRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Qualification is explicitly mocked; separate tests exercise its actual reject/gate contracts.
    from types import SimpleNamespace as NS

    from pocket_alpha.forecasts.models import ModelStage
    from pocket_alpha.paper_trading.models import PaperConfig
    from pocket_alpha.paper_trading.service import PaperService
    from pocket_alpha.research.registry import ModelRegistry
    from tests.strategy_fixtures import run_config
    from tests.test_research_registry import policy

    service = registry(repository)
    artifact = service.register(definition())
    model_id, account_id = uuid4(), uuid4()
    model_event = NS(content_hash="a" * 64, to_stage=ModelStage.CHALLENGER, at=START)
    monkeypatch.setattr(ModelRegistry, "get", lambda self, key: (object(), (model_event,)))
    monkeypatch.setattr(StrategyRegistry, "_evidence", lambda *args, **kwargs: None)
    monkeypatch.setattr(PaperService, "view", lambda self, key: NS(state=NS(state_hash="b" * 64)))
    selected = policy()
    service.transition(
        artifact.strategy_id, 0, StrategyStage.CANDIDATE, "MOCK_CONTRACT", model_id, policy=selected
    )
    with pytest.raises(ValueError, match="preserve"):
        service.transition(
            artifact.strategy_id,
            1,
            StrategyStage.PAPER,
            "CHANGED_MODEL",
            uuid4(),
            account_id,
            selected,
        )
    with pytest.raises(ValueError, match="preserve"):
        service.transition(
            artifact.strategy_id,
            1,
            StrategyStage.PAPER,
            "CHANGED_POLICY",
            model_id,
            account_id,
            selected.model_copy(update={"version": "other"}),
        )
    with pytest.raises(ValueError, match="bound"):
        service.transition(
            artifact.strategy_id, 1, StrategyStage.PAPER, "NO_ACCOUNT", model_id, policy=selected
        )
    service.transition(
        artifact.strategy_id,
        1,
        StrategyStage.PAPER,
        "MOCK_CONTRACT",
        model_id,
        account_id,
        selected,
    )
    data = dataset().inputs
    cfg = PaperConfig(
        origin="SYNTHETIC",
        asset=data.asset,
        market=data.market,
        venue=data.venue,
        mapping=data.mapping,
        timeframe=data.query.timeframe,
        start=START,
        run=run_config(),
        maximum_events=100,
    )
    assert service.operational(artifact.strategy_id, account_id, cfg)
    assert not service.operational(artifact.strategy_id, uuid4(), cfg)
    model_event.at = START + timedelta(seconds=1)
    assert not service.operational(artifact.strategy_id, account_id, cfg)
    model_event.at = START
    model_event.to_stage = ModelStage.DEGRADED
    assert not service.operational(artifact.strategy_id, account_id, cfg)
    model_event.to_stage = ModelStage.SHADOW
    with pytest.raises(ValueError, match="preserve"):
        service.transition(
            artifact.strategy_id,
            2,
            StrategyStage.SHADOW,
            "OTHER_ACCOUNT",
            model_id,
            uuid4(),
            selected,
        )
    service.transition(
        artifact.strategy_id,
        2,
        StrategyStage.SHADOW,
        "MOCK_CONTRACT",
        model_id,
        account_id,
        selected,
    )
    service.transition(artifact.strategy_id, 3, StrategyStage.DEGRADED, "DEGRADED")
    loaded = service.get(artifact.strategy_id)
    assert loaded is not None and len(loaded[1]) == 5
    assert not service.operational(artifact.strategy_id, account_id, cfg)


def test_rehashed_policy_change_cannot_rewrite_qualified_history(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pocket_alpha.backtesting.models import digest
    from pocket_alpha.strategies.registry import StrategyEvent
    from tests.test_research_registry import policy

    service = registry(repository)
    artifact = service.register(definition())
    # Model proof is mocked, so no real qualification or readiness is asserted.
    monkeypatch.setattr(StrategyRegistry, "_evidence", lambda *args, **kwargs: None)
    previous = service.get(artifact.strategy_id)
    assert previous is not None
    prior = previous[1][0]
    for revision, stage, selected in [
        (1, StrategyStage.CANDIDATE, policy()),
        (2, StrategyStage.PAPER, policy().model_copy(update={"version": "changed"})),
    ]:
        draft = StrategyEvent.model_construct(
            strategy_id=artifact.strategy_id,
            revision=revision,
            from_stage=prior.to_stage,
            to_stage=stage,
            at=START,
            reason="MOCK_CONTRACT",
            model_artifact_id=uuid4() if revision == 1 else prior.model_artifact_id,
            model_event_hash="a" * 64,
            policy=selected,
            previous_hash=prior.content_hash,
            content_hash="0" * 64,
        )
        event = StrategyEvent.model_validate(
            draft.model_dump()
            | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
        )
        repository.session.add(
            StrategyEventRecord(
                strategy_id=artifact.strategy_id,
                revision=revision,
                content_hash=event.content_hash,
                payload=event.model_dump_json(),
            )
        )
        prior = event
    head = repository.session.get(StrategyRecord, artifact.strategy_id)
    assert head is not None
    head.revision, head.stage = 2, "PAPER"
    repository.session.flush()
    with pytest.raises(ValueError, match="frozen"):
        service.get(artifact.strategy_id)
