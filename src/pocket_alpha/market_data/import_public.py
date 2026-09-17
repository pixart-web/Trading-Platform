"""Explicit opt-in read-only imports; never run at application startup."""

import argparse
from datetime import datetime

from sqlalchemy.orm import Session

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.market_data.coinbase import CoinbaseHistoricalProvider
from pocket_alpha.market_data.datasets import DatasetRepository, MarketDataset
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.service import HistoricalIngestion
from pocket_alpha.market_data.storage import MarketRepository


def import_registered(session: Session, asset_id: str, query: CandleQuery) -> MarketDataset:
    clock = SystemClock()
    HistoricalIngestion(MarketRepository(session), CoinbaseHistoricalProvider(), clock).ingest(
        asset_id, query, FreshnessPolicy()
    )
    return DatasetRepository(session).freeze(query, "coinbase-exchange", "REAL", clock.now())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import public Coinbase candles for an explicitly registered market"
    )
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--market-id", required=True)
    parser.add_argument("--timeframe", choices=["1m", "5m", "15m", "1h", "1d"], required=True)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    query = CandleQuery(
        market_id=args.market_id,
        timeframe=Timeframe(args.timeframe),
        start=args.start,
        end=args.end,
    )
    engine = build_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            dataset = import_registered(session, args.asset_id, query)
        print(dataset.model_dump_json(exclude={"inputs"}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
