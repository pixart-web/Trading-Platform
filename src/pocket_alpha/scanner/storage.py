import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Index, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.analysis.models import AnalyzeReport
from pocket_alpha.analysis.storage import AnalyzeReportRecord
from pocket_alpha.database import Base
from pocket_alpha.domain.models import AssetType
from pocket_alpha.market_data.storage import AssetRecord, MarketRecord, Timestamp
from pocket_alpha.scanner.models import ScanFilters, ScanMarket, ScanReport


class ScanReportRecord(Base):
    __tablename__ = "scan_reports"
    __table_args__ = (
        Index(
            "ix_scan_reports_timeframe_horizon_as_of",
            "candle_timeframe",
            "horizon",
            "as_of",
        ),
    )
    scan_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    candle_timeframe: Mapped[str] = mapped_column(String(3))
    horizon: Mapped[str] = mapped_column(String(3))
    as_of: Mapped[datetime] = mapped_column(Timestamp())
    generated_at: Mapped[datetime] = mapped_column(Timestamp())
    status: Mapped[str] = mapped_column(String(16))
    scanner_version: Mapped[str] = mapped_column(String(128))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ConflictingScanReport(Exception):
    """An immutable scan identity already has different content."""


def _json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class ScannerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def universe(self, filters: ScanFilters) -> tuple[ScanMarket, ...]:
        statement = select(MarketRecord, AssetRecord).join(
            AssetRecord, MarketRecord.asset_id == AssetRecord.asset_id
        )
        if filters.asset_types:
            statement = statement.where(
                AssetRecord.asset_type.in_(tuple(item.value for item in filters.asset_types))
            )
        if filters.venue_ids:
            statement = statement.where(MarketRecord.venue_id.in_(filters.venue_ids))
        if filters.quote_currencies:
            statement = statement.where(MarketRecord.quote_currency.in_(filters.quote_currencies))
        if filters.market_ids:
            statement = statement.where(MarketRecord.market_id.in_(filters.market_ids))
        rows = self.session.execute(statement.order_by(MarketRecord.market_id).limit(1001)).all()
        if len(rows) > 1000:
            raise ValueError("scanner universe exceeds 1000 markets; narrow the filters")
        return tuple(
            ScanMarket(
                market_id=market.market_id,
                asset_id=market.asset_id,
                symbol=market.symbol,
                name=asset.name,
                asset_type=AssetType(asset.asset_type),
                venue_id=market.venue_id,
                quote_currency=market.quote_currency,
            )
            for market, asset in rows
        )

    def reports(
        self, market_ids: tuple[str, ...], candle_timeframe: str, as_of: datetime
    ) -> dict[str, AnalyzeReport]:
        if not market_ids:
            return {}
        rows = self.session.scalars(
            select(AnalyzeReportRecord)
            .where(
                AnalyzeReportRecord.market_id.in_(market_ids),
                AnalyzeReportRecord.candle_timeframe == candle_timeframe,
                AnalyzeReportRecord.as_of == as_of,
            )
            .order_by(
                AnalyzeReportRecord.market_id,
                AnalyzeReportRecord.generated_at.desc(),
                AnalyzeReportRecord.report_id.desc(),
            )
        )
        reports: dict[str, AnalyzeReport] = {}
        for row in rows:
            reports.setdefault(row.market_id, AnalyzeReport.model_validate_json(row.payload))
        return reports

    def put(self, report: ScanReport) -> bool:
        payload = _json(report)
        values = {
            "scan_id": report.scan_id,
            "candle_timeframe": report.candle_timeframe.value,
            "horizon": report.horizon.value,
            "as_of": report.as_of,
            "generated_at": report.generated_at,
            "status": report.status.value,
            "scanner_version": report.scanner_version,
            "input_hash": report.input_hash,
            "payload": payload,
        }
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        with self.session.begin_nested():
            inserted = self.session.scalar(
                insert(ScanReportRecord)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(ScanReportRecord.scan_id)
            )
            if inserted is not None:
                return True
            row = self.session.get(ScanReportRecord, report.scan_id, populate_existing=True)
            if row is None or row.payload != payload:
                raise ConflictingScanReport("scan identity conflicts with persisted content")
        return False

    def find(self, scan_id: UUID) -> ScanReport | None:
        row = self.session.get(ScanReportRecord, scan_id)
        return ScanReport.model_validate_json(row.payload) if row else None

    def get(self, scan_id: UUID) -> ScanReport:
        report = self.find(scan_id)
        if report is None:
            raise LookupError("scan not found")
        return report

    def recent(self, limit: int = 20) -> tuple[ScanReport, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("bounded scan query required")
        rows = self.session.scalars(
            select(ScanReportRecord)
            .order_by(ScanReportRecord.generated_at.desc(), ScanReportRecord.scan_id.desc())
            .limit(limit)
        )
        return tuple(ScanReport.model_validate_json(row.payload) for row in rows)
