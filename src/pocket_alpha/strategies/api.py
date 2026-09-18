from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.market_data.api import DB
from pocket_alpha.market_data.quality import DataRejected
from pocket_alpha.strategies.registry import StrategyArtifact, StrategyEvent, StrategyRegistry

router = APIRouter(prefix="/api/v1/strategies", tags=["research-PAPER-strategies"])


@router.get("")
def strategies(
    db: DB, response: Response
) -> tuple[tuple[StrategyArtifact, tuple[StrategyEvent, ...]], ...]:
    response.headers["Cache-Control"] = "no-store"
    try:
        registry = StrategyRegistry(db, SystemClock())
        return tuple(value for key in registry.ids() if (value := registry.get(key)) is not None)
    except (SQLAlchemyError, ValueError, LookupError, StopIteration, DataRejected) as error:
        raise HTTPException(
            503, "strategy storage or qualification evidence unavailable"
        ) from error


@router.get("/{strategy_id}")
def strategy(
    strategy_id: UUID, db: DB, response: Response
) -> tuple[StrategyArtifact, tuple[StrategyEvent, ...]]:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = StrategyRegistry(db, SystemClock()).get(strategy_id)
        if value is None:
            raise HTTPException(404, "strategy not found")
        return value
    except (SQLAlchemyError, ValueError, LookupError, StopIteration, DataRejected) as error:
        raise HTTPException(
            503, "strategy storage or qualification evidence unavailable"
        ) from error
