"""Immutable forecasts and separate outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("forecast_id", sa.Uuid(), primary_key=True),
        sa.Column("market_id", sa.String(128), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("asset_id", sa.String(128), sa.ForeignKey("assets.asset_id"), nullable=False),
        sa.Column("candle_timeframe", sa.String(3), nullable=False),
        sa.Column("horizon", sa.String(3), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_forecasts_market_horizon_generated",
        "forecasts",
        ["market_id", "horizon", "generated_at"],
    )
    op.create_table(
        "forecast_outcomes",
        sa.Column("outcome_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "forecast_id",
            sa.Uuid(),
            sa.ForeignKey("forecasts.forecast_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_price_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_forecast_outcomes_forecast_id", "forecast_outcomes", ["forecast_id"])


def downgrade() -> None:
    op.drop_index("ix_forecast_outcomes_forecast_id", table_name="forecast_outcomes")
    op.drop_table("forecast_outcomes")
    op.drop_index("ix_forecasts_market_horizon_generated", table_name="forecasts")
    op.drop_table("forecasts")
