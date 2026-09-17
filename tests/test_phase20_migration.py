import importlib
from datetime import UTC, datetime

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, create_engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError


def test_0011_upgrade_foreign_keys_uniqueness_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module("migrations.versions.0011_context_and_datasets")
    assert migration.revision == "0011" and migration.down_revision == "0010"
    engine = create_engine("sqlite://")
    prerequisites = MetaData()
    Table("assets", prerequisites, Column("asset_id", String(128), primary_key=True))
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            prerequisites.create_all(connection)
            connection.execute(insert(prerequisites.tables["assets"]).values(asset_id="synthetic"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            metadata = MetaData()
            metadata.reflect(connection)
            entities, mappings, observations = (
                metadata.tables[t]
                for t in ("context_entities", "context_mappings", "context_observations")
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(entities).values(entity_id="bad", asset_id="missing", payload="{}")
                )
            connection.execute(insert(entities).values(entity_id="topic", payload="{}"))
            connection.execute(
                insert(mappings).values(
                    source="fixture", entity_id="topic", external_entity_id="topic"
                )
            )
            now = datetime(2025, 1, 1, tzinfo=UTC)
            data = dict(
                observation_id="00000000000000000000000000002001",
                entity_id="topic",
                source="fixture",
                source_record_id="1",
                event_key="event",
                revision=1,
                published_at=now,
                available_at=now,
                ingested_at=now,
                payload="{}",
            )
            connection.execute(insert(observations).values(data))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(observations).values(
                        data
                        | {
                            "observation_id": "00000000000000000000000000002002",
                            "source_record_id": "2",
                        }
                    )
                )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(observations).values(
                        data
                        | {
                            "observation_id": "00000000000000000000000000002003",
                            "source": "unmapped",
                        }
                    )
                )
            for invalid in ({"published_at": datetime(2025, 1, 2, tzinfo=UTC)}, {"revision": 2}):
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(
                        insert(observations).values(
                            data
                            | {
                                "observation_id": "00000000000000000000000000002004",
                                "source_record_id": "invalid",
                                "event_key": "invalid",
                            }
                            | invalid
                        )
                    )
            assert "ix_context_cutoff" in {
                i["name"] for i in inspect(connection).get_indexes("context_observations")
            }
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["assets"]
            assert connection.scalar(text("SELECT count(*) FROM assets")) == 1
    finally:
        engine.dispose()
