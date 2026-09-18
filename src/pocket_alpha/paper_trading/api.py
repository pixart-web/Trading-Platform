"""Read-only PAPER API. Creation and controls require a trusted local operator."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.market_data.api import DB
from pocket_alpha.paper_trading.models import PaperView
from pocket_alpha.paper_trading.service import PaperService
from pocket_alpha.paper_trading.storage import PaperRepository

router = APIRouter(prefix="/api/v1/paper", tags=["PAPER-simulation"])


def service(db: DB) -> PaperService:
    return PaperService(PaperRepository(db), SystemClock())


@router.get("/accounts")
def accounts(db: DB, response: Response) -> tuple[PaperView, ...]:
    response.headers["Cache-Control"] = "no-store"
    try:
        paper = service(db)
        return tuple(v for key in paper.repository.ids() if (v := paper.view(key)) is not None)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        raise HTTPException(503, "PAPER storage unavailable or reconciliation failed") from error


@router.get("/accounts/{account_id}")
def account(account_id: UUID, db: DB, response: Response) -> PaperView:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = service(db).view(account_id)
        if value is None:
            raise HTTPException(404, "PAPER account not found")
        return value
    except (SQLAlchemyError, ValueError, LookupError) as error:
        raise HTTPException(503, "PAPER storage unavailable or reconciliation failed") from error
