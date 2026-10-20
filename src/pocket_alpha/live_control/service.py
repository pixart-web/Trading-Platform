import hashlib
import json
from datetime import UTC, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pocket_alpha.audit.models import AuditEvent, AuditReason
from pocket_alpha.audit.repository import append_event
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.config import Settings
from pocket_alpha.live_control.models import (
    Broker,
    ConfigureControl,
    ControlAction,
    LiveControlEventRecord,
    LiveControlRecord,
    LiveControlSnapshot,
    LivePolicy,
    MarketKind,
    ReadinessEvidence,
    TradingMode,
    TransitionControl,
)

CONTROL_KEY = "primary"


class ControlConflict(Exception):
    pass


class ControlRejected(Exception):
    pass


def digest(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class LiveControlService:
    def __init__(self, db: Session, settings: Settings, clock: Clock) -> None:
        self.db = db
        self.settings = settings
        self.clock = clock

    def _row(self, *, lock: bool = False) -> LiveControlRecord:
        statement = select(LiveControlRecord).where(LiveControlRecord.control_key == CONTROL_KEY)
        if lock:
            statement = statement.with_for_update()
        row = self.db.scalars(statement).one_or_none()
        if row is None:
            row = LiveControlRecord(
                control_key=CONTROL_KEY,
                control_id=uuid4(),
                revision=0,
                mode=TradingMode.OFF.value,
                broker=None,
                market=None,
                account_identity_hash=None,
                policy_payload=None,
                policy_hash=None,
                readiness_payload=None,
                kill_switch_active=False,
                updated_at=utc(self.clock.now()),
            )
            self.db.add(row)
            self.db.flush()
        return row

    def snapshot(self) -> LiveControlSnapshot:
        return self._snapshot(self._row())

    def _snapshot(self, row: LiveControlRecord) -> LiveControlSnapshot:
        updated_at = row.updated_at
        if updated_at.tzinfo is None or updated_at.utcoffset() is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return LiveControlSnapshot(
            control_id=row.control_id,
            revision=row.revision,
            mode=TradingMode(row.mode),
            broker=Broker(row.broker) if row.broker else None,
            market=MarketKind(row.market) if row.market else None,
            account_identity_hash=row.account_identity_hash,
            policy=LivePolicy.model_validate_json(row.policy_payload)
            if row.policy_payload
            else None,
            policy_hash=row.policy_hash,
            readiness=ReadinessEvidence.model_validate_json(row.readiness_payload)
            if row.readiness_payload
            else None,
            kill_switch_active=row.kill_switch_active,
            live_deployment_enabled=self.settings.live_trading_enabled,
            derivative_deployment_enabled=self.settings.derivative_execution_enabled,
            updated_at=utc(updated_at),
        )

    def configure(
        self, command: ConfigureControl, *, actor: str, correlation_id: UUID
    ) -> LiveControlSnapshot:
        row = self._row(lock=True)
        self._revision(row, command.expected_revision)
        if row.mode in {TradingMode.LIVE_ARMED.value, TradingMode.LIVE_ACTIVE.value}:
            raise ControlRejected("disable live control before changing policy")
        row.broker = command.broker.value
        row.market = command.market.value
        row.account_identity_hash = command.account_identity_hash
        row.policy_payload = command.policy.model_dump_json()
        row.policy_hash = digest(command.policy)
        row.readiness_payload = None
        self._advance(row, actor, correlation_id, "LIVE_CONTROL_CONFIGURED")
        append_event(
            self.db,
            AuditEvent(
                correlation_id=correlation_id,
                reason=AuditReason.LIVE_CONTROL_CONFIGURED,
                actor=actor,
            ),
        )
        return self._snapshot(row)

    def record_readiness(
        self,
        evidence: ReadinessEvidence,
        *,
        expected_revision: int,
        actor: str,
        correlation_id: UUID,
    ) -> LiveControlSnapshot:
        row = self._row(lock=True)
        self._revision(row, expected_revision)
        if row.mode == TradingMode.LIVE_ACTIVE.value:
            raise ControlRejected("disable live control before replacing readiness evidence")
        row.readiness_payload = evidence.model_dump_json()
        self._advance(row, actor, correlation_id, "LIVE_READINESS_UPDATED")
        append_event(
            self.db,
            AuditEvent(
                correlation_id=correlation_id,
                reason=AuditReason.LIVE_READINESS_UPDATED,
                actor=actor,
            ),
        )
        return self._snapshot(row)

    def transition(
        self, command: TransitionControl, *, actor: str, correlation_id: UUID
    ) -> LiveControlSnapshot:
        row = self._row(lock=True)
        self._revision(row, command.expected_revision)
        if command.confirmation != command.action.value.replace("_", " "):
            raise ControlRejected("operator confirmation does not match action")
        current = TradingMode(row.mode)
        target = self._target(current, command.action)
        if command.action == ControlAction.ARM_LIVE:
            self._require_configured(row)
        elif command.action == ControlAction.ACTIVATE_LIVE:
            self._require_activation(row)
        if command.action == ControlAction.ACTIVATE_KILL_SWITCH:
            row.kill_switch_active = True
        elif command.action == ControlAction.RESET_KILL_SWITCH:
            row.kill_switch_active = False
            row.readiness_payload = None
        row.mode = target.value
        self._advance(row, actor, correlation_id, command.action.value)
        append_event(
            self.db,
            AuditEvent(
                correlation_id=correlation_id,
                reason=AuditReason.LIVE_CONTROL_TRANSITIONED,
                actor=actor,
            ),
        )
        return self._snapshot(row)

    @staticmethod
    def _revision(row: LiveControlRecord, expected: int) -> None:
        if row.revision != expected:
            raise ControlConflict("live control revision changed")

    @staticmethod
    def _target(current: TradingMode, action: ControlAction) -> TradingMode:
        allowed: dict[ControlAction, tuple[set[TradingMode], TradingMode]] = {
            ControlAction.ENABLE_PAPER: ({TradingMode.OFF, TradingMode.HALTED}, TradingMode.PAPER),
            ControlAction.ARM_LIVE: (
                {TradingMode.OFF, TradingMode.PAPER, TradingMode.HALTED},
                TradingMode.LIVE_ARMED,
            ),
            ControlAction.ACTIVATE_LIVE: ({TradingMode.LIVE_ARMED}, TradingMode.LIVE_ACTIVE),
            ControlAction.DISABLE_LIVE: (
                {
                    TradingMode.PAPER,
                    TradingMode.LIVE_ARMED,
                    TradingMode.LIVE_ACTIVE,
                    TradingMode.HALTED,
                },
                TradingMode.OFF,
            ),
            ControlAction.HALT_NEW_ORDERS: (
                {TradingMode.PAPER, TradingMode.LIVE_ARMED, TradingMode.LIVE_ACTIVE},
                TradingMode.HALTED,
            ),
            ControlAction.ACTIVATE_KILL_SWITCH: (set(TradingMode), TradingMode.KILL_SWITCH),
            ControlAction.RESET_KILL_SWITCH: ({TradingMode.KILL_SWITCH}, TradingMode.OFF),
        }
        sources, target = allowed[action]
        if current not in sources:
            raise ControlRejected(f"invalid transition from {current.value}")
        return target

    @staticmethod
    def _require_configured(row: LiveControlRecord) -> None:
        if not all((row.broker, row.market, row.account_identity_hash, row.policy_payload)):
            raise ControlRejected("live control is not configured")
        if row.kill_switch_active:
            raise ControlRejected("kill switch requires explicit reset")

    def _require_activation(self, row: LiveControlRecord) -> None:
        self._require_configured(row)
        if not self.settings.live_trading_enabled:
            raise ControlRejected("live deployment gate is disabled")
        if row.market == "FUTURES" and not self.settings.derivative_execution_enabled:
            raise ControlRejected("derivative deployment gate is disabled")
        if not row.readiness_payload or not row.policy_payload:
            raise ControlRejected("current readiness evidence is missing")
        evidence = ReadinessEvidence.model_validate_json(row.readiness_payload)
        policy = LivePolicy.model_validate_json(row.policy_payload)
        if not all(
            (
                evidence.credential_qualified,
                evidence.account_qualified,
                evidence.risk_ready,
                evidence.strategy_ready,
                evidence.market_data_healthy,
                evidence.infrastructure_healthy,
                evidence.reconciliation_healthy,
                evidence.execution_healthy,
            )
        ):
            raise ControlRejected("one or more live readiness gates failed")
        now = utc(self.clock.now())
        verified = utc(evidence.verified_at)
        maximum_evidence_age = min(
            policy.maximum_data_age_seconds,
            policy.maximum_account_age_seconds,
        )
        if not verified <= now <= verified + timedelta(seconds=maximum_evidence_age):
            raise ControlRejected("live readiness evidence is stale or future-dated")

    def _advance(
        self, row: LiveControlRecord, actor: str, correlation_id: UUID, event_type: str
    ) -> None:
        previous = self.db.scalars(
            select(LiveControlEventRecord)
            .where(LiveControlEventRecord.control_id == row.control_id)
            .order_by(LiveControlEventRecord.revision.desc())
            .limit(1)
        ).one_or_none()
        row.revision += 1
        row.updated_at = utc(self.clock.now())
        payload = json.dumps(
            {
                "control_id": str(row.control_id),
                "revision": row.revision,
                "mode": row.mode,
                "broker": row.broker,
                "market": row.market,
                "account_identity_hash": row.account_identity_hash,
                "policy_hash": row.policy_hash,
                "readiness_hash": digest(json.loads(row.readiness_payload))
                if row.readiness_payload
                else None,
                "kill_switch_active": row.kill_switch_active,
                "event_type": event_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        previous_hash = previous.content_hash if previous else None
        content_hash = hashlib.sha256(((previous_hash or "") + payload).encode()).hexdigest()
        self.db.add(
            LiveControlEventRecord(
                event_id=uuid4(),
                control_id=row.control_id,
                revision=row.revision,
                occurred_at=row.updated_at,
                actor=actor,
                correlation_id=correlation_id,
                event_type=event_type,
                previous_hash=previous_hash,
                content_hash=content_hash,
                payload=payload,
            )
        )
        self.db.flush()
