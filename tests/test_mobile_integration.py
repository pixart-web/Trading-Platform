"""Native boundary against disposable PostgreSQL and Redis, never production."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.main import create_app
from pocket_alpha.mobile.models import ConsumedRefreshRecord, DeviceSessionRecord, OperatorRecord
from pocket_alpha.mobile.security import password_hash


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("PA_INTEGRATION") != "1", reason="requires disposable DB and Redis")
def test_native_identity_postgres_redis_and_server_ledger() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(environment="test", mobile_api_enabled=True)
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
        with Session(engine) as db, db.begin():
            ids = select(DeviceSessionRecord.session_id).where(
                DeviceSessionRecord.user_id == user_id
            )
            db.execute(
                delete(ConsumedRefreshRecord).where(ConsumedRefreshRecord.session_id.in_(ids))
            )
            db.execute(delete(DeviceSessionRecord).where(DeviceSessionRecord.user_id == user_id))
            db.execute(delete(OperatorRecord).where(OperatorRecord.user_id == user_id))
        engine.dispose()
