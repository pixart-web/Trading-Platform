"""Autopilot is a durable orchestrator over the existing spot risk/execution boundary."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import ROUND_CEILING, Decimal, localcontext
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import Clock, SystemClock, utc
from pocket_alpha.directional.models import DirectionalSide
from pocket_alpha.portfolio.models import PortfolioSnapshotStatus, PositionStatus
from pocket_alpha.spot_execution.engine import SpotExecution, client_id
from pocket_alpha.spot_execution.models import SpotPolicy

from .models import (
    AutopilotCandidate,
    AutopilotCycle,
    AutopilotDecision,
    AutopilotPolicy,
    CandidateAssessment,
)


class AutopilotError(Exception):
    pass


class Journal:
    """Policy-pinned append-only local audit chain with serialized cycle admission."""

    def __init__(self, path: Path, policy_hash: str, account_hash: str) -> None:
        self.connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.connection.execute("PRAGMA synchronous=FULL")
        with self.transaction():
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), "
                "policy_hash TEXT NOT NULL, account_hash TEXT NOT NULL, version TEXT NOT NULL)"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, "
                "payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL)"
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO identity VALUES (1, ?, ?, 'autopilot-journal-1')",
                (policy_hash, account_hash),
            )
            identity = self.connection.execute(
                "SELECT policy_hash, account_hash, version FROM identity WHERE id=1"
            ).fetchone()
            if identity != (policy_hash, account_hash, "autopilot-journal-1"):
                raise AutopilotError("AUTOPILOT_JOURNAL_IDENTITY_MISMATCH")
            self.read()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def read(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT sequence, payload, previous, hash FROM events ORDER BY sequence LIMIT 10001"
        ).fetchall()
        if len(rows) > 10000:
            raise AutopilotError("AUTOPILOT_JOURNAL_BUDGET_EXCEEDED")
        previous = "0" * 64
        events: list[dict[str, Any]] = []
        for expected, (sequence, payload, prior, content) in enumerate(rows, 1):
            event: dict[str, Any] = json.loads(payload)
            if (
                sequence != expected
                or prior != previous
                or content != digest({"previous": prior, "event": event})
            ):
                raise AutopilotError("AUTOPILOT_JOURNAL_INTEGRITY_FAILURE")
            previous = content
            events.append(event)
        return events

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT sequence, hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence, previous = (row[0] + 1, row[1]) if row else (1, "0" * 64)
        if sequence > 10000:
            raise AutopilotError("AUTOPILOT_JOURNAL_BUDGET_EXCEEDED")
        content = digest({"previous": previous, "event": event})
        self.connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (sequence, json.dumps(event, sort_keys=True), previous, content),
        )
        return event

    def close(self) -> None:
        self.connection.close()


class Autopilot:
    def __init__(
        self,
        path: Path,
        policy: AutopilotPolicy,
        execution: SpotExecution,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.policy = AutopilotPolicy.model_validate_json(policy.model_dump_json())
        self.execution = execution
        self.clock = clock or SystemClock()
        self._validate_policy_stack(execution.policy)
        self.journal = Journal(path, digest(self.policy), execution.policy.account_identity_hash)

    def _validate_policy_stack(self, spot: SpotPolicy) -> None:
        policy = self.policy
        if not set(policy.strategy_hashes).issubset(spot.strategy_hashes):
            raise AutopilotError("AUTOPILOT_STRATEGY_POLICY_EXCEEDS_EXECUTION")
        checks = (
            policy.maximum_capital <= spot.capital_limit,
            policy.maximum_exposure <= spot.total_exposure_limit,
            policy.maximum_daily_loss <= spot.daily_loss_limit,
            policy.maximum_drawdown <= spot.maximum_drawdown,
            policy.maximum_simultaneous_positions <= spot.maximum_positions,
            policy.stale_data_seconds <= spot.maximum_data_age_seconds,
        )
        if not all(checks):
            raise AutopilotError("AUTOPILOT_LIMIT_EXCEEDS_EXECUTION_POLICY")

    def close(self) -> None:
        self.journal.close()

    def _event(self, kind: str, cycle_id: str = "", **data: Any) -> dict[str, Any]:
        return {
            "kind": kind,
            "cycle_id": cycle_id,
            "at": utc(self.clock.now()).isoformat(),
            **data,
        }

    def suspend(self, reason: str) -> dict[str, Any]:
        if not reason or len(reason) > 128:
            raise AutopilotError("INVALID_SUSPENSION_REASON")
        with self.journal.transaction():
            events = self.journal.read()
            if any(event["kind"] == "KILL" for event in events):
                raise AutopilotError("KILL_SWITCH_LATCHED")
            return self.journal.append(self._event("SUSPENDED", reason=reason))

    def resume(self, reason: str) -> dict[str, Any]:
        if not reason or len(reason) > 128:
            raise AutopilotError("INVALID_RESUME_REASON")
        with self.journal.transaction():
            events = self.journal.read()
            if any(event["kind"] == "KILL" for event in events):
                raise AutopilotError("KILL_SWITCH_LATCHED")
            if not self._suspended(events):
                raise AutopilotError("AUTOPILOT_NOT_SUSPENDED")
            return self.journal.append(self._event("RESUMED", reason=reason))

    def kill(self, reason: str) -> dict[str, Any]:
        if not reason or len(reason) > 128:
            raise AutopilotError("INVALID_KILL_REASON")
        with self.journal.transaction():
            events = self.journal.read()
            kill_event = next(
                (event for event in reversed(events) if event["kind"] == "KILL"), None
            )
            if kill_event is None:
                kill_event = self.journal.append(self._event("KILL", reason=reason))
            if any(event["kind"] == "EXECUTION_KILL_CONFIRMED" for event in events):
                return kill_event
        try:
            self.execution.kill()
        except Exception:
            with self.journal.transaction():
                self.journal.read()
                self.journal.append(self._event("EXECUTION_KILL_FAILED"))
            raise AutopilotError("EXECUTION_KILL_PROPAGATION_FAILED") from None
        with self.journal.transaction():
            self.journal.read()
            self.journal.append(self._event("EXECUTION_KILL_CONFIRMED"))
        return kill_event

    @staticmethod
    def _suspended(events: list[dict[str, Any]]) -> bool:
        state = False
        for event in events:
            if event["kind"] == "SUSPENDED":
                state = True
            elif event["kind"] == "RESUMED":
                state = False
        return state

    @staticmethod
    def _execution_state(event: dict[str, Any]) -> Literal["SETTLED", "UNRESOLVED", "UNKNOWN"]:
        kind, status = event.get("kind"), event.get("status")
        if kind == "UNKNOWN" or status == "UNKNOWN":
            return "UNKNOWN"
        if kind == "PREPARED" or status in {"NEW", "PARTIALLY_FILLED"}:
            return "UNRESOLVED"
        if kind == "RISK_REJECTED" or (
            kind == "REPORT" and status in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED"}
        ):
            return "SETTLED"
        return "UNKNOWN"

    @staticmethod
    def _unresolved(events: list[dict[str, Any]]) -> bool:
        states: dict[str, str] = {}
        for event in events:
            if event["kind"] == "CYCLE_DECISION" and event["decision"]["outcome"] == "SUBMIT":
                selected = event["decision"]["selected_client_id"]
                states[selected] = "UNKNOWN"
            elif event["kind"] in {"CYCLE_RESULT", "RECONCILIATION"}:
                selected = event.get("selected_client_id")
                if selected:
                    states[selected] = event["execution_state"]
        return any(state in {"UNKNOWN", "UNRESOLVED"} for state in states.values())

    def run(self, cycle: AutopilotCycle) -> dict[str, Any]:
        cycle = AutopilotCycle.model_validate_json(cycle.model_dump_json())
        cycle_key, cycle_hash = str(cycle.cycle_id), digest(cycle)
        selected: AutopilotCandidate | None = None
        with self.journal.transaction():
            events = self.journal.read()
            existing = [event for event in events if event["cycle_id"] == cycle_key]
            if existing:
                if existing[0].get("cycle_hash") != cycle_hash:
                    raise AutopilotError("AUTOPILOT_CYCLE_IDEMPOTENCY_CONFLICT")
                if (
                    existing[-1]["kind"] == "CYCLE_DECISION"
                    and existing[-1]["decision"]["outcome"] == "SUBMIT"
                ):
                    return self.journal.append(
                        self._event(
                            "CYCLE_RESULT",
                            cycle_key,
                            cycle_hash=cycle_hash,
                            selected_client_id=existing[-1]["decision"]["selected_client_id"],
                            decision=existing[-1]["decision"],
                            execution_state="UNKNOWN",
                            reason="RECOVERED_UNKNOWN_EXECUTION_STATE",
                            execution_event=None,
                        )
                    )
                return existing[-1]
            decision, selected = self._decide(cycle, events)
            event = self.journal.append(
                self._event(
                    "CYCLE_DECISION",
                    cycle_key,
                    cycle_hash=cycle_hash,
                    decision=decision.model_dump(mode="json"),
                )
            )
            if selected is None:
                return event
        assert selected is not None
        selected_id = client_id(selected.request)
        try:
            execution_event = self.execution.submit(selected.request)
            state = self._execution_state(execution_event)
            reason = None
        except Exception:
            execution_event = None
            state = "UNKNOWN"
            reason = "EXECUTION_CALL_FAILED"
        with self.journal.transaction():
            self.journal.read()
            return self.journal.append(
                self._event(
                    "CYCLE_RESULT",
                    cycle_key,
                    cycle_hash=cycle_hash,
                    selected_client_id=selected_id,
                    decision=decision.model_dump(mode="json"),
                    execution_state=state,
                    reason=reason,
                    execution_event=execution_event,
                )
            )

    def reconcile(self, cycle_id: UUID) -> dict[str, Any]:
        cycle_key = str(cycle_id)
        with self.journal.transaction():
            events = self.journal.read()
            related = [event for event in events if event["cycle_id"] == cycle_key]
            decision = next((event for event in related if event["kind"] == "CYCLE_DECISION"), None)
            if decision is None or decision["decision"]["outcome"] != "SUBMIT":
                raise AutopilotError("AUTOPILOT_CYCLE_NOT_SUBMITTED")
            selected_id = decision["decision"]["selected_client_id"]
            latest = related[-1]
            if latest.get("execution_state") == "SETTLED":
                return latest
        try:
            execution_event = self.execution.reconcile(selected_id)
            state = self._execution_state(execution_event)
            reason = None
        except Exception:
            execution_event = None
            state = "UNKNOWN"
            reason = "EXECUTION_RECONCILIATION_FAILED"
        with self.journal.transaction():
            self.journal.read()
            return self.journal.append(
                self._event(
                    "RECONCILIATION",
                    cycle_key,
                    cycle_hash=decision["cycle_hash"],
                    selected_client_id=selected_id,
                    decision=decision["decision"],
                    execution_state=state,
                    reason=reason,
                    execution_event=execution_event,
                )
            )

    def _decide(
        self, cycle: AutopilotCycle, events: list[dict[str, Any]]
    ) -> tuple[AutopilotDecision, AutopilotCandidate | None]:
        now = utc(self.clock.now())
        reasons = self._global_reasons(cycle, events, now)
        assessments: list[CandidateAssessment] = []
        eligible: list[AutopilotCandidate] = []
        for candidate in cycle.candidates[: self.policy.maximum_candidates_per_cycle]:
            candidate_reasons = self._candidate_reasons(cycle, candidate, now)
            assessments.append(
                CandidateAssessment(
                    client_id=client_id(candidate.request),
                    eligible=not candidate_reasons,
                    reasons=tuple(candidate_reasons),
                )
            )
            if not candidate_reasons:
                eligible.append(candidate)
        if len(cycle.candidates) > self.policy.maximum_candidates_per_cycle:
            reasons.append("CANDIDATE_BUDGET_EXCEEDED")
        selected = None if reasons or not eligible else min(eligible, key=self._selection_key)
        if not reasons and not eligible:
            reasons.append("NO_ELIGIBLE_CANDIDATE")
        outcome: Literal["HALTED", "NO_ACTION", "SUBMIT"]
        if selected is not None:
            outcome = "SUBMIT"
        elif reasons and reasons != ["NO_ELIGIBLE_CANDIDATE"]:
            outcome = "HALTED"
        else:
            outcome = "NO_ACTION"
        decision = AutopilotDecision(
            cycle_id=cycle.cycle_id,
            cycle_hash=digest(cycle),
            policy_hash=digest(self.policy),
            assessed_at=now,
            outcome=outcome,
            selected_client_id=client_id(selected.request) if selected else None,
            reasons=tuple(dict.fromkeys(reasons)),
            candidates=tuple(assessments),
            submission_permitted=selected is not None,
        )
        return decision, selected

    def _global_reasons(
        self, cycle: AutopilotCycle, events: list[dict[str, Any]], now: datetime
    ) -> list[str]:
        reasons: list[str] = []
        spot = self.execution.policy
        if self.policy.mode != "SYNTHETIC_QUALIFICATION" or not self.policy.enabled:
            reasons.append("AUTOPILOT_DISABLED")
        if (
            spot.mode != "SYNTHETIC_QUALIFICATION"
            or not spot.global_enable
            or not spot.manual_enable
            or self.execution.broker.origin != "SYNTHETIC"
        ):
            reasons.append("EXECUTION_STACK_NOT_QUALIFIED")
        if any(event["kind"] == "KILL" for event in events):
            reasons.append("KILL_SWITCH")
        if self._suspended(events):
            reasons.append("MANUALLY_SUSPENDED")
        if self._unresolved(events):
            reasons.append("EXECUTION_STATE_UNRESOLVED")
        if any(datetime.fromisoformat(event["at"]) > now for event in events):
            reasons.append("JOURNAL_CLOCK_MOVED_BACKWARDS")
        if not 0 <= (now - cycle.requested_at).total_seconds() <= self.policy.stale_data_seconds:
            reasons.append("CYCLE_STALE_OR_FUTURE")
        if (
            not 0
            <= (now - cycle.health.checked_at).total_seconds()
            <= self.policy.stale_data_seconds
        ):
            reasons.append("HEALTH_STALE_OR_FUTURE")
        if cycle.health.checked_at > cycle.requested_at:
            reasons.append("HEALTH_AVAILABLE_AFTER_CYCLE")
        checks = (
            (cycle.health.provider_ready, "PROVIDER_UNAVAILABLE"),
            (cycle.health.risk_ready, "RISK_STATE_UNAVAILABLE"),
            (cycle.health.portfolio_ready, "PORTFOLIO_STATE_INCONSISTENT"),
            (cycle.health.reconciliation_resolved, "RECONCILIATION_UNRESOLVED"),
            (cycle.health.execution_ready, "EXECUTION_STATE_UNAVAILABLE"),
        )
        reasons.extend(reason for ready, reason in checks if not ready)
        attempts = [
            datetime.fromisoformat(event["at"])
            for event in events
            if event["kind"] == "CYCLE_DECISION" and event["decision"]["outcome"] == "SUBMIT"
        ]
        if attempts and (now - max(attempts)).total_seconds() < self.policy.cooldown_seconds:
            reasons.append("COOLDOWN_ACTIVE")
        return reasons

    def _candidate_reasons(
        self, cycle: AutopilotCycle, candidate: AutopilotCandidate, now: datetime
    ) -> list[str]:
        request = candidate.request
        policy = self.policy
        reasons: list[str] = []
        if request.strategy.asset_id not in policy.asset_ids:
            reasons.append("ASSET_NOT_ALLOWED")
        if digest(request.strategy) not in policy.strategy_hashes:
            reasons.append("STRATEGY_NOT_ALLOWED")
        if candidate.model_event.to_stage.value != "SHADOW":
            reasons.append("MODEL_NOT_SHADOW_READY")
        if candidate.strategy_event.to_stage.value != "SHADOW":
            reasons.append("STRATEGY_NOT_SHADOW_READY")
        timestamps = (
            request.proposal.at,
            request.quote_at,
            request.loss_context_at,
            request.portfolio.as_of,
            request.portfolio.generated_at,
            candidate.model_event.at,
            candidate.strategy_event.at,
        )
        if any(
            not 0 <= (now - value).total_seconds() <= policy.stale_data_seconds
            for value in timestamps
        ):
            reasons.append("STALE_OR_FUTURE_INPUT")
        if any(value > cycle.requested_at for value in timestamps):
            reasons.append("INPUT_AVAILABLE_AFTER_CYCLE")
        portfolio = request.portfolio
        if (
            portfolio.status != PortfolioSnapshotStatus.COMPLETE
            or portfolio.equity is None
            or portfolio.total_market_value is None
        ):
            reasons.append("PORTFOLIO_STATE_INCONSISTENT")
        else:
            with localcontext() as context:
                context.prec = 80
                quantity = request.intent.quantity or Decimal(0)
                reserve = (
                    quantity
                    * request.limit_price
                    * (1 + self.execution.policy.maximum_fee_fraction)
                ).quantize(Decimal("1e-18"), rounding=ROUND_CEILING)
                projected = portfolio.total_market_value + (
                    reserve if request.intent.action == "BUY" else Decimal(0)
                )
                if projected > policy.maximum_capital:
                    reasons.append("AUTOPILOT_CAPITAL_LIMIT")
                if projected > policy.maximum_exposure:
                    reasons.append("AUTOPILOT_EXPOSURE_LIMIT")
                loss = request.daily_start_equity + request.daily_net_flows - portfolio.equity
                if loss >= policy.maximum_daily_loss:
                    reasons.append("AUTOPILOT_DAILY_LOSS_LIMIT")
                if portfolio.equity > request.high_water_equity:
                    reasons.append("HIGH_WATER_INCONSISTENT")
                elif (
                    request.high_water_equity - portfolio.equity
                ) / request.high_water_equity >= policy.maximum_drawdown:
                    reasons.append("AUTOPILOT_DRAWDOWN_LIMIT")
                positions = {
                    item.market.market_id
                    for item in portfolio.positions
                    if item.status == PositionStatus.OPEN
                }
                new_position = (
                    request.intent.action == "BUY" and request.strategy.market_id not in positions
                )
                if len(positions) + int(new_position) > policy.maximum_simultaneous_positions:
                    reasons.append("AUTOPILOT_POSITION_LIMIT")
        if request.intent.action == "BUY":
            reasons.extend(self._scan_reasons(cycle, candidate, now))
        return reasons

    def _scan_reasons(
        self, cycle: AutopilotCycle, candidate: AutopilotCandidate, now: datetime
    ) -> list[str]:
        scan = cycle.scan
        if scan is None:
            return ["SCAN_EVIDENCE_MISSING"]
        if not 0 <= (now - scan.generated_at).total_seconds() <= self.policy.stale_data_seconds:
            return ["SCAN_STALE_OR_FUTURE"]
        if scan.generated_at > cycle.requested_at:
            return ["SCAN_AVAILABLE_AFTER_CYCLE"]
        group = next(
            (item for item in scan.groups if item.policy_hash == candidate.scan_policy_hash), None
        )
        entry = (
            next((item for item in group.entries if item.rank == candidate.scan_rank), None)
            if group
            else None
        )
        request = candidate.request
        if entry is None or (
            entry.market.market_id,
            entry.market.asset_id,
            entry.opportunity.candle_timeframe,
            entry.opportunity.horizon,
            entry.opportunity.direction,
        ) != (
            request.strategy.market_id,
            request.strategy.asset_id,
            request.strategy.timeframe,
            request.strategy.horizon,
            DirectionalSide.LONG,
        ):
            return ["SCAN_EVIDENCE_MISMATCH"]
        return []

    @staticmethod
    def _selection_key(candidate: AutopilotCandidate) -> tuple[int, int, str, str]:
        request = candidate.request
        return (
            0 if request.intent.action == "SELL" else 1,
            candidate.scan_rank or 0,
            request.strategy.asset_id,
            client_id(request),
        )
