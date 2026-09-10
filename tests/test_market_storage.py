from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from pocket_alpha.domain.market import Market, Venue
from pocket_alpha.domain.models import Asset, AssetType
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import CandleRecord, ConflictingCandle, MarketRepository
from tests.market_fixtures import QUERY, START, register, sample


def test_persist_exact_idempotent_and_ordered(repository: MarketRepository) -> None:
    assert repository.put((sample(2), sample(0), sample(1))) == 3
    assert repository.put((sample(0), sample(1), sample(2))) == 0
    candles = repository.candles(QUERY)
    assert [c.open_time for c in candles] == list(QUERY.schedule())
    assert candles[0].open == Decimal("100.123456789123456789")
    assert candles[0].volume == Decimal("2.123456789123456789")
    assert candles[0].open_time == START


def test_conflict_rolls_back_whole_batch(repository: MarketRepository) -> None:
    repository.put((sample(),))
    with pytest.raises(ConflictingCandle):
        repository.put((sample(1), sample(close="102")))
    assert len(repository.candles(QUERY)) == 1
    assert repository.candles(QUERY)[0].close == Decimal("101")


def test_reimport_preserves_first_receipt(repository: MarketRepository) -> None:
    repository.put((sample(),))
    assert repository.put((sample(received_at=START + timedelta(days=1)),)) == 0
    assert repository.candles(QUERY)[0].received_at == START + timedelta(hours=1)


def test_database_uniqueness(repository: MarketRepository) -> None:
    repository.put((sample(),))
    with pytest.raises(IntegrityError), repository.session.begin_nested():
        repository.session.add(CandleRecord(**sample().model_dump()))
        repository.session.flush()


def test_foreign_key(repository: MarketRepository) -> None:
    with pytest.raises(IntegrityError):
        repository.put((sample(market_id="missing"),))


def test_metadata_idempotency_and_mapping(repository: MarketRepository) -> None:
    register(repository)
    assert repository.mapping("test-market", "fixture").instrument_id == "PROVIDER-TEST"
    with pytest.raises(LookupError):
        repository.mapping("test-market", "unknown")


def test_multiple_listings_and_metadata_conflict(repository: MarketRepository) -> None:
    asset = Asset(
        asset_id="test-asset", symbol="TEST", name="Synthetic asset", asset_type=AssetType.STOCK
    )
    venue = Venue(venue_id="test-venue", name="Synthetic venue")
    market = Market(
        market_id="second",
        asset_id=asset.asset_id,
        venue_id=venue.venue_id,
        symbol="TEST/USD",
        quote_currency="USD",
    )
    mapping = ProviderMapping(source="fixture", market_id="second", instrument_id="SECOND")
    repository.register(asset, venue, market, mapping)
    with pytest.raises(ValueError):
        repository.register(asset.model_copy(update={"name": "Changed"}), venue, market, mapping)
    with pytest.raises(ValueError):
        repository.register(asset.model_copy(update={"asset_id": "wrong"}), venue, market, mapping)
    with pytest.raises(ValueError):
        repository.register(asset, venue, market, mapping.model_copy(update={"market_id": "wrong"}))


def test_query_bounds(repository: MarketRepository) -> None:
    with pytest.raises(ValueError):
        repository.candles(QUERY, limit=10002)


def test_postgres_ohlc_constraint(repository: MarketRepository) -> None:
    if repository.session.get_bind().dialect.name != "postgresql":
        pytest.skip("numeric checks require PostgreSQL")
    with pytest.raises(IntegrityError), repository.session.begin_nested():
        values = sample().model_dump()
        values["high"] = Decimal(1)
        repository.session.add(CandleRecord(**values))
        repository.session.flush()
