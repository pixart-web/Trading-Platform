"""Bounded discovery of existing analytical snapshots, without recomputation."""

import base64
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, or_, select

from pocket_alpha.analysis.storage import AnalyzeReportRecord
from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.market_data.api import DB
from pocket_alpha.market_data.storage import MarketRecord
from pocket_alpha.watchlists.storage import StaleWatchlistRevision, WatchlistRepository

router = APIRouter(prefix="/api/v1", tags=["native read models"])


class SnapshotReference(DomainModel):
    report_id: UUID
    as_of: datetime
    generated_at: datetime
    status: str
    report_version: str


class SnapshotPage(DomainModel):
    market_id: str
    candle_timeframe: Timeframe
    items: tuple[SnapshotReference, ...]
    next_cursor: str | None


@router.get("/markets/{market_id}/analysis/snapshots")
def snapshots(
    market_id: str,
    timeframe: Timeframe,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> SnapshotPage:
    if db.get(MarketRecord, market_id) is None:
        raise HTTPException(404, "market not found")
    now = SystemClock().now()
    statement = select(
        AnalyzeReportRecord.report_id,
        AnalyzeReportRecord.as_of,
        AnalyzeReportRecord.generated_at,
        AnalyzeReportRecord.status,
        AnalyzeReportRecord.report_version,
    ).where(
        AnalyzeReportRecord.market_id == market_id,
        AnalyzeReportRecord.candle_timeframe == timeframe.value,
        AnalyzeReportRecord.as_of <= now,
        AnalyzeReportRecord.generated_at <= now,
    )
    if cursor:
        try:
            stamp, identifier = (
                base64.b64decode(cursor, altchars=b"-_", validate=True).decode().split("|")
            )
            before = utc(datetime.fromisoformat(stamp))
            report_id = UUID(identifier)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, "invalid snapshot cursor") from error
        statement = statement.where(
            or_(
                AnalyzeReportRecord.as_of < before,
                and_(
                    AnalyzeReportRecord.as_of == before, AnalyzeReportRecord.report_id < report_id
                ),
            )
        )
    rows = list(
        db.execute(
            statement.order_by(
                AnalyzeReportRecord.as_of.desc(), AnalyzeReportRecord.report_id.desc()
            ).limit(limit + 1)
        )
    )
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = visible[-1]
        next_cursor = base64.urlsafe_b64encode(
            f"{last.as_of.isoformat()}|{last.report_id}".encode()
        ).decode()
    return SnapshotPage(
        market_id=market_id,
        candle_timeframe=timeframe,
        items=tuple(
            SnapshotReference(
                report_id=row.report_id,
                as_of=row.as_of,
                generated_at=row.generated_at,
                status=row.status,
                report_version=row.report_version,
            )
            for row in visible
        ),
        next_cursor=next_cursor,
    )


@router.delete("/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(
    watchlist_id: UUID, db: DB, expected_revision: Annotated[int, Query(ge=1)]
) -> None:
    try:
        WatchlistRepository(db).archive(watchlist_id, expected_revision, SystemClock().now())
        db.commit()
    except (LookupError, StaleWatchlistRevision) as error:
        db.rollback()
        raise HTTPException(404 if isinstance(error, LookupError) else 409, str(error)) from error


class CandleReference(DomainModel):
    open_time: datetime
    close_time: datetime
    received_at: datetime
    source: str


class LatestCandle(DomainModel):
    market_id: str
    candle_timeframe: Timeframe
    candle: CandleReference | None
    age_seconds: int | None


@router.get("/markets/{market_id}/candles/latest")
def latest_candle(market_id: str, timeframe: Timeframe, db: DB) -> LatestCandle:
    from pocket_alpha.market_data.storage import CandleRecord

    if db.get(MarketRecord, market_id) is None:
        raise HTTPException(404, "market not found")
    now = SystemClock().now()
    row = db.execute(
        select(
            CandleRecord.open_time,
            CandleRecord.close_time,
            CandleRecord.received_at,
            CandleRecord.source,
        )
        .where(
            CandleRecord.market_id == market_id,
            CandleRecord.timeframe == timeframe.value,
            CandleRecord.close_time <= now,
            CandleRecord.received_at <= now,
        )
        .order_by(CandleRecord.open_time.desc())
        .limit(1)
    ).first()
    return LatestCandle(
        market_id=market_id,
        candle_timeframe=timeframe,
        candle=None
        if row is None
        else CandleReference(
            open_time=row.open_time,
            close_time=row.close_time,
            received_at=row.received_at,
            source=row.source,
        ),
        age_seconds=None if row is None else int((now - row.close_time).total_seconds()),
    )
