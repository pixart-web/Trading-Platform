"""Additive single-workspace native identity and revocable rotating device sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_operators",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("workspace", sa.String(16), nullable=False, unique=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("workspace = 'operator'", name="ck_mobile_single_workspace"),
    )
    op.create_table(
        "mobile_sessions",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("mobile_operators.user_id"), nullable=False),
        sa.Column("device_name", sa.String(80), nullable=False),
        sa.Column("access_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        *(
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("access_expires_at", "expires_at", "created_at", "last_seen_at")
        ),
        sa.Column("step_up_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_mobile_sessions_user_id", "mobile_sessions", ["user_id"])
    op.create_table(
        "mobile_consumed_refresh",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mobile_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_mobile_consumed_refresh_session_id", "mobile_consumed_refresh", ["session_id"]
    )


def downgrade() -> None:
    op.drop_table("mobile_consumed_refresh")
    op.drop_table("mobile_sessions")
    op.drop_table("mobile_operators")
