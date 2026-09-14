from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import Field

from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.market_data.api import DB
from pocket_alpha.watchlists.models import AlertEvent, SnapshotResult, Watchlist, WatchlistSnapshot
from pocket_alpha.watchlists.service import WatchlistSnapshotService
from pocket_alpha.watchlists.storage import (
    ConflictingWatchlist,
    ConflictingWatchlistSnapshot,
    StaleWatchlistRevision,
    WatchlistRepository,
)

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])
Revision = Annotated[int, Query(ge=1)]
Limit = Annotated[int, Query(ge=1, le=500)]


class CreateWatchlist(DomainModel):
    watchlist_id: UUID
    name: str = Field(min_length=1, max_length=80)


class RenameWatchlist(DomainModel):
    name: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=1)


class AddWatchlistMember(DomainModel):
    member_id: UUID
    candle_timeframe: Timeframe
    expected_revision: int = Field(ge=1)


class CaptureWatchlist(DomainModel):
    snapshot_id: UUID
    as_of: datetime


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, str(error))
    if isinstance(
        error, (StaleWatchlistRevision, ConflictingWatchlist, ConflictingWatchlistSnapshot)
    ):
        return HTTPException(409, str(error))
    return HTTPException(422, str(error))


@router.get("")
def watchlists(db: DB, response: Response) -> tuple[Watchlist, ...]:
    response.headers["Cache-Control"] = "no-store"
    return WatchlistRepository(db).list()


@router.post("")
def create_watchlist(payload: CreateWatchlist, db: DB, response: Response) -> Watchlist:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = WatchlistRepository(db).create(
            payload.watchlist_id, payload.name, SystemClock().now()
        )
        db.commit()
        return value
    except (ValueError, ConflictingWatchlist) as error:
        db.rollback()
        raise _translate(error) from error


@router.get("/{watchlist_id}")
def watchlist(watchlist_id: UUID, db: DB, response: Response) -> Watchlist:
    response.headers["Cache-Control"] = "no-store"
    try:
        return WatchlistRepository(db).get(watchlist_id)
    except LookupError as error:
        raise _translate(error) from error


@router.patch("/{watchlist_id}")
def rename_watchlist(
    watchlist_id: UUID, payload: RenameWatchlist, db: DB, response: Response
) -> Watchlist:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = WatchlistRepository(db).rename(
            watchlist_id, payload.name, payload.expected_revision, SystemClock().now()
        )
        db.commit()
        return value
    except (ValueError, LookupError, StaleWatchlistRevision) as error:
        db.rollback()
        raise _translate(error) from error


@router.put("/{watchlist_id}/markets/{market_id}")
def add_market(
    watchlist_id: UUID,
    market_id: str,
    payload: AddWatchlistMember,
    db: DB,
    response: Response,
) -> Watchlist:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = WatchlistRepository(db).add_member(
            watchlist_id,
            payload.member_id,
            market_id,
            payload.candle_timeframe.value,
            payload.expected_revision,
            SystemClock().now(),
        )
        db.commit()
        return value
    except (ValueError, LookupError, StaleWatchlistRevision, ConflictingWatchlist) as error:
        db.rollback()
        raise _translate(error) from error


@router.delete("/{watchlist_id}/markets/{market_id}")
def remove_market(
    watchlist_id: UUID,
    market_id: str,
    expected_revision: Revision,
    db: DB,
    response: Response,
) -> Watchlist:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = WatchlistRepository(db).remove_member(
            watchlist_id, market_id, expected_revision, SystemClock().now()
        )
        db.commit()
        return value
    except (LookupError, StaleWatchlistRevision) as error:
        db.rollback()
        raise _translate(error) from error


@router.post("/{watchlist_id}/snapshots")
def capture_snapshot(
    watchlist_id: UUID, payload: CaptureWatchlist, db: DB, response: Response
) -> SnapshotResult:
    response.headers["Cache-Control"] = "no-store"
    try:
        as_of = utc(payload.as_of)
        value = WatchlistSnapshotService(WatchlistRepository(db), SystemClock()).capture(
            watchlist_id, payload.snapshot_id, as_of
        )
        db.commit()
        return value
    except (ValueError, LookupError, ConflictingWatchlistSnapshot) as error:
        db.rollback()
        raise _translate(error) from error


@router.get("/{watchlist_id}/snapshots/latest")
def latest_snapshot(watchlist_id: UUID, db: DB, response: Response) -> WatchlistSnapshot | None:
    response.headers["Cache-Control"] = "no-store"
    repository = WatchlistRepository(db)
    try:
        repository.get(watchlist_id)
    except LookupError as error:
        raise _translate(error) from error
    return repository.latest_snapshot(watchlist_id)


@router.get("/{watchlist_id}/alerts")
def alerts(
    watchlist_id: UUID,
    db: DB,
    response: Response,
    limit: Limit = 100,
) -> tuple[AlertEvent, ...]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return WatchlistRepository(db).alerts(watchlist_id, limit)
    except (ValueError, LookupError) as error:
        raise _translate(error) from error
