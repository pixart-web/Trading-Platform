"""Native boundary against disposable PostgreSQL and Redis, never production."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import count
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import event, select, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import Session

from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.main import create_app
from pocket_alpha.mobile.models import DeviceSessionRecord, OperatorRecord
from pocket_alpha.mobile.security import password_hash


@pytest.fixture
def native_services(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    # A fresh owned schema makes repeated tests independent of the provisioned E2E workspace.
    original = Settings(environment="test")
    schema = "pa_native_" + uuid4().hex
    admin = build_engine(original)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(original.database_url.get_secret_value()).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    monkeypatch.setenv("PA_DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv(
        "PA_REDIS_URL",
        urlsplit(original.redis_url.get_secret_value())._replace(path="/15").geturl(),
    )
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield Settings(environment="test", mobile_api_enabled=True)
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("PA_INTEGRATION") != "1", reason="requires disposable DB and Redis")
def test_native_identity_postgres_redis_and_server_ledger(native_services: Settings) -> None:
    settings = native_services
    engine = build_engine(settings)
    user_id = uuid4()
    password = "disposable-native-integration-passphrase"  # pragma: allowlist secret
    with Session(engine) as db, db.begin():
        db.add(
            OperatorRecord(
                user_id=user_id,
                workspace="operator",
                username="native-test",
                password_hash=password_hash(password),
                disabled=False,
            )
        )
    try:
        with TestClient(create_app(settings)) as client:
            signed = client.post(
                "/mobile/api/v1/auth/login",
                json={
                    "username": "native-test",
                    "password": password,
                    "device_name": "integration",
                },
            )
            assert signed.status_code == 200, signed.text
            credentials = signed.json()
            headers = {"Authorization": "Bearer " + credentials["access_token"]}
            assert client.get("/mobile/api/v1/status", headers=headers).status_code == 200
            created = client.post(
                "/mobile/api/v1/watchlists",
                headers=headers,
                json={"watchlist_id": str(uuid4()), "name": "Native integration"},
            )
            assert created.status_code == 200
            changed = client.post(
                "/mobile/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]}
            )
            assert changed.status_code == 200
            assert client.get("/mobile/api/v1/watchlists", headers=headers).status_code == 401
            headers["Authorization"] = "Bearer " + changed.json()["access_token"]
            assert client.get("/mobile/api/v1/watchlists", headers=headers).status_code == 200
            assert (
                client.post(
                    "/mobile/api/v1/auth/refresh",
                    json={"refresh_token": credentials["refresh_token"]},
                ).status_code
                == 401
            )
            assert client.get("/mobile/api/v1/watchlists", headers=headers).status_code == 401
            with Session(engine) as db:
                sessions = list(
                    db.scalars(
                        select(DeviceSessionRecord).where(DeviceSessionRecord.user_id == user_id)
                    )
                )
                assert len(sessions) == 1 and sessions[0].revoked
                assert sessions[0].access_hash != changed.json()["access_token"]
            # Exercise distributed Redis admission using only these disposable auth keys.
            cache = Redis.from_url(settings.redis_url.get_secret_value())
            from pocket_alpha.common.clock import SystemClock

            key = "mobile-auth:" + str(int(SystemClock().now().timestamp()) // 60)
            cache.set(key, 21, ex=120)
            assert (
                client.post(
                    "/mobile/api/v1/auth/login",
                    json={
                        "username": "native-test",
                        "password": password,
                        "device_name": "limited",
                    },
                ).status_code
                == 429
            )
            cache.delete(key)
            cache.close()
    finally:
        engine.dispose()


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("PA_INTEGRATION") != "1", reason="requires disposable DB and Redis")
def test_concurrent_refresh_replay_revokes_the_new_token(native_services: Settings) -> None:
    setup_engine = build_engine(native_services)
    password = "disposable-concurrent-refresh-password"  # pragma: allowlist secret
    with Session(setup_engine) as db, db.begin():
        db.add(
            OperatorRecord(
                user_id=uuid4(),
                workspace="operator",
                username="concurrency",
                password_hash=password_hash(password),
                disabled=False,
            )
        )
    setup_engine.dispose()
    app = create_app(native_services)
    with TestClient(app) as client:
        issued = client.post(
            "/mobile/api/v1/auth/login",
            json={
                "username": "concurrency",
                "password": password,
                "device_name": "concurrent-test",
            },
        )
        assert issued.status_code == 200
        token = issued.json()["refresh_token"]
        barrier, observed = Barrier(2), count()

        def synchronize_initial_reads(
            connection: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if "FROM mobile_consumed_refresh" in statement and next(observed) < 2:
                barrier.wait(timeout=10)

        event.listen(app.state.engine, "after_cursor_execute", synchronize_initial_reads)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [
                    pool.submit(
                        client.post, "/mobile/api/v1/auth/refresh", json={"refresh_token": token}
                    )
                    for _ in range(2)
                ]
                results = [future.result(timeout=15) for future in pending]
            assert sorted(result.status_code for result in results) == [200, 401]
            rotated = next(result.json() for result in results if result.status_code == 200)
            assert (
                client.get(
                    "/mobile/api/v1/status",
                    headers={"Authorization": "Bearer " + rotated["access_token"]},
                ).status_code
                == 401
            )
        finally:
            event.remove(app.state.engine, "after_cursor_execute", synchronize_initial_reads)
