import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import Field, SecretStr
from redis.exceptions import RedisError
from sqlalchemy import func, select, update

from pocket_alpha.audit.models import AuditEvent, AuditReason
from pocket_alpha.audit.repository import append_event
from pocket_alpha.common.clock import SystemClock
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.market_data.api import DB
from pocket_alpha.mobile.models import ConsumedRefreshRecord, DeviceSessionRecord, OperatorRecord
from pocket_alpha.mobile.security import token_hash, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["native identity"])


class Login(DomainModel):
    username: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_.@+-]+$")
    password: SecretStr = Field(min_length=1, max_length=256)
    device_name: str = Field(min_length=1, max_length=80)


class Refresh(DomainModel):
    refresh_token: SecretStr = Field(min_length=40, max_length=128)


class Credentials(DomainModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 300
    session_id: UUID
    user_id: UUID


def rate_limit(request: Request) -> None:
    # Distributed fixed windows. No username/IP appears in Redis keys or logs.
    # A global limit also bounds attempts across invented accounts and proxy addresses.
    key = "mobile-auth:" + str(int(SystemClock().now().timestamp()) // 60)
    try:
        count = request.app.state.cache.incr(key)
        if count == 1:
            request.app.state.cache.expire(key, 120)
        if count > 20:
            raise HTTPException(429, "authentication rate limit", headers={"Retry-After": "60"})
    except RedisError as error:
        raise HTTPException(503, "authentication temporarily unavailable") from error


def require_session(
    request: Request, db: DB, authorization: Annotated[str | None, Header()] = None
) -> DeviceSessionRecord:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(401, "authentication required")
    token = authorization[7:]
    if not 40 <= len(token) <= 128:
        raise HTTPException(401, "invalid session")
    row = db.scalar(
        select(DeviceSessionRecord).where(DeviceSessionRecord.access_hash == token_hash(token))
    )
    now = SystemClock().now()
    if row is None or row.revoked or row.access_expires_at <= now or row.expires_at <= now:
        raise HTTPException(401, "invalid or expired session")
    operator = db.get(OperatorRecord, row.user_id)
    if operator is None or operator.disabled:
        raise HTTPException(401, "invalid session")
    if (
        request.method == "POST"
        and "/portfolios/" in request.url.path
        and request.url.path.endswith("/entries")
        and (row.step_up_expires_at is None or row.step_up_expires_at <= now)
    ):
        raise HTTPException(403, "recent password confirmation required for accounting edits")
    return row


Identity = Annotated[DeviceSessionRecord, Depends(require_session)]


def credentials(row: DeviceSessionRecord, access: str, refresh: str) -> Credentials:
    return Credentials(
        access_token=access,
        refresh_token=refresh,
        session_id=row.session_id,
        user_id=row.user_id,
    )


@router.post("/login", dependencies=[Depends(rate_limit)])
def login(payload: Login, db: DB, response: Response) -> Credentials:
    response.headers["Cache-Control"] = "no-store"
    row = db.scalar(select(OperatorRecord).where(OperatorRecord.username == payload.username))
    # Valid-length dummy hash preserves scrypt cost for absent/disabled identities.
    import base64

    dummy = "scrypt$" + base64.b64encode(bytes(48)).decode()
    valid = verify_password(
        payload.password.get_secret_value(), row.password_hash if row else dummy
    )
    if not valid or row is None or row.disabled:
        raise HTTPException(401, "invalid credentials")
    now = SystemClock().now()
    count = db.scalar(
        select(func.count())
        .select_from(DeviceSessionRecord)
        .where(
            DeviceSessionRecord.user_id == row.user_id,
            DeviceSessionRecord.revoked.is_(False),
            DeviceSessionRecord.expires_at > now,
        )
    )
    if count is not None and count >= 20:
        raise HTTPException(429, "revoke an existing device session first")
    access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    session = DeviceSessionRecord(
        session_id=uuid4(),
        user_id=row.user_id,
        device_name=payload.device_name,
        access_hash=token_hash(access),
        refresh_hash=token_hash(refresh),
        access_expires_at=now + timedelta(minutes=5),
        expires_at=now + timedelta(days=30),
        created_at=now,
        last_seen_at=now,
        revision=1,
        revoked=False,
    )
    db.add(session)
    append_event(
        db,
        AuditEvent(correlation_id=uuid4(), reason=AuditReason.MOBILE_LOGIN, actor=str(row.user_id)),
    )
    db.commit()
    return credentials(session, access, refresh)


@router.post("/refresh", dependencies=[Depends(rate_limit)])
def refresh(payload: Refresh, db: DB, response: Response) -> Credentials:
    response.headers["Cache-Control"] = "no-store"
    digest = token_hash(payload.refresh_token.get_secret_value())
    consumed = db.get(ConsumedRefreshRecord, digest)
    if consumed is not None:
        db.execute(
            update(DeviceSessionRecord)
            .where(DeviceSessionRecord.session_id == consumed.session_id)
            .values(revoked=True)
        )
        append_event(
            db,
            AuditEvent(
                correlation_id=uuid4(),
                reason=AuditReason.MOBILE_REFRESH_REPLAY,
                actor=str(consumed.session_id),
            ),
        )
        db.commit()  # Replay revocation must survive the subsequent 401.
        raise HTTPException(401, "refresh replay; session revoked")
    row = db.scalar(
        select(DeviceSessionRecord)
        .where(DeviceSessionRecord.refresh_hash == digest)
        .with_for_update()
    )
    now = SystemClock().now()
    if row is None or row.revoked or row.expires_at <= now:
        raise HTTPException(401, "invalid or expired session")
    operator = db.get(OperatorRecord, row.user_id)
    if operator is None or operator.disabled:
        raise HTTPException(401, "invalid session")
    access, refresh_token = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    revision = row.revision
    changed = db.scalar(
        update(DeviceSessionRecord)
        .where(
            DeviceSessionRecord.session_id == row.session_id,
            DeviceSessionRecord.revision == revision,
            DeviceSessionRecord.revoked.is_(False),
        )
        .values(
            access_hash=token_hash(access),
            refresh_hash=token_hash(refresh_token),
            access_expires_at=now + timedelta(minutes=5),
            last_seen_at=now,
            revision=revision + 1,
        )
        .returning(DeviceSessionRecord.session_id)
    )
    if changed is None:
        db.rollback()
        raise HTTPException(409, "session changed; sign in again")
    db.add(ConsumedRefreshRecord(token_hash=digest, session_id=row.session_id))
    db.commit()
    return credentials(row, access, refresh_token)


@router.get("/sessions")
def sessions(identity: Identity, db: DB, response: Response) -> list[dict[str, object]]:
    response.headers["Cache-Control"] = "no-store"
    rows = db.scalars(
        select(DeviceSessionRecord)
        .where(
            DeviceSessionRecord.user_id == identity.user_id,
            DeviceSessionRecord.revoked.is_(False),
            DeviceSessionRecord.expires_at > SystemClock().now(),
        )
        .order_by(DeviceSessionRecord.created_at.desc())
        .limit(20)
    )
    return [
        {
            "session_id": str(row.session_id),
            "device_name": row.device_name,
            "created_at": row.created_at.isoformat(),
            "last_seen_at": row.last_seen_at.isoformat(),
            "expires_at": row.expires_at.isoformat(),
            "current": row.session_id == identity.session_id,
        }
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke(session_id: UUID, identity: Identity, db: DB) -> None:
    row = db.scalar(
        select(DeviceSessionRecord).where(
            DeviceSessionRecord.session_id == session_id,
            DeviceSessionRecord.user_id == identity.user_id,
        )
    )
    if row is None:
        raise HTTPException(404, "session not found")
    row.revoked = True
    append_event(
        db,
        AuditEvent(
            correlation_id=uuid4(),
            reason=AuditReason.MOBILE_SESSION_REVOKED,
            actor=str(identity.user_id),
        ),
    )
    db.commit()


class StepUp(DomainModel):
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post("/step-up", dependencies=[Depends(rate_limit)], status_code=204)
def step_up(payload: StepUp, identity: Identity, db: DB) -> None:
    operator = db.get(OperatorRecord, identity.user_id)
    if operator is None or not verify_password(
        payload.password.get_secret_value(), operator.password_hash
    ):
        raise HTTPException(401, "invalid credentials")
    identity.step_up_expires_at = SystemClock().now() + timedelta(minutes=5)
    db.commit()
