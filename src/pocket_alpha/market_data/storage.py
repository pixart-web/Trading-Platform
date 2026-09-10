from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import TypeDecorator, TypeEngine

from pocket_alpha.common.clock import utc
from pocket_alpha.database import Base
from pocket_alpha.domain.market import Candle, CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.market_data.providers import ProviderMapping


class ExactDecimal(TypeDecorator[Decimal]):
    """PostgreSQL numeric; text in SQLite avoids its floating-point NUMERIC coercion."""

    impl = Numeric(38, 18)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(String(60) if dialect.name == "sqlite" else Numeric(38, 18))

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Decimal | str | None:
        if value is None:
            return None
        return str(value) if dialect.name == "sqlite" else value

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None


class Timestamp(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return utc(value) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else utc(value)


class AssetRecord(Base):
    __tablename__ = "assets"
    asset_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    asset_type: Mapped[str] = mapped_column(String(16))


class VenueRecord(Base):
    __tablename__ = "venues"
    venue_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))


class MarketRecord(Base):
    __tablename__ = "markets"
    market_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.venue_id"))
    symbol: Mapped[str] = mapped_column(String(64))
    quote_currency: Mapped[str] = mapped_column(String(12))


class MappingRecord(Base):
    __tablename__ = "provider_mappings"
    __table_args__ = (UniqueConstraint("source", "instrument_id", name="uq_provider_instrument"),)
    source: Mapped[str] = mapped_column(String(128), primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(256))


class CandleRecord(Base):
    __tablename__ = "candles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source", "market_id"],
            ["provider_mappings.source", "provider_mappings.market_id"],
            name="fk_candle_provider_mapping",
        ),
        CheckConstraint(
            "high >= open AND high >= close AND low <= open AND low <= close", name="ck_candle_ohlc"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("low > 0 AND volume >= 0", name="ck_candle_positive").ddl_if(
            dialect="postgresql"
        ),
        CheckConstraint(
            "close_time > open_time AND received_at >= close_time", name="ck_candle_time"
        ),
    )
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(3), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(Timestamp(), primary_key=True)
    close_time: Mapped[datetime] = mapped_column(Timestamp())
    open: Mapped[Decimal] = mapped_column(ExactDecimal())
    high: Mapped[Decimal] = mapped_column(ExactDecimal())
    low: Mapped[Decimal] = mapped_column(ExactDecimal())
    close: Mapped[Decimal] = mapped_column(ExactDecimal())
    volume: Mapped[Decimal] = mapped_column(ExactDecimal())
    source: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(Timestamp())


class ConflictingCandle(Exception):
    """Existing immutable observation differs; explicit correction workflow required."""


def asset_value(row: AssetRecord) -> Asset:
    return Asset(
        asset_id=row.asset_id,
        symbol=row.symbol,
        name=row.name,
        asset_type=AssetType(row.asset_type),
    )


def market_value(row: MarketRecord) -> Market:
    return Market(
        market_id=row.market_id,
        asset_id=row.asset_id,
        venue_id=row.venue_id,
        symbol=row.symbol,
        quote_currency=row.quote_currency,
    )


def candle_value(row: CandleRecord) -> Candle:
    return Candle(
        market_id=row.market_id,
        timeframe=Timeframe(row.timeframe),
        open_time=row.open_time,
        close_time=row.close_time,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        source=row.source,
        received_at=row.received_at,
    )


class MarketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(
        self, asset: Asset, venue: Venue, market: Market, mapping: ProviderMapping
    ) -> None:
        if market.asset_id != asset.asset_id or market.venue_id != venue.venue_id:
            raise ValueError("market references must match")
        if mapping.market_id != market.market_id:
            raise ValueError("mapping market must match")
        with self.session.begin_nested():
            self._register(AssetRecord, asset.asset_id, asset.model_dump())
            self._register(VenueRecord, venue.venue_id, venue.model_dump())
            self._register(MarketRecord, market.market_id, market.model_dump())
            self._register(MappingRecord, (mapping.source, mapping.market_id), mapping.model_dump())

    def _register(
        self, model: type[Base], key: str | tuple[str, str], values: dict[str, Any]
    ) -> None:
        stored = self.session.get(model, key)
        if stored is None:
            self.session.add(model(**values))
            self.session.flush()
        elif any(getattr(stored, field) != value for field, value in values.items()):
            raise ValueError("metadata conflict; explicit correction required")

    def mapping(self, market_id: str, source: str) -> ProviderMapping:
        row = self.session.get(MappingRecord, (source, market_id))
        if row is None:
            raise LookupError("provider mapping not registered")
        return ProviderMapping(
            source=row.source, market_id=row.market_id, instrument_id=row.instrument_id
        )

    def put(self, candles: tuple[Candle, ...]) -> int:
        inserted = 0
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        with self.session.begin_nested():
            for candle in candles:
                statement = (
                    insert(CandleRecord)
                    .values(**candle.model_dump())
                    .on_conflict_do_nothing(index_elements=["market_id", "timeframe", "open_time"])
                    .returning(CandleRecord.market_id)
                )
                if self.session.execute(statement).scalar_one_or_none() is not None:
                    inserted += 1
                else:
                    stored = self.session.get(
                        CandleRecord,
                        (candle.market_id, candle.timeframe.value, candle.open_time),
                        populate_existing=True,
                    )
                    if stored is None or candle_value(stored).model_dump(
                        exclude={"received_at"}
                    ) != (candle.model_dump(exclude={"received_at"})):
                        raise ConflictingCandle("observation conflicts with persisted candle")
        return inserted

    def candles(self, query: CandleQuery, limit: int = 10000) -> tuple[Candle, ...]:
        if not 1 <= limit <= 10001:
            raise ValueError("bounded query required")
        rows = self.session.scalars(
            select(CandleRecord)
            .where(
                CandleRecord.market_id == query.market_id,
                CandleRecord.timeframe == query.timeframe.value,
                CandleRecord.open_time >= query.start,
                CandleRecord.open_time < query.end,
            )
            .order_by(CandleRecord.open_time)
            .limit(limit)
        )
        return tuple(candle_value(row) for row in rows)
