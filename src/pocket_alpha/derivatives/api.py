from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.derivatives.models import (
    DerivativeContext,
    DerivativeContract,
    DerivativePolicy,
    OptionSkew,
    TermStructure,
)
from pocket_alpha.derivatives.service import DerivativeService
from pocket_alpha.derivatives.storage import DerivativeRepository
from pocket_alpha.domain.market import Identifier
from pocket_alpha.market_data.api import DB

router = APIRouter(prefix="/api/v1/derivatives", tags=["derivative-intelligence"])
Age = Annotated[int, Query(ge=1, le=86400)]


def service(db: DB, response: Response) -> DerivativeService:
    response.headers["Cache-Control"] = "no-store"
    return DerivativeService(DerivativeRepository(db), SystemClock())


def translate(error: Exception) -> HTTPException:
    if isinstance(error, SQLAlchemyError):
        return HTTPException(503, "derivative storage unavailable")
    return HTTPException(404 if isinstance(error, LookupError) else 422, str(error))


@router.get("/contracts")
def contracts(
    underlying_asset_id: Identifier,
    venue_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
) -> tuple[DerivativeContract, ...]:
    try:
        app = service(db, response)
        cutoff, _ = app.cutoff(as_of)
        return app.repository.contracts(underlying_asset_id, venue_id, cutoff)
    except (ValueError, LookupError, SQLAlchemyError) as error:
        raise translate(error) from error


@router.get("/term-structure")
def curve(
    underlying_asset_id: Identifier,
    venue_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
    maximum_age_seconds: Age = 300,
) -> TermStructure:
    try:
        return service(db, response).curve(
            underlying_asset_id,
            venue_id,
            as_of,
            DerivativePolicy(maximum_age_seconds=maximum_age_seconds),
        )
    except (ValueError, LookupError, SQLAlchemyError) as error:
        raise translate(error) from error


@router.get("/option-skew")
def skew(
    call_contract_id: Identifier,
    put_contract_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
    maximum_age_seconds: Age = 300,
) -> OptionSkew:
    try:
        return service(db, response).skew(
            call_contract_id,
            put_contract_id,
            as_of,
            DerivativePolicy(maximum_age_seconds=maximum_age_seconds),
        )
    except (ValueError, LookupError, SQLAlchemyError) as error:
        raise translate(error) from error


@router.get("/{contract_id}/context")
def context(
    contract_id: Identifier,
    as_of: datetime,
    db: DB,
    response: Response,
    maximum_age_seconds: Age = 300,
) -> DerivativeContext:
    try:
        return service(db, response).context(
            contract_id,
            as_of,
            DerivativePolicy(maximum_age_seconds=maximum_age_seconds),
        )
    except (ValueError, LookupError, SQLAlchemyError) as error:
        raise translate(error) from error
