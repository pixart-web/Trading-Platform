"""Versioned strategy registry and immutable lifecycle evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_registry",
        sa.Column("strategy_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("market_id", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("version", "market_id", name="uq_strategy_market_version"),
        sa.CheckConstraint(
            "stage IN ('RESEARCH','CANDIDATE','PAPER','SHADOW','DEGRADED','SUSPENDED','RETIRED')",
            name="ck_strategy_no_live",
        ),
    )
    op.create_table(
        "strategy_events",
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategy_registry.strategy_id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_events")
    op.drop_table("strategy_registry")
