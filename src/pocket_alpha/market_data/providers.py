from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from pocket_alpha.domain.market import CandleQuery, Identifier, OrderBook, Quote, Trade
from pocket_alpha.domain.models import Asset, DomainModel


class ProviderMapping(DomainModel):
    source: Identifier
    market_id: Identifier
    instrument_id: str = Field(min_length=1, max_length=256)


class ProviderError(Exception):
    """Adapter failed; callers must not substitute invented records."""


@dataclass(frozen=True)
class CandlePage:
    records: tuple[Mapping[str, object], ...]
    next_cursor: str | None = None


class MarketDataProvider(Protocol):
    @property
    def source(self) -> str: ...


class HistoricalMarketDataProvider(MarketDataProvider, Protocol):
    def candles(
        self, query: CandleQuery, mapping: ProviderMapping, cursor: str | None
    ) -> CandlePage: ...


class StreamingMarketDataProvider(MarketDataProvider, Protocol):
    def events(self, mapping: ProviderMapping) -> Iterator[Trade | Quote | OrderBook]: ...


class AssetMetadataProvider(MarketDataProvider, Protocol):
    def assets(self) -> tuple[Asset, ...]: ...


class FixtureProvider:
    """Synthetic tests only. Preserve payload order/errors; do not clean bad feeds."""

    source = "fixture"

    def __init__(self, pages: tuple[CandlePage, ...], *, fail: bool = False) -> None:
        self.pages = deepcopy(pages)
        self.fail = fail

    def candles(
        self, query: CandleQuery, mapping: ProviderMapping, cursor: str | None
    ) -> CandlePage:
        if self.fail or mapping.source != self.source:
            raise ProviderError("fixture provider failure")
        try:
            return deepcopy(self.pages[int(cursor) if cursor is not None else 0])
        except (ValueError, IndexError) as error:
            raise ProviderError("invalid fixture cursor") from error
