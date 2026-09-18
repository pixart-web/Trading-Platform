"""Durable one-shot spot dispatch and reconciliation, with native execution hard-blocked."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import localcontext
from pathlib import Path
from typing import Any, Literal, Protocol

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import Clock, SystemClock, utc
from pocket_alpha.spot_execution.binance import BinanceSpotBroker
from pocket_alpha.spot_execution.models import BrokerReport, SpotPolicy, SpotRequest
from pocket_alpha.spot_execution.risk import evaluate


class ExecutionError(Exception):
    pass


class BrokerPort(Protocol):
    origin: Literal["REAL", "SYNTHETIC"]

    def submit(self, client_id: str, request: SpotRequest) -> BrokerReport: ...
    def query(self, client_id: str, symbol: str) -> BrokerReport | None: ...


class DisabledNativeBroker:
    origin: Literal["REAL", "SYNTHETIC"] = "REAL"

    def submit(self, client_id: str, request: SpotRequest) -> BrokerReport:
        raise ExecutionError("FOUNDATION_LIVE_DISABLED")

    def query(self, client_id: str, symbol: str) -> BrokerReport | None:
        raise ExecutionError("AUTHENTICATED_NATIVE_EXECUTION_UNQUALIFIED")


def client_id(request: SpotRequest) -> str:
    identity = (
        request.observation.state.account_identity_hash
        + ":"
        + digest(request.strategy)
        + ":"
        + request.intent.client_id
    )
    return "pa" + hashlib.sha256(identity.encode()).hexdigest()[:32]


class Journal:
    """Account-pinned local SQLite log, append-only hash chain, serialized admission."""

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
                "INSERT OR IGNORE INTO identity VALUES (1, ?, ?, 'spot-journal-1')",
                (account, origin),
            )
            identity = self.connection.execute(
                "SELECT account, origin, version FROM identity WHERE id=1"
            ).fetchone()
            if identity != (account, origin, "spot-journal-1"):
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


class SpotExecution:
    def __init__(
        self,
        path: Path,
        policy: SpotPolicy,
        *,
        broker: BrokerPort | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.policy = SpotPolicy.model_validate_json(policy.model_dump_json())
        self.broker = broker or BinanceSpotBroker(self.policy, clock=clock)
        self.clock = clock or SystemClock()
        self.journal = Journal(path, policy.account_identity_hash, self.broker.origin)

    def _event(self, kind: str, cid: str = "", **data: Any) -> dict[str, Any]:
        return {"kind": kind, "client_id": cid, "at": utc(self.clock.now()).isoformat(), **data}

    def kill(self) -> None:
        with self.journal.transaction():
            self.journal.read()
            self.journal.append(self._event("KILL"))
        # Intentionally latched: no automatic re-enable, cancel or liquidation.

    def submit(self, request: SpotRequest) -> dict[str, Any]:
        request = SpotRequest.model_validate_json(request.model_dump_json())
        cid, request_hash = client_id(request), digest(request)
        with self.journal.transaction():
            events = self.journal.read()
            existing = [x for x in events if x["client_id"] == cid]
            if existing:
                first = existing[0]
                if first["request_hash"] != request_hash:
                    raise ExecutionError("IDEMPOTENCY_CONFLICT")
                # PREPARED after a crash is indeterminate; never call submit a second time.
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
                killed=any(x["kind"] == "KILL" for x in events),
            )
            reasons = list(decision.reasons)
            states: dict[str, str] = {}
            for event in events:
                if event["client_id"]:
                    states[event["client_id"]] = event.get("status", event["kind"])
            if any(
                x in {"PREPARED", "UNKNOWN", "NEW", "PARTIALLY_FILLED"} for x in states.values()
            ):
                reasons.append("ACCOUNT_FLOW_UNRESOLVED")
            prepared = [x for x in events if x["kind"] == "PREPARED"]
            if (
                sum(
                    0 <= (now - datetime.fromisoformat(x["at"])).total_seconds() < 60
                    for x in prepared
                )
                >= self.policy.maximum_orders_per_minute
            ):
                reasons.append("MINUTE_RATE_LIMIT")
            if (
                sum(datetime.fromisoformat(x["at"]).date() == now.date() for x in prepared)
                >= self.policy.maximum_orders_per_day
            ):
                reasons.append("DAILY_RATE_LIMIT")
            accounted = [x for x in events if x["kind"] in {"PREPARED", "REPORT", "UNKNOWN"}]
            if accounted and request.observation.completed_at <= max(
                datetime.fromisoformat(x["at"]) for x in accounted
            ):
                reasons.append("ACCOUNT_SNAPSHOT_NOT_REFRESHED")
            if any(datetime.fromisoformat(x["at"]) > now for x in events):
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
            if any(x["kind"] == "KILL" for x in self.journal.read()):
                return self.journal.append(
                    self._event("REPORT", cid, status="REJECTED", reason="KILL_BEFORE_DISPATCH")
                )
        try:
            report = self.broker.submit(cid, request)
        except Exception:
            return self._unknown(cid, "SUBMISSION_RESULT_UNKNOWN")
        return self._accept(cid, report)

    def _unknown(self, cid: str, reason: str, report: BrokerReport | None = None) -> dict[str, Any]:
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

    def _accept(self, cid: str, incoming: BrokerReport) -> dict[str, Any]:
        try:
            report = BrokerReport.model_validate_json(incoming.model_dump_json())
            with self.journal.transaction():
                events = self.journal.read()
                history = [x for x in events if x["client_id"] == cid]
                prepared = next(x for x in history if x["kind"] == "PREPARED")
                request = SpotRequest.model_validate(prepared["request"])
                if (
                    report.client_id,
                    report.symbol,
                    report.side,
                    report.original_quantity,
                    report.limit_price,
                ) != (
                    cid,
                    request.symbol,
                    request.intent.action,
                    request.intent.quantity,
                    request.limit_price,
                ):
                    raise ExecutionError("BROKER_IDENTITY_MISMATCH")
                now = utc(self.clock.now())
                if not datetime.fromisoformat(prepared["at"]) <= report.at <= now:
                    raise ExecutionError("BROKER_REPORT_TIME_INVALID")
                if any(
                    x is history[-1]
                    and x["kind"] == "REPORT"
                    and x.get("report") == report.model_dump(mode="json")
                    for x in history
                ):
                    return history[-1]
                prior_reports = [
                    x["report"] for x in history if x["kind"] == "REPORT" and x.get("report")
                ]
                if prior_reports:
                    previous = BrokerReport.model_validate(prior_reports[-1])
                    if any(x == report.model_dump(mode="json") for x in prior_reports):
                        if prior_reports[-1] != report.model_dump(mode="json"):
                            return history[-1]
                        return self.journal.append(
                            self._event(
                                "REPORT",
                                cid,
                                status=report.status,
                                report=report.model_dump(mode="json"),
                            )
                        )
                    if (
                        previous.status in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED"}
                        or report.order_id != previous.order_id
                        or report.executed_quantity < previous.executed_quantity
                        or report.cumulative_quote < previous.cumulative_quote
                        or (
                            report.executed_quantity == previous.executed_quantity
                            and report.cumulative_quote != previous.cumulative_quote
                        )
                        or report.at < previous.at
                    ):
                        raise ExecutionError("BROKER_REPORT_REGRESSION")
                    old_fees = {x.asset: x.amount for x in previous.commissions}
                    new_fees = {x.asset: x.amount for x in report.commissions}
                    if any(new_fees.get(asset, 0) < amount for asset, amount in old_fees.items()):
                        raise ExecutionError("COMMISSION_REGRESSION")
                with localcontext() as context:
                    context.prec = 80
                    limit_value = report.executed_quantity * report.limit_price
                    if (report.side == "BUY" and report.cumulative_quote > limit_value) or (
                        report.side == "SELL" and report.cumulative_quote < limit_value
                    ):
                        raise ExecutionError("LIMIT_PRICE_VIOLATION")
                    if any(
                        x.amount > 0 and x.asset != self.policy.quote_asset
                        for x in report.commissions
                    ):
                        raise ExecutionError("UNVALUED_COMMISSION")
                    if (
                        sum((x.amount for x in report.commissions), start=limit_value * 0)
                        > limit_value * self.policy.maximum_fee_fraction
                    ):
                        raise ExecutionError("COMMISSION_BUDGET_EXCEEDED")
                return self.journal.append(
                    self._event(
                        "REPORT", cid, status=report.status, report=report.model_dump(mode="json")
                    )
                )
        except Exception:
            return self._unknown(cid, "BROKER_REPORT_REQUIRES_RECONCILIATION", incoming)

    def reconcile(self, cid: str) -> dict[str, Any]:
        with self.journal.transaction():
            events = self.journal.read()
            prepared = next(
                (x for x in events if x["client_id"] == cid and x["kind"] == "PREPARED"), None
            )
            if prepared is None:
                raise ExecutionError("ORDER_NOT_SUBMITTED")
            symbol = prepared["request"]["symbol"]
        try:
            report = self.broker.query(cid, symbol)
        except Exception:
            return self._unknown(cid, "QUERY_RESULT_UNKNOWN")
        if report is None:
            return self._unknown(cid, "ORDER_NOT_FOUND_NOT_PROOF_OF_REJECTION")
        return self._accept(cid, report)
