"""Synthetic mechanics only; no orders, network calls or profitability evidence."""

import json
from collections.abc import Mapping
from datetime import timedelta
from decimal import Context, Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.models import Intent, StrategyView, digest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.paper_trading.models import (
    PaperConfig,
    PaperInput,
    PaperJournal,
    PaperState,
    canonical_state,
)
from pocket_alpha.paper_trading.service import PaperService
from pocket_alpha.paper_trading.storage import (
    PaperAccountRecord,
    PaperConflict,
    PaperJournalRecord,
    PaperRepository,
)
from tests.backtest_fixtures import Plan, config, dataset
from tests.market_fixtures import START

D = Decimal


class CheckpointPlan(Plan):
    def __init__(self, decisions: Mapping[int, tuple[Intent, ...]]) -> None:
        super().__init__(decisions)
        self.count = 0

    def checkpoint(self) -> str:
        return json.dumps({"count": self.count}, sort_keys=True, separators=(",", ":"))

    def restore(self, checkpoint: str) -> None:
        self.count = json.loads(checkpoint)["count"]

    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        self.count += 1
        return super().on_event(view)


def setup(
    repository: MarketRepository,
    plan: CheckpointPlan,
    prices: tuple[str, ...] = ("100",) * 10,
    volumes: tuple[str, ...] | None = None,
) -> tuple[PaperService, PaperState]:
    data = dataset(prices, volumes).inputs
    repository.register(data.asset, data.venue, data.market, data.mapping)
    cfg = PaperConfig(
        origin="SYNTHETIC",
        asset=data.asset,
        market=data.market,
        venue=data.venue,
        mapping=data.mapping,
        timeframe=data.query.timeframe,
        start=START,
        run=config(),
        maximum_events=100,
    )
    paper = PaperService(
        PaperRepository(repository.session), FrozenClock(START + timedelta(minutes=1))
    )
    return paper, paper.create(cfg, plan)


def bar(
    paper: PaperService,
    state: PaperState,
    plan: CheckpointPlan,
    index: int = 0,
    prices: tuple[str, ...] = ("100",) * 10,
    volumes: tuple[str, ...] | None = None,
    delay: int = 0,
) -> PaperState:
    candle = dataset(prices, volumes).inputs.candles[index]
    paper.clock = FrozenClock(candle.received_at + timedelta(seconds=delay))
    return paper.process(
        state.account_id,
        PaperInput(event_id=uuid4(), at=paper.clock.now(), kind="CANDLE", candle=candle),
        plan,
        state.revision,
    )


def control(
    paper: PaperService, state: PaperState, plan: CheckpointPlan, kind: str, **kwargs: object
) -> PaperState:
    event = PaperInput.model_validate(
        dict(event_id=uuid4(), at=paper.clock.now(), kind=kind) | kwargs
    )
    return paper.process(state.account_id, event, plan, state.revision)


def test_same_execution_round_trip_and_restart_without_callbacks(
    repository: MarketRepository,
) -> None:
    decisions = {
        1: (Intent(client_id="buy", action="BUY", quantity=D(2)),),
        5: (Intent(client_id="sell", action="SELL", quantity=D(2)),),
    }
    plan = CheckpointPlan(decisions)
    paper, state = setup(repository, plan)
    for i in range(10):
        state = bar(paper, state, plan, i)
        restored = paper.repository.load(state.account_id)
        assert restored is not None and restored[1].state() == state
    assert len(plan.views) == 10 and plan.count == 10
    report = Backtester(FrozenClock(dataset().inputs.captured_at)).run(
        dataset(), config(), Plan(decisions)
    )
    assert state.portfolio == report.final_portfolio
    assert [(f.at, f.price, f.quantity, f.fee, f.realized_pnl) for f in state.fills] == [
        (f.at, f.price, f.quantity, f.fee, f.realized_pnl) for f in report.fills
    ]
    assert state.total_fees > 0 and state.realized_pnl < 0
    assert all(
        any(
            o.risk_id == f.risk_id and o.state == "APPROVED" and o.at < f.bar_open
            for o in state.orders
        )
        for f in state.fills
    )
    assert state.mode == "PAPER" and not state.live_ready and not state.profitability_claim
    replacement = CheckpointPlan(decisions)
    with localcontext(Context(prec=80)):
        assert paper.repository.load(state.account_id) is not None
    assert replacement.count == 0 and replacement.views == []


def test_partial_fills_cash_reservation_rejection_and_cancel(repository: MarketRepository) -> None:
    plan = CheckpointPlan(
        {
            1: (
                Intent(client_id="buy", action="BUY", quantity=D(3)),
                Intent(client_id="short", action="SELL", quantity=D(1)),
            ),
            4: (Intent(client_id="cancel", action="CANCEL", cancel_client_id="buy"),),
        }
    )
    paper, state = setup(repository, plan)
    volumes = ("10",) * 10
    state = bar(paper, state, plan, 0, volumes=volumes)
    assert state.portfolio.reserved_cash > 0 and any(e.state == "REJECTED" for e in state.orders)
    for i in range(1, 4):
        state = bar(paper, state, plan, i, volumes=volumes)
    assert any(e.state == "PARTIALLY_FILLED" for e in state.orders)
    assert sum(f.quantity for f in state.fills) == 2 and state.portfolio.reserved_cash == 0
    assert any(e.state == "CANCELLED" for e in state.orders)


def test_idempotency_conflicts_and_processing_clock(repository: MarketRepository) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    candle = dataset().inputs.candles[0]
    paper.clock = FrozenClock(candle.close_time + timedelta(seconds=5))
    event = PaperInput(event_id=uuid4(), at=candle.close_time, kind="CANDLE", candle=candle)
    state = paper.process(state.account_id, event, plan, 0)
    assert state.at == paper.clock.now()
    assert paper.process(state.account_id, event, plan, 0) == state and len(plan.views) == 1
    with pytest.raises(PaperConflict):
        paper.process(
            state.account_id,
            event.model_copy(update={"kind": "HEARTBEAT", "candle": None}),
            plan,
            1,
        )
    with pytest.raises(PaperConflict):
        control(paper, state.model_copy(update={"revision": 0}), plan, "HEARTBEAT")
    row = repository.session.scalar(select(PaperJournalRecord))
    assert (
        row is not None
        and json.loads(row.payload)["input"]["candle"]["received_at"]
        == candle.model_dump(mode="json")["received_at"]
    )


def test_disconnect_reconciliation_staleness_and_latched_kill(repository: MarketRepository) -> None:
    plan = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan)
    state = control(paper, state, plan, "DISCONNECT", reason="UNKNOWN_ORDER_STATE")
    assert state.status == "SUSPENDED" and not state.pending and state.portfolio.reserved_cash == 0
    state = control(paper, state, plan, "RECONCILE", reconciliation_hash="0" * 64)
    assert state.reason == "RECONCILIATION_MISMATCH"
    state = control(paper, state, plan, "RECONCILE", reconciliation_hash=state.accounting_hash)
    assert state.status == "ACTIVE"
    paper.clock = FrozenClock(state.at + timedelta(seconds=61))
    view = paper.view(state.account_id)
    assert view is not None and not view.ready and view.readiness_reason == "STALE_FEED"
    state = control(paper, state, plan, "HEARTBEAT")
    assert state.status == "SUSPENDED" and state.reason == "STALE_FEED"
    state = bar(paper, state, plan, 1)
    assert state.status == "SUSPENDED" and len(plan.views) == 1
    state = control(paper, state, plan, "RECONCILE", reconciliation_hash=state.accounting_hash)
    assert state.status == "ACTIVE"
    state = control(paper, state, plan, "KILL")
    state = control(paper, state, plan, "RECONCILE", reconciliation_hash=state.accounting_hash)
    assert state.status == "HALTED" and not state.pending


def test_gap_future_receipt_and_strategy_failure_fail_closed(repository: MarketRepository) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan, 1)
    assert (
        state.reason == "INVALID_MARKET_DATA" and state.next_open == START and len(plan.views) == 0
    )
    state = bar(paper, state, plan, 0, delay=3600)
    assert state.status == "SUSPENDED" and state.reason == "STALE_FEED"


class Broken(CheckpointPlan):
    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        raise RuntimeError("private detail")


def test_callback_exception_is_durable_and_checkpoint_unchanged(
    repository: MarketRepository,
) -> None:
    plan = Broken({})
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan)
    assert state.reason == "STRATEGY_FAILED" and state.strategy_checkpoint == '{"count":0}'
    assert paper.repository.load(state.account_id) is not None


def test_conflicting_intents_do_not_leave_half_submitted_orders(
    repository: MarketRepository,
) -> None:
    plan = CheckpointPlan(
        {
            1: (
                Intent(client_id="same", action="BUY", quantity=D(1)),
                Intent(client_id="same", action="BUY", quantity=D(2)),
            )
        }
    )
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan)
    assert state.reason == "STRATEGY_FAILED" and not state.orders and not state.pending
    assert (
        state.strategy_checkpoint == '{"count":0}'
        and paper.repository.load(state.account_id) is not None
    )


@pytest.mark.parametrize("target", ["header", "state", "journal"])
def test_corruption_blocks_recovery(repository: MarketRepository, target: str) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    state = bar(paper, state, plan)
    if target == "journal":
        journal = repository.session.scalar(select(PaperJournalRecord))
        assert journal is not None
        journal.payload = (
            journal.payload.replace('"count":1', '"count":2')
            if '"count":1' in journal.payload
            else "{}"
        )
    else:
        row = repository.session.get(PaperAccountRecord, state.account_id)
        assert row is not None
        setattr(row, target, "{}")
    repository.session.flush()
    with pytest.raises(ValueError):
        paper.repository.load(state.account_id)


def test_current_bucket_mode_and_checkpoint_boundaries(repository: MarketRepository) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None
    cfg = loaded[0].config
    with pytest.raises(ValidationError):
        PaperConfig.model_validate(cfg.model_dump() | {"mode": "LIVE"})
    paper.clock = FrozenClock(START + timedelta(hours=2))
    with pytest.raises(ValidationError, match="current native candle"):
        paper.create(cfg, plan)
    for invalid in ["[]", '{"z":NaN}', '{"z": 1}']:
        with pytest.raises(ValueError):
            canonical_state(invalid)
    closed = control(paper, state, plan, "CLOSE")
    with pytest.raises(ValueError):
        control(paper, closed, plan, "HEARTBEAT")


def test_latency_expiry_and_stale_processing_prevent_fills(repository: MarketRepository) -> None:
    plan = CheckpointPlan({1: (Intent(client_id="slow", action="BUY", quantity=D(1)),)})
    data = dataset().inputs
    repository.register(data.asset, data.venue, data.market, data.mapping)
    base = config()
    cfg = PaperConfig(
        origin="SYNTHETIC",
        asset=data.asset,
        market=data.market,
        venue=data.venue,
        mapping=data.mapping,
        timeframe=data.query.timeframe,
        start=START,
        maximum_events=20,
        run=base.model_copy(
            update={
                "costs": base.costs.model_copy(
                    update={"latency_seconds": 30, "order_lifetime_seconds": 120}
                )
            }
        ),
    )
    paper = PaperService(
        PaperRepository(repository.session), FrozenClock(START + timedelta(seconds=1))
    )
    state = paper.create(cfg, plan)
    state = bar(paper, state, plan)
    assert not state.pending[0].acknowledged
    paper.clock = FrozenClock(state.at + timedelta(seconds=30))
    state = control(paper, state, plan, "HEARTBEAT")
    assert state.pending[0].acknowledged and not state.fills
    paper.clock = FrozenClock(state.at + timedelta(seconds=31))
    state = control(paper, state, plan, "HEARTBEAT")
    assert state.status == "SUSPENDED" and not state.pending
    assert state.portfolio.reserved_cash == 0 and not state.fills


def test_drawdown_latches_with_inventory_and_no_fictitious_exit(
    repository: MarketRepository,
) -> None:
    plan = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D(20)),)})
    paper, state = setup(repository, plan)
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None
    cfg = loaded[0].config
    cfg = cfg.model_copy(
        update={
            "run": cfg.run.model_copy(
                update={"risk": cfg.run.risk.model_copy(update={"maximum_drawdown": D("0.01")})}
            )
        }
    )
    state = paper.create(cfg, plan)
    prices = ("100", "100", "100", "50")
    for i in range(4):
        state = bar(paper, state, plan, i, prices=prices)
    assert state.status == "HALTED" and state.reason == "DRAWDOWN_LIMIT"
    assert state.portfolio.quantity == 10 and len(state.fills) == 1 and not state.pending
    assert state.unrealized_pnl is not None and state.unrealized_pnl < 0
    state = control(paper, state, plan, "RECONCILE", reconciliation_hash=state.accounting_hash)
    assert state.status == "HALTED" and state.portfolio.quantity == 10


def test_low_decimal_context_does_not_change_paper_accounting(repository: MarketRepository) -> None:
    plan = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D("1.23")),)})
    with localcontext(Context(prec=5)):
        paper, state = setup(repository, plan)
        for i in range(3):
            state = bar(paper, state, plan, i)
        view = paper.view(state.account_id)
        assert view is not None and view.state == state
    assert state.portfolio.quantity == D("1.23") and state.total_fees > 0


def test_append_failure_rolls_back_state_orders_and_checkpoint(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    plan = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    paper, state = setup(repository, plan)
    original = paper.repository.append

    def failed(entry: PaperJournal, result: PaperState) -> None:
        original(entry, result)
        raise SQLAlchemyError("private failure")

    monkeypatch.setattr(paper.repository, "append", failed)
    with pytest.raises(SQLAlchemyError):
        bar(paper, state, plan)
    repository.session.expire_all()
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None and loaded[1].state() == state and not loaded[2]
    monkeypatch.setattr(paper.repository, "append", original)
    state = bar(paper, state, plan)
    assert state.revision == 1 and state.strategy_checkpoint == '{"count":1}'


def test_code_drift_is_not_ready_and_budget_allows_kill(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None
    cfg = loaded[0].config.model_copy(update={"maximum_events": 1})
    state = paper.create(cfg, plan)
    state = bar(paper, state, plan)
    view = paper.view(state.account_id)
    assert (
        view is not None and not view.ready and view.readiness_reason == "JOURNAL_BUDGET_EXHAUSTED"
    )
    with pytest.raises(ValueError, match="budget"):
        control(paper, state, plan, "HEARTBEAT")
    state = control(paper, state, plan, "KILL")
    assert state.status == "HALTED"
    monkeypatch.setattr("pocket_alpha.paper_trading.service.current_code_hash", lambda: "f" * 64)
    view = paper.view(state.account_id)
    assert (
        view is not None and not view.ready and view.readiness_reason == "RUNTIME_IDENTITY_CHANGED"
    )
    with pytest.raises(ValueError, match="identity"):
        control(paper, state, plan, "CLOSE")


def test_json_logs_identify_paper_and_do_not_include_checkpoint(
    repository: MarketRepository, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    from pocket_alpha.observability import JsonFormatter

    logger = logging.getLogger("pocket_alpha.paper_trading.service")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=logger.name):
            paper, state = setup(repository, CheckpointPlan({}))
    finally:
        logger.removeHandler(caplog.handler)
    record = next(r for r in caplog.records if r.name == "pocket_alpha.paper_trading.service")
    output = json.loads(JsonFormatter().format(record))
    assert output["mode"] == "PAPER" and output["account_id"] == str(state.account_id)
    assert "checkpoint" not in output and "transaction prepared" in output["event"]


def test_committed_restart_in_new_database_session(tmp_path: object) -> None:
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from pocket_alpha.database import Base

    assert isinstance(tmp_path, Path)
    path = tmp_path / "paper.sqlite"
    engine = create_engine("sqlite:///" + str(path))
    Base.metadata.create_all(engine)
    first = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    with Session(engine) as session, session.begin():
        paper, state = setup(MarketRepository(session), first)
        state = bar(paper, state, first)
    engine.dispose()
    engine = create_engine("sqlite:///" + str(path))
    try:
        with Session(engine) as session, session.begin():
            second = CheckpointPlan({})
            paper = PaperService(PaperRepository(session), FrozenClock(state.at))
            restored = paper.view(state.account_id)
            assert restored is not None and restored.state == state and not second.views
            state = bar(paper, state, second, 1)
            assert second.count == 2 and len(second.views) == 1 and state.revision == 2
    finally:
        engine.dispose()


def rehash(state: PaperState) -> dict[str, object]:
    accounting = dict(
        portfolio=state.portfolio.model_dump(mode="json"),
        pending=[p.model_dump(mode="json") for p in state.pending],
        fills=[f.model_dump(mode="json") for f in state.fills],
    )
    state = state.model_copy(update={"accounting_hash": digest(accounting)})
    return state.model_dump() | dict(
        state_hash=digest(state.model_dump(mode="json", exclude={"state_hash"}))
    )


def test_rehashed_financial_tampering_is_rejected_independently(
    repository: MarketRepository,
) -> None:
    plan = CheckpointPlan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    paper, state = setup(repository, plan)
    for i in range(3):
        state = bar(paper, state, plan, i)
    modified = state.model_copy(
        update={
            "portfolio": state.portfolio.model_copy(
                update={"cash": state.portfolio.cash + 1, "equity": state.portfolio.equity + 1}
            )
        }
    )
    with pytest.raises(ValidationError, match="cash and inventory"):
        PaperState.model_validate(rehash(modified))
    events = tuple(
        e.model_copy(update={"sequence": i})
        for i, e in enumerate((e for e in state.orders if e.state != "APPROVED"), start=1)
    )
    with pytest.raises(ValidationError, match="prior risk approval"):
        PaperState.model_validate(rehash(state.model_copy(update={"orders": events})))


def test_cas_conflict_rolls_back_all_tentative_writes(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import update

    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    original = paper.repository.append

    def changed(entry: PaperJournal, result: PaperState) -> None:
        repository.session.execute(
            update(PaperAccountRecord)
            .where(PaperAccountRecord.account_id == state.account_id)
            .values(revision=entry.revision)
        )
        original(entry, result)

    monkeypatch.setattr(paper.repository, "append", changed)
    with pytest.raises(PaperConflict):
        bar(paper, state, plan)
    repository.session.expire_all()
    loaded = paper.repository.load(state.account_id)
    assert loaded is not None and loaded[1].state() == state and loaded[2] == ()


def test_consistent_head_tampering_still_fails_journal_reconciliation(
    repository: MarketRepository,
) -> None:
    paper, state = setup(repository, CheckpointPlan({}))
    modified = PaperState.model_validate(
        rehash(
            state.model_copy(
                update={
                    "initial_cash": state.initial_cash + 1,
                    "portfolio": state.portfolio.model_copy(
                        update={
                            "cash": state.portfolio.cash + 1,
                            "equity": state.portfolio.equity + 1,
                        }
                    ),
                }
            )
        )
    )
    row = repository.session.get(PaperAccountRecord, state.account_id)
    assert row is not None
    row.state = modified.model_dump_json()
    row.state_hash = modified.state_hash
    repository.session.flush()
    with pytest.raises(ValueError, match="persisted state"):
        paper.repository.load(state.account_id)
