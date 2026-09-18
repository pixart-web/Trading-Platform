"""Append-only reproducible offline simulation reports."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_reports",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("market_data_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_backtest_dataset_input", "backtest_reports", ["dataset_id", "input_hash"])


def downgrade() -> None:
    op.drop_index("ix_backtest_dataset_input", table_name="backtest_reports")
    op.drop_table("backtest_reports")
