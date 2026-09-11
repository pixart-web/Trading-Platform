from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import ValidationError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.intelligence.zones.models import ZoneSnapshot
from pocket_alpha.intelligence.zones.service import SupportResistance
from pocket_alpha.market_data.api import DB
from pocket_alpha.market_data.quality import (
    DataQualityResult,
    DataRejected,
    FreshnessPolicy,
    Severity,
)
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRecord, MarketRepository

router = APIRouter(prefix="/api/v1", tags=["support resistance"])


class ZoneResponse(DomainModel):
    candles: tuple[Candle, ...]
    quality: DataQualityResult
    truncated: bool = False
    next_start: None = None
    snapshot: ZoneSnapshot


@router.get("/markets/{market_id}/zones")
def zones(
    market_id: str, timeframe: Timeframe, start: datetime, end: datetime, db: DB, response: Response
) -> ZoneResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        query = CandleQuery(market_id=market_id, timeframe=timeframe, start=start, end=end)
        if len(query.schedule()) > 1000:
            raise ValueError("maximum 1000 candles")
    except (ValidationError, ValueError) as error:
        raise HTTPException(
            422, "invalid zone time range; maximum 1000 candles and UTC offsets required"
        ) from error
    if db.get(MarketRecord, market_id) is None:
        raise HTTPException(404, "market not found")
    clock = SystemClock()
    try:
        candles, history = SupportResistance(MarketReplay(MarketRepository(db), clock)).chart(
            query, FreshnessPolicy()
        )
    except DataRejected as error:
        raise HTTPException(422, "market data rejected for zone analysis") from error
    return ZoneResponse(
        candles=candles,
        snapshot=history[-1],
        quality=DataQualityResult(
            valid=True,
            severity=Severity.OK,
            reason_codes=(),
            timestamp=clock.now(),
            source=candles[0].source,
            affected_records=(),
            missing_intervals=(),
        ),
    )
