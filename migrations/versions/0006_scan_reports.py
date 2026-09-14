"""Immutable cross-market scan reports."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_reports",
        sa.Column("scan_id", sa.Uuid(), primary_key=True),
        sa.Column("candle_timeframe", sa.String(3), nullable=False),
        sa.Column("horizon", sa.String(3), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scanner_version", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_scan_reports_timeframe_horizon_as_of",
        "scan_reports",
        ["candle_timeframe", "horizon", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_reports_timeframe_horizon_as_of", table_name="scan_reports")
    op.drop_table("scan_reports")
