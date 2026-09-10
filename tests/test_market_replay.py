from datetime import timedelta

import pytest

from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy, ReasonCode
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, QUERY, START, sample


def test_deterministic_replay_boundaries(repository: MarketRepository) -> None:
    repository.put((sample(3), sample(2), sample(0), sample(1)))
    replay = MarketReplay(repository, CLOCK)
    first = replay.replay(QUERY, FreshnessPolicy())
    assert first == replay.replay(QUERY, FreshnessPolicy())
    assert [event.candle.open_time for event in first] == list(QUERY.schedule())
    assert all(event.available_at >= event.candle.close_time for event in first)


def test_late_arrival_is_not_released_early(repository: MarketRepository) -> None:
    repository.put((sample(received_at=START + timedelta(hours=4)), sample(1), sample(2)))
    result = MarketReplay(repository, CLOCK).replay(QUERY, FreshnessPolicy())
    assert result[-1].candle.open_time == START
    assert result[-1].available_at == START + timedelta(hours=4)


def test_gap_preserved_but_not_trusted(repository: MarketRepository) -> None:
    repository.put((sample(0), sample(2)))
    replay = MarketReplay(repository, CLOCK)
    batch = replay.inspect(QUERY, FreshnessPolicy())
    assert len(batch.events) == 2
    assert batch.quality.missing_intervals == (START + timedelta(hours=1),)
    with pytest.raises(DataRejected):
        replay.replay(QUERY, FreshnessPolicy())


def test_empty_replay(repository: MarketRepository) -> None:
    replay = MarketReplay(repository, CLOCK)
    batch = replay.inspect(QUERY, FreshnessPolicy())
    assert batch.events == ()
    assert ReasonCode.MISSING_INTERVAL in batch.quality.reason_codes
    closed = CandleQuery.model_validate({**QUERY.model_dump(), "expected_opens": ()})
    assert replay.replay(closed, FreshnessPolicy()) == ()
