import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from pocket_alpha.main import create_app


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("PA_INTEGRATION") != "1", reason="requires disposable DB and Redis")
def test_migration_round_trip_and_readiness() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").status_code == 200
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
