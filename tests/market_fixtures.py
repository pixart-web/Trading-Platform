from datetime import UTC, datetime, timedelta

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository

START = datetime(2025, 1, 1, tzinfo=UTC)
CLOCK = FrozenClock(START + timedelta(days=2))
QUERY = CandleQuery(
    market_id="test-market", timeframe=Timeframe.H1, start=START, end=START + timedelta(hours=3)
)


def raw(hour: int = 0, **changes: object) -> dict[str, object]:
    """Explicitly synthetic observations. Never registered by application startup."""
    start = START + timedelta(hours=hour)
    return {
        "market_id": "test-market",
        "timeframe": "1h",
        "open_time": start,
        "close_time": start + timedelta(hours=1),
        "open": "100.123456789123456789",
        "high": "110",
        "low": "90",
        "close": "101",
        "volume": "2.123456789123456789",
        "source": "fixture",
        "received_at": start + timedelta(hours=1),
        **changes,
    }


def sample(hour: int = 0, **changes: object) -> Candle:
    return Candle.model_validate(raw(hour, **changes))


def register(repo: MarketRepository) -> None:
    repo.register(
        Asset(
            asset_id="test-asset", symbol="TEST", name="Synthetic asset", asset_type=AssetType.STOCK
        ),
        Venue(venue_id="test-venue", name="Synthetic venue"),
        Market(
            market_id="test-market",
            asset_id="test-asset",
            venue_id="test-venue",
            symbol="TEST",
            quote_currency="EUR",
        ),
        ProviderMapping(source="fixture", market_id="test-market", instrument_id="PROVIDER-TEST"),
    )
