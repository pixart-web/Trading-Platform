from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock, SystemClock
from pocket_alpha.domain.market import Candle, CandleQuery, OrderBook, Quote, Trade, TradingSession
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from tests.market_fixtures import QUERY, START, raw, sample


@pytest.mark.parametrize("asset_type", list(AssetType))
def test_universal_asset(asset_type: AssetType) -> None:
    asset = Asset(asset_id="universal", symbol="BTC/EUR", name="Example", asset_type=asset_type)
    assert "provider" not in asset.model_dump()


def test_valid_candle_precision_and_frozen() -> None:
    candle = sample()
    assert candle.open == Decimal("100.123456789123456789")
    assert candle.volume == Decimal("2.123456789123456789")
    with pytest.raises(ValidationError):
        candle.close = Decimal(5)


@pytest.mark.parametrize(
    "changes",
    [
        {"high": "95"},
        {"low": "105"},
        {"open": "0"},
        {"close": "-1"},
        {"volume": "-1"},
        {"volume": "NaN"},
        {"high": "Infinity"},
        {"open": "broken"},
        {"open": "0.0000000000000000001"},
        {"open": "100000000000000000000"},
        {"open_time": START.replace(tzinfo=None)},
        {"close_time": START},
        {"close_time": START + timedelta(hours=2)},
        {"received_at": START},
    ],
)
def test_invalid_candle(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Candle.model_validate({**raw(), **changes})


def test_utc_normalized_and_zero_volume() -> None:
    candle = sample(open_time="2025-01-01T01:00:00+01:00", volume="0")
    assert candle.open_time == START
    assert candle.open_time.utcoffset() == timedelta(0)


def test_incomplete_bar_rejected() -> None:
    with pytest.raises(ValidationError):
        sample(close_time=START + timedelta(minutes=30))


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_timeframe(timeframe: Timeframe) -> None:
    assert timeframe.duration > timedelta(0)
    query = CandleQuery(
        market_id="m", timeframe=timeframe, start=START, end=START + 3 * timeframe.duration
    )
    assert len(query.schedule()) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"end": START},
        {"end": START + timedelta(minutes=61)},
        {"end": START + timedelta(hours=10001)},
        {"expected_opens": (START, START)},
        {"expected_opens": (START + timedelta(hours=1), START)},
        {"expected_opens": (START - timedelta(hours=1),)},
    ],
)
def test_query_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CandleQuery.model_validate({**QUERY.model_dump(), **changes})


def test_explicit_session_schedule() -> None:
    query = CandleQuery.model_validate({**QUERY.model_dump(), "expected_opens": (START,)})
    assert query.schedule() == (START,)
    session = TradingSession.model_validate(
        {
            "market_id": "m",
            "opens_at": START,
            "closes_at": START + timedelta(hours=6),
            "status": "OPEN",
        }
    )
    assert session.closes_at > session.opens_at
    with pytest.raises(ValidationError):
        TradingSession.model_validate({**session.model_dump(), "closes_at": START})


def test_quote_and_trade() -> None:
    quote = {"market_id": "m", "timestamp": START, "bid": "10", "ask": "11", "source": "test"}
    assert Quote.model_validate(quote).bid == Decimal(10)
    for change in ({"ask": "9"}, {"bid_size": "-1"}):
        with pytest.raises(ValidationError):
            Quote.model_validate({**quote, **change})
    trade = {"market_id": "m", "timestamp": START, "price": "1", "quantity": "2", "source": "test"}
    assert Trade.model_validate(trade).provider_trade_id is None
    with pytest.raises(ValidationError):
        Trade.model_validate({**trade, "quantity": "0"})


def test_order_book_integrity() -> None:
    book: dict[str, object] = {
        "market_id": "m",
        "timestamp": START,
        "source": "test",
        "bids": ({"side": "BID", "price": "10", "quantity": "1"},),
        "asks": ({"side": "ASK", "price": "11", "quantity": "1"},),
    }
    assert OrderBook.model_validate(book).sequence is None
    for levels in (
        ({"side": "ASK", "price": "10", "quantity": "1"},),
        ({"side": "BID", "price": "11", "quantity": "1"},),
        ({"side": "BID", "price": "10", "quantity": "1"},) * 2,
        (
            {"side": "BID", "price": "9", "quantity": "1"},
            {"side": "BID", "price": "10", "quantity": "1"},
        ),
    ):
        with pytest.raises(ValidationError):
            OrderBook.model_validate({**book, "bids": levels})


def test_clocks() -> None:
    assert FrozenClock(START).now() == START
    assert SystemClock().now().utcoffset() == timedelta(0)
    with pytest.raises(ValueError):
        FrozenClock(START.replace(tzinfo=None))
