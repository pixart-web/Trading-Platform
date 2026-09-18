"""Persistent PAPER heads and append-only replay journals."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_accounts",
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("header_hash", sa.String(64), nullable=False),
        sa.Column("header", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.CheckConstraint("mode = 'PAPER'", name="ck_paper_account_mode"),
    )
    op.create_table(
        "paper_journal",
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("paper_accounts.account_id"), primary_key=True
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.CheckConstraint("mode = 'PAPER'", name="ck_paper_journal_mode"),
        sa.UniqueConstraint("account_id", "event_id", name="uq_paper_event"),
    )


def downgrade() -> None:
    # Export journals first: this removes only PAPER data, never research or market records.
    op.drop_table("paper_journal")
    op.drop_table("paper_accounts")
