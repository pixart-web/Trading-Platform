import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0014_mode_uniqueness_foreign_key_and_preserved_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module("migrations.versions.0014_paper")
    assert migration.revision == "0014" and migration.down_revision == "0013"
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("CREATE TABLE preserved (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO preserved VALUES (1)"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            key = "00000000000000000000000000002301"
            account = text("INSERT INTO paper_accounts VALUES (:id,:mode,0,:hash,'{}',:hash,'{}')")
            connection.execute(account, dict(id=key, mode="PAPER", hash="a" * 64))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(account, dict(id="0" * 32, mode="LIVE", hash="a" * 64))
            statement = text(
                "INSERT INTO paper_journal VALUES (:id,:revision,'PAPER',:event,:hash,'{}')"
            )
            values = dict(
                id=key, revision=1, event="00000000000000000000000000002302", hash="b" * 64
            )
            connection.execute(statement, values)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, values | dict(revision=2))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, values | dict(id="0" * 32))
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["preserved"]
            assert connection.scalar(text("SELECT count(*) FROM preserved")) == 1
    finally:
        engine.dispose()
