from dataclasses import dataclass
from datetime import datetime

from pocket_alpha.common.clock import Clock
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.market_data.quality import (
    DataQualityResult,
    DataRejected,
    FreshnessPolicy,
    inspect_candles,
)
from pocket_alpha.market_data.storage import MarketRepository


@dataclass(frozen=True)
class ReplayEvent:
    available_at: datetime
    candle: Candle


@dataclass(frozen=True)
class ReplayBatch:
    events: tuple[ReplayEvent, ...]
    quality: DataQualityResult

    def trusted_events(self) -> tuple[ReplayEvent, ...]:
        if not self.quality.valid:
            raise DataRejected(self.quality)
        return self.events


class MarketReplay:
    def __init__(self, repository: MarketRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def inspect(self, query: CandleQuery, policy: FreshnessPolicy) -> ReplayBatch:
        candles = self.repository.candles(query, limit=10001)
        _, quality = inspect_candles(
            [c.model_dump() for c in candles],
            query,
            candles[0].source if candles else "stored",
            policy,
            self.clock,
        )
        # received_at is at least close_time. Never release data at open_time.
        events = tuple(
            sorted(
                (ReplayEvent(c.received_at, c) for c in candles),
                key=lambda event: (event.available_at, event.candle.open_time),
            )
        )
        return ReplayBatch(events, quality)

    def replay(self, query: CandleQuery, policy: FreshnessPolicy) -> tuple[ReplayEvent, ...]:
        return self.inspect(query, policy).trusted_events()
