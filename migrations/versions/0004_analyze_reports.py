"""Immutable Analyze reports."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyze_reports",
        sa.Column("report_id", sa.Uuid(), primary_key=True),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False),
        sa.Column("candle_timeframe", sa.String(3), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("report_version", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_analyze_reports_market_timeframe_as_of",
        "analyze_reports",
        ["market_id", "candle_timeframe", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_analyze_reports_market_timeframe_as_of", table_name="analyze_reports")
    op.drop_table("analyze_reports")
