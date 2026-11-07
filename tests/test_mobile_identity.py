from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.routing import Mount

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.config import Settings
from pocket_alpha.database import Base
from pocket_alpha.main import create_app
from pocket_alpha.mobile.auth import rate_limit
from pocket_alpha.mobile.models import DeviceSessionRecord, OperatorRecord
from pocket_alpha.mobile.security import password_hash, verify_password

PASSWORD = "test-only-long-operator-passphrase"  # pragma: allowlist secret


@pytest.fixture
def native() -> Iterator[tuple[TestClient, Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    app = create_app(Settings(environment="test", mobile_api_enabled=True))
    app.state.engine = engine
    mobile = next(
        route.app for route in app.routes if isinstance(route, Mount) and route.path == "/mobile"
    )
    assert isinstance(mobile, FastAPI)
    mobile.dependency_overrides[rate_limit] = lambda: None
    with Session(engine) as db:
        db.add(
            OperatorRecord(
                user_id=uuid4(),
                username="operator",
                workspace="operator",
                password_hash=password_hash(PASSWORD),
                disabled=False,
            )
        )
        db.commit()
        yield TestClient(app), db
    engine.dispose()


def login(client: TestClient) -> dict[str, str]:
    result = client.post(
        "/mobile/api/v1/auth/login",
        json={"username": "operator", "password": PASSWORD, "device_name": "Android test"},
    )
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()  # type: ignore[no-any-return]


def headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": "Bearer " + tokens["access_token"]}


def test_password_hash_is_salted_and_bounded() -> None:
    first, second = password_hash(PASSWORD), password_hash(PASSWORD)
    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password("incorrect", first)
    assert not verify_password(PASSWORD, "invalid")
    with pytest.raises(ValueError):
        password_hash("short")


def test_login_rotation_replay_and_revocation(native: tuple[TestClient, Session]) -> None:
    client, db = native
    first = login(client)
    assert client.get("/mobile/api/v1/markets", headers=headers(first)).status_code == 200
    rotated = client.post(
        "/mobile/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200
    second = rotated.json()
    assert client.get("/mobile/api/v1/status", headers=headers(first)).status_code == 401
    assert client.get("/mobile/api/v1/status", headers=headers(second)).status_code == 200
    assert (
        client.post(
            "/mobile/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        ).status_code
        == 401
    )
    assert client.get("/mobile/api/v1/status", headers=headers(second)).status_code == 401
    row = db.scalar(select(DeviceSessionRecord))
    assert row is not None
    assert row.refresh_hash != second["refresh_token"]
    assert row.access_hash != second["access_token"]
    db.refresh(row)
    assert row.revoked


def test_session_inventory_logout_and_expiry(native: tuple[TestClient, Session]) -> None:
    client, db = native
    first, second = login(client), login(client)
    inventory = client.get("/mobile/api/v1/auth/sessions", headers=headers(first))
    assert inventory.status_code == 200 and len(inventory.json()) == 2
    assert not any("hash" in key for item in inventory.json() for key in item)
    assert (
        client.delete(
            "/mobile/api/v1/auth/sessions/" + second["session_id"], headers=headers(first)
        ).status_code
        == 204
    )
    assert client.get("/mobile/api/v1/status", headers=headers(second)).status_code == 401
    row = db.get(DeviceSessionRecord, __import__("uuid").UUID(first["session_id"]))
    assert row is not None
    row.access_expires_at = SystemClock().now() - timedelta(seconds=1)
    db.commit()
    assert client.get("/mobile/api/v1/status", headers=headers(first)).status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "markets",
        "watchlists",
        "portfolios",
        "scans",
        "paper/accounts",
        "strategies",
        "research/reports/" + str(uuid4()),
    ],
)
def test_all_business_routes_require_identity(
    native: tuple[TestClient, Session], path: str
) -> None:
    client, _ = native
    assert client.get("/mobile/api/v1/" + path).status_code == 401


def test_boundaries_and_invalid_credentials(native: tuple[TestClient, Session]) -> None:
    client, _ = native
    token = login(client)
    for path in ("live-control", "execution", "broker", "autopilot", "health/ready"):
        assert client.get("/mobile/api/v1/" + path, headers=headers(token)).status_code == 404
    assert client.get("/mobile/openapi.json").status_code == 404
    assert (
        client.post(
            "/mobile/api/v1/auth/login",
            json={
                "username": "operator",
                "password": "wrong",  # pragma: allowlist secret -- invalid login fixture
                "device_name": "phone",
            },  # pragma: allowlist secret
        ).status_code
        == 401
    )
    assert client.post("/mobile/api/v1/auth/login", content=b"x" * 16385).status_code == 413
    assert (
        client.post(
            "/mobile/api/v1/watchlists",
            headers=headers(token),
            json={"watchlist_id": str(uuid4()), "name": "Native list"},
        ).status_code
        == 200
    )
    assert (
        client.get("/mobile/api/v1/watchlists", headers=headers(token)).json()[0]["name"]
        == "Native list"
    )


def test_accounting_requires_step_up(native: tuple[TestClient, Session]) -> None:
    client, _ = native
    tokens = login(client)
    portfolio_id = str(uuid4())
    created = client.post(
        "/mobile/api/v1/portfolios",
        headers=headers(tokens),
        json={"portfolio_id": portfolio_id, "name": "Manual", "base_currency": "USD"},
    )
    assert created.status_code == 200
    payload = {
        "entry_id": str(uuid4()),
        "entry_type": "DEPOSIT",
        "expected_revision": 1,
        "occurred_at": SystemClock().now().isoformat(),
        "cash_amount": "10.01",
    }
    path = f"/mobile/api/v1/portfolios/{portfolio_id}/entries"
    assert client.post(path, headers=headers(tokens), json=payload).status_code == 403
    assert (
        client.post(
            "/mobile/api/v1/auth/step-up", headers=headers(tokens), json={"password": "incorrect"}
        ).status_code
        == 403
    )
    assert client.get("/mobile/api/v1/status", headers=headers(tokens)).status_code == 200
    assert (
        client.post(
            "/mobile/api/v1/auth/step-up", headers=headers(tokens), json={"password": PASSWORD}
        ).status_code
        == 204
    )
    assert client.post(path, headers=headers(tokens), json=payload).status_code == 200
    assert client.post(path, headers=headers(tokens), json=payload).status_code == 200
    entries = client.get(path, headers=headers(tokens)).json()
    assert len(entries) == 1 and entries[0]["cash_amount"] == "10.010000000000000000"


def test_snapshot_discovery_is_bounded_and_requires_identity(
    native: tuple[TestClient, Session],
) -> None:
    client, db = native
    from pocket_alpha.market_data.storage import MarketRepository
    from tests.market_fixtures import register

    register(MarketRepository(db))
    db.commit()
    tokens = login(client)
    path = "/mobile/api/v1/markets/test-market/analysis/snapshots"
    assert client.get(path, params={"timeframe": "1h"}).status_code == 401
    empty = client.get(path, headers=headers(tokens), params={"timeframe": "1h"})
    assert empty.status_code == 200 and empty.json()["items"] == []
    assert (
        client.get(
            path, headers=headers(tokens), params={"timeframe": "1h", "limit": 101}
        ).status_code
        == 422
    )
    assert (
        client.get(
            path, headers=headers(tokens), params={"timeframe": "1h", "cursor": "invalid"}
        ).status_code
        == 422
    )


def test_watchlist_deletion_is_revision_checked_and_preserves_history(
    native: tuple[TestClient, Session],
) -> None:
    client, db = native
    from pocket_alpha.watchlists.storage import WatchlistRecord

    tokens = login(client)
    identifier = str(uuid4())
    path = f"/mobile/api/v1/watchlists/{identifier}"
    assert (
        client.post(
            "/mobile/api/v1/watchlists",
            headers=headers(tokens),
            json={"watchlist_id": identifier, "name": "Delete me"},
        ).status_code
        == 200
    )
    assert (
        client.delete(path, headers=headers(tokens), params={"expected_revision": 2}).status_code
        == 409
    )
    assert (
        client.delete(path, headers=headers(tokens), params={"expected_revision": 1}).status_code
        == 204
    )
    assert client.get(path, headers=headers(tokens)).status_code == 404
    assert client.get("/mobile/api/v1/watchlists", headers=headers(tokens)).json() == []
    row = db.get(WatchlistRecord, __import__("uuid").UUID(identifier))
    assert row is not None
    db.refresh(row)
    assert row.archived and row.revision == 2


def test_snapshot_cursor_discovers_existing_reports_without_loading_payloads(
    native: tuple[TestClient, Session],
) -> None:
    client, db = native
    from pocket_alpha.analysis.storage import AnalyzeRepository
    from pocket_alpha.market_data.storage import MarketRepository
    from tests.market_fixtures import register
    from tests.test_analyze import SERVICE, unavailable_request
    from tests.test_opportunity_score import GENERATED

    register(MarketRepository(db))
    report = SERVICE.assemble(unavailable_request(), generated_at=GENERATED)
    AnalyzeRepository(db).put(report)
    second = report.model_copy(update={"report_id": uuid4()})
    AnalyzeRepository(db).put(second)
    db.commit()
    tokens = login(client)
    path = "/mobile/api/v1/markets/test-market/analysis/snapshots"
    page = client.get(path, headers=headers(tokens), params={"timeframe": "1h", "limit": 1})
    assert page.status_code == 200
    first = page.json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    assert "payload" not in first["items"][0]
    following = client.get(
        path,
        headers=headers(tokens),
        params={"timeframe": "1h", "limit": 1, "cursor": first["next_cursor"]},
    ).json()
    assert len(following["items"]) == 1 and following["next_cursor"] is None
    assert following["items"][0]["report_id"] != first["items"][0]["report_id"]


def test_latest_candle_uses_stored_closed_data_and_excludes_future(
    native: tuple[TestClient, Session],
) -> None:
    client, db = native
    from pocket_alpha.market_data.storage import MarketRepository
    from tests.market_fixtures import register, sample

    repository = MarketRepository(db)
    register(repository)
    future = SystemClock().now() + timedelta(days=1)
    repository.put(
        (
            sample(0),
            sample(1),
            sample(
                2,
                open_time=future,
                close_time=future + timedelta(hours=1),
                received_at=future + timedelta(hours=1),
            ),
        )
    )
    db.commit()
    tokens = login(client)
    path = "/mobile/api/v1/markets/test-market/candles/latest"
    result = client.get(path, headers=headers(tokens), params={"timeframe": "1h"})
    assert result.status_code == 200
    assert result.json()["candle"]["source"] == "fixture"
    assert result.json()["candle"]["close_time"].startswith("2025-01-01T02:00:00")
    assert result.json()["age_seconds"] > 0
    assert client.get(path, params={"timeframe": "1h"}).status_code == 401
