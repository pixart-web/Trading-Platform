from alembic import context

from pocket_alpha.analysis.storage import AnalyzeReportRecord
from pocket_alpha.audit.models import AuditRecord
from pocket_alpha.config import Settings
from pocket_alpha.database import Base, build_engine
from pocket_alpha.derivatives.storage import DerivativeContractRecord, DerivativeObservationRecord
from pocket_alpha.forecasts.storage import ForecastOutcomeRecord, ForecastRecord
from pocket_alpha.fundamentals.storage import FundamentalFactRecord, FundamentalMappingRecord
from pocket_alpha.market_data.storage import CandleRecord
from pocket_alpha.portfolio.storage import PortfolioEntryRecord, PortfolioRecord
from pocket_alpha.portfolio_intelligence.storage import PortfolioIntelligenceRecord
from pocket_alpha.scanner.storage import ScanReportRecord
from pocket_alpha.watchlists.storage import (
    AlertEventRecord,
    WatchlistMemberRecord,
    WatchlistRecord,
    WatchlistSnapshotItemRecord,
    WatchlistSnapshotRecord,
)

target_metadata = Base.metadata
assert DerivativeContractRecord.__tablename__ in target_metadata.tables
assert DerivativeObservationRecord.__tablename__ in target_metadata.tables
assert FundamentalFactRecord.__tablename__ in target_metadata.tables
assert FundamentalMappingRecord.__tablename__ in target_metadata.tables
assert AuditRecord.__tablename__ in target_metadata.tables
assert AnalyzeReportRecord.__tablename__ in target_metadata.tables
assert CandleRecord.__tablename__ in target_metadata.tables
assert ForecastRecord.__tablename__ in target_metadata.tables
assert ForecastOutcomeRecord.__tablename__ in target_metadata.tables
assert ScanReportRecord.__tablename__ in target_metadata.tables
assert PortfolioRecord.__tablename__ in target_metadata.tables
assert PortfolioEntryRecord.__tablename__ in target_metadata.tables
assert PortfolioIntelligenceRecord.__tablename__ in target_metadata.tables
assert WatchlistRecord.__tablename__ in target_metadata.tables
assert WatchlistMemberRecord.__tablename__ in target_metadata.tables
assert WatchlistSnapshotRecord.__tablename__ in target_metadata.tables
assert WatchlistSnapshotItemRecord.__tablename__ in target_metadata.tables
assert AlertEventRecord.__tablename__ in target_metadata.tables

if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(Settings())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
