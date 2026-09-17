import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.contextual.api import router
from pocket_alpha.contextual.storage import ContextRepository
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import START
from tests.test_phase20_context import setup


def test_context_api_read_only_and_cutoff(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/context/macro:synthetic", params={"as_of": START.isoformat()}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["observations"] == []
        assert set(response.json()["unavailable_kinds"]) == {"NEWS", "SENTIMENT", "MACRO"}
        assert (
            client.get("/api/v1/context/unknown", params={"as_of": START.isoformat()}).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/context/macro:synthetic", params={"as_of": "2025-01-01"}
            ).status_code
            == 422
        )
        assert client.post("/api/v1/context/macro:synthetic").status_code == 405

        def failure(self: ContextRepository, entity_id: str, lock: bool = False) -> None:
            raise SQLAlchemyError("sensitive connection string")

        monkeypatch.setattr(ContextRepository, "entity", failure)
        error = client.get("/api/v1/context/macro:synthetic", params={"as_of": START.isoformat()})
        assert error.status_code == 503 and "sensitive" not in error.text
