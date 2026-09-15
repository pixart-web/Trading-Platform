from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.market import Identifier
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.market_data.api import DB
from pocket_alpha.portfolio.storage import PortfolioRepository
from pocket_alpha.portfolio_intelligence.models import (
    PortfolioIntelligencePolicy,
    PortfolioIntelligenceReport,
)
from pocket_alpha.portfolio_intelligence.service import PortfolioIntelligenceService
from pocket_alpha.portfolio_intelligence.storage import (
    ConflictingPortfolioIntelligence,
    PortfolioIntelligenceRepository,
)

router = APIRouter(tags=["portfolio-intelligence"])
Limit = Annotated[int, Query(ge=1, le=100)]


class CreatePortfolioIntelligence(DomainModel):
    analysis_id: UUID
    as_of: datetime
    benchmark_market_id: Identifier | None = None
    policy: PortfolioIntelligencePolicy = PortfolioIntelligencePolicy()


def _service(db: DB) -> PortfolioIntelligenceService:
    return PortfolioIntelligenceService(
        PortfolioRepository(db), PortfolioIntelligenceRepository(db), SystemClock()
    )


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, str(error))
    if isinstance(error, ConflictingPortfolioIntelligence):
        return HTTPException(409, str(error))
    return HTTPException(422, str(error))


@router.get("/api/v1/portfolios/{portfolio_id}/intelligence")
def recent(
    portfolio_id: UUID,
    db: DB,
    response: Response,
    limit: Limit = 20,
) -> tuple[PortfolioIntelligenceReport, ...]:
    response.headers["Cache-Control"] = "no-store"
    try:
        PortfolioRepository(db).get(portfolio_id)
        return PortfolioIntelligenceRepository(db).recent(portfolio_id, limit)
    except (ValueError, LookupError) as error:
        raise _translate(error) from error


@router.post("/api/v1/portfolios/{portfolio_id}/intelligence")
def create(
    portfolio_id: UUID,
    payload: CreatePortfolioIntelligence,
    db: DB,
    response: Response,
) -> PortfolioIntelligenceReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        report = _service(db).create(
            payload.analysis_id,
            portfolio_id,
            utc(payload.as_of),
            payload.policy,
            payload.benchmark_market_id,
        )
        db.commit()
        return report
    except (ValueError, LookupError, ConflictingPortfolioIntelligence) as error:
        db.rollback()
        raise _translate(error) from error


@router.get("/api/v1/portfolio-intelligence/{analysis_id}")
def get(
    analysis_id: UUID,
    db: DB,
    response: Response,
) -> PortfolioIntelligenceReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        return PortfolioIntelligenceRepository(db).get(analysis_id)
    except LookupError as error:
        raise _translate(error) from error
