"""Explicit operator-triggered SEC import; never runs at application startup."""

import argparse
import os

from sqlalchemy.orm import Session

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.fundamentals.models import FundamentalMapping
from pocket_alpha.fundamentals.providers import SecCompanyFactsProvider
from pocket_alpha.fundamentals.service import FundamentalService
from pocket_alpha.fundamentals.storage import ConflictingFundamental, FundamentalRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import read-only SEC fundamentals for a registered stock"
    )
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--cik", required=True)
    args = parser.parse_args()
    provider = SecCompanyFactsProvider(os.environ.get("PA_SEC_USER_AGENT", ""))
    clock = SystemClock()
    engine = build_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            repository = FundamentalRepository(session)
            mapping = repository.mapping(provider.source, args.asset_id)
            if mapping is not None and mapping.instrument_id != args.cik:
                raise ConflictingFundamental("registered SEC mapping differs from requested CIK")
            if mapping is None:
                repository.register(
                    FundamentalMapping(
                        source=provider.source,
                        asset_id=args.asset_id,
                        instrument_id=args.cik,
                        created_at=clock.now(),
                    )
                )
            inserted = FundamentalService(repository, clock).ingest(provider, args.asset_id)
        print(f"Imported {inserted} immutable fundamental facts")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
