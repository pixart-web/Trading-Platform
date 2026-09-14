import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.common.clock import utc
from pocket_alpha.database import Base
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.market_data.storage import MarketRecord, Timestamp
from pocket_alpha.watchlists.models import (
    AlertEvent,
    Watchlist,
    WatchlistMember,
    WatchlistSnapshot,
    WatchlistSnapshotItem,
)


class WatchlistRecord(Base):
    __tablename__ = "watchlists"
    watchlist_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(Timestamp())
    updated_at: Mapped[datetime] = mapped_column(Timestamp())


class WatchlistMemberRecord(Base):
    __tablename__ = "watchlist_members"
    __table_args__ = (
        Index("uq_watchlist_member_market", "watchlist_id", "market_id", unique=True),
    )
    member_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"), index=True
    )
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"))
    candle_timeframe: Mapped[str] = mapped_column(String(3))
    added_at: Mapped[datetime] = mapped_column(Timestamp())


class WatchlistSnapshotRecord(Base):
    __tablename__ = "watchlist_snapshots"
    __table_args__ = (Index("ix_watchlist_snapshots_list_as_of", "watchlist_id", "as_of"),)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(ForeignKey("watchlists.watchlist_id"))
    watchlist_revision: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(Timestamp())
    generated_at: Mapped[datetime] = mapped_column(Timestamp())
    status: Mapped[str] = mapped_column(String(16))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class WatchlistSnapshotItemRecord(Base):
    __tablename__ = "watchlist_snapshot_items"
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("watchlist_snapshots.snapshot_id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"), index=True)
    report_id: Mapped[UUID | None] = mapped_column(ForeignKey("analyze_reports.report_id"))
    payload: Mapped[str] = mapped_column(Text)


class AlertEventRecord(Base):
    __tablename__ = "watchlist_alert_events"
    __table_args__ = (Index("ix_watchlist_alerts_list_created", "watchlist_id", "created_at"),)
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(ForeignKey("watchlists.watchlist_id"))
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("watchlist_snapshots.snapshot_id"))
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"))
    event_type: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(Timestamp())
    created_at: Mapped[datetime] = mapped_column(Timestamp())
    payload: Mapped[str] = mapped_column(Text)


class ConflictingWatchlist(Exception):
    """An identity conflicts with persisted watchlist content."""


class StaleWatchlistRevision(Exception):
    """The caller edited a revision which is no longer current."""


class ConflictingWatchlistSnapshot(Exception):
    """An immutable snapshot identity already has different content."""


def _json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class WatchlistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _insert(self, model: type[Base], values: dict[str, Any]) -> bool:
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        return (
            self.session.execute(
                insert(model)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(*model.__table__.primary_key)
            ).first()
            is not None
        )

    def create(self, watchlist_id: UUID, name: str, created_at: datetime) -> Watchlist:
        stamp = utc(created_at)
        normalized = name.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("watchlist name must contain 1..80 characters")
        values = {
            "watchlist_id": watchlist_id,
            "name": normalized,
            "revision": 1,
            "created_at": stamp,
            "updated_at": stamp,
        }
        with self.session.begin_nested():
            if not self._insert(WatchlistRecord, values):
                row = self.session.get(WatchlistRecord, watchlist_id, populate_existing=True)
                if row is None or row.name != normalized:
                    raise ConflictingWatchlist(
                        "watchlist identity conflicts with persisted content"
                    )
        return self.get(watchlist_id)

    def list(self, limit: int = 100) -> tuple[Watchlist, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("bounded watchlist query required")
        rows = self.session.scalars(
            select(WatchlistRecord)
            .order_by(WatchlistRecord.created_at, WatchlistRecord.watchlist_id)
            .limit(limit)
        )
        return tuple(self._value(row) for row in rows)

    def get(self, watchlist_id: UUID) -> Watchlist:
        row = self.session.get(WatchlistRecord, watchlist_id)
        if row is None:
            raise LookupError("watchlist not found")
        return self._value(row)

    def _value(self, row: WatchlistRecord) -> Watchlist:
        members = self.session.scalars(
            select(WatchlistMemberRecord)
            .where(WatchlistMemberRecord.watchlist_id == row.watchlist_id)
            .order_by(WatchlistMemberRecord.added_at, WatchlistMemberRecord.member_id)
        )
        return Watchlist(
            watchlist_id=row.watchlist_id,
            name=row.name,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
            members=tuple(
                WatchlistMember(
                    member_id=item.member_id,
                    market_id=item.market_id,
                    asset_id=item.asset_id,
                    candle_timeframe=Timeframe(item.candle_timeframe),
                    added_at=item.added_at,
                )
                for item in members
            ),
        )

    def rename(
        self, watchlist_id: UUID, name: str, expected_revision: int, updated_at: datetime
    ) -> Watchlist:
        normalized = name.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("watchlist name must contain 1..80 characters")
        self._advance(
            watchlist_id,
            expected_revision,
            utc(updated_at),
            extra={"name": normalized},
        )
        return self.get(watchlist_id)

    def add_member(
        self,
        watchlist_id: UUID,
        member_id: UUID,
        market_id: str,
        candle_timeframe: str,
        expected_revision: int,
        added_at: datetime,
    ) -> Watchlist:
        market = self.session.get(MarketRecord, market_id)
        if market is None:
            raise LookupError("market not found")
        existing = self.session.scalar(
            select(WatchlistMemberRecord).where(
                WatchlistMemberRecord.watchlist_id == watchlist_id,
                WatchlistMemberRecord.market_id == market_id,
            )
        )
        if existing is not None:
            if existing.member_id != member_id or existing.candle_timeframe != candle_timeframe:
                raise ConflictingWatchlist("market already belongs to watchlist")
            return self.get(watchlist_id)
        if self.session.get(WatchlistMemberRecord, member_id) is not None:
            raise ConflictingWatchlist("member identity already exists")
        if len(self.get(watchlist_id).members) >= 250:
            raise ValueError("watchlist member limit reached")
        stamp = utc(added_at)
        with self.session.begin_nested():
            self._advance(watchlist_id, expected_revision, stamp)
            self.session.add(
                WatchlistMemberRecord(
                    member_id=member_id,
                    watchlist_id=watchlist_id,
                    market_id=market_id,
                    asset_id=market.asset_id,
                    candle_timeframe=candle_timeframe,
                    added_at=stamp,
                )
            )
            self.session.flush()
        return self.get(watchlist_id)

    def remove_member(
        self, watchlist_id: UUID, market_id: str, expected_revision: int, updated_at: datetime
    ) -> Watchlist:
        member = self.session.scalar(
            select(WatchlistMemberRecord).where(
                WatchlistMemberRecord.watchlist_id == watchlist_id,
                WatchlistMemberRecord.market_id == market_id,
            )
        )
        if member is None:
            raise LookupError("watchlist member not found")
        stamp = utc(updated_at)
        with self.session.begin_nested():
            self._advance(watchlist_id, expected_revision, stamp)
            self.session.execute(
                delete(WatchlistMemberRecord).where(
                    WatchlistMemberRecord.member_id == member.member_id
                )
            )
        return self.get(watchlist_id)

    def _advance(
        self,
        watchlist_id: UUID,
        expected_revision: int,
        updated_at: datetime,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        values = {"revision": expected_revision + 1, "updated_at": updated_at, **(extra or {})}
        changed = self.session.scalar(
            update(WatchlistRecord)
            .where(
                WatchlistRecord.watchlist_id == watchlist_id,
                WatchlistRecord.revision == expected_revision,
            )
            .values(**values)
            .returning(WatchlistRecord.watchlist_id)
        )
        if changed is None:
            if self.session.get(WatchlistRecord, watchlist_id) is None:
                raise LookupError("watchlist not found")
            raise StaleWatchlistRevision("watchlist revision is stale")

    def snapshot_fingerprint(
        self, watchlist: Watchlist, as_of: datetime, items: Sequence[WatchlistSnapshotItem]
    ) -> str:
        value = canonical(
            {
                "watchlist_id": watchlist.watchlist_id,
                "watchlist_revision": watchlist.revision,
                "as_of": as_of,
                "members": [member.model_dump() for member in watchlist.members],
                "items": [item.model_dump() for item in items],
            }
        )
        return hashlib.sha256(_json(value).encode()).hexdigest()

    def put_snapshot(self, snapshot: WatchlistSnapshot, events: tuple[AlertEvent, ...]) -> bool:
        payload = _json(snapshot)
        values = {
            "snapshot_id": snapshot.snapshot_id,
            "watchlist_id": snapshot.watchlist_id,
            "watchlist_revision": snapshot.watchlist_revision,
            "as_of": snapshot.as_of,
            "generated_at": snapshot.generated_at,
            "status": snapshot.status.value,
            "input_hash": snapshot.input_hash,
            "payload": payload,
        }
        with self.session.begin_nested():
            if not self._insert(WatchlistSnapshotRecord, values):
                row = self.session.get(
                    WatchlistSnapshotRecord, snapshot.snapshot_id, populate_existing=True
                )
                if row is None or row.payload != payload:
                    raise ConflictingWatchlistSnapshot(
                        "snapshot identity conflicts with persisted content"
                    )
                return False
            for item in snapshot.items:
                self.session.add(
                    WatchlistSnapshotItemRecord(
                        snapshot_id=snapshot.snapshot_id,
                        member_id=item.member_id,
                        market_id=item.market_id,
                        report_id=item.report_id,
                        payload=_json(item),
                    )
                )
            for event in events:
                self.session.add(
                    AlertEventRecord(
                        event_id=event.event_id,
                        watchlist_id=event.watchlist_id,
                        snapshot_id=event.snapshot_id,
                        market_id=event.market_id,
                        event_type=event.event_type.value,
                        observed_at=event.observed_at,
                        created_at=event.created_at,
                        payload=_json(event),
                    )
                )
            self.session.flush()
        return True

    def latest_snapshot(
        self, watchlist_id: UUID, *, before: datetime | None = None
    ) -> WatchlistSnapshot | None:
        statement = select(WatchlistSnapshotRecord).where(
            WatchlistSnapshotRecord.watchlist_id == watchlist_id
        )
        if before is not None:
            statement = statement.where(WatchlistSnapshotRecord.as_of < utc(before))
        row = self.session.scalar(
            statement.order_by(
                WatchlistSnapshotRecord.as_of.desc(),
                WatchlistSnapshotRecord.generated_at.desc(),
                WatchlistSnapshotRecord.snapshot_id.desc(),
            ).limit(1)
        )
        return WatchlistSnapshot.model_validate_json(row.payload) if row else None

    def snapshot(self, snapshot_id: UUID) -> WatchlistSnapshot | None:
        row = self.session.get(WatchlistSnapshotRecord, snapshot_id)
        return WatchlistSnapshot.model_validate_json(row.payload) if row else None

    def events_for_snapshot(self, snapshot_id: UUID) -> tuple[AlertEvent, ...]:
        rows = self.session.scalars(
            select(AlertEventRecord)
            .where(AlertEventRecord.snapshot_id == snapshot_id)
            .order_by(AlertEventRecord.event_id)
        )
        return tuple(AlertEvent.model_validate_json(row.payload) for row in rows)

    def alerts(self, watchlist_id: UUID, limit: int = 100) -> tuple[AlertEvent, ...]:
        if self.session.get(WatchlistRecord, watchlist_id) is None:
            raise LookupError("watchlist not found")
        if not 1 <= limit <= 500:
            raise ValueError("bounded alert query required")
        rows = self.session.scalars(
            select(AlertEventRecord)
            .where(AlertEventRecord.watchlist_id == watchlist_id)
            .order_by(AlertEventRecord.created_at.desc(), AlertEventRecord.event_id.desc())
            .limit(limit)
        )
        return tuple(AlertEvent.model_validate_json(row.payload) for row in rows)
