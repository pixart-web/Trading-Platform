from decimal import ROUND_HALF_EVEN, Context, localcontext
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.backtesting.models import digest
from pocket_alpha.database import Base
from pocket_alpha.paper_trading.engine import PaperRuntime
from pocket_alpha.paper_trading.models import PaperHeader, PaperJournal, PaperState


class PaperAccountRecord(Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (CheckConstraint("mode = 'PAPER'", name="ck_paper_account_mode"),)
    account_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    revision: Mapped[int] = mapped_column()
    header_hash: Mapped[str] = mapped_column(String(64))
    header: Mapped[str] = mapped_column(Text)
    state_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(Text)


class PaperJournalRecord(Base):
    __tablename__ = "paper_journal"
    __table_args__ = (
        CheckConstraint("mode = 'PAPER'", name="ck_paper_journal_mode"),
        UniqueConstraint("account_id", "event_id", name="uq_paper_event"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_accounts.account_id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    event_id: Mapped[UUID] = mapped_column(Uuid)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class PaperConflict(Exception):
    pass


class PaperRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def load(
        self, account_id: UUID
    ) -> tuple[PaperHeader, PaperRuntime, tuple[PaperJournal, ...]] | None:
        row = self.session.get(PaperAccountRecord, account_id)
        if row is None:
            return None
        header = PaperHeader.model_validate_json(row.header)
        stored = PaperState.model_validate_json(row.state)
        if (
            row.mode != "PAPER"
            or row.header_hash != digest(header)
            or header.account_id != account_id
            or stored.account_id != account_id
            or row.state_hash != stored.state_hash
            or row.revision != stored.revision
        ):
            raise ValueError("paper account header/state/index corrupted")
        rows = self.session.scalars(
            select(PaperJournalRecord)
            .where(PaperJournalRecord.account_id == account_id)
            .order_by(PaperJournalRecord.revision)
        ).all()
        entries = tuple(PaperJournal.model_validate_json(e.payload) for e in rows)
        if len(entries) != row.revision or len({e.input.event_id for e in entries}) != len(entries):
            raise ValueError("paper journal incomplete or duplicate event")
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            runtime = PaperRuntime(
                account_id, header.config, header.created_at, header.initial_checkpoint
            )
            previous_hash = runtime.state().state_hash
            for i, (record, entry) in enumerate(zip(rows, entries, strict=True), start=1):
                if (
                    record.mode != "PAPER"
                    or entry.account_id != account_id
                    or entry.revision != i
                    or record.revision != i
                    or record.event_id != entry.input.event_id
                    or record.content_hash != entry.content_hash
                    or entry.previous_hash != previous_hash
                ):
                    raise ValueError("paper journal audit chain corrupted")
                runtime.market(entry.input)
                runtime.decisions(entry.intents, entry.strategy_checkpoint, entry.failure)
                if runtime.state().state_hash != entry.state_hash:
                    raise ValueError("paper journal reconciliation failed")
                previous_hash = entry.content_hash
            if runtime.state() != stored:
                raise ValueError("paper persisted state does not reconcile with journal")
        return header, runtime, entries

    def create(self, header: PaperHeader, state: PaperState) -> None:
        header = PaperHeader.model_validate_json(header.model_dump_json())
        state = PaperState.model_validate_json(state.model_dump_json())
        if state.revision != 0 or header.account_id != state.account_id:
            raise ValueError("paper genesis identity invalid")
        self.session.add(
            PaperAccountRecord(
                account_id=header.account_id,
                mode="PAPER",
                revision=0,
                header_hash=digest(header),
                header=header.model_dump_json(),
                state_hash=state.state_hash,
                state=state.model_dump_json(),
            )
        )
        self.session.flush()

    def append(self, entry: PaperJournal, state: PaperState) -> None:
        from typing import cast

        from sqlalchemy import CursorResult

        entry = PaperJournal.model_validate_json(entry.model_dump_json())
        state = PaperState.model_validate_json(state.model_dump_json())
        if (
            entry.account_id != state.account_id
            or entry.revision != state.revision
            or entry.state_hash != state.state_hash
        ):
            raise ValueError("paper journal/state identity invalid")
        result = self.session.execute(
            update(PaperAccountRecord)
            .where(
                PaperAccountRecord.account_id == entry.account_id,
                PaperAccountRecord.revision == entry.revision - 1,
            )
            .values(
                revision=entry.revision, state_hash=state.state_hash, state=state.model_dump_json()
            )
        )
        if cast(CursorResult[object], result).rowcount != 1:
            raise PaperConflict("paper account revision changed; reload before retry")
        self.session.add(
            PaperJournalRecord(
                account_id=entry.account_id,
                revision=entry.revision,
                mode="PAPER",
                event_id=entry.input.event_id,
                content_hash=entry.content_hash,
                payload=entry.model_dump_json(),
            )
        )
        self.session.flush()

    def ids(self, limit: int = 100) -> tuple[UUID, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("paper account query must be bounded")
        return tuple(
            self.session.scalars(
                select(PaperAccountRecord.account_id)
                .order_by(PaperAccountRecord.account_id)
                .limit(limit)
            )
        )
