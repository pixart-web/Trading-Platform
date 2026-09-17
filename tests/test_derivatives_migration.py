"""Migration DDL runs only in an ephemeral SQLite database, never real orders/data."""

import importlib
from datetime import UTC, datetime

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, create_engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0010_additive_upgrade_constraints_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = importlib.import_module("migrations.versions.0010_derivatives")
    assert migration.revision == "0010" and migration.down_revision == "0009"
    engine = create_engine("sqlite://")
    prerequisites = MetaData()
    Table("assets", prerequisites, Column("asset_id", String(128), primary_key=True))
    Table("venues", prerequisites, Column("venue_id", String(128), primary_key=True))
    original_op = migration.op
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            prerequisites.create_all(connection)
            connection.execute(
                insert(prerequisites.tables["assets"]).values(asset_id="synthetic-asset")
            )
            connection.execute(
                insert(prerequisites.tables["venues"]).values(venue_id="synthetic-venue")
            )
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            reflected = MetaData()
            reflected.reflect(connection)
            contracts = reflected.tables["derivative_contracts"]
            observations = reflected.tables["derivative_observations"]
            now = datetime(2025, 1, 1, tzinfo=UTC)
            contract = {
                "contract_id": "derivative:synthetic",
                "underlying_asset_id": "synthetic-asset",
                "venue_id": "synthetic-venue",
                "source": "fixture",
                "external_contract_id": "FIXTURE",
                "available_at": now,
                "ingested_at": now,
                "payload": "{}",
            }
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(contracts).values(contract | {"underlying_asset_id": "missing"})
                )
            connection.execute(insert(contracts).values(contract))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(contracts).values(contract | {"contract_id": "derivative:duplicate"})
                )
            observation = {
                "observation_id": "00000000000000000000000000001901",
                "contract_id": "derivative:synthetic",
                "source_record_id": "fixture:1",
                "revision": 1,
                "observed_at": now,
                "published_at": now,
                "available_at": now,
                "ingested_at": now,
                "payload": "{}",
            }
            connection.execute(insert(observations).values(observation))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(observations).values(
                        observation
                        | {
                            "observation_id": "00000000000000000000000000001902",
                            "source_record_id": "fixture:2",
                        }
                    )
                )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(observations).values(
                        observation
                        | {
                            "observation_id": "00000000000000000000000000001903",
                            "observed_at": datetime(2025, 1, 2, tzinfo=UTC),
                            "contract_id": "missing",
                        }
                    )
                )
            names = {
                index["name"]
                for index in inspect(connection).get_indexes("derivative_observations")
            }
            assert "ix_derivative_observation_cutoff" in names
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == {"assets", "venues"}
            assert connection.scalar(text("SELECT count(*) FROM assets")) == 1
    finally:
        monkeypatch.setattr(migration, "op", original_op)
        engine.dispose()
