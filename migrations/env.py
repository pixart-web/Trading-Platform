from alembic import context

from pocket_alpha.audit.models import AuditRecord
from pocket_alpha.config import Settings
from pocket_alpha.database import Base, build_engine
from pocket_alpha.market_data.storage import CandleRecord

target_metadata = Base.metadata
assert AuditRecord.__tablename__ in target_metadata.tables
assert CandleRecord.__tablename__ in target_metadata.tables

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
