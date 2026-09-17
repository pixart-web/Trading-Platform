from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.contextual.models import ContextSnapshot
from pocket_alpha.contextual.service import ContextService
from pocket_alpha.contextual.storage import ContextRepository
from pocket_alpha.domain.market import Identifier
from pocket_alpha.market_data.api import DB

router = APIRouter(prefix="/api/v1/context", tags=["contextual-intelligence"])


@router.get("/{entity_id}")
def context(entity_id: Identifier, as_of: datetime, db: DB, response: Response) -> ContextSnapshot:
    response.headers["Cache-Control"] = "no-store"
    try:
        return ContextService(ContextRepository(db), SystemClock()).snapshot(entity_id, as_of)
    except SQLAlchemyError as error:
        raise HTTPException(503, "context storage unavailable") from error
    except (LookupError, ValueError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 422, str(error)) from error
