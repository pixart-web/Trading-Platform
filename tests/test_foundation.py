import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from pocket_alpha.audit.models import AuditEvent, AuditReason, AuditRecord
from pocket_alpha.audit.repository import append_event
from pocket_alpha.config import Settings
from pocket_alpha.database import Base
from pocket_alpha.domain.models import Asset, AssetType, ForecastHorizon, Money, TimestampedModel
from pocket_alpha.main import create_app
from pocket_alpha.observability import JsonFormatter


def test_live_execution_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PA_LIVE_TRADING_ENABLED", "true")
    with pytest.raises(ValidationError):
        Settings()


def test_secrets_are_masked() -> None:
    assert "local_only" not in repr(Settings())


def test_domain_precision_and_immutability() -> None:
    money = Money.model_validate({"amount": "0.123456789123456789", "currency": "EUR"})
    assert money.amount == Decimal("0.123456789123456789")
    with pytest.raises(ValidationError):
        Money(amount=Decimal("NaN"), currency="EUR")
    asset = Asset(
        asset_id="example", symbol="EX", name="Synthetic fixture", asset_type=AssetType.ETF
    )
    with pytest.raises(ValidationError):
        asset.symbol = "CHANGED"
    assert len(ForecastHorizon) == 13


def test_timestamps_reject_naive_and_normalize_utc() -> None:
    with pytest.raises(ValidationError):
        TimestampedModel(observed_at=datetime(2026, 1, 1))
    model = TimestampedModel.model_validate({"observed_at": "2026-01-01T01:00:00+01:00"})
    assert model.observed_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_audit_persists_and_duplicate_does_not_overwrite() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    event = AuditEvent(correlation_id=uuid4(), reason=AuditReason.SYSTEM_STARTED, actor="test")
    with Session(engine) as session, session.begin():
        append_event(session, event)
    with Session(engine) as session:
        stored = session.scalars(select(AuditRecord)).one()
        assert stored.event_id == event.event_id
        assert stored.reason == event.reason
        session.expunge(stored)
        with pytest.raises(IntegrityError):
            append_event(session, event)
        session.rollback()
    engine.dispose()


@pytest.mark.parametrize("healthy", [True, False])
def test_health_dependency_status(healthy: bool) -> None:
    engine = MagicMock()
    cache = MagicMock()
    cache.ping.return_value = True
    if not healthy:
        engine.connect.side_effect = SQLAlchemyError("private database details")
        cache.ping.side_effect = RedisConnectionError("private redis details")
    with (
        patch("pocket_alpha.main.build_engine", return_value=engine),
        patch("pocket_alpha.main.Redis.from_url", return_value=cache),
        patch("pocket_alpha.main.append_event"),
        TestClient(create_app(Settings())) as client,
    ):
        response = client.get("/health/live")
        assert response.status_code == 200
        UUID(response.headers["X-Correlation-ID"])
        response = client.get("/health/ready")
        assert response.status_code == (200 if healthy else 503)
        assert response.json()["checks"]["database"] is healthy
        assert response.json()["checks"]["redis"] is healthy
        assert "private" not in response.text
    cache.close.assert_called_once()
    engine.dispose.assert_called_once()


def test_failed_startup_audit_prevents_readiness() -> None:
    with (
        patch("pocket_alpha.main.build_engine"),
        patch("pocket_alpha.main.Redis.from_url"),
        patch("pocket_alpha.main.append_event", side_effect=SQLAlchemyError("secret")),
        TestClient(create_app(Settings())) as client,
    ):
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["audit"] is False


def test_structured_logging_allowlists_fields() -> None:
    record = logging.LogRecord("pocket_alpha", logging.INFO, "", 0, "http_request", (), None)
    record.api_key = "not-to-be-logged"
    record.correlation_id = "example"
    output = JsonFormatter().format(record)
    assert "not-to-be-logged" not in output
    assert json.loads(output)["correlation_id"] == "example"
