"""Universal assets, listings, provider mappings and canonical candles."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(128), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("asset_type", sa.String(16), nullable=False),
    )
    op.create_table(
        "venues",
        sa.Column("venue_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
    )
    op.create_table(
        "markets",
        sa.Column("market_id", sa.String(128), primary_key=True),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False),
        sa.Column("venue_id", sa.String(128), sa.ForeignKey("venues.venue_id"), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("quote_currency", sa.String(12), nullable=False),
    )
    op.create_index("ix_markets_asset_id", "markets", ["asset_id"])
    op.create_table(
        "provider_mappings",
        sa.Column("source", sa.String(128), primary_key=True),
        sa.Column(
            "market_id", sa.String(128), sa.ForeignKey("markets.market_id"), primary_key=True
        ),
        sa.Column("instrument_id", sa.String(256), nullable=False),
        sa.UniqueConstraint("source", "instrument_id", name="uq_provider_instrument"),
    )
    op.create_table(
        "candles",
        sa.ForeignKeyConstraint(
            ["source", "market_id"],
            ["provider_mappings.source", "provider_mappings.market_id"],
            name="fk_candle_provider_mapping",
        ),
        sa.Column(
            "market_id", sa.String(128), sa.ForeignKey("markets.market_id"), primary_key=True
        ),
        sa.Column("timeframe", sa.String(3), primary_key=True),
        sa.Column("open_time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(38, 18), nullable=False),
        sa.Column("high", sa.Numeric(38, 18), nullable=False),
        sa.Column("low", sa.Numeric(38, 18), nullable=False),
        sa.Column("close", sa.Numeric(38, 18), nullable=False),
        sa.Column("volume", sa.Numeric(38, 18), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "high >= open AND high >= close AND low <= open AND low <= close", name="ck_candle_ohlc"
        ),
        sa.CheckConstraint("low > 0 AND volume >= 0", name="ck_candle_positive"),
        sa.CheckConstraint(
            "close_time > open_time AND received_at >= close_time", name="ck_candle_time"
        ),
    )


def downgrade() -> None:
    op.drop_table("candles")
    op.drop_table("provider_mappings")
    op.drop_index("ix_markets_asset_id", table_name="markets")
    op.drop_table("markets")
    op.drop_table("venues")
    op.drop_table("assets")
