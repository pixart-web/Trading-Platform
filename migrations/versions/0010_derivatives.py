"""Immutable derivative identity and causal observation revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "derivative_contracts",
        sa.Column("contract_id", sa.String(128), primary_key=True),
        sa.Column(
            "underlying_asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False
        ),
        sa.Column("venue_id", sa.String(128), sa.ForeignKey("venues.venue_id"), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("external_contract_id", sa.String(256), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "source", "external_contract_id", name="uq_derivative_external_contract"
        ),
    )
    op.create_index(
        "ix_derivative_underlying_venue",
        "derivative_contracts",
        ["underlying_asset_id", "venue_id"],
    )
    op.create_table(
        "derivative_observations",
        sa.Column("observation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "contract_id",
            sa.String(128),
            sa.ForeignKey("derivative_contracts.contract_id"),
            nullable=False,
        ),
        sa.Column("source_record_id", sa.String(256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_observation_id",
            sa.Uuid(),
            sa.ForeignKey("derivative_observations.observation_id"),
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("contract_id", "source_record_id", name="uq_derivative_source_record"),
        sa.UniqueConstraint(
            "contract_id", "observed_at", "revision", name="uq_derivative_revision"
        ),
    )
    op.create_index(
        "ix_derivative_observation_cutoff",
        "derivative_observations",
        ["contract_id", "observed_at", "available_at", "ingested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_derivative_observation_cutoff", table_name="derivative_observations")
    op.drop_table("derivative_observations")
    op.drop_index("ix_derivative_underlying_venue", table_name="derivative_contracts")
    op.drop_table("derivative_contracts")
