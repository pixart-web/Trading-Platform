from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.market_data.providers import CandlePage, FixtureProvider, ProviderError
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.service import HistoricalIngestion
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, QUERY, raw


def provider() -> FixtureProvider:
    return FixtureProvider((CandlePage((raw(), raw(1)), "1"), CandlePage((raw(2),))))


def test_paged_ingestion_and_reimport(repository: MarketRepository) -> None:
    metrics = MagicMock()
    service = HistoricalIngestion(repository, provider(), CLOCK, metrics)
    first = service.ingest("test-asset", QUERY, FreshnessPolicy())
    second = service.ingest("test-asset", QUERY, FreshnessPolicy())
    assert first.inserted == 3 and first.quality.valid
    assert second.inserted == 0 and second.duplicates == 3
    metrics.increment.assert_any_call("records_ingested", 3)


@pytest.mark.parametrize(
    "records",
    [
        (raw(), raw(), raw(1), raw(2)),
        (raw(), raw(2)),
        (raw(1), raw(), raw(2)),
        (raw(high="1"), raw(1), raw(2)),
    ],
)
def test_bad_fixture_never_persists(
    repository: MarketRepository, records: tuple[dict[str, object], ...]
) -> None:
    service = HistoricalIngestion(repository, FixtureProvider((CandlePage(records),)), CLOCK)
    with pytest.raises(DataRejected):
        service.ingest("test-asset", QUERY, FreshnessPolicy())
    assert not repository.candles(QUERY)


def test_stale_fixture(repository: MarketRepository) -> None:
    service = HistoricalIngestion(repository, provider(), CLOCK)
    with pytest.raises(DataRejected):
        service.ingest("test-asset", QUERY, FreshnessPolicy(max_age=timedelta(minutes=1)))
    assert not repository.candles(QUERY)


@pytest.mark.parametrize(
    "bad_provider",
    [
        FixtureProvider((), fail=True),
        FixtureProvider((CandlePage((raw(),), "missing"),)),
        FixtureProvider((CandlePage((raw(),), "0"),)),
        FixtureProvider((CandlePage((raw(),) * 10001),)),
        FixtureProvider(tuple(CandlePage((), str(i + 1)) for i in range(100))),
    ],
)
def test_provider_errors_are_atomic(
    repository: MarketRepository, bad_provider: FixtureProvider
) -> None:
    with pytest.raises(ProviderError):
        HistoricalIngestion(repository, bad_provider, CLOCK).ingest(
            "test-asset", QUERY, FreshnessPolicy()
        )
    assert not repository.candles(QUERY)


def test_wrong_asset(repository: MarketRepository) -> None:
    with pytest.raises(LookupError):
        HistoricalIngestion(repository, provider(), CLOCK).ingest("wrong", QUERY, FreshnessPolicy())


def test_storage_failure_propagates(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> int:
        raise SQLAlchemyError("private credentials")

    monkeypatch.setattr(repository, "put", fail)
    with pytest.raises(SQLAlchemyError):
        HistoricalIngestion(repository, provider(), CLOCK).ingest(
            "test-asset", QUERY, FreshnessPolicy()
        )
