"""Mock public payloads test boundaries only. No empirical REAL-data claim."""

from datetime import timedelta
from uuid import UUID

import pytest

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.market_data.providers import CandlePage, ProviderError, ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.paper_trading.feed import PublicPaperPoller
from pocket_alpha.paper_trading.models import PaperConfig
from pocket_alpha.paper_trading.service import PaperService
from pocket_alpha.paper_trading.storage import PaperRepository
from tests.backtest_fixtures import config, dataset
from tests.market_fixtures import START
from tests.test_paper_trading import CheckpointPlan, setup


class MockNative:
    source = "coinbase-exchange"

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    def candles(
        self, query: CandleQuery, mapping: ProviderMapping, cursor: str | None
    ) -> CandlePage:
        self.calls += 1
        if self.mode == "offline":
            raise ProviderError("private failure")
        if self.mode == "gap":
            return CandlePage((), None)
        original = dataset().inputs.candles[0]
        bar = original.model_copy(
            update=dict(
                market_id=query.market_id,
                timeframe=Timeframe.M1,
                open_time=query.start,
                close_time=query.end,
                received_at=query.end,
                source=self.source,
            )
        )
        return CandlePage((bar.model_dump(),), None)


def native(repository: MarketRepository) -> tuple[PaperService, UUID, CheckpointPlan]:
    asset = Asset(
        asset_id="crypto:BTC", symbol="BTC", name="MOCK ONLY", asset_type=AssetType.CRYPTO
    )
    venue = Venue(venue_id="coinbase-exchange", name="MOCK ONLY")
    market = Market(
        market_id="coinbase:BTC-USD",
        asset_id=asset.asset_id,
        venue_id=venue.venue_id,
        symbol="BTC-USD",
        quote_currency="USD",
    )
    mapping = ProviderMapping(
        source="coinbase-exchange", market_id=market.market_id, instrument_id="BTC-USD"
    )
    repository.register(asset, venue, market, mapping)
    paper = PaperService(
        PaperRepository(repository.session), FrozenClock(START + timedelta(seconds=10))
    )
    plan = CheckpointPlan({})
    state = paper.create(
        PaperConfig(
            origin="REAL",
            asset=asset,
            venue=venue,
            market=market,
            mapping=mapping,
            timeframe=Timeframe.M1,
            start=START,
            run=config(),
            maximum_events=10,
        ),
        plan,
    )
    return paper, state.account_id, plan


@pytest.mark.parametrize("mode", ["valid", "gap", "offline"])
def test_explicit_native_polling_and_failure_suspend(
    repository: MarketRepository, mode: str
) -> None:
    paper, key, plan = native(repository)
    provider = MockNative(mode)
    poller = PublicPaperPoller(paper, provider)
    assert provider.calls == 0
    waiting = poller.poll(key, plan)
    assert waiting.status == "WAITING_DATA" and provider.calls == 0
    paper.clock = FrozenClock(START + timedelta(minutes=1, seconds=2))
    state = poller.poll(key, plan)
    assert provider.calls == 1
    if mode == "valid":
        assert state.status == "ACTIVE" and state.last_close == START + timedelta(minutes=1)
        assert state.at == paper.clock.now() and len(plan.views) == 1
    else:
        assert state.reason == "FEED_UNAVAILABLE" and state.status == "SUSPENDED" and not plan.views
    assert not state.fills and not state.live_ready
    assert paper.repository.load(key) is not None


def test_public_poller_rejects_synthetic_origin(repository: MarketRepository) -> None:
    plan = CheckpointPlan({})
    paper, state = setup(repository, plan)
    provider = MockNative("valid")
    with pytest.raises(ValueError):
        PublicPaperPoller(paper, provider).poll(state.account_id, plan)
    assert provider.calls == 0
