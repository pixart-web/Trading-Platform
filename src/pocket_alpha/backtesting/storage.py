from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.backtesting.models import BacktestReport
from pocket_alpha.database import Base
from pocket_alpha.market_data.datasets import MarketDataset, MarketDatasetRecord
from pocket_alpha.market_data.quality import DataRejected


class BacktestRecord(Base):
    __tablename__ = "backtest_reports"
    __table_args__ = (Index("ix_backtest_dataset_input", "dataset_id", "input_hash"),)
    run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("market_data_datasets.dataset_id"))
    input_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ConflictingBacktest(Exception):
    pass


class BacktestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: UUID) -> BacktestReport | None:
        row = self.session.get(BacktestRecord, run_id)
        if row is None:
            return None
        report = BacktestReport.model_validate_json(row.payload)
        if (report.run_id, report.input_hash, report.content_hash, report.dataset_id) != (
            row.run_id,
            row.input_hash,
            row.content_hash,
            row.dataset_id,
        ):
            raise ValueError("stored backtest index does not match immutable payload")
        self.check_dataset(report)
        return report

    def put(self, report: BacktestReport) -> BacktestReport:
        report = BacktestReport.model_validate_json(report.model_dump_json())
        self.check_dataset(report, importing=True)
        dialect = self.session.get_bind().dialect.name
        if dialect not in {"sqlite", "postgresql"}:
            raise ValueError("unsupported backtest storage dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        with self.session.begin_nested():
            self.session.execute(
                insert(BacktestRecord)
                .values(
                    run_id=report.run_id,
                    dataset_id=report.dataset_id,
                    input_hash=report.input_hash,
                    content_hash=report.content_hash,
                    payload=report.model_dump_json(),
                )
                .on_conflict_do_nothing(index_elements=["run_id"])
            )
            self.session.flush()
            stored = self.get(report.run_id)
            assert stored is not None
            if stored.content_hash != report.content_hash:
                raise ConflictingBacktest("same backtest inputs produced different results")
            return stored

    def check_dataset(self, report: BacktestReport, importing: bool = False) -> None:
        parent = self.session.get(MarketDatasetRecord, report.dataset_id)
        if parent is None:
            if importing:
                raise LookupError("backtest dataset must be stored first")
            raise ValueError("stored backtest dataset missing")
        try:
            dataset = MarketDataset.model_validate_json(parent.payload)
        except DataRejected as error:
            raise ValueError("stored backtest dataset quality invalid") from error
        if (
            report.dataset_hash,
            report.origin,
            report.market_id,
            report.asset_id,
            report.venue_id,
            report.quote_currency,
        ) != (
            dataset.content_hash,
            dataset.inputs.origin,
            dataset.inputs.market.market_id,
            dataset.inputs.asset.asset_id,
            dataset.inputs.venue.venue_id,
            dataset.inputs.market.quote_currency,
        ):
            raise ValueError("backtest provenance does not match stored dataset")
