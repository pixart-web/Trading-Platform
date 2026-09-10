from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.domain.market import Candle, CandleQuery, Market
from pocket_alpha.domain.models import Asset, DomainModel, Timeframe
from pocket_alpha.market_data.quality import DataQualityResult, FreshnessPolicy, inspect_candles
from pocket_alpha.market_data.storage import (
    AssetRecord,
    MarketRecord,
    MarketRepository,
    asset_value,
    market_value,
)

router = APIRouter(prefix="/api/v1", tags=["market data"])


def session_dependency(request: Request) -> Iterator[Session]:
    try:
        with Session(request.app.state.engine) as session:
            yield session
    except SQLAlchemyError as error:
        raise HTTPException(503, "market storage unavailable") from error


DB = Annotated[Session, Depends(session_dependency)]
Limit = Annotated[int, Query(ge=1, le=1000)]
Offset = Annotated[int, Query(ge=0, le=100000)]


class CandleResponse(DomainModel):
    candles: tuple[Candle, ...]
    quality: DataQualityResult
    truncated: bool
    next_start: datetime | None


@router.get("/assets")
def assets(db: DB, limit: Limit = 100, offset: Offset = 0) -> list[Asset]:
    return [
        asset_value(row)
        for row in db.scalars(
            select(AssetRecord).order_by(AssetRecord.asset_id).offset(offset).limit(limit)
        )
    ]


@router.get("/assets/{asset_id}")
def asset(asset_id: str, db: DB) -> Asset:
    row = db.get(AssetRecord, asset_id)
    if row is None:
        raise HTTPException(404, "asset not found")
    return asset_value(row)


@router.get("/markets")
def markets(db: DB, limit: Limit = 100, offset: Offset = 0) -> list[Market]:
    return [
        market_value(row)
        for row in db.scalars(
            select(MarketRecord).order_by(MarketRecord.market_id).offset(offset).limit(limit)
        )
    ]


@router.get("/markets/{market_id}/candles")
def candles(
    market_id: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    db: DB,
    limit: Limit = 1000,
) -> CandleResponse:
    try:
        query = CandleQuery(market_id=market_id, timeframe=timeframe, start=start, end=end)
    except ValidationError as error:
        raise HTTPException(
            422, "invalid or oversized candle time range; UTC offsets required"
        ) from error
    if db.get(MarketRecord, market_id) is None:
        raise HTTPException(404, "market not found")
    data = MarketRepository(db).candles(query, limit=limit + 1)
    truncated = len(data) > limit
    visible = data[:limit]
    _, quality = inspect_candles(
        [c.model_dump() for c in visible],
        query,
        visible[0].source if visible else "stored",
        FreshnessPolicy(),
        SystemClock(),
    )
    return CandleResponse(
        candles=visible,
        quality=quality,
        truncated=truncated,
        next_start=data[limit].open_time if truncated else None,
    )
