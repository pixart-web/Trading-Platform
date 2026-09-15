"""Manual portfolios and immutable accounting entries."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("portfolio_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("base_currency", sa.String(12), nullable=False),
        sa.Column("accounting_method", sa.String(32), nullable=False),
        sa.Column("valuation_timeframe", sa.String(3), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_portfolio_revision"),
    )
    op.create_table(
        "portfolio_entries",
        sa.Column("entry_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Uuid(),
            sa.ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(12), nullable=False),
        sa.Column("cash_amount", sa.Numeric(38, 18), nullable=True),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=True),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=True),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=True),
        sa.Column("unit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("fee", sa.Numeric(38, 18), nullable=False),
        sa.Column("gross_value", sa.Numeric(38, 18), nullable=False),
        sa.Column("cash_effect", sa.Numeric(38, 18), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(250), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("portfolio_id", "sequence", name="uq_portfolio_entry_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_portfolio_entry_sequence"),
        sa.CheckConstraint("fee >= 0", name="ck_portfolio_entry_fee"),
        sa.CheckConstraint("gross_value > 0", name="ck_portfolio_entry_gross"),
        sa.CheckConstraint("recorded_at >= occurred_at", name="ck_portfolio_entry_time"),
    )
    op.create_index("ix_portfolio_entries_portfolio_id", "portfolio_entries", ["portfolio_id"])
    op.create_index(
        "ix_portfolio_entries_portfolio_occurred",
        "portfolio_entries",
        ["portfolio_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_entries_portfolio_occurred", table_name="portfolio_entries")
    op.drop_index("ix_portfolio_entries_portfolio_id", table_name="portfolio_entries")
    op.drop_table("portfolio_entries")
    op.drop_table("portfolios")
