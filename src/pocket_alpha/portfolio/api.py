from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import Field

from pocket_alpha.common.clock import SystemClock, utc
from pocket_alpha.domain.models import Currency, DomainModel, Timeframe
from pocket_alpha.market_data.api import DB
from pocket_alpha.portfolio.models import Portfolio, PortfolioEntry, PortfolioSnapshot
from pocket_alpha.portfolio.service import PortfolioEntryRequest, PortfolioService
from pocket_alpha.portfolio.storage import (
    ConflictingPortfolio,
    PortfolioRepository,
    StalePortfolioRevision,
)

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0, le=10000)]


class CreatePortfolio(DomainModel):
    portfolio_id: UUID
    name: str = Field(min_length=1, max_length=80)
    base_currency: Currency
    valuation_timeframe: Timeframe = Timeframe.H1


class PortfolioEntryResult(DomainModel):
    entry: PortfolioEntry
    portfolio: Portfolio


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, str(error))
    if isinstance(error, (ConflictingPortfolio, StalePortfolioRevision)):
        return HTTPException(409, str(error))
    return HTTPException(422, str(error))


@router.get("")
def portfolios(db: DB, response: Response) -> tuple[Portfolio, ...]:
    response.headers["Cache-Control"] = "no-store"
    return PortfolioRepository(db).list()


@router.post("")
def create_portfolio(payload: CreatePortfolio, db: DB, response: Response) -> Portfolio:
    response.headers["Cache-Control"] = "no-store"
    try:
        value = PortfolioRepository(db).create(
            payload.portfolio_id,
            payload.name,
            payload.base_currency,
            SystemClock().now(),
            payload.valuation_timeframe.value,
        )
        db.commit()
        return value
    except (ValueError, ConflictingPortfolio) as error:
        db.rollback()
        raise _translate(error) from error


@router.get("/{portfolio_id}")
def portfolio(portfolio_id: UUID, db: DB, response: Response) -> Portfolio:
    response.headers["Cache-Control"] = "no-store"
    try:
        return PortfolioRepository(db).get(portfolio_id)
    except LookupError as error:
        raise _translate(error) from error


@router.get("/{portfolio_id}/entries")
def entries(
    portfolio_id: UUID,
    db: DB,
    response: Response,
    limit: Limit = 100,
    offset: Offset = 0,
) -> tuple[PortfolioEntry, ...]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return PortfolioRepository(db).entries(portfolio_id, limit, offset)
    except (ValueError, LookupError) as error:
        raise _translate(error) from error


@router.post("/{portfolio_id}/entries")
def record_entry(
    portfolio_id: UUID,
    payload: PortfolioEntryRequest,
    db: DB,
    response: Response,
) -> PortfolioEntryResult:
    response.headers["Cache-Control"] = "no-store"
    repository = PortfolioRepository(db)
    try:
        entry = PortfolioService(repository, SystemClock()).record(portfolio_id, payload)
        value = PortfolioEntryResult(entry=entry, portfolio=repository.get(portfolio_id))
        db.commit()
        return value
    except (
        ValueError,
        LookupError,
        ConflictingPortfolio,
        StalePortfolioRevision,
    ) as error:
        db.rollback()
        raise _translate(error) from error


@router.get("/{portfolio_id}/snapshot")
def snapshot(
    portfolio_id: UUID,
    as_of: datetime,
    db: DB,
    response: Response,
) -> PortfolioSnapshot:
    response.headers["Cache-Control"] = "no-store"
    try:
        return PortfolioService(PortfolioRepository(db), SystemClock()).snapshot(
            portfolio_id, utc(as_of)
        )
    except (ValueError, LookupError) as error:
        raise _translate(error) from error
