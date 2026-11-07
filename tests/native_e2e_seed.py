"""Explicitly seed disposable native E2E fixtures; never called by application startup."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.domain.market import Candle, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.main import create_app
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.mobile.models import OperatorRecord
from pocket_alpha.mobile.security import password_hash

PASSWORD = "disposable-android-e2e-password"  # pragma: allowlist secret -- synthetic test identity


def main() -> None:
    settings = Settings()
    url = make_url(settings.database_url.get_secret_value())
    if (
        settings.environment != "test"
        or os.getenv("PA_INTEGRATION") != "1"
        or settings.live_trading_enabled
        or settings.derivative_execution_enabled
        or url.database != "pocket_alpha_native_e2e"
        or url.host not in {"localhost", "127.0.0.1"}
    ):
        raise SystemExit(
            "requires an explicit localhost disposable pocket_alpha_native_e2e database"
        )
    create_app(
        settings
    )  # Register the same mapped models as the real backend, without startup I/O.
    command.upgrade(Config("alembic.ini"), "head")
    engine = build_engine(settings)
    try:
        with Session(engine) as db, db.begin():
            owner = db.scalar(select(OperatorRecord).limit(1))
            if owner is not None and owner.username != "android-e2e":
                raise SystemExit("refusing to replace a provisioned operator")
            if owner is None:
                db.add(
                    OperatorRecord(
                        user_id=uuid4(),
                        workspace="operator",
                        username="android-e2e",
                        password_hash=password_hash(PASSWORD),
                        disabled=False,
                    )
                )
            repository = MarketRepository(db)
            repository.register(
                Asset(
                    asset_id="android-e2e",
                    symbol="SYNTHETIC-E2E",
                    name="Synthetic Android E2E fixture",
                    asset_type=AssetType.CRYPTO,
                ),
                Venue(venue_id="synthetic-e2e", name="Synthetic E2E venue"),
                Market(
                    market_id="android-e2e",
                    asset_id="android-e2e",
                    venue_id="synthetic-e2e",
                    symbol="SYNTHETIC-E2E",
                    quote_currency="USD",
                ),
                ProviderMapping(
                    source="synthetic-e2e", market_id="android-e2e", instrument_id="synthetic-e2e"
                ),
            )
            end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            candles = []
            for index in range(501):
                start = end - timedelta(hours=501 - index)
                hour = int(start.timestamp()) // 3600
                opened = Decimal(100) + Decimal(hour % 20) / 2
                closed = opened + (Decimal("1") if hour % 3 else Decimal("-0.5"))
                candles.append(
                    Candle(
                        market_id="android-e2e",
                        timeframe=Timeframe.H1,
                        open_time=start,
                        close_time=start + timedelta(hours=1),
                        open=opened,
                        high=max(opened, closed) + 1,
                        low=min(opened, closed) - 1,
                        close=closed,
                        volume=Decimal(200 + hour % 100),
                        source="synthetic-e2e",
                        received_at=start + timedelta(hours=1),
                    )
                )
            repository.put(tuple(candles))
    finally:
        engine.dispose()
    print("Disposable SYNTHETIC-E2E market and operator seeded; no real trading capability.")


if __name__ == "__main__":
    main()
