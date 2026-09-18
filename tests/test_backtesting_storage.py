from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.backtesting.api import router
from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.models import Intent
from pocket_alpha.backtesting.service import BacktestService
from pocket_alpha.backtesting.storage import BacktestRecord, BacktestRepository, ConflictingBacktest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.datasets import MarketDatasetRecord
from pocket_alpha.market_data.storage import MarketRepository
from tests.backtest_fixtures import Plan, config, dataset


def test_persistent_reproducibility_conflict_and_dataset_identity(
    repository: MarketRepository,
) -> None:
    data = dataset()
    repository.session.add(
        MarketDatasetRecord(dataset_id=data.dataset_id, payload=data.model_dump_json())
    )
    repository.session.flush()
    storage = BacktestRepository(repository.session)
    clock = FrozenClock(data.inputs.captured_at)
    policy = config()
    decisions = {1: (Intent(client_id="buy", action="BUY", quantity=Decimal(1)),)}
    first = BacktestService(storage, clock).run(data.dataset_id, policy, Plan(decisions))
    assert storage.get(first.run_id) == first
    later = BacktestService(storage, FrozenClock(clock.now() + timedelta(seconds=1))).run(
        data.dataset_id, policy, Plan(decisions)
    )
    assert later == first
    with pytest.raises(ConflictingBacktest):
        BacktestService(storage, clock).run(data.dataset_id, policy, Plan({}))
    assert storage.get(first.run_id) == first
    assert storage.get(uuid4()) is None
    with pytest.raises(LookupError):
        BacktestService(storage, clock).run(uuid4(), policy, Plan({}))
    fresh = dataset().model_copy(update={"dataset_id": UUID(int=2199)})
    with pytest.raises(LookupError):
        storage.put(Backtester(clock).run(fresh, policy, Plan({})))
    row = repository.session.get(BacktestRecord, first.run_id)
    assert row is not None
    row.content_hash = "0" * 64
    repository.session.flush()
    with pytest.raises(ValueError, match="index"):
        storage.get(first.run_id)


def test_read_only_api_and_dependency_errors(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = dataset()
    repository.session.add(
        MarketDatasetRecord(dataset_id=data.dataset_id, payload=data.model_dump_json())
    )
    repository.session.flush()
    report = BacktestService(
        BacktestRepository(repository.session), FrozenClock(data.inputs.captured_at)
    ).run(data.dataset_id, config(), Plan({}))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    with TestClient(app) as client:
        response = client.get(f"/api/v1/backtests/{report.run_id}")
        assert (
            response.status_code == 200 and response.json()["content_hash"] == report.content_hash
        )
        assert response.headers["cache-control"] == "no-store"
        assert client.get(f"/api/v1/backtests/{uuid4()}").status_code == 404
        assert client.post(f"/api/v1/backtests/{report.run_id}").status_code == 405

        def failed(self: BacktestRepository, run_id: UUID) -> None:
            raise SQLAlchemyError("sensitive connection detail")

        monkeypatch.setattr(BacktestRepository, "get", failed)
        failure = client.get(f"/api/v1/backtests/{report.run_id}")
        assert failure.status_code == 503 and "sensitive" not in failure.text
