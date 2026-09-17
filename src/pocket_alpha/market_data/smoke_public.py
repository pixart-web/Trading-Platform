"""Opt-in public-data gate evidence, explicitly isolated from production databases."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.contextual.models import ContextEntity, ContextMapping
from pocket_alpha.contextual.providers import FederalReserveNewsProvider
from pocket_alpha.contextual.service import ContextService
from pocket_alpha.contextual.storage import ContextRepository
from pocket_alpha.database import Base
from pocket_alpha.domain.market import CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.market_data.datasets import DatasetRepository
from pocket_alpha.market_data.import_public import import_registered
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit public GET smoke; creates local REAL evidence in data/local"
    )
    parser.add_argument("--public-read", action="store_true", required=True)
    parser.parse_args()
    directory = Path("data/local").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    engine = create_engine(f"sqlite:///{(directory / (identifier + '.sqlite')).as_posix()}")
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    clock = SystemClock()
    query = CandleQuery(
        market_id="coinbase:BTC-USD",
        timeframe=Timeframe.H1,
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 2, tzinfo=UTC),
    )
    try:
        with Session(engine) as session, session.begin():
            MarketRepository(session).register(
                Asset(
                    asset_id="crypto:BTC", symbol="BTC", name="Bitcoin", asset_type=AssetType.CRYPTO
                ),
                Venue(venue_id="coinbase-exchange", name="Coinbase Exchange"),
                Market(
                    market_id=query.market_id,
                    asset_id="crypto:BTC",
                    venue_id="coinbase-exchange",
                    symbol="BTC-USD",
                    quote_currency="USD",
                ),
                ProviderMapping(
                    source="coinbase-exchange", market_id=query.market_id, instrument_id="BTC-USD"
                ),
            )
            dataset = import_registered(session, "crypto:BTC", query)
            repo = ContextRepository(session)
            repo.register(
                ContextEntity(
                    entity_id="macro:fed", name="Federal Reserve announcements", kind="MACRO"
                ),
                ContextMapping(
                    source="federal-reserve-rss",
                    entity_id="macro:fed",
                    external_entity_id="press-releases",
                ),
            )
            context = ContextService(repo, clock)
            news_inserted = context.ingest("macro:fed", FederalReserveNewsProvider())
            snapshot = context.snapshot("macro:fed", clock.now())
        with Session(engine) as session:
            stored = DatasetRepository(session).get(dataset.dataset_id)
            if stored != dataset or stored.replay() != dataset.replay():
                raise ValueError("persisted real dataset failed deterministic replay")
            again = ContextService(ContextRepository(session), clock).snapshot(
                "macro:fed", snapshot.as_of
            )
            if again.input_hash != snapshot.input_hash:
                raise ValueError("persisted news failed deterministic snapshot")
        (directory / (identifier + ".dataset.json")).write_text(
            dataset.model_dump_json(), encoding="utf-8", newline="\n"
        )
        evidence = dict(
            origin="REAL",
            source=dataset.inputs.mapping.source,
            instrument=dataset.inputs.mapping.instrument_id,
            dataset_id=str(dataset.dataset_id),
            content_hash=dataset.content_hash,
            candles=len(dataset.inputs.candles),
            start=query.start.isoformat(),
            end=query.end.isoformat(),
            captured_at=dataset.inputs.captured_at.isoformat(),
            stored_replay_equal=True,
            context_source="federal-reserve-rss",
            news_inserted=news_inserted,
            context_input_hash=snapshot.input_hash,
            context_cutoff=snapshot.as_of.isoformat(),
            stored_context_equal=True,
            storage="isolated SQLite evidence, not production PostgreSQL",
        )
        (directory / (identifier + ".evidence.json")).write_text(
            json.dumps(evidence, indent=2), encoding="utf-8", newline="\n"
        )
        print(json.dumps(evidence, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
