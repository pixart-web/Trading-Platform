import importlib
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0012_additive_upgrade_fk_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = importlib.import_module("migrations.versions.0012_backtests")
    assert migration.revision == "0012" and migration.down_revision == "0011"
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("market_data_datasets", metadata, Column("dataset_id", Uuid(), primary_key=True))
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            metadata.create_all(connection)
            connection.execute(
                insert(metadata.tables["market_data_datasets"]).values(dataset_id=UUID(int=2100))
            )
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            reflected = MetaData()
            reflected.reflect(connection)
            table = reflected.tables["backtest_reports"]
            values = dict(
                run_id="00000000000000000000000000002101",
                dataset_id=UUID(int=2100).hex,
                input_hash="1" * 64,
                content_hash="2" * 64,
                payload="{}",
            )
            connection.execute(insert(table).values(values))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(table).values(values))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(table).values(
                        values
                        | {
                            "run_id": "00000000000000000000000000002102",
                            "dataset_id": "00000000000000000000000000002999",
                        }
                    )
                )
            assert "ix_backtest_dataset_input" in {
                i["name"] for i in inspect(connection).get_indexes("backtest_reports")
            }
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["market_data_datasets"]
            assert connection.scalar(text("SELECT count(*) FROM market_data_datasets")) == 1
    finally:
        engine.dispose()
