import hmac
import re
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.config import Settings
from pocket_alpha.live_control.models import (
    ConfigureControl,
    LiveControlSnapshot,
    TransitionControl,
)
from pocket_alpha.live_control.service import ControlConflict, ControlRejected, LiveControlService
from pocket_alpha.market_data.api import DB

router = APIRouter(prefix="/api/v1/live-control", tags=["live control"])
ProxyToken = Annotated[str | None, Header(alias="X-PA-Control-Token")]
Actor = Annotated[str | None, Header(alias="X-PA-Actor")]
Correlation = Annotated[str | None, Header(alias="X-Correlation-ID")]


def authorize(token: str | None, actor: str | None, settings: Settings) -> str:
    expected = settings.control_proxy_token.get_secret_value()
    if len(expected) < 32:
        raise HTTPException(503, "live control authentication is not configured")
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "live control authentication failed")
    if actor is None or not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,128}", actor):
        raise HTTPException(401, "live control actor is invalid")
    return actor


def correlation(value: str | None) -> UUID:
    try:
        return UUID(value) if value else uuid4()
    except ValueError as error:
        raise HTTPException(400, "invalid correlation id") from error


@router.get("")
def read_control(
    request: Request,
    db: DB,
    response: Response,
    token: ProxyToken = None,
    actor: Actor = None,
) -> LiveControlSnapshot:
    settings: Settings = request.app.state.settings
    authorize(token, actor, settings)
    response.headers["Cache-Control"] = "no-store"
    try:
        return LiveControlService(db, settings, SystemClock()).snapshot()
    except SQLAlchemyError as error:
        raise HTTPException(503, "live control storage unavailable") from error


@router.put("")
def configure_control(
    command: ConfigureControl,
    request: Request,
    db: DB,
    response: Response,
    token: ProxyToken = None,
    actor: Actor = None,
    correlation_id: Correlation = None,
) -> LiveControlSnapshot:
    settings: Settings = request.app.state.settings
    operator = authorize(token, actor, settings)
    response.headers["Cache-Control"] = "no-store"
    try:
        result = LiveControlService(db, settings, SystemClock()).configure(
            command, actor=operator, correlation_id=correlation(correlation_id)
        )
        db.commit()
        return result
    except ControlConflict as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except ControlRejected as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(503, "live control storage unavailable") from error


@router.post("/transitions")
def transition_control(
    command: TransitionControl,
    request: Request,
    db: DB,
    response: Response,
    token: ProxyToken = None,
    actor: Actor = None,
    correlation_id: Correlation = None,
) -> LiveControlSnapshot:
    settings: Settings = request.app.state.settings
    operator = authorize(token, actor, settings)
    response.headers["Cache-Control"] = "no-store"
    try:
        result = LiveControlService(db, settings, SystemClock()).transition(
            command, actor=operator, correlation_id=correlation(correlation_id)
        )
        db.commit()
        return result
    except ControlConflict as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except ControlRejected as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(503, "live control storage unavailable") from error
