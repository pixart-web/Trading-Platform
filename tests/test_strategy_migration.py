import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0015_no_live_uniqueness_foreign_key_preserved_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module("migrations.versions.0015_strategies")
    assert migration.revision == "0015" and migration.down_revision == "0014"
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("CREATE TABLE preserved (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO preserved VALUES (1)"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            key = "00000000000000000000000000002401"
            insert = text(
                "INSERT INTO strategy_registry VALUES (:id,'v1','market',0,:stage,:hash,'{}')"
            )
            values = dict(id=key, stage="RESEARCH", hash="a" * 64)
            connection.execute(insert, values)
            for change in [dict(id="1" * 32, stage="LIVE"), dict(id="1" * 32)]:
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(insert, values | change)
            event = text("INSERT INTO strategy_events VALUES (:id,0,:hash,'{}')")
            connection.execute(event, values)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(event, values | dict(id="0" * 32))
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["preserved"]
            assert connection.scalar(text("SELECT count(*) FROM preserved")) == 1
    finally:
        engine.dispose()
