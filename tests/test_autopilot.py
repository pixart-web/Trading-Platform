"""Phase 28 synthetic orchestration qualification; no native orders or network."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from pocket_alpha.autopilot.engine import Autopilot, AutopilotError
from pocket_alpha.autopilot.models import (
    AutopilotCandidate,
    AutopilotCycle,
    AutopilotHealth,
    AutopilotPolicy,
)
from pocket_alpha.backtesting.models import Intent, digest
from pocket_alpha.directional.models import DirectionalSide
from pocket_alpha.domain.models import AssetType, ForecastHorizon
from pocket_alpha.forecasts.models import ModelStage
from pocket_alpha.research.registry import RegistryEvent
from pocket_alpha.scanner.models import (
    ScanFilters,
    ScanMarket,
    ScanPolicyGroup,
    ScanRankEntry,
    ScanReport,
    ScanStatus,
)
from pocket_alpha.spot_execution.engine import SpotExecution
from pocket_alpha.spot_execution.models import SpotRequest
from pocket_alpha.strategies.models import StrategyStage
from pocket_alpha.strategies.registry import StrategyEvent
from tests.test_analyze import full_request
from tests.test_spot_execution import SyntheticBroker, request
from tests.test_spot_execution import policy as spot_policy


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def policy(value: SpotRequest, **changes: Any) -> AutopilotPolicy:
    data: dict[str, Any] = {
        "version": "synthetic-autopilot-1",
        "mode": "SYNTHETIC_QUALIFICATION",
        "enabled": True,
        "asset_ids": (value.strategy.asset_id,),
        "strategy_hashes": (digest(value.strategy),),
        "maximum_capital": D(30),
        "maximum_exposure": D(30),
        "maximum_daily_loss": D(5),
        "maximum_drawdown": D("0.1"),
        "maximum_simultaneous_positions": 1,
        "cooldown_seconds": 5,
        "stale_data_seconds": 30,
        "maximum_candidates_per_cycle": 20,
    }
    data.update(changes)
    return AutopilotPolicy(**data)


def scan(value: SpotRequest, *, generated_at: datetime | None = None) -> ScanReport:
    base = next(
        item.opportunity for item in full_request().horizons if item.horizon == ForecastHorizon.H4
    )
    assert base is not None and base.direction == DirectionalSide.LONG and base.eligible
    at = generated_at or value.proposal.at
    opportunity = base.model_copy(
        update={
            "market_id": value.strategy.market_id,
            "asset_id": value.strategy.asset_id,
            "candle_timeframe": value.strategy.timeframe,
            "horizon": value.strategy.horizon,
            "as_of": at,
            "generated_at": at,
        }
    )
    entry = ScanRankEntry(
        rank=1,
        market=ScanMarket(
            market_id=value.strategy.market_id,
            asset_id=value.strategy.asset_id,
            symbol=value.symbol,
            name="Synthetic Autopilot market",
            asset_type=AssetType.CRYPTO,
            venue_id="binance",
            quote_currency="USDT",
        ),
        report_id=UUID(int=2801),
        opportunity=opportunity,
    )
    return ScanReport(
        scan_id=UUID(int=2802),
        candle_timeframe=value.strategy.timeframe,
        horizon=value.strategy.horizon,
        as_of=at,
        generated_at=at,
        filters=ScanFilters(),
        status=ScanStatus.RESULTS,
        universe_size=1,
        analyze_reports_found=1,
        groups=(
            ScanPolicyGroup(
                policy_version=opportunity.policy_version,
                policy_hash=opportunity.policy_hash,
                entries=(entry,),
            ),
        ),
        excluded=(),
        input_hash="2" * 64,
    )


def lifecycle(
    value: SpotRequest,
    model_stage: ModelStage = ModelStage.SHADOW,
    strategy_stage: StrategyStage = StrategyStage.SHADOW,
) -> tuple[RegistryEvent, StrategyEvent]:
    at = value.proposal.at
    artifact_id = uuid5(NAMESPACE_URL, "synthetic-model:" + value.strategy.model_version)
    model_draft = RegistryEvent.model_construct(
        artifact_id=artifact_id,
        revision=2,
        from_stage=ModelStage.CHALLENGER,
        to_stage=model_stage,
        at=at,
        reason="SYNTHETIC_LIFECYCLE_FIXTURE",
        evidence_id=None,
        evidence_hash=None,
        policy=None,
        previous_hash="3" * 64,
        content_hash="0" * 64,
    )
    model_event = RegistryEvent.model_validate(
        model_draft.model_dump()
        | {"content_hash": digest(model_draft.model_dump(mode="json", exclude={"content_hash"}))}
    )
    strategy_id = uuid5(NAMESPACE_URL, "pocket-alpha-strategy:" + value.proposal.definition_hash)
    strategy_draft = StrategyEvent.model_construct(
        strategy_id=strategy_id,
        revision=3,
        from_stage=StrategyStage.PAPER,
        to_stage=strategy_stage,
        at=at,
        reason="SYNTHETIC_LIFECYCLE_FIXTURE",
        model_artifact_id=artifact_id,
        model_event_hash=model_event.content_hash,
        paper_account_id=UUID(int=2803),
        paper_state_hash="4" * 64,
        policy=None,
        previous_hash="5" * 64,
        content_hash="0" * 64,
    )
    strategy_event = StrategyEvent.model_validate(
        strategy_draft.model_dump()
        | {"content_hash": digest(strategy_draft.model_dump(mode="json", exclude={"content_hash"}))}
    )
    return model_event, strategy_event


def candidate(
    value: SpotRequest,
    *,
    report: ScanReport | None = None,
    model_stage: ModelStage = ModelStage.SHADOW,
    strategy_stage: StrategyStage = StrategyStage.SHADOW,
) -> AutopilotCandidate:
    report = report or scan(value)
    model_event, strategy_event = lifecycle(value, model_stage, strategy_stage)
    return AutopilotCandidate(
        request=value,
        model_event=model_event,
        strategy_event=strategy_event,
        scan_policy_hash=report.groups[0].policy_hash,
        scan_rank=1,
    )


def health(at: datetime, **changes: Any) -> AutopilotHealth:
    data: dict[str, Any] = {
        "checked_at": at,
        "provider_ready": True,
        "risk_ready": True,
        "portfolio_ready": True,
        "reconciliation_resolved": True,
        "execution_ready": True,
    }
    data.update(changes)
    return AutopilotHealth(**data)


def cycle(
    value: SpotRequest,
    *,
    report: ScanReport | None = None,
    candidates: tuple[AutopilotCandidate, ...] | None = None,
    state: AutopilotHealth | None = None,
    requested_at: datetime | None = None,
    cycle_id: UUID | None = None,
) -> AutopilotCycle:
    report = report or scan(value)
    at = requested_at or value.proposal.at
    return AutopilotCycle(
        cycle_id=cycle_id or uuid4(),
        requested_at=at,
        health=state or health(at),
        scan=report,
        candidates=candidates if candidates is not None else (candidate(value, report=report),),
    )


def subject(
    tmp_path: Path,
    value: SpotRequest,
    *,
    autopilot_policy: AutopilotPolicy | None = None,
    execution_policy: Any = None,
    native: bool = False,
) -> tuple[Autopilot, SpotExecution, SyntheticBroker | None, MutableClock]:
    clock = MutableClock(value.proposal.at)
    broker = None if native else SyntheticBroker()
    execution = SpotExecution(
        tmp_path / "spot.sqlite",
        execution_policy or spot_policy(value),
        broker=broker,
        clock=clock,
    )
    app = Autopilot(
        tmp_path / "autopilot.sqlite",
        autopilot_policy or policy(value),
        execution,
        clock=clock,
    )
    return app, execution, broker, clock


def close(app: Autopilot, execution: SpotExecution) -> None:
    app.close()
    execution.journal.close()


def decision(result: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], result["decision"])


def test_happy_path_uses_shared_execution_and_audits_decision(tmp_path: Path) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    result = app.run(cycle(value))
    assert result["kind"] == "CYCLE_RESULT"
    assert decision(result)["outcome"] == "SUBMIT"
    assert not decision(result)["execution_authorized"]
    assert result["execution_event"]["kind"] == "REPORT"
    assert result["execution_event"]["status"] == "NEW"
    assert result["execution_state"] == "UNRESOLVED"
    assert broker.submissions == 1
    assert [event["kind"] for event in app.journal.read()] == [
        "CYCLE_DECISION",
        "CYCLE_RESULT",
    ]
    close(app, execution)


def test_exact_cycle_retry_is_idempotent(tmp_path: Path) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    item = cycle(value)
    first = app.run(item)
    assert app.run(item) == first and broker.submissions == 1
    close(app, execution)


def test_cycle_id_reuse_with_changed_content_rejects(tmp_path: Path) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)
    item = cycle(value)
    app.run(item)
    changed = item.model_copy(update={"requested_at": item.requested_at - timedelta(seconds=1)})
    with pytest.raises(AutopilotError, match="IDEMPOTENCY_CONFLICT"):
        app.run(changed)
    close(app, execution)


def test_default_disabled_policy_never_dispatches(tmp_path: Path) -> None:
    value = request()
    disabled = policy(value, mode="DISABLED", enabled=False)
    app, execution, broker, _ = subject(tmp_path, value, autopilot_policy=disabled)
    assert broker is not None
    result = app.run(cycle(value))
    assert decision(result)["outcome"] == "HALTED"
    assert "AUTOPILOT_DISABLED" in decision(result)["reasons"]
    assert broker.submissions == 0
    close(app, execution)


@pytest.mark.parametrize(
    "field,reason",
    [
        ("provider_ready", "PROVIDER_UNAVAILABLE"),
        ("risk_ready", "RISK_STATE_UNAVAILABLE"),
        ("portfolio_ready", "PORTFOLIO_STATE_INCONSISTENT"),
        ("reconciliation_resolved", "RECONCILIATION_UNRESOLVED"),
        ("execution_ready", "EXECUTION_STATE_UNAVAILABLE"),
    ],
)
def test_dependency_health_fails_closed(tmp_path: Path, field: str, reason: str) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    result = app.run(cycle(value, state=health(value.proposal.at, **{field: False})))
    assert reason in decision(result)["reasons"] and broker.submissions == 0
    close(app, execution)


@pytest.mark.parametrize("target", ["cycle", "health"])
def test_stale_control_state_halts(tmp_path: Path, target: str) -> None:
    value = request()
    app, execution, broker, clock = subject(tmp_path, value)
    assert broker is not None
    clock.instant += timedelta(seconds=31)
    item = cycle(value)
    if target == "health":
        item = item.model_copy(
            update={"requested_at": clock.instant, "health": health(value.proposal.at)}
        )
    result = app.run(item)
    expected = "HEALTH_STALE_OR_FUTURE" if target == "health" else "CYCLE_STALE_OR_FUTURE"
    assert expected in decision(result)["reasons"] and broker.submissions == 0
    close(app, execution)


def test_manual_suspend_resume_and_kill_survive_restart(tmp_path: Path) -> None:
    value = request()
    auto_path = tmp_path / "autopilot.sqlite"
    app, execution, broker, clock = subject(tmp_path, value)
    assert broker is not None
    app.suspend("OPERATOR_REVIEW")
    assert "MANUALLY_SUSPENDED" in decision(app.run(cycle(value)))["reasons"]
    app.resume("REVIEW_COMPLETE")
    clock.instant += timedelta(seconds=1)
    resumed = app.run(cycle(value, requested_at=clock.instant, state=health(clock.instant)))
    assert decision(resumed)["outcome"] == "SUBMIT"
    app.kill("EMERGENCY_STOP")
    app.close()
    reopened = Autopilot(auto_path, policy(value), execution, clock=clock)
    stopped = reopened.run(cycle(value, requested_at=clock.instant, state=health(clock.instant)))
    assert "KILL_SWITCH" in decision(stopped)["reasons"]
    with pytest.raises(AutopilotError, match="KILL_SWITCH_LATCHED"):
        reopened.resume("CANNOT_RESET")
    close(reopened, execution)


def test_unresolved_blocks_until_existing_order_is_reconciled(tmp_path: Path) -> None:
    value = request()
    app, execution, broker, clock = subject(tmp_path, value)
    assert broker is not None
    first_cycle = cycle(value)
    assert app.run(first_cycle)["execution_state"] == "UNRESOLVED"
    blocked = app.run(cycle(value))
    assert "EXECUTION_STATE_UNRESOLVED" in decision(blocked)["reasons"]
    assert broker.submissions == 1 and broker.latest is not None
    quantity = broker.latest.original_quantity
    broker.latest = broker.latest.model_copy(
        update={
            "status": "FILLED",
            "executed_quantity": quantity,
            "cumulative_quote": quantity * broker.latest.limit_price,
        }
    )
    assert app.reconcile(first_cycle.cycle_id)["execution_state"] == "SETTLED"
    clock.instant += timedelta(seconds=6)
    after = app.run(cycle(value, requested_at=clock.instant, state=health(clock.instant)))
    assert "EXECUTION_STATE_UNRESOLVED" not in decision(after)["reasons"]
    close(app, execution)


def test_cooldown_is_durable_after_settled_risk_rejection(tmp_path: Path) -> None:
    value = request().model_copy(update={"health_ready": False})
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    first = app.run(cycle(value))
    assert first["execution_event"]["kind"] == "RISK_REJECTED"
    assert first["execution_state"] == "SETTLED"
    second = app.run(cycle(value))
    assert "COOLDOWN_ACTIVE" in decision(second)["reasons"]
    assert broker.submissions == 0
    close(app, execution)


def test_risk_rejection_is_authoritative(tmp_path: Path) -> None:
    value = request().model_copy(update={"independent_qualification": False})
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    result = app.run(cycle(value))
    assert decision(result)["outcome"] == "SUBMIT"
    assert result["execution_event"]["kind"] == "RISK_REJECTED"
    assert "QUALIFICATION_MISSING" in result["execution_event"]["reasons"]
    assert broker.submissions == 0
    close(app, execution)


def test_native_execution_stack_is_never_reachable(tmp_path: Path) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value, native=True)
    result = app.run(cycle(value))
    assert "EXECUTION_STACK_NOT_QUALIFIED" in decision(result)["reasons"]
    assert decision(result)["outcome"] == "HALTED"
    close(app, execution)


@pytest.mark.parametrize(
    "auto_change,error",
    [
        ({"maximum_capital": D(101)}, "LIMIT_EXCEEDS"),
        ({"maximum_exposure": D(31), "maximum_capital": D(31)}, "LIMIT_EXCEEDS"),
        ({"maximum_daily_loss": D(6)}, "LIMIT_EXCEEDS"),
        ({"maximum_drawdown": D("0.2")}, "LIMIT_EXCEEDS"),
        ({"maximum_simultaneous_positions": 2}, "LIMIT_EXCEEDS"),
        ({"stale_data_seconds": 31}, "LIMIT_EXCEEDS"),
        ({"strategy_hashes": ("0" * 64,)}, "STRATEGY_POLICY_EXCEEDS"),
    ],
)
def test_policy_cannot_exceed_execution_policy(
    tmp_path: Path, auto_change: dict[str, Any], error: str
) -> None:
    value = request()
    execution = SpotExecution(
        tmp_path / "spot.sqlite", spot_policy(value), broker=SyntheticBroker()
    )
    with pytest.raises(AutopilotError, match=error):
        Autopilot(tmp_path / "auto.sqlite", policy(value, **auto_change), execution)
    execution.journal.close()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("asset", "ASSET_NOT_ALLOWED"),
        ("model", "MODEL_NOT_SHADOW_READY"),
        ("strategy", "STRATEGY_NOT_SHADOW_READY"),
        ("capital", "AUTOPILOT_CAPITAL_LIMIT"),
        ("daily", "AUTOPILOT_DAILY_LOSS_LIMIT"),
        ("drawdown", "AUTOPILOT_DRAWDOWN_LIMIT"),
        ("scan", "SCAN_EVIDENCE_MISMATCH"),
    ],
)
def test_candidate_gates_are_explained(tmp_path: Path, case: str, reason: str) -> None:
    value = request()
    auto_policy = policy(value)
    item = candidate(value)
    if case == "asset":
        auto_policy = policy(value, asset_ids=("other-asset",))
    elif case == "model":
        item = candidate(value, model_stage=ModelStage.DEGRADED)
    elif case == "strategy":
        item = candidate(value, strategy_stage=StrategyStage.DEGRADED)
    elif case == "capital":
        auto_policy = policy(value, maximum_capital=D(3), maximum_exposure=D(3))
    elif case == "daily":
        value = value.model_copy(update={"daily_start_equity": D("1207.12")})
        item = candidate(value)
    elif case == "drawdown":
        value = value.model_copy(update={"high_water_equity": D(1400)})
        item = candidate(value)
    else:
        item = item.model_copy(update={"scan_rank": 2})
    app, execution, broker, _ = subject(tmp_path, value, autopilot_policy=auto_policy)
    assert broker is not None
    result = app.run(cycle(value, candidates=(item,)))
    assessed = decision(result)["candidates"][0]
    assert reason in assessed["reasons"]
    assert decision(result)["outcome"] == "NO_ACTION" and broker.submissions == 0
    close(app, execution)


def test_no_candidates_is_audited_no_action(tmp_path: Path) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    result = app.run(cycle(value, candidates=()))
    assert decision(result)["outcome"] == "NO_ACTION"
    assert decision(result)["reasons"] == ["NO_ELIGIBLE_CANDIDATE"]
    assert broker.submissions == 0
    close(app, execution)


def test_candidate_budget_halts_instead_of_truncating(tmp_path: Path) -> None:
    value = request()
    limited = policy(value, maximum_candidates_per_cycle=1)
    second_request = value.model_copy(
        update={"intent": Intent(client_id="synthetic-intent-2", action="BUY", quantity=D("0.01"))}
    )
    candidates = (candidate(value), candidate(second_request))
    app, execution, broker, _ = subject(tmp_path, value, autopilot_policy=limited)
    assert broker is not None
    result = app.run(cycle(value, candidates=candidates))
    assert "CANDIDATE_BUDGET_EXCEEDED" in decision(result)["reasons"]
    assert broker.submissions == 0
    close(app, execution)


def test_crash_after_decision_never_blindly_resubmits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    item = cycle(value)

    def crash(_: SpotRequest) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(execution, "submit", crash)
    with pytest.raises(KeyboardInterrupt):
        app.run(item)
    recovered = app.run(item)
    assert recovered["execution_state"] == "UNKNOWN"
    assert recovered["reason"] == "RECOVERED_UNKNOWN_EXECUTION_STATE"
    assert broker.submissions == 0
    close(app, execution)


def test_execution_exception_is_sanitized_and_blocks_followup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)

    def fail(_: SpotRequest) -> dict[str, Any]:
        raise RuntimeError("secret upstream detail")

    monkeypatch.setattr(execution, "submit", fail)
    first = app.run(cycle(value))
    assert first["reason"] == "EXECUTION_CALL_FAILED"
    assert "secret" not in json_text(first)
    blocked = app.run(cycle(value))
    assert "EXECUTION_STATE_UNRESOLVED" in decision(blocked)["reasons"]
    close(app, execution)


def json_text(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True)


def test_journal_integrity_failure_is_detected(tmp_path: Path) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)
    app.run(cycle(value, candidates=()))
    app.journal.connection.execute("UPDATE events SET payload='{}' WHERE sequence=1")
    with pytest.raises(AutopilotError, match="INTEGRITY_FAILURE"):
        app.journal.read()
    app.close()
    execution.journal.close()


def test_journal_is_pinned_to_policy_identity(tmp_path: Path) -> None:
    value = request()
    auto_path = tmp_path / "autopilot.sqlite"
    app, execution, _, _ = subject(tmp_path, value)
    app.close()
    with pytest.raises(AutopilotError, match="JOURNAL_IDENTITY_MISMATCH"):
        Autopilot(
            auto_path,
            policy(value, version="synthetic-autopilot-2", cooldown_seconds=6),
            execution,
        )
    execution.journal.close()


def test_schemas_reject_ambiguous_inputs() -> None:
    value = request()
    with pytest.raises(ValidationError):
        policy(value, asset_ids=(value.strategy.asset_id, value.strategy.asset_id))
    with pytest.raises(ValidationError):
        policy(value, maximum_exposure=D(31), maximum_capital=D(30))
    with pytest.raises(ValidationError):
        AutopilotCandidate.model_validate({"request": value})


def test_reconciliation_requires_a_submitted_cycle(tmp_path: Path) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)
    empty = cycle(value, candidates=())
    app.run(empty)
    with pytest.raises(AutopilotError, match="CYCLE_NOT_SUBMITTED"):
        app.reconcile(empty.cycle_id)
    close(app, execution)


def test_orphan_submit_decision_blocks_every_new_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None

    def crash(_: SpotRequest) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(execution, "submit", crash)
    with pytest.raises(KeyboardInterrupt):
        app.run(cycle(value))
    blocked = app.run(cycle(value))
    assert "EXECUTION_STATE_UNRESOLVED" in decision(blocked)["reasons"]
    assert broker.submissions == 0
    close(app, execution)


def test_unrecognized_execution_result_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)
    monkeypatch.setattr(execution, "submit", lambda _: {"kind": "UNRECOGNIZED"})
    result = app.run(cycle(value))
    assert result["execution_state"] == "UNKNOWN"
    close(app, execution)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("health", "HEALTH_AVAILABLE_AFTER_CYCLE"),
        ("scan", "SCAN_AVAILABLE_AFTER_CYCLE"),
        ("input", "INPUT_AVAILABLE_AFTER_CYCLE"),
    ],
)
def test_evidence_must_exist_at_declared_cycle_time(tmp_path: Path, case: str, reason: str) -> None:
    value = request()
    app, execution, broker, _ = subject(tmp_path, value)
    assert broker is not None
    earlier = value.proposal.at - timedelta(seconds=1)
    if case == "health":
        item = cycle(value, requested_at=earlier, state=health(value.proposal.at))
    elif case == "scan":
        report = scan(value)
        item = cycle(
            value,
            report=report,
            requested_at=earlier,
            state=health(earlier),
        )
    else:
        item = cycle(value, requested_at=earlier, state=health(earlier))
    result = app.run(item)
    if case == "input":
        assert reason in decision(result)["candidates"][0]["reasons"]
    else:
        assert (
            reason in decision(result)["reasons"]
            or reason in decision(result)["candidates"][0]["reasons"]
        )
    assert broker.submissions == 0
    close(app, execution)


def test_kill_propagates_to_shared_execution_latch(tmp_path: Path) -> None:
    value = request()
    app, execution, _, _ = subject(tmp_path, value)
    app.kill("OPERATOR_EMERGENCY")
    assert any(event["kind"] == "EXECUTION_KILL_CONFIRMED" for event in app.journal.read())
    assert any(event["kind"] == "KILL" for event in execution.journal.read())
    close(app, execution)
