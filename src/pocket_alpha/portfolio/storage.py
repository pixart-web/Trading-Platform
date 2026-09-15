import json
from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.domain.models import AssetType, Timeframe
from pocket_alpha.market_data.storage import (
    AssetRecord,
    CandleRecord,
    ExactDecimal,
    MarketRecord,
    Timestamp,
)
from pocket_alpha.portfolio.models import (
    Portfolio,
    PortfolioEntry,
    PortfolioMarket,
)


class PortfolioRecord(Base):
    __tablename__ = "portfolios"
    portfolio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    base_currency: Mapped[str] = mapped_column(String(12))
    accounting_method: Mapped[str] = mapped_column(String(32))
    valuation_timeframe: Mapped[str] = mapped_column(String(3))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(Timestamp())
    updated_at: Mapped[datetime] = mapped_column(Timestamp())


class PortfolioEntryRecord(Base):
    __tablename__ = "portfolio_entries"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "sequence", name="uq_portfolio_entry_sequence"),
        Index("ix_portfolio_entries_portfolio_occurred", "portfolio_id", "occurred_at"),
    )
    entry_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(12))
    cash_amount: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    market_id: Mapped[str | None] = mapped_column(ForeignKey("markets.market_id"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.asset_id"), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    fee: Mapped[Decimal] = mapped_column(ExactDecimal())
    gross_value: Mapped[Decimal] = mapped_column(ExactDecimal())
    cash_effect: Mapped[Decimal] = mapped_column(ExactDecimal())
    occurred_at: Mapped[datetime] = mapped_column(Timestamp())
    recorded_at: Mapped[datetime] = mapped_column(Timestamp())
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)
    payload: Mapped[str] = mapped_column(Text)


class PortfolioPrice(NamedTuple):
    close: Decimal
    close_time: datetime
    received_at: datetime


class ConflictingPortfolio(Exception):
    """A portfolio or entry identity conflicts with persisted content."""


class StalePortfolioRevision(Exception):
    """The caller used a revision that is no longer current."""


def _json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _entry_value(row: PortfolioEntryRecord) -> PortfolioEntry:
    return PortfolioEntry.model_validate_json(row.payload)


class PortfolioRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _insert(self, model: type[Base], values: dict[str, Any]) -> bool:
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        return (
            self.session.execute(
                insert(model)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(*model.__table__.primary_key)
            ).first()
            is not None
        )

    def create(
        self,
        portfolio_id: UUID,
        name: str,
        base_currency: str,
        created_at: datetime,
        valuation_timeframe: str = "1h",
    ) -> Portfolio:
        normalized_name = name.strip()
        normalized_currency = base_currency.strip().upper()
        values = {
            "portfolio_id": portfolio_id,
            "name": normalized_name,
            "base_currency": normalized_currency,
            "accounting_method": "MOVING_AVERAGE_V1",
            "valuation_timeframe": Timeframe(valuation_timeframe).value,
            "revision": 1,
            "created_at": created_at,
            "updated_at": created_at,
        }
        candidate = Portfolio(
            portfolio_id=portfolio_id,
            name=normalized_name,
            base_currency=normalized_currency,
            valuation_timeframe=Timeframe(valuation_timeframe),
            revision=1,
            created_at=created_at,
            updated_at=created_at,
        )
        with self.session.begin_nested():
            if not self._insert(PortfolioRecord, values):
                row = self.session.get(PortfolioRecord, portfolio_id, populate_existing=True)
                if row is None or (
                    row.name,
                    row.base_currency,
                    row.accounting_method,
                    row.valuation_timeframe,
                ) != (
                    candidate.name,
                    candidate.base_currency,
                    candidate.accounting_method,
                    candidate.valuation_timeframe.value,
                ):
                    raise ConflictingPortfolio(
                        "portfolio identity conflicts with persisted content"
                    )
        return self.get(portfolio_id)

    def list(self, limit: int = 100) -> tuple[Portfolio, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("bounded portfolio query required")
        rows = self.session.scalars(
            select(PortfolioRecord)
            .order_by(PortfolioRecord.created_at, PortfolioRecord.portfolio_id)
            .limit(limit)
        )
        return tuple(self._value(row) for row in rows)

    def get(self, portfolio_id: UUID) -> Portfolio:
        row = self.session.get(PortfolioRecord, portfolio_id)
        if row is None:
            raise LookupError("portfolio not found")
        return self._value(row)

    @staticmethod
    def _value(row: PortfolioRecord) -> Portfolio:
        return Portfolio(
            portfolio_id=row.portfolio_id,
            name=row.name,
            base_currency=row.base_currency,
            accounting_method="MOVING_AVERAGE_V1",
            valuation_timeframe=Timeframe(row.valuation_timeframe),
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def find_entry(self, entry_id: UUID) -> PortfolioEntry | None:
        row = self.session.get(PortfolioEntryRecord, entry_id)
        return _entry_value(row) if row is not None else None

    def entries(
        self, portfolio_id: UUID, limit: int = 500, offset: int = 0
    ) -> tuple[PortfolioEntry, ...]:
        self.get(portfolio_id)
        if not 1 <= limit <= 500 or not 0 <= offset <= 10000:
            raise ValueError("bounded portfolio entry query required")
        rows = self.session.scalars(
            select(PortfolioEntryRecord)
            .where(PortfolioEntryRecord.portfolio_id == portfolio_id)
            .order_by(PortfolioEntryRecord.sequence)
            .offset(offset)
            .limit(limit)
        )
        return tuple(_entry_value(row) for row in rows)

    def accounting_entries(
        self, portfolio_id: UUID, as_of: datetime | None = None
    ) -> tuple[PortfolioEntry, ...]:
        self.get(portfolio_id)
        statement = select(PortfolioEntryRecord).where(
            PortfolioEntryRecord.portfolio_id == portfolio_id
        )
        if as_of is not None:
            statement = statement.where(
                PortfolioEntryRecord.occurred_at <= as_of,
                PortfolioEntryRecord.recorded_at <= as_of,
            )
        rows = tuple(
            self.session.scalars(statement.order_by(PortfolioEntryRecord.sequence).limit(10001))
        )
        if len(rows) > 10000:
            raise ValueError("portfolio ledger exceeds 10000 entries")
        return tuple(_entry_value(row) for row in rows)

    def append(self, entry: PortfolioEntry, expected_revision: int) -> bool:
        payload = _json(entry)
        existing = self.session.get(PortfolioEntryRecord, entry.entry_id)
        if existing is not None:
            if existing.payload != payload:
                raise ConflictingPortfolio(
                    "portfolio entry identity conflicts with persisted content"
                )
            return False
        values = {
            **entry.model_dump(exclude={"schema_version"}),
            "entry_type": entry.entry_type.value,
            "payload": payload,
        }
        with self.session.begin_nested():
            changed = self.session.scalar(
                update(PortfolioRecord)
                .where(
                    PortfolioRecord.portfolio_id == entry.portfolio_id,
                    PortfolioRecord.revision == expected_revision,
                )
                .values(revision=expected_revision + 1, updated_at=entry.recorded_at)
                .returning(PortfolioRecord.portfolio_id)
            )
            if changed is None:
                if self.session.get(PortfolioRecord, entry.portfolio_id) is None:
                    raise LookupError("portfolio not found")
                raise StalePortfolioRevision("portfolio revision is stale")
            if not self._insert(PortfolioEntryRecord, values):
                raise ConflictingPortfolio("portfolio entry identity already exists")
        return True

    def market(self, market_id: str) -> PortfolioMarket:
        row = self.session.execute(
            select(MarketRecord, AssetRecord)
            .join(AssetRecord, MarketRecord.asset_id == AssetRecord.asset_id)
            .where(MarketRecord.market_id == market_id)
        ).one_or_none()
        if row is None:
            raise LookupError("market not found")
        market, asset = row
        return PortfolioMarket(
            market_id=market.market_id,
            asset_id=market.asset_id,
            symbol=market.symbol,
            name=asset.name,
            asset_type=AssetType(asset.asset_type),
            venue_id=market.venue_id,
            quote_currency=market.quote_currency,
        )

    def latest_prices(
        self, market_ids: tuple[str, ...], as_of: datetime, timeframe: Timeframe
    ) -> dict[str, PortfolioPrice]:
        result: dict[str, PortfolioPrice] = {}
        for market_id in market_ids:
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
            if row is not None:
                result[market_id] = PortfolioPrice(row.close, row.close_time, row.received_at)
        return result
