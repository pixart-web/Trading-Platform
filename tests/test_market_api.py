from collections.abc import Iterator
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import START, sample


def client_for(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def parameters() -> dict[str, str]:
    return {
        "timeframe": "1h",
        "start": START.isoformat(),
        "end": (START + timedelta(hours=3)).isoformat(),
    }


def test_metadata_endpoints(repository: MarketRepository) -> None:
    client = client_for(repository)
    assert client.get("/api/v1/assets").json()[0]["asset_id"] == "test-asset"
    assert client.get("/api/v1/assets/test-asset").json()["asset_type"] == "STOCK"
    assert client.get("/api/v1/assets/missing").status_code == 404
    assert client.get("/api/v1/markets").json()[0]["quote_currency"] == "EUR"
    assert client.get("/api/v1/assets", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/markets", params={"limit": 1001}).status_code == 422
    assert client.get("/api/v1/assets", params={"offset": 100001}).status_code == 422
    assert client.post("/api/v1/assets", json={}).status_code == 405


def test_candles_api_paging_and_quality(repository: MarketRepository) -> None:
    repository.put((sample(2), sample(), sample(1)))
    client = client_for(repository)
    response = client.get("/api/v1/markets/test-market/candles", params=parameters())
    assert response.status_code == 200
    data = response.json()
    assert len(data["candles"]) == 3 and data["quality"]["valid"]
    assert data["candles"][0]["open"] == "100.123456789123456789"
    short = client.get("/api/v1/markets/test-market/candles", params={**parameters(), "limit": "1"})
    assert short.json()["truncated"] and short.json()["next_start"] is not None
    assert short.json()["quality"]["valid"] is False
    assert len(short.json()["candles"]) == 1


def test_candle_query_validation(repository: MarketRepository) -> None:
    client = client_for(repository)
    assert client.get("/api/v1/markets/missing/candles", params=parameters()).status_code == 404
    for changes in (
        {"timeframe": "12h"},
        {"start": "2025-01-01T00:00:00"},
        {"end": START.isoformat()},
        {"limit": "1001"},
        {"end": (START + timedelta(days=500)).isoformat()},
    ):
        assert (
            client.get(
                "/api/v1/markets/test-market/candles", params={**parameters(), **changes}
            ).status_code
            == 422
        )


def test_storage_unavailable_is_503() -> None:
    app = create_app()
    # A real Engine failure at connection checkout exercises the dependency's exception boundary.
    from sqlalchemy import create_engine, event

    broken = create_engine("sqlite://")

    def fail(*args: object) -> None:
        raise SQLAlchemyError("private credentials")

    event.listen(broken, "connect", fail)
    app.state.engine = broken
    response = TestClient(app).get("/api/v1/assets")
    assert response.status_code == 503
    assert "private credentials" not in response.text
    broken.dispose()
