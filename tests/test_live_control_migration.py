import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0016_safe_seed_constraints_and_clean_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module("migrations.versions.0016_live_control")
    assert migration.revision == "0016" and migration.down_revision == "0015"
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("CREATE TABLE preserved (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO preserved VALUES (1)"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            row = connection.execute(
                text("SELECT revision, mode, kill_switch_active FROM live_control")
            ).one()
            assert row == (0, "OFF", 0)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text(
                        "UPDATE live_control SET mode='LIVE', revision=-1 "
                        "WHERE control_key='primary'"
                    )
                )
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["preserved"]
            assert connection.scalar(text("SELECT count(*) FROM preserved")) == 1
    finally:
        engine.dispose()
