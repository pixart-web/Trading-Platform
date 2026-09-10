from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.domain.models import DomainModel


class AuditReason(StrEnum):
    SYSTEM_STARTED = "SYSTEM_STARTED"
    CONFIGURATION_CHANGED = "CONFIGURATION_CHANGED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class AuditEvent(DomainModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID
    reason: AuditReason
    actor: str = Field(min_length=1, max_length=128)


class AuditRecord(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    reason: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(128))
