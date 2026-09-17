"""Causal context observations and frozen labelled market datasets."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_entities",
        sa.Column("entity_id", sa.String(128), primary_key=True),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "context_mappings",
        sa.Column("source", sa.String(128), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(128),
            sa.ForeignKey("context_entities.entity_id"),
            primary_key=True,
        ),
        sa.Column("external_entity_id", sa.String(256), nullable=False),
        sa.UniqueConstraint("source", "external_entity_id", name="uq_context_external_entity"),
    )
    op.create_table(
        "context_observations",
        sa.Column("observation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "entity_id", sa.String(128), sa.ForeignKey("context_entities.entity_id"), nullable=False
        ),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(256), nullable=False),
        sa.Column("event_key", sa.String(256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_observation_id",
            sa.Uuid(),
            sa.ForeignKey("context_observations.observation_id"),
            nullable=True,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source", "entity_id"],
            ["context_mappings.source", "context_mappings.entity_id"],
            name="fk_context_provider_mapping",
        ),
        sa.CheckConstraint(
            "published_at <= available_at AND available_at <= ingested_at", name="ck_context_time"
        ),
        sa.CheckConstraint(
            "revision >= 1 AND ((revision = 1 AND supersedes_observation_id IS NULL) "
            "OR (revision > 1 AND supersedes_observation_id IS NOT NULL))",
            name="ck_context_revision",
        ),
        sa.UniqueConstraint(
            "source", "entity_id", "source_record_id", name="uq_context_source_record"
        ),
        sa.UniqueConstraint(
            "source", "entity_id", "event_key", "revision", name="uq_context_revision"
        ),
    )
    op.create_index(
        "ix_context_cutoff", "context_observations", ["entity_id", "available_at", "ingested_at"]
    )
    op.create_table(
        "market_data_datasets",
        sa.Column("dataset_id", sa.Uuid(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data_datasets")
    op.drop_index("ix_context_cutoff", table_name="context_observations")
    op.drop_table("context_observations")
    op.drop_table("context_mappings")
    op.drop_table("context_entities")
