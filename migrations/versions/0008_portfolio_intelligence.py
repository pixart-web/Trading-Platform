"""Immutable portfolio intelligence reports."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_intelligence_reports",
        sa.Column("analysis_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Uuid(),
            sa.ForeignKey("portfolios.portfolio_id"),
            nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_portfolio_intelligence_reports_portfolio_id",
        "portfolio_intelligence_reports",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_portfolio_intelligence_portfolio_as_of",
        "portfolio_intelligence_reports",
        ["portfolio_id", "as_of"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_intelligence_portfolio_as_of",
        table_name="portfolio_intelligence_reports",
    )
    op.drop_index(
        "ix_portfolio_intelligence_reports_portfolio_id",
        table_name="portfolio_intelligence_reports",
    )
    op.drop_table("portfolio_intelligence_reports")
