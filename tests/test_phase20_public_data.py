"""Synthetic HTTP responses only; public network smoke is explicitly opt-in."""

import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pocket_alpha.common.public_http import PublicClient, PublicDataError, Response
from pocket_alpha.contextual.providers import ContextProviderError, FederalReserveNewsProvider
from pocket_alpha.domain.market import Candle, CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.market_data.coinbase import CoinbaseHistoricalProvider
from pocket_alpha.market_data.datasets import (
    DatasetInputs,
    DatasetRepository,
    MarketDataset,
    MarketDatasetRecord,
)
from pocket_alpha.market_data.providers import ProviderError, ProviderMapping
from pocket_alpha.market_data.quality import DataRejected
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, QUERY, START, sample


class Transport:
    def __init__(self, *responses: Response) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str, timeout: float, maximum_bytes: int) -> Response:
        self.urls.append(url)
        return self.responses.pop(0)


def client(transport: Transport) -> PublicClient:
    # Explicit arguments keep this helper strongly typed; no network and no real waits.
    return PublicClient(transport=transport, clock=CLOCK, sleep=lambda _: None, monotonic=lambda: 0)


def test_retry_is_bounded_and_byte_budget_enforced() -> None:
    transport = Transport(Response(429, b"", {"retry-after": "1"}), Response(200, b"ok", {}))
    assert client(transport).get("https://example.org/data") == (b"ok", CLOCK.now())
    assert len(transport.urls) == 2
    for delay in ("20", "-1", "nan", "inf"):
        with pytest.raises(PublicDataError, match="embargo"):
            client(Transport(Response(429, b"", {"retry-after": delay}))).get(
                "https://example.org/data"
            )
    with pytest.raises(PublicDataError, match="exhausted"):
        client(Transport(*(Response(503, b"", {}) for _ in range(3)))).get(
            "https://example.org/data"
        )
    with pytest.raises(PublicDataError, match="status 403"):
        client(Transport(Response(403, b"secret-body-not-logged", {}))).get(
            "https://example.org/data"
        )
    limited = PublicClient(transport=Transport(Response(200, b"1234", {})), maximum_bytes=3)
    with pytest.raises(PublicDataError, match="byte budget"):
        limited.get("https://example.org/data")
    with pytest.raises(ValueError, match="HTTPS"):
        client(Transport()).get("http://example.org/data")


def test_coinbase_native_mapping_decimal_order_and_window_filter() -> None:
    rows = [
        [int((START + timedelta(hours=h)).timestamp()), 90, 110, 100, 101, "2.123456789123456789"]
        for h in (3, 2, 1, 0, -1)
    ]
    transport = Transport(Response(200, json.dumps(rows).encode(), {}))
    provider = CoinbaseHistoricalProvider(client(transport))
    mapping = ProviderMapping(
        source=provider.source, market_id=QUERY.market_id, instrument_id="BTC-USD"
    )
    page = provider.candles(QUERY, mapping)
    records = tuple(Candle.model_validate(r) for r in page.records)
    assert tuple(c.open_time for c in records) == QUERY.schedule()
    assert records[0].volume == Decimal("2.123456789123456789")
    assert all(c.received_at == CLOCK.now() for c in records)
    assert page.next_cursor is None
    assert "/products/BTC-USD/candles?" in transport.urls[0]
    with pytest.raises(ValueError, match="mapping"):
        provider.candles(QUERY, mapping.model_copy(update={"source": "fixture"}))
    with pytest.raises(ValueError, match="native"):
        provider.candles(QUERY.model_copy(update={"timeframe": Timeframe.H4}), mapping)
    with pytest.raises(ProviderError, match="cursor"):
        provider.candles(QUERY, mapping, "2025-01-01T00:00:00")


def test_coinbase_time_pagination_and_malformed_fail_closed() -> None:
    transport = Transport(Response(200, b"[]", {}), Response(200, b"[]", {}))
    provider = CoinbaseHistoricalProvider(client(transport))
    query = CandleQuery(
        market_id=QUERY.market_id,
        timeframe=Timeframe.H1,
        start=START,
        end=START + timedelta(hours=300),
    )
    mapping = ProviderMapping(
        source=provider.source, market_id=query.market_id, instrument_id="BTC-USD"
    )
    first = provider.candles(query, mapping)
    assert first.next_cursor == (START + timedelta(hours=299)).isoformat()
    assert provider.candles(query, mapping, first.next_cursor).next_cursor is None
    for body in (
        b"{}",
        b"not-json",
        b"[[true,90,110,100,101,1]]",
        b"[[1735689600,110,90,100,101,1]]",
    ):
        with pytest.raises(ProviderError):
            CoinbaseHistoricalProvider(client(Transport(Response(200, body, {})))).candles(
                QUERY, mapping
            )


def test_rss_preserves_only_primary_metadata_and_rejects_xml_entities() -> None:
    xml = (
        b"<rss><channel><item><title>Synthetic announcement</title>"
        b"<link>https://www.federalreserve.gov/newsevents/pressreleases/test.htm</link>"
        b"<guid>synthetic-id</guid><pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate>"
        b"</item></channel></rss>"
    )
    provider = FederalReserveNewsProvider(client(Transport(Response(200, xml, {}))))
    record = provider.observations("press-releases").records[0]
    assert record.published_at == START and record.value is None and record.method_version is None
    for body in (
        b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss/>',
        xml.replace(b"www.federalreserve.gov", b"example.org"),
        xml.replace(b"<pubDate>", b"<missing>"),
        b"<rss>",
    ):
        with pytest.raises(ContextProviderError):
            FederalReserveNewsProvider(client(Transport(Response(200, body, {})))).observations(
                "press-releases"
            )


def test_frozen_dataset_origin_hash_and_replay(repository: MarketRepository) -> None:
    repository.put(tuple(sample(h) for h in range(3)))
    repo = DatasetRepository(repository.session)
    dataset = repo.freeze(QUERY, "fixture", "SYNTHETIC", CLOCK.now())
    stored = repo.get(dataset.dataset_id)
    assert stored == dataset
    assert MarketDataset.model_validate_json(dataset.model_dump_json()).replay() == dataset.replay()
    assert all(e.available_at == CLOCK.now() for e in dataset.replay())
    assert repo.get(uuid4()) is None
    with pytest.raises(ValueError, match="public market source"):
        repo.freeze(QUERY, "fixture", "REAL", CLOCK.now())
    with pytest.raises(ValidationError, match="hash"):
        MarketDataset(dataset_id=dataset.dataset_id, inputs=dataset.inputs, content_hash="0" * 64)
    row = repository.session.get(MarketDatasetRecord, dataset.dataset_id)
    assert row is not None
    row.payload = dataset.model_dump_json().replace(
        "100.123456789123456789", "100.123456789123456788"
    )
    repository.session.flush()
    with pytest.raises(ValidationError, match="hash"):
        repo.get(dataset.dataset_id)


def test_dataset_never_mixes_sources_or_accepts_gaps_or_future_availability() -> None:
    mapping = ProviderMapping(
        source="fixture", market_id=QUERY.market_id, instrument_id="synthetic"
    )
    for candles, captured in (
        (tuple(sample(h) for h in (0, 2)), CLOCK.now()),
        (tuple(sample(h) for h in range(3)), START),
        ((sample(0), sample(1, source="coinbase-exchange"), sample(2)), CLOCK.now()),
    ):
        with pytest.raises(DataRejected):
            DatasetInputs(
                origin="SYNTHETIC",
                market=Market(
                    market_id=QUERY.market_id,
                    asset_id="synthetic",
                    venue_id="synthetic",
                    symbol="TEST",
                    quote_currency="EUR",
                ),
                asset=Asset(
                    asset_id="synthetic",
                    symbol="TEST",
                    name="Synthetic",
                    asset_type=AssetType.STOCK,
                ),
                venue=Venue(venue_id="synthetic", name="Synthetic"),
                mapping=mapping,
                query=QUERY,
                captured_at=captured,
                candles=candles,
            )


@pytest.mark.parametrize("bad", ["asset-type", "quote", "venue", "symbol"])
def test_real_dataset_rejects_unverified_economic_identity(bad: str) -> None:
    # Explicitly synthetic fixtures used only to test rejection; never real research evidence.
    asset = Asset(
        asset_id="synthetic:BTC", symbol="BTC", name="Synthetic BTC", asset_type=AssetType.CRYPTO
    )
    market = Market(
        market_id=QUERY.market_id,
        asset_id=asset.asset_id,
        venue_id="coinbase-exchange",
        symbol="BTC-USD",
        quote_currency="USD",
    )
    if bad == "asset-type":
        asset = asset.model_copy(update={"asset_type": AssetType.STOCK})
    elif bad == "quote":
        market = market.model_copy(update={"quote_currency": "EUR"})
    elif bad == "venue":
        market = market.model_copy(update={"venue_id": "synthetic-venue"})
    else:
        market = market.model_copy(update={"symbol": "BTC-EUR"})
    with pytest.raises(ValueError, match="product mapping"):
        DatasetInputs(
            origin="REAL",
            mapping=ProviderMapping(
                source="coinbase-exchange", market_id=QUERY.market_id, instrument_id="BTC-USD"
            ),
            market=market,
            asset=asset,
            venue=Venue(venue_id=market.venue_id, name="Synthetic venue"),
            query=QUERY,
            captured_at=CLOCK.now(),
            candles=tuple(sample(h, source="coinbase-exchange") for h in range(3)),
        )
