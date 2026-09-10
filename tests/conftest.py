import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from pocket_alpha.config import Settings
from pocket_alpha.database import Base, build_engine
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import register


@pytest.fixture(params=["sqlite", "postgresql"])
def repository(request: pytest.FixtureRequest) -> Iterator[MarketRepository]:
    if request.param == "postgresql":
        if os.getenv("PA_INTEGRATION") != "1":
            pytest.skip("PostgreSQL service not configured")
        command.upgrade(Config("alembic.ini"), "head")
        engine = build_engine(Settings())
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        with engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            repo = MarketRepository(session)
            register(repo)
            yield repo
        transaction.rollback()
    engine.dispose()
