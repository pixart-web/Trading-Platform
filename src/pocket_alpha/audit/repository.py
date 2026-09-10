from sqlalchemy.orm import Session

from pocket_alpha.audit.models import AuditEvent, AuditRecord


def append_event(session: Session, event: AuditEvent) -> None:
    """Caller owns the transaction; duplicate IDs fail, never overwrite history."""
    session.add(AuditRecord(**event.model_dump()))
    session.flush()
