"""Durable derivative dispatch qualification with native execution hard-blocked."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Literal, Protocol

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import Clock, SystemClock, utc
from pocket_alpha.derivative_execution.models import (
    DerivativeBrokerReport,
    DerivativeExecutionPolicy,
    DerivativeExecutionRequest,
)
from pocket_alpha.derivative_execution.risk import evaluate


class ExecutionError(Exception):
    pass


class BrokerPort(Protocol):
    origin: Literal["REAL", "SYNTHETIC"]

    def submit(
        self, client_id: str, request: DerivativeExecutionRequest
    ) -> DerivativeBrokerReport: ...

    def query(self, client_id: str, contract_id: str) -> DerivativeBrokerReport | None: ...


class DisabledNativeDerivativeBroker:
    """No credentials, network calls, transfers, withdrawals or order endpoints."""

    origin: Literal["REAL", "SYNTHETIC"] = "REAL"

    def submit(self, client_id: str, request: DerivativeExecutionRequest) -> DerivativeBrokerReport:
        raise ExecutionError("FOUNDATION_DERIVATIVE_LIVE_DISABLED")

    def query(self, client_id: str, contract_id: str) -> DerivativeBrokerReport | None:
        raise ExecutionError("AUTHENTICATED_DERIVATIVE_QUERY_UNQUALIFIED")


def client_id(request: DerivativeExecutionRequest) -> str:
    identity = (
        request.account.account_identity_hash
        + ":"
        + request.strategy.definition_hash
        + ":"
        + str(request.intent.intent_id)
    )
    return "pd" + hashlib.sha256(identity.encode()).hexdigest()[:32]


class Journal:
    """Account-pinned SQLite log with a serialized append-only hash chain."""

    def __init__(self, path: Path, account: str, origin: str) -> None:
        self.connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.connection.execute("PRAGMA synchronous=FULL")
        with self.transaction():
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), "
                "account TEXT NOT NULL, origin TEXT NOT NULL, version TEXT NOT NULL)"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, "
                "payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL)"
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO identity VALUES (1, ?, ?, 'derivative-journal-1')",
                (account, origin),
            )
            identity = self.connection.execute(
                "SELECT account, origin, version FROM identity WHERE id=1"
            ).fetchone()
            if identity != (account, origin, "derivative-journal-1"):
                raise ExecutionError("JOURNAL_IDENTITY_MISMATCH")
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
            raise ExecutionError("JOURNAL_BUDGET_EXCEEDED")
        previous = "0" * 64
        result: list[dict[str, Any]] = []
        for expected, (sequence, payload, prior, content) in enumerate(rows, 1):
            event: dict[str, Any] = json.loads(payload)
            if (
                sequence != expected
                or prior != previous
                or content != digest({"previous": prior, "event": event})
            ):
                raise ExecutionError("JOURNAL_INTEGRITY_FAILURE")
            previous = content
            result.append(event)
        return result

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT sequence, hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence, previous = (row[0] + 1, row[1]) if row else (1, "0" * 64)
        if sequence > 10000:
            raise ExecutionError("JOURNAL_BUDGET_EXCEEDED")
        content = digest({"previous": previous, "event": event})
        self.connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (sequence, json.dumps(event, sort_keys=True), previous, content),
        )
        return event

    def close(self) -> None:
        self.connection.close()


class DerivativeExecution:
    def __init__(
        self,
        path: Path,
        policy: DerivativeExecutionPolicy,
        *,
        broker: BrokerPort | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.policy = DerivativeExecutionPolicy.model_validate_json(policy.model_dump_json())
        self.broker = broker or DisabledNativeDerivativeBroker()
        self.clock = clock or SystemClock()
        self.journal = Journal(path, policy.account_identity_hash, self.broker.origin)

    def _event(self, kind: str, cid: str = "", **data: Any) -> dict[str, Any]:
        return {
            "kind": kind,
            "client_id": cid,
            "at": utc(self.clock.now()).isoformat(),
            **data,
        }

    def kill(self) -> None:
        with self.journal.transaction():
            self.journal.read()
            self.journal.append(self._event("KILL"))
        # Latched by design: re-enable and automated liquidation are unavailable.

    def submit(self, request: DerivativeExecutionRequest) -> dict[str, Any]:
        request = DerivativeExecutionRequest.model_validate_json(request.model_dump_json())
        cid, request_hash = client_id(request), digest(request)
        with self.journal.transaction():
            events = self.journal.read()
            existing = [event for event in events if event["client_id"] == cid]
            if existing:
                first = existing[0]
                if first["request_hash"] != request_hash:
                    raise ExecutionError("IDEMPOTENCY_CONFLICT")
                if existing[-1]["kind"] == "PREPARED":
                    return self.journal.append(
                        self._event(
                            "UNKNOWN",
                            cid,
                            status="UNKNOWN",
                            reason="RECOVERED_INDETERMINATE_DISPATCH",
                        )
                    )
                return existing[-1]

            now = utc(self.clock.now())
            decision = evaluate(
                request,
                self.policy,
                now=now,
                broker_origin=self.broker.origin,
                killed=any(event["kind"] == "KILL" for event in events),
            )
            reasons = list(decision.reasons)
            states: dict[str, str] = {}
            for event in events:
                if event["client_id"]:
                    states[event["client_id"]] = event.get("status", event["kind"])
            if any(
                state in {"PREPARED", "UNKNOWN", "NEW", "PARTIALLY_FILLED"}
                for state in states.values()
            ):
                reasons.append("ACCOUNT_FLOW_UNRESOLVED")
            prepared = [event for event in events if event["kind"] == "PREPARED"]
            if (
                sum(
                    0 <= (now - datetime.fromisoformat(event["at"])).total_seconds() < 60
                    for event in prepared
                )
                >= self.policy.maximum_orders_per_minute
            ):
                reasons.append("MINUTE_RATE_LIMIT")
            if (
                sum(datetime.fromisoformat(event["at"]).date() == now.date() for event in prepared)
                >= self.policy.maximum_orders_per_day
            ):
                reasons.append("DAILY_RATE_LIMIT")
            accounted = [
                event for event in events if event["kind"] in {"PREPARED", "REPORT", "UNKNOWN"}
            ]
            if accounted and request.account.completed_at <= max(
                datetime.fromisoformat(event["at"]) for event in accounted
            ):
                reasons.append("ACCOUNT_SNAPSHOT_NOT_REFRESHED")
            if any(datetime.fromisoformat(event["at"]) > now for event in events):
                reasons.append("JOURNAL_CLOCK_MOVED_BACKWARDS")
            if reasons:
                return self.journal.append(
                    self._event(
                        "RISK_REJECTED",
                        cid,
                        request_hash=request_hash,
                        reasons=list(dict.fromkeys(reasons)),
                        decision=decision.model_dump(mode="json"),
                    )
                )
            self.journal.append(
                self._event(
                    "PREPARED",
                    cid,
                    request_hash=request_hash,
                    request=request.model_dump(mode="json"),
                    decision=decision.model_dump(mode="json"),
                )
            )

        with self.journal.transaction():
            if any(event["kind"] == "KILL" for event in self.journal.read()):
                return self.journal.append(
                    self._event(
                        "REPORT",
                        cid,
                        status="REJECTED",
                        reason="KILL_BEFORE_DISPATCH",
                    )
                )
        try:
            report = self.broker.submit(cid, request)
        except Exception:
            return self._unknown(cid, "SUBMISSION_RESULT_UNKNOWN")
        return self._accept(cid, report)

    def _unknown(
        self,
        cid: str,
        reason: str,
        report: DerivativeBrokerReport | None = None,
    ) -> dict[str, Any]:
        with self.journal.transaction():
            self.journal.read()
            return self.journal.append(
                self._event(
                    "UNKNOWN",
                    cid,
                    status="UNKNOWN",
                    reason=reason,
                    report=report.model_dump(mode="json") if report else None,
                )
            )

    def _accept(self, cid: str, incoming: DerivativeBrokerReport) -> dict[str, Any]:
        try:
            report = DerivativeBrokerReport.model_validate_json(incoming.model_dump_json())
            with self.journal.transaction():
                events = self.journal.read()
                history = [event for event in events if event["client_id"] == cid]
                prepared = next(event for event in history if event["kind"] == "PREPARED")
                request = DerivativeExecutionRequest.model_validate(prepared["request"])
                intent = request.intent
                if (
                    report.client_id,
                    report.contract_id,
                    report.position_side,
                    report.order_side,
                    report.effect,
                    report.reduce_only,
                    report.original_contracts,
                    report.limit_price,
                ) != (
                    cid,
                    intent.contract_id,
                    intent.position_side,
                    intent.order_side,
                    intent.effect,
                    intent.reduce_only,
                    intent.contracts,
                    intent.limit_price,
                ):
                    raise ExecutionError("BROKER_IDENTITY_MISMATCH")
                now = utc(self.clock.now())
                if not datetime.fromisoformat(prepared["at"]) <= report.at <= now:
                    raise ExecutionError("BROKER_REPORT_TIME_INVALID")
                serialized = report.model_dump(mode="json")
                if history[-1]["kind"] == "REPORT" and history[-1].get("report") == serialized:
                    return history[-1]
                prior_reports = [
                    event["report"]
                    for event in history
                    if event["kind"] == "REPORT" and event.get("report")
                ]
                if prior_reports:
                    previous = DerivativeBrokerReport.model_validate(prior_reports[-1])
                    if serialized in prior_reports:
                        if prior_reports[-1] != serialized:
                            return history[-1]
                        return self.journal.append(
                            self._event(
                                "REPORT",
                                cid,
                                status=report.status,
                                report=serialized,
                            )
                        )
                    previous_fees = {fee.currency: fee.amount for fee in previous.commissions}
                    current_fees = {fee.currency: fee.amount for fee in report.commissions}
                    if (
                        previous.status in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED"}
                        or report.order_id != previous.order_id
                        or report.executed_contracts < previous.executed_contracts
                        or report.cumulative_settlement_value < previous.cumulative_settlement_value
                        or (
                            report.executed_contracts == previous.executed_contracts
                            and report.cumulative_settlement_value
                            != previous.cumulative_settlement_value
                        )
                        or report.at < previous.at
                        or any(
                            current_fees.get(currency, Decimal(0)) < amount
                            for currency, amount in previous_fees.items()
                        )
                    ):
                        raise ExecutionError("BROKER_REPORT_REGRESSION")
                with localcontext() as context:
                    context.prec = 80
                    limit_value = (
                        report.executed_contracts
                        * request.market.contract.multiplier
                        * report.limit_price
                    )
                    if (
                        report.order_side == "BUY"
                        and report.cumulative_settlement_value > limit_value
                    ) or (
                        report.order_side == "SELL"
                        and report.cumulative_settlement_value < limit_value
                    ):
                        raise ExecutionError("LIMIT_PRICE_VIOLATION")
                    if any(
                        fee.amount > 0 and fee.currency != self.policy.collateral_currency
                        for fee in report.commissions
                    ):
                        raise ExecutionError("UNVALUED_COMMISSION")
                    total_fees = sum((fee.amount for fee in report.commissions), start=Decimal(0))
                    if total_fees > limit_value * self.policy.maximum_fee_fraction:
                        raise ExecutionError("COMMISSION_BUDGET_EXCEEDED")
                    if abs(report.funding_paid) > (
                        limit_value * self.policy.maximum_funding_fraction
                    ):
                        raise ExecutionError("FUNDING_BUDGET_EXCEEDED")
                    if report.effect == "OPEN" and report.realized_pnl != 0:
                        raise ExecutionError("OPEN_REPORT_HAS_REALIZED_PNL")
                return self.journal.append(
                    self._event(
                        "REPORT",
                        cid,
                        status=report.status,
                        report=serialized,
                    )
                )
        except Exception:
            return self._unknown(cid, "BROKER_REPORT_REQUIRES_RECONCILIATION", incoming)

    def reconcile(self, cid: str) -> dict[str, Any]:
        with self.journal.transaction():
            events = self.journal.read()
            prepared = next(
                (
                    event
                    for event in events
                    if event["client_id"] == cid and event["kind"] == "PREPARED"
                ),
                None,
            )
            if prepared is None:
                raise ExecutionError("ORDER_NOT_SUBMITTED")
            contract_id = prepared["request"]["intent"]["contract_id"]
        try:
            report = self.broker.query(cid, contract_id)
        except Exception:
            return self._unknown(cid, "QUERY_RESULT_UNKNOWN")
        if report is None:
            return self._unknown(cid, "ORDER_NOT_FOUND_NOT_PROOF_OF_REJECTION")
        return self._accept(cid, report)
