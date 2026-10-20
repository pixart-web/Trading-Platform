"""Persistent live control state and append-only transition evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_control",
        sa.Column("control_key", sa.String(32), primary_key=True),
        sa.Column("control_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("broker", sa.String(16)),
        sa.Column("market", sa.String(16)),
        sa.Column("account_identity_hash", sa.String(64)),
        sa.Column("policy_payload", sa.Text()),
        sa.Column("policy_hash", sa.String(64)),
        sa.Column("readiness_payload", sa.Text()),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_live_control_revision"),
        sa.CheckConstraint(
            "mode IN ('OFF','PAPER','LIVE_ARMED','LIVE_ACTIVE','HALTED','KILL_SWITCH')",
            name="ck_live_control_mode",
        ),
        sa.CheckConstraint(
            "broker IS NULL OR broker IN ('BINANCE','KUCOIN')", name="ck_live_control_broker"
        ),
        sa.CheckConstraint(
            "market IS NULL OR market IN ('SPOT','FUTURES')", name="ck_live_control_market"
        ),
    )
    op.create_table(
        "live_control_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "control_id",
            sa.Uuid(),
            sa.ForeignKey("live_control.control_id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("control_id", "revision", name="uq_live_control_event_revision"),
        sa.UniqueConstraint("content_hash", name="uq_live_control_event_hash"),
    )
    op.create_index("ix_live_control_events_occurred_at", "live_control_events", ["occurred_at"])
    op.create_index(
        "ix_live_control_events_correlation_id", "live_control_events", ["correlation_id"]
    )
    op.execute(
        sa.text(
            """INSERT INTO live_control
            (control_key, control_id, revision, mode, kill_switch_active, updated_at)
            VALUES ('primary', '00000000-0000-4000-8000-000000000030', 0, 'OFF', false,
                    CURRENT_TIMESTAMP)"""
        )
    )


def downgrade() -> None:
    op.drop_index("ix_live_control_events_correlation_id", table_name="live_control_events")
    op.drop_index("ix_live_control_events_occurred_at", table_name="live_control_events")
    op.drop_table("live_control_events")
    op.drop_table("live_control")
