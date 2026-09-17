from datetime import datetime

from fastapi import APIRouter, HTTPException, Response

from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.market import Identifier
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.fundamentals.context import FundamentalContext, financial_context
from pocket_alpha.fundamentals.models import FundamentalSnapshot
from pocket_alpha.fundamentals.service import FundamentalService
from pocket_alpha.fundamentals.storage import FundamentalRepository
from pocket_alpha.market_data.api import DB

router = APIRouter(tags=["fundamentals"])


@router.get("/api/v1/assets/{asset_id}/fundamentals")
def snapshot(
    asset_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
) -> FundamentalSnapshot:
    response.headers["Cache-Control"] = "no-store"
    try:
        return FundamentalService(FundamentalRepository(db), SystemClock()).snapshot(
            asset_id, utc(as_of)
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/api/v1/assets/{asset_id}/fundamental-context")
def context(
    asset_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
    price_market_id: Identifier | None = None,
    price_timeframe: Timeframe = Timeframe.D1,
) -> FundamentalContext:
    report = snapshot(asset_id, as_of, db, response)
    try:
        price = (
            FundamentalRepository(db).price(
                asset_id,
                price_market_id,
                price_timeframe,
                report.as_of,
            )
            if price_market_id is not None
            else None
        )
        return financial_context(report, price)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
