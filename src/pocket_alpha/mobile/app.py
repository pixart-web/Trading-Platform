from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from pocket_alpha.analysis.api import router as analysis
from pocket_alpha.backtesting.api import router as backtesting
from pocket_alpha.contextual.api import router as contextual
from pocket_alpha.derivatives.api import router as derivatives
from pocket_alpha.fundamentals.api import router as fundamentals
from pocket_alpha.intelligence.zones.api import router as zones
from pocket_alpha.market_data.api import router as market
from pocket_alpha.mobile.auth import Identity, require_session
from pocket_alpha.mobile.auth import router as auth
from pocket_alpha.paper_trading.api import router as paper
from pocket_alpha.portfolio.api import router as portfolio
from pocket_alpha.portfolio_intelligence.api import router as portfolio_intelligence
from pocket_alpha.research.api import router as research
from pocket_alpha.scanner.api import router as scanner
from pocket_alpha.strategies.api import router as strategies
from pocket_alpha.watchlists.api import router as watchlists


def create_mobile_app(parent: FastAPI) -> FastAPI:
    app = FastAPI(title="Pocket Alpha native API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state = parent.state
    app.include_router(auth)
    for router in (
        market,
        analysis,
        zones,
        watchlists,
        scanner,
        portfolio,
        portfolio_intelligence,
        fundamentals,
        derivatives,
        contextual,
        backtesting,
        research,
        paper,
        strategies,
    ):
        app.include_router(router, dependencies=[Depends(require_session)])

    @app.middleware("http")
    async def boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Bounded body prevents parsing huge JSON before authentication/validation.
        body = bytearray()
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 16384:
                return JSONResponse({"detail": "request too large"}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/v1/status")
    def status(identity: Identity) -> dict[str, object]:
        return {
            "status": "authenticated",
            "workspace": "single_operator",
            "real_money_authorized": False,
            "research_submission_available": False,
            "incremental_sync_available": False,
            "push_available": False,
            "execution_monitoring_available": False,
        }

    return app
