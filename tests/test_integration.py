import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.main import create_app


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("PA_INTEGRATION") != "1", reason="requires disposable DB and Redis")
def test_migration_round_trip_and_readiness() -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "0001")
    engine = build_engine(Settings())
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO audit_events
            (event_id, occurred_at, correlation_id, reason, actor)
            VALUES ('00000000-0000-0000-0000-000000000001', now(),
            '00000000-0000-0000-0000-000000000002', 'SYSTEM_STARTED', 'migration-test')
            ON CONFLICT DO NOTHING""")
        )
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").status_code == 200
    command.downgrade(config, "0001")
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM audit_events WHERE actor='migration-test'")
            )
            == 1
        )
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()
