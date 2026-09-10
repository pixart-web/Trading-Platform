import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import Clock
from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.market_data.providers import HistoricalMarketDataProvider, ProviderError
from pocket_alpha.market_data.quality import (
    DataQualityResult,
    DataRejected,
    FreshnessPolicy,
    inspect_candles,
)
from pocket_alpha.market_data.storage import ConflictingCandle, MarketRecord, MarketRepository

logger = logging.getLogger("pocket_alpha")


class Metrics(Protocol):
    def increment(self, name: str, amount: int = 1) -> None: ...


class NoopMetrics:
    def increment(self, name: str, amount: int = 1) -> None:
        pass


@dataclass(frozen=True)
class IngestionResult:
    inserted: int
    duplicates: int
    quality: DataQualityResult


class HistoricalIngestion:
    def __init__(
        self,
        repository: MarketRepository,
        provider: HistoricalMarketDataProvider,
        clock: Clock,
        metrics: Metrics | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.clock = clock
        self.metrics = metrics or NoopMetrics()

    def ingest(self, asset_id: str, query: CandleQuery, policy: FreshnessPolicy) -> IngestionResult:
        """Validate entire bounded import before writing. Caller commits the transaction."""
        logger.info("ingestion_started")
        try:
            market = self.repository.session.get(MarketRecord, query.market_id)
            if market is None or market.asset_id != asset_id:
                raise LookupError("asset/market not registered")
            mapping = self.repository.mapping(query.market_id, self.provider.source)
            records: list[Mapping[str, object]] = []
            cursor: str | None = None
            cursors: set[str] = set()
            for _ in range(100):
                page = self.provider.candles(query, mapping, cursor)
                records.extend(page.records)
                if len(records) > 10000:
                    raise ProviderError("provider exceeded bounded import")
                cursor = page.next_cursor
                if cursor is None:
                    break
                if cursor in cursors:
                    raise ProviderError("provider cursor cycle")
                cursors.add(cursor)
            else:
                raise ProviderError("provider exceeded page budget")
            candles, quality = inspect_candles(
                records, query, self.provider.source, policy, self.clock
            )
            if not quality.valid:
                self.metrics.increment("records_rejected", len(records))
                self.metrics.increment("gaps_detected", len(quality.missing_intervals))
                for reason in quality.reason_codes:
                    logger.warning("data_quality_" + reason.value.lower())
                raise DataRejected(quality)
            inserted = self.repository.put(candles)
            duplicates = len(candles) - inserted
            self.metrics.increment("records_ingested", inserted)
            if duplicates:
                logger.info("duplicate_records_unchanged")
            logger.info("ingestion_completed")
            return IngestionResult(inserted, duplicates, quality)
        except ProviderError:
            self.metrics.increment("ingestion_failures")
            logger.error("provider_failure")
            raise
        except (SQLAlchemyError, ConflictingCandle):
            self.metrics.increment("ingestion_failures")
            logger.error("persistence_failure")
            raise
