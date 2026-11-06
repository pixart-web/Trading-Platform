from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.market_data.storage import Timestamp


class OperatorRecord(Base):
    __tablename__ = "mobile_operators"
    __table_args__ = (CheckConstraint("workspace = 'operator'", name="ck_mobile_single_workspace"),)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Existing financial records belong to one operator workspace. Public signup is forbidden.
    workspace: Mapped[str] = mapped_column(String(16), unique=True, default="operator")
    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceSessionRecord(Base):
    __tablename__ = "mobile_sessions"
    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("mobile_operators.user_id"), index=True)
    device_name: Mapped[str] = mapped_column(String(80))
    access_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    step_up_expires_at: Mapped[datetime | None] = mapped_column(Timestamp(), nullable=True)
    access_expires_at: Mapped[datetime] = mapped_column(Timestamp())
    expires_at: Mapped[datetime] = mapped_column(Timestamp())
    created_at: Mapped[datetime] = mapped_column(Timestamp())
    last_seen_at: Mapped[datetime] = mapped_column(Timestamp())
    revision: Mapped[int] = mapped_column(Integer, default=1)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ConsumedRefreshRecord(Base):
    __tablename__ = "mobile_consumed_refresh"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("mobile_sessions.session_id", ondelete="CASCADE"), index=True
    )
