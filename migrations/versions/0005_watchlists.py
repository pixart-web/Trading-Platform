"""Persistent watchlists, immutable snapshots and alert events."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("watchlist_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "watchlist_members",
        sa.Column("member_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "watchlist_id",
            sa.Uuid(),
            sa.ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False),
        sa.Column("candle_timeframe", sa.String(3), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlist_members_watchlist_id", "watchlist_members", ["watchlist_id"])
    op.create_index(
        "uq_watchlist_member_market",
        "watchlist_members",
        ["watchlist_id", "market_id"],
        unique=True,
    )
    op.create_table(
        "watchlist_snapshots",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.watchlist_id"), nullable=False
        ),
        sa.Column("watchlist_revision", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_watchlist_snapshots_list_as_of", "watchlist_snapshots", ["watchlist_id", "as_of"]
    )
    op.create_table(
        "watchlist_snapshot_items",
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("watchlist_snapshots.snapshot_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("member_id", sa.Uuid(), primary_key=True),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("report_id", sa.Uuid(), sa.ForeignKey("analyze_reports.report_id")),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_watchlist_snapshot_items_market_id", "watchlist_snapshot_items", ["market_id"]
    )
    op.create_table(
        "watchlist_alert_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.watchlist_id"), nullable=False
        ),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("watchlist_snapshots.snapshot_id"),
            nullable=False,
        ),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_watchlist_alerts_list_created",
        "watchlist_alert_events",
        ["watchlist_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_alerts_list_created", table_name="watchlist_alert_events")
    op.drop_table("watchlist_alert_events")
    op.drop_index("ix_watchlist_snapshot_items_market_id", table_name="watchlist_snapshot_items")
    op.drop_table("watchlist_snapshot_items")
    op.drop_index("ix_watchlist_snapshots_list_as_of", table_name="watchlist_snapshots")
    op.drop_table("watchlist_snapshots")
    op.drop_index("uq_watchlist_member_market", table_name="watchlist_members")
    op.drop_index("ix_watchlist_members_watchlist_id", table_name="watchlist_members")
    op.drop_table("watchlist_members")
    op.drop_table("watchlists")
