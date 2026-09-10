import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pocket_alpha.audit.models import AuditEvent, AuditReason
from pocket_alpha.audit.repository import append_event
from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.market_data.api import router as market_router
from pocket_alpha.observability import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        engine = build_engine(config)
        cache: Redis = Redis.from_url(
            config.redis_url.get_secret_value(), socket_connect_timeout=3, socket_timeout=3
        )
        app.state.engine = engine
        app.state.cache = cache
        app.state.audit_ready = False
        try:
            with Session(engine) as session, session.begin():
                append_event(
                    session,
                    AuditEvent(
                        correlation_id=uuid4(), reason=AuditReason.SYSTEM_STARTED, actor="system"
                    ),
                )
            app.state.audit_ready = True
        except SQLAlchemyError:
            logging.getLogger("pocket_alpha").error("startup_audit_unavailable")
        try:
            yield
        finally:
            cache.close()
            engine.dispose()

    app = FastAPI(title="Pocket Alpha", version="0.1.0", lifespan=lifespan)
    app.include_router(market_router)

    @app.middleware("http")
    async def correlation(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logging.getLogger("pocket_alpha").info(
            "http_request",
            extra={"correlation_id": correlation_id, "status_code": response.status_code},
        )
        return response

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready(request: Request) -> JSONResponse:
        checks = {"database": False, "redis": False, "audit": request.app.state.audit_ready}
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM audit_events LIMIT 1"))
                connection.execute(text("SELECT 1 FROM candles LIMIT 1"))
            checks["database"] = True
        except SQLAlchemyError:
            pass
        try:
            checks["redis"] = bool(request.app.state.cache.ping())
        except RedisError:
            pass
        healthy = all(checks.values())
        return JSONResponse(
            {"status": "ready" if healthy else "not_ready", "checks": checks},
            status_code=200 if healthy else 503,
        )

    return app


app = create_app()
