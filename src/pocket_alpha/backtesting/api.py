from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.backtesting.models import BacktestReport
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.market_data.api import DB

router = APIRouter(prefix="/api/v1/backtests", tags=["offline-research"])


@router.get("/{run_id}")
def report(run_id: UUID, db: DB, response: Response) -> BacktestReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        stored = BacktestRepository(db).get(run_id)
        if stored is None:
            raise HTTPException(404, "backtest report not found")
        return stored
    except (SQLAlchemyError, ValueError) as error:
        raise HTTPException(503, "backtest storage unavailable or invalid") from error
