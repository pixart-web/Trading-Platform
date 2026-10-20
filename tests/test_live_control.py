from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from pocket_alpha.audit.models import AuditRecord
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.config import Settings
from pocket_alpha.database import Base
from pocket_alpha.live_control.models import (
    Broker,
    ConfigureControl,
    ControlAction,
    LiveControlEventRecord,
    LivePolicy,
    MarketKind,
    ReadinessEvidence,
    TradingMode,
    TransitionControl,
)
from pocket_alpha.live_control.service import ControlConflict, ControlRejected, LiveControlService
from pocket_alpha.main import create_app

NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def policy(**changes: object) -> LivePolicy:
    values: dict[str, object] = {
        "version": "operator-policy-1",
        "currency": "EUR",
        "capital_limit": Decimal("10000"),
        "order_notional_limit": Decimal("500"),
        "total_exposure_limit": Decimal("10000"),
        "position_notional_limit": Decimal("2000"),
        "strategy_exposure_limit": Decimal("3000"),
        "broker_exposure_limit": Decimal("10000"),
        "asset_exposure_limit": Decimal("2500"),
        "daily_loss_limit": Decimal("250"),
        "maximum_drawdown": Decimal("0.10"),
        "maximum_leverage": Decimal("1"),
        "maximum_positions": 10,
        "maximum_orders_per_minute": 5,
        "maximum_orders_per_day": 100,
        "maximum_slippage_fraction": Decimal("0.002"),
        "maximum_spread_fraction": Decimal("0.003"),
        "maximum_price_deviation_fraction": Decimal("0.005"),
        "maximum_data_age_seconds": 30,
        "maximum_account_age_seconds": 30,
    }
    values.update(changes)
    return LivePolicy.model_validate(values)


def configure(revision: int = 0, **policy_changes: object) -> ConfigureControl:
    return ConfigureControl(
        expected_revision=revision,
        broker=Broker.BINANCE,
        market=MarketKind.SPOT,
        account_identity_hash="a" * 64,
        policy=policy(**policy_changes),
        confirmation="CONFIGURE LIVE CONTROL",
    )


def action(revision: int, value: ControlAction) -> TransitionControl:
    return TransitionControl(
        expected_revision=revision,
        action=value,
        confirmation=value.value.replace("_", " "),
    )


def evidence(**changes: object) -> ReadinessEvidence:
    values: dict[str, object] = {
        "source": "independent-qualification-service",
        "verified_at": NOW,
        "credential_qualified": True,
        "account_qualified": True,
        "risk_ready": True,
        "strategy_ready": True,
        "market_data_healthy": True,
        "infrastructure_healthy": True,
        "reconciliation_healthy": True,
        "execution_healthy": True,
        "evidence_hash": "b" * 64,
    }
    values.update(changes)
    return ReadinessEvidence.model_validate(values)


@pytest.fixture
def service() -> Iterator[tuple[LiveControlService, Session]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(
        live_trading_enabled=True,
        control_proxy_token=SecretStr("x" * 32),
    )
    yield LiveControlService(session, settings, FrozenClock(NOW)), session
    session.close()
    engine.dispose()


def test_policy_rejects_incoherent_limits() -> None:
    with pytest.raises(ValidationError, match="order limit exceeds position limit"):
        policy(order_notional_limit=Decimal("3000"))


def test_default_is_off_and_flag_alone_cannot_activate(
    service: tuple[LiveControlService, Session],
) -> None:
    control, _ = service
    initial = control.snapshot()
    assert initial.mode == TradingMode.OFF
    assert initial.live_deployment_enabled
    with pytest.raises(ControlRejected, match="invalid transition"):
        control.transition(
            action(initial.revision, ControlAction.ACTIVATE_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )


def test_configure_arm_and_activate_requires_fresh_complete_evidence(
    service: tuple[LiveControlService, Session],
) -> None:
    control, session = service
    configured = control.configure(configure(), actor="operator", correlation_id=uuid4())
    assert configured.policy_hash and configured.mode == TradingMode.OFF
    armed = control.transition(
        action(configured.revision, ControlAction.ARM_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    with pytest.raises(ControlRejected, match="evidence is missing"):
        control.transition(
            action(armed.revision, ControlAction.ACTIVATE_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )
    halted = control.transition(
        action(armed.revision, ControlAction.HALT_NEW_ORDERS),
        actor="operator",
        correlation_id=uuid4(),
    )
    ready = control.record_readiness(
        evidence(),
        expected_revision=halted.revision,
        actor="qualification-service",
        correlation_id=uuid4(),
    )
    rearmed = control.transition(
        action(ready.revision, ControlAction.ARM_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    active = control.transition(
        action(rearmed.revision, ControlAction.ACTIVATE_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    assert active.mode == TradingMode.LIVE_ACTIVE
    assert len(session.scalars(select(LiveControlEventRecord)).all()) == 6
    assert len(session.scalars(select(AuditRecord)).all()) == 6


def test_failed_readiness_and_stale_evidence_fail_closed(
    service: tuple[LiveControlService, Session],
) -> None:
    control, _ = service
    configured = control.configure(configure(), actor="operator", correlation_id=uuid4())
    ready = control.record_readiness(
        evidence(execution_healthy=False),
        expected_revision=configured.revision,
        actor="qualification-service",
        correlation_id=uuid4(),
    )
    armed = control.transition(
        action(ready.revision, ControlAction.ARM_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    with pytest.raises(ControlRejected, match="readiness gates failed"):
        control.transition(
            action(armed.revision, ControlAction.ACTIVATE_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )

    halted = control.transition(
        action(armed.revision, ControlAction.HALT_NEW_ORDERS),
        actor="operator",
        correlation_id=uuid4(),
    )
    stale = control.record_readiness(
        evidence(verified_at=NOW - timedelta(minutes=1)),
        expected_revision=halted.revision,
        actor="qualification-service",
        correlation_id=uuid4(),
    )
    rearmed = control.transition(
        action(stale.revision, ControlAction.ARM_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    with pytest.raises(ControlRejected, match="stale"):
        control.transition(
            action(rearmed.revision, ControlAction.ACTIVATE_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )


def test_account_freshness_limit_can_be_stricter_than_market_data(
    service: tuple[LiveControlService, Session],
) -> None:
    control, _ = service
    configured = control.configure(
        configure(maximum_data_age_seconds=120, maximum_account_age_seconds=30),
        actor="operator",
        correlation_id=uuid4(),
    )
    ready = control.record_readiness(
        evidence(verified_at=NOW - timedelta(seconds=31)),
        expected_revision=configured.revision,
        actor="qualification-service",
        correlation_id=uuid4(),
    )
    armed = control.transition(
        action(ready.revision, ControlAction.ARM_LIVE),
        actor="operator",
        correlation_id=uuid4(),
    )
    with pytest.raises(ControlRejected, match="stale"):
        control.transition(
            action(armed.revision, ControlAction.ACTIVATE_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )


def test_kill_switch_persists_and_requires_explicit_reset(
    service: tuple[LiveControlService, Session],
) -> None:
    control, session = service
    configured = control.configure(configure(), actor="operator", correlation_id=uuid4())
    killed = control.transition(
        action(configured.revision, ControlAction.ACTIVATE_KILL_SWITCH),
        actor="operator",
        correlation_id=uuid4(),
    )
    assert killed.mode == TradingMode.KILL_SWITCH and killed.kill_switch_active
    session.commit()
    restored = control.snapshot()
    assert restored.kill_switch_active
    with pytest.raises(ControlRejected, match="invalid transition"):
        control.transition(
            action(restored.revision, ControlAction.ARM_LIVE),
            actor="operator",
            correlation_id=uuid4(),
        )
    reset = control.transition(
        action(restored.revision, ControlAction.RESET_KILL_SWITCH),
        actor="operator",
        correlation_id=uuid4(),
    )
    assert reset.mode == TradingMode.OFF and not reset.kill_switch_active


def test_revision_and_confirmation_prevent_stale_or_accidental_actions(
    service: tuple[LiveControlService, Session],
) -> None:
    control, _ = service
    configured = control.configure(configure(), actor="operator", correlation_id=uuid4())
    with pytest.raises(ControlConflict):
        control.transition(
            action(0, ControlAction.ARM_LIVE), actor="operator", correlation_id=uuid4()
        )
    bad = action(configured.revision, ControlAction.ARM_LIVE).model_copy(
        update={"confirmation": "yes"}
    )
    with pytest.raises(ControlRejected, match="confirmation"):
        control.transition(bad, actor="operator", correlation_id=uuid4())


def test_api_requires_internal_proxy_token_and_returns_safe_default() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    cache = MagicMock()
    cache.ping.return_value = True
    settings = Settings(control_proxy_token=SecretStr("x" * 32))
    with (
        patch("pocket_alpha.main.build_engine", return_value=engine),
        patch("pocket_alpha.main.Redis.from_url", return_value=cache),
        TestClient(create_app(settings)) as client,
    ):
        assert client.get("/api/v1/live-control").status_code == 401
        response = client.get(
            "/api/v1/live-control",
            headers={"X-PA-Control-Token": "x" * 32, "X-PA-Actor": "operator"},
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "OFF"
        assert response.headers["Cache-Control"] == "no-store"
    engine.dispose()
