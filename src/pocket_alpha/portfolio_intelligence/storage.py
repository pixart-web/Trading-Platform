import json
from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ForeignKey, Index, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.market_data.storage import CandleRecord, MarketRecord, Timestamp
from pocket_alpha.portfolio_intelligence.models import PortfolioIntelligenceReport


class PortfolioIntelligenceRecord(Base):
    __tablename__ = "portfolio_intelligence_reports"
    __table_args__ = (
        Index(
            "ix_portfolio_intelligence_portfolio_as_of",
            "portfolio_id",
            "as_of",
        ),
    )
    analysis_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(ForeignKey("portfolios.portfolio_id"), index=True)
    as_of: Mapped[datetime] = mapped_column(Timestamp())
    generated_at: Mapped[datetime] = mapped_column(Timestamp())
    policy_version: Mapped[str] = mapped_column(String(128))
    policy_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ClosePoint(NamedTuple):
    close_time: datetime
    received_at: datetime
    close: Decimal


class ConflictingPortfolioIntelligence(Exception):
    """An immutable portfolio-intelligence identity has different content."""


def _json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PortfolioIntelligenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def closes(
        self,
        market_ids: tuple[str, ...],
        timeframe: Timeframe,
        as_of: datetime,
        limit: int,
    ) -> dict[str, tuple[ClosePoint, ...]]:
        if not 2 <= limit <= 501:
            raise ValueError("portfolio intelligence candle query must be bounded")
        result: dict[str, tuple[ClosePoint, ...]] = {}
        for market_id in market_ids:
            rows = tuple(
                self.session.scalars(
                    select(CandleRecord)
                    .where(
                        CandleRecord.market_id == market_id,
                        CandleRecord.timeframe == timeframe.value,
                        CandleRecord.close_time <= as_of,
                        CandleRecord.received_at <= as_of,
                    )
                    .order_by(CandleRecord.close_time.desc(), CandleRecord.received_at.desc())
                    .limit(limit)
                )
            )
            result[market_id] = tuple(
                ClosePoint(row.close_time, row.received_at, row.close) for row in reversed(rows)
            )
        return result

    def market_exists(self, market_id: str) -> bool:
        return self.session.get(MarketRecord, market_id) is not None

    def put(self, report: PortfolioIntelligenceReport) -> bool:
        payload = _json(report)
        values: dict[str, Any] = {
            "analysis_id": report.analysis_id,
            "portfolio_id": report.portfolio_id,
            "as_of": report.as_of,
            "generated_at": report.generated_at,
            "policy_version": report.policy.policy_version,
            "policy_hash": report.policy_hash,
            "input_hash": report.input_hash,
            "payload": payload,
        }
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        with self.session.begin_nested():
            inserted = self.session.scalar(
                insert(PortfolioIntelligenceRecord)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(PortfolioIntelligenceRecord.analysis_id)
            )
            if inserted is not None:
                return True
            row = self.session.get(
                PortfolioIntelligenceRecord, report.analysis_id, populate_existing=True
            )
            if row is None or row.payload != payload:
                raise ConflictingPortfolioIntelligence(
                    "portfolio intelligence identity conflicts with persisted content"
                )
        return False

    def find(self, analysis_id: UUID) -> PortfolioIntelligenceReport | None:
        row = self.session.get(PortfolioIntelligenceRecord, analysis_id)
        return PortfolioIntelligenceReport.model_validate_json(row.payload) if row else None

    def get(self, analysis_id: UUID) -> PortfolioIntelligenceReport:
        report = self.find(analysis_id)
        if report is None:
            raise LookupError("portfolio intelligence report not found")
        return report

    def recent(
        self, portfolio_id: UUID, limit: int = 20
    ) -> tuple[PortfolioIntelligenceReport, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("bounded portfolio intelligence query required")
        rows = self.session.scalars(
            select(PortfolioIntelligenceRecord)
            .where(PortfolioIntelligenceRecord.portfolio_id == portfolio_id)
            .order_by(
                PortfolioIntelligenceRecord.generated_at.desc(),
                PortfolioIntelligenceRecord.analysis_id.desc(),
            )
            .limit(limit)
        )
        return tuple(PortfolioIntelligenceReport.model_validate_json(row.payload) for row in rows)
