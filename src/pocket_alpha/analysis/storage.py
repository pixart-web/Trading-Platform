import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.analysis.models import AnalyzeReport
from pocket_alpha.database import Base
from pocket_alpha.market_data.storage import Timestamp


class AnalyzeReportRecord(Base):
    __tablename__ = "analyze_reports"
    __table_args__ = (
        Index(
            "ix_analyze_reports_market_timeframe_as_of",
            "market_id",
            "candle_timeframe",
            "as_of",
        ),
    )
    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"))
    candle_timeframe: Mapped[str] = mapped_column(String(3))
    as_of: Mapped[datetime] = mapped_column(Timestamp())
    generated_at: Mapped[datetime] = mapped_column(Timestamp())
    status: Mapped[str] = mapped_column(String(16))
    report_version: Mapped[str] = mapped_column(String(128))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ConflictingAnalyzeReport(Exception):
    """An immutable Analyze report identity already has different content."""


def _payload(report: AnalyzeReport) -> str:
    return json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class AnalyzeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _insert(self, values: dict[str, Any]) -> bool:
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        return (
            self.session.execute(
                insert(AnalyzeReportRecord)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(AnalyzeReportRecord.report_id)
            ).scalar_one_or_none()
            is not None
        )

    def put(self, report: AnalyzeReport) -> bool:
        payload = _payload(report)
        values = {
            "report_id": report.report_id,
            "market_id": report.market_id,
            "asset_id": report.asset_id,
            "candle_timeframe": report.candle_timeframe.value,
            "as_of": report.as_of,
            "generated_at": report.generated_at,
            "status": report.status.value,
            "report_version": report.report_version,
            "input_hash": report.input_hash,
            "payload": payload,
        }
        with self.session.begin_nested():
            if self._insert(values):
                return True
            row = self.session.get(AnalyzeReportRecord, report.report_id, populate_existing=True)
            if row is None or row.payload != payload:
                raise ConflictingAnalyzeReport(
                    "Analyze report identity conflicts with persisted content"
                )
        return False

    def report(self, report_id: UUID) -> AnalyzeReport:
        row = self.session.get(AnalyzeReportRecord, report_id)
        if row is None:
            raise LookupError("Analyze report not found")
        return AnalyzeReport.model_validate_json(row.payload)

    def at(self, market_id: str, candle_timeframe: str, as_of: datetime) -> AnalyzeReport | None:
        row = self.session.scalar(
            select(AnalyzeReportRecord)
            .where(
                AnalyzeReportRecord.market_id == market_id,
                AnalyzeReportRecord.candle_timeframe == candle_timeframe,
                AnalyzeReportRecord.as_of == as_of,
            )
            .order_by(
                AnalyzeReportRecord.generated_at.desc(),
                AnalyzeReportRecord.report_id.desc(),
            )
            .limit(1)
        )
        return AnalyzeReport.model_validate_json(row.payload) if row is not None else None
