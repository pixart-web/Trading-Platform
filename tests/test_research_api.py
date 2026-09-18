from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.research.api import router
from pocket_alpha.research.registry import ModelRegistry
from pocket_alpha.research.service import ResearchService
from pocket_alpha.research.storage import ResearchRepository
from tests.research_fixtures import CLOCK, Factory, plan, seed


def test_research_routes_are_read_only_and_fail_closed(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = ResearchRepository(repository.session)
    report = ResearchService(storage, CLOCK).run(plan(seed(storage)), Factory())
    artifact = ModelRegistry(storage, CLOCK).register(report.report_id, "baseline")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    client = TestClient(app)
    response = client.get(f"/api/v1/research/reports/{report.report_id}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["profitability_claim"] is False
    assert client.get(f"/api/v1/research/models/{artifact.artifact_id}").status_code == 200
    assert client.get(f"/api/v1/research/reports/{uuid4()}").status_code == 404
    assert client.get(f"/api/v1/research/models/{uuid4()}").status_code == 404
    assert client.post(f"/api/v1/research/reports/{report.report_id}").status_code == 405

    def broken(self: ResearchRepository, report_id: object) -> None:
        raise SQLAlchemyError("private connection detail")

    monkeypatch.setattr(ResearchRepository, "get", broken)
    failed = client.get(f"/api/v1/research/reports/{report.report_id}")
    assert failed.status_code == 503 and "private" not in failed.text
    assert client.get(f"/api/v1/research/models/{artifact.artifact_id}").status_code == 503

    from pocket_alpha.market_data.quality import (
        DataQualityResult,
        DataRejected,
        ReasonCode,
        Severity,
    )

    def invalid(self: ResearchRepository, report_id: object) -> None:
        raise DataRejected(
            DataQualityResult(
                valid=False,
                severity=Severity.ERROR,
                reason_codes=(ReasonCode.MISSING_INTERVAL,),
                timestamp=CLOCK.now(),
                source="private-source",
                affected_records=(),
                missing_intervals=(),
            )
        )

    monkeypatch.setattr(ResearchRepository, "get", invalid)
    rejected = client.get(f"/api/v1/research/reports/{report.report_id}")
    assert rejected.status_code == 503 and "private-source" not in rejected.text
    assert client.get(f"/api/v1/research/models/{artifact.artifact_id}").status_code == 503
