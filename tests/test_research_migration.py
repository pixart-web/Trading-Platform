import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0013_additive_upgrade_consumption_uniqueness_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module("migrations.versions.0013_research")
    assert migration.revision == "0013" and migration.down_revision == "0012"
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("CREATE TABLE preserved (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO preserved VALUES (1)"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            study = "00000000000000000000000000002201"
            connection.execute(
                text("INSERT INTO research_studies VALUES (:id,:hash,:payload)"),
                dict(id=study, hash="a" * 64, payload="{}"),
            )
            claim = dict(asset="CRYPTO:BTC", study=study, hash="b" * 64, payload="{}")
            statement = text(
                "INSERT INTO research_holdout_consumption VALUES (:asset,:study,:hash,:payload)"
            )
            connection.execute(statement, claim)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, claim)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, claim | dict(asset="CRYPTO:ETH", study="0" * 32))
            assert len(inspect(connection).get_table_names()) == 6
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["preserved"]
            assert connection.scalar(text("SELECT count(*) FROM preserved")) == 1
    finally:
        engine.dispose()
