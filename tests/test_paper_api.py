from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.paper_trading.api import router
from pocket_alpha.paper_trading.storage import PaperRepository
from tests.test_paper_trading import CheckpointPlan, setup


def test_paper_read_only_api_and_failed_reconciliation(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    paper, state = setup(repository, CheckpointPlan({}))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    client = TestClient(app)
    response = client.get("/api/v1/paper/accounts")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()[0]["mode"] == "PAPER" and not response.json()[0]["live_ready"]
    assert client.get(f"/api/v1/paper/accounts/{state.account_id}").status_code == 200
    assert client.get(f"/api/v1/paper/accounts/{uuid4()}").status_code == 404
    assert client.post("/api/v1/paper/accounts").status_code == 405
    assert client.delete(f"/api/v1/paper/accounts/{state.account_id}").status_code == 405

    def broken(self: PaperRepository, key: object) -> None:
        raise SQLAlchemyError("private details")

    monkeypatch.setattr(PaperRepository, "load", broken)
    failed = client.get(f"/api/v1/paper/accounts/{state.account_id}")
    assert failed.status_code == 503 and "private" not in failed.text
    assert client.get("/api/v1/paper/accounts").status_code == 503
