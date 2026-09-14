from datetime import datetime

from fastapi import APIRouter, HTTPException, Response

from pocket_alpha.analysis.models import (
    AnalyzeResponseStatus,
    AnalyzeSnapshotResponse,
)
from pocket_alpha.analysis.storage import AnalyzeRepository
from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.market_data.api import DB
from pocket_alpha.market_data.storage import MarketRecord

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get("/markets/{market_id}/analysis")
def analysis(
    market_id: str,
    timeframe: Timeframe,
    as_of: datetime,
    db: DB,
    response: Response,
) -> AnalyzeSnapshotResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        requested_as_of = utc(as_of)
    except ValueError as error:
        raise HTTPException(422, "Analyze as-of time requires a UTC offset") from error
    if requested_as_of > utc(SystemClock().now()):
        raise HTTPException(422, "Analyze as-of time cannot be in the future")
    if db.get(MarketRecord, market_id) is None:
        raise HTTPException(404, "market not found")
    report = AnalyzeRepository(db).at(market_id, timeframe.value, requested_as_of)
    if report is None:
        return AnalyzeSnapshotResponse(
            market_id=market_id,
            candle_timeframe=timeframe,
            requested_as_of=requested_as_of,
            status=AnalyzeResponseStatus.UNAVAILABLE,
            unavailable_reason="NO_ANALYSIS_SNAPSHOT",
        )
    return AnalyzeSnapshotResponse(
        market_id=market_id,
        candle_timeframe=timeframe,
        requested_as_of=requested_as_of,
        status=AnalyzeResponseStatus.AVAILABLE,
        report=report,
    )
