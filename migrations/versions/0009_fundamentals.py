"""Append-only corporate fundamental facts and explicit provider identities."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_mappings",
        sa.Column("source", sa.String(128), primary_key=True),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), primary_key=True),
        sa.Column("instrument_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "instrument_id", name="uq_fundamental_instrument"),
    )
    op.create_table(
        "fundamental_facts",
        sa.Column("fact_id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(256), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_fact_id", sa.Uuid(), sa.ForeignKey("fundamental_facts.fact_id")),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "source",
            "asset_id",
            "source_record_id",
            name="uq_fundamental_source_record",
        ),
    )
    op.create_index(
        "ix_fundamental_asset_availability",
        "fundamental_facts",
        ["asset_id", "available_at", "ingested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_fundamental_asset_availability", table_name="fundamental_facts")
    op.drop_table("fundamental_facts")
    op.drop_table("fundamental_mappings")
