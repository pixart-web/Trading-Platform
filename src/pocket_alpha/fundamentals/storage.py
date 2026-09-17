from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.fundamentals.context import FundamentalPrice
from pocket_alpha.fundamentals.models import FundamentalFact, FundamentalMapping
from pocket_alpha.market_data.storage import AssetRecord, CandleRecord, MarketRecord, Timestamp


class FundamentalMappingRecord(Base):
    __tablename__ = "fundamental_mappings"
    __table_args__ = (
        UniqueConstraint("source", "instrument_id", name="uq_fundamental_instrument"),
    )
    source: Mapped[str] = mapped_column(String(128), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(Timestamp())


class FundamentalFactRecord(Base):
    __tablename__ = "fundamental_facts"
    __table_args__ = (
        UniqueConstraint(
            "source", "asset_id", "source_record_id", name="uq_fundamental_source_record"
        ),
        Index("ix_fundamental_asset_availability", "asset_id", "available_at", "ingested_at"),
    )
    fact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"))
    source: Mapped[str] = mapped_column(String(128))
    source_record_id: Mapped[str] = mapped_column(String(256))
    available_at: Mapped[datetime] = mapped_column(Timestamp())
    ingested_at: Mapped[datetime] = mapped_column(Timestamp())
    supersedes_fact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fundamental_facts.fact_id"), nullable=True
    )
    payload: Mapped[str] = mapped_column(Text)


class ConflictingFundamental(Exception):
    """An immutable fundamental identity has different content."""


def series_key(fact: FundamentalFact) -> tuple[str, ...]:
    return (
        fact.source,
        fact.source_concept,
        fact.metric.value,
        fact.unit,
        str(fact.period_start),
        str(fact.period_end),
    )


class FundamentalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_asset(self, asset_id: str) -> None:
        if (
            self.session.scalar(
                select(AssetRecord).where(AssetRecord.asset_id == asset_id).with_for_update()
            )
            is None
        ):
            raise LookupError("fundamental asset is not registered")

    def asset_exists(self, asset_id: str) -> bool:
        return self.session.get(AssetRecord, asset_id) is not None

    def register(self, mapping: FundamentalMapping) -> bool:
        if not self.asset_exists(mapping.asset_id):
            raise LookupError("fundamental asset is not registered")
        asset = self.session.get(AssetRecord, mapping.asset_id)
        if (
            mapping.source == "sec-companyfacts"
            and asset is not None
            and asset.asset_type != "STOCK"
        ):
            raise ValueError("SEC corporate fundamentals require a registered stock")
        existing = self.mapping(mapping.source, mapping.asset_id)
        if existing is not None:
            if existing != mapping:
                raise ConflictingFundamental("fundamental mapping cannot be rewritten")
            return False
        self.session.add(FundamentalMappingRecord(**mapping.model_dump(exclude={"schema_version"})))
        self.session.flush()
        return True

    def mapping(self, source: str, asset_id: str) -> FundamentalMapping | None:
        row = self.session.get(FundamentalMappingRecord, (source, asset_id))
        if row is None:
            return None
        return FundamentalMapping(
            source=row.source,
            asset_id=row.asset_id,
            instrument_id=row.instrument_id,
            created_at=row.created_at,
        )

    def get(self, fact_id: UUID) -> FundamentalFact | None:
        row = self.session.get(FundamentalFactRecord, fact_id)
        return FundamentalFact.model_validate_json(row.payload) if row is not None else None

    def put(self, fact: FundamentalFact) -> bool:
        existing = self.get(fact.fact_id)
        if existing is not None:
            if existing != fact:
                raise ConflictingFundamental("fundamental fact cannot be rewritten")
            return False
        if self.mapping(fact.source, fact.asset_id) is None:
            raise LookupError("fundamental fact requires explicit provider mapping")
        if fact.supersedes_fact_id is not None:
            previous = self.get(fact.supersedes_fact_id)
            if (
                previous is None
                or previous.asset_id != fact.asset_id
                or series_key(previous) != series_key(fact)
                or fact.revision != previous.revision + 1
                or fact.published_at < previous.published_at
            ):
                raise ValueError("fundamental revision does not supersede a coherent prior fact")
        self.session.add(
            FundamentalFactRecord(
                fact_id=fact.fact_id,
                asset_id=fact.asset_id,
                source=fact.source,
                source_record_id=fact.source_record_id,
                available_at=fact.available_at,
                ingested_at=fact.ingested_at,
                supersedes_fact_id=fact.supersedes_fact_id,
                payload=fact.model_dump_json(),
            )
        )
        self.session.flush()
        return True

    def price(
        self,
        asset_id: str,
        market_id: str,
        timeframe: Timeframe,
        as_of: datetime,
    ) -> FundamentalPrice | None:
        market = self.session.get(MarketRecord, market_id)
        if market is None or market.asset_id != asset_id:
            raise LookupError("valuation market does not belong to fundamental asset")
        row = self.session.scalar(
            select(CandleRecord)
            .where(
                CandleRecord.market_id == market_id,
                CandleRecord.timeframe == timeframe.value,
                CandleRecord.close_time <= as_of,
                CandleRecord.received_at <= as_of,
            )
            .order_by(CandleRecord.close_time.desc(), CandleRecord.received_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return FundamentalPrice(
            asset_id=asset_id,
            market_id=market_id,
            currency=market.quote_currency,
            price=row.close,
            timeframe=timeframe,
            close_time=row.close_time,
            received_at=row.received_at,
            source=row.source,
        )

    def available(self, asset_id: str, as_of: datetime) -> tuple[FundamentalFact, ...]:
        rows = self.session.scalars(
            select(FundamentalFactRecord)
            .where(
                FundamentalFactRecord.asset_id == asset_id,
                FundamentalFactRecord.available_at <= as_of,
                FundamentalFactRecord.ingested_at <= as_of,
            )
            .order_by(FundamentalFactRecord.fact_id)
            .limit(10001)
        ).all()
        if len(rows) > 10000:
            raise ValueError("fundamental query exceeds bounded history")
        return tuple(FundamentalFact.model_validate_json(row.payload) for row in rows)
