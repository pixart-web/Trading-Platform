from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.derivatives.models import (
    DerivativeContract,
    DerivativeObservation,
    validate_contract_sample,
)
from pocket_alpha.market_data.storage import AssetRecord, MarketRecord, Timestamp, VenueRecord


class DerivativeContractRecord(Base):
    __tablename__ = "derivative_contracts"
    __table_args__ = (
        UniqueConstraint("source", "external_contract_id", name="uq_derivative_external_contract"),
        Index("ix_derivative_underlying_venue", "underlying_asset_id", "venue_id"),
    )
    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    underlying_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"))
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.venue_id"))
    source: Mapped[str] = mapped_column(String(128))
    external_contract_id: Mapped[str] = mapped_column(String(256))
    available_at: Mapped[datetime] = mapped_column(Timestamp())
    ingested_at: Mapped[datetime] = mapped_column(Timestamp())
    payload: Mapped[str] = mapped_column(Text)


class DerivativeObservationRecord(Base):
    __tablename__ = "derivative_observations"
    __table_args__ = (
        UniqueConstraint("contract_id", "source_record_id", name="uq_derivative_source_record"),
        UniqueConstraint("contract_id", "observed_at", "revision", name="uq_derivative_revision"),
        Index(
            "ix_derivative_observation_cutoff",
            "contract_id",
            "observed_at",
            "available_at",
            "ingested_at",
        ),
    )
    observation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("derivative_contracts.contract_id"))
    source_record_id: Mapped[str] = mapped_column(String(256))
    revision: Mapped[int]
    observed_at: Mapped[datetime] = mapped_column(Timestamp())
    published_at: Mapped[datetime] = mapped_column(Timestamp())
    available_at: Mapped[datetime] = mapped_column(Timestamp())
    ingested_at: Mapped[datetime] = mapped_column(Timestamp())
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("derivative_observations.observation_id"),
        nullable=True,
    )
    payload: Mapped[str] = mapped_column(Text)


class ConflictingDerivative(Exception):
    """Immutable derivative metadata or observation identity conflicts."""


class DerivativeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(self, contract: DerivativeContract) -> bool:
        existing = self.get_contract(contract.contract_id)
        if existing is not None:
            if existing != contract:
                raise ConflictingDerivative("derivative metadata cannot be rewritten")
            return False
        if self.session.get(AssetRecord, contract.underlying_asset_id) is None:
            raise LookupError("derivative underlying asset is not registered")
        if self.session.get(VenueRecord, contract.venue_id) is None:
            raise LookupError("derivative venue is not registered")
        if (
            self.session.get(AssetRecord, contract.contract_id) is not None
            or self.session.get(MarketRecord, contract.contract_id) is not None
        ):
            raise ConflictingDerivative("derivative identity collides with asset or market")
        self.session.add(
            DerivativeContractRecord(
                contract_id=contract.contract_id,
                underlying_asset_id=contract.underlying_asset_id,
                venue_id=contract.venue_id,
                source=contract.source,
                external_contract_id=contract.external_contract_id,
                available_at=contract.available_at,
                ingested_at=contract.ingested_at,
                payload=contract.model_dump_json(),
            )
        )
        self.session.flush()
        return True

    def get_contract(self, contract_id: str, lock: bool = False) -> DerivativeContract | None:
        statement = select(DerivativeContractRecord).where(
            DerivativeContractRecord.contract_id == contract_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return DerivativeContract.model_validate_json(row.payload) if row is not None else None

    def get(self, observation_id: UUID) -> DerivativeObservation | None:
        row = self.session.get(DerivativeObservationRecord, observation_id)
        return DerivativeObservation.model_validate_json(row.payload) if row is not None else None

    def put(self, observation: DerivativeObservation) -> bool:
        previous = self.get(observation.observation_id)
        if previous is not None:
            if previous != observation:
                raise ConflictingDerivative("derivative observation cannot be rewritten")
            return False
        contract = self.get_contract(observation.contract_id)
        if contract is None:
            raise LookupError("derivative contract is not registered")
        if (
            observation.source != contract.source
            or observation.external_contract_id != contract.external_contract_id
            or observation.ingested_at < contract.ingested_at
            or observation.available_at < contract.available_at
        ):
            raise ValueError("derivative observation provenance does not match contract")
        if observation.supersedes_observation_id is not None:
            parent = self.get(observation.supersedes_observation_id)
            if (
                parent is None
                or parent.contract_id != observation.contract_id
                or parent.observed_at != observation.observed_at
                or parent.revision + 1 != observation.revision
                or parent.published_at > observation.published_at
                or parent.available_at > observation.available_at
                or parent.ingested_at > observation.ingested_at
            ):
                raise ValueError("derivative revision does not supersede a coherent observation")
        validate_contract_sample(contract, observation)
        self.session.add(
            DerivativeObservationRecord(
                observation_id=observation.observation_id,
                contract_id=observation.contract_id,
                source_record_id=observation.source_record_id,
                revision=observation.revision,
                observed_at=observation.observed_at,
                published_at=observation.published_at,
                available_at=observation.available_at,
                ingested_at=observation.ingested_at,
                supersedes_observation_id=observation.supersedes_observation_id,
                payload=observation.model_dump_json(),
            )
        )
        self.session.flush()
        return True

    def history(self, contract_id: str, as_of: datetime) -> tuple[DerivativeObservation, ...]:
        rows = self.session.scalars(
            select(DerivativeObservationRecord)
            .where(
                DerivativeObservationRecord.contract_id == contract_id,
                DerivativeObservationRecord.published_at <= as_of,
                DerivativeObservationRecord.available_at <= as_of,
                DerivativeObservationRecord.ingested_at <= as_of,
            )
            .order_by(
                DerivativeObservationRecord.observed_at,
                DerivativeObservationRecord.revision,
            )
            .limit(10001)
        ).all()
        if len(rows) > 10000:
            raise ValueError("derivative import history exceeds bounded limit")
        return tuple(DerivativeObservation.model_validate_json(row.payload) for row in rows)

    def latest(self, contract_id: str, as_of: datetime) -> DerivativeObservation | None:
        row = self.session.scalar(
            select(DerivativeObservationRecord)
            .where(
                DerivativeObservationRecord.contract_id == contract_id,
                DerivativeObservationRecord.observed_at <= as_of,
                DerivativeObservationRecord.published_at <= as_of,
                DerivativeObservationRecord.available_at <= as_of,
                DerivativeObservationRecord.ingested_at <= as_of,
            )
            .order_by(
                DerivativeObservationRecord.observed_at.desc(),
                DerivativeObservationRecord.revision.desc(),
            )
            .limit(1)
        )
        return DerivativeObservation.model_validate_json(row.payload) if row is not None else None

    def contracts(
        self,
        underlying_asset_id: str,
        venue_id: str,
        as_of: datetime,
    ) -> tuple[DerivativeContract, ...]:
        if self.session.get(AssetRecord, underlying_asset_id) is None:
            raise LookupError("derivative underlying asset is not registered")
        if self.session.get(VenueRecord, venue_id) is None:
            raise LookupError("derivative venue is not registered")
        rows = self.session.scalars(
            select(DerivativeContractRecord)
            .where(
                DerivativeContractRecord.underlying_asset_id == underlying_asset_id,
                DerivativeContractRecord.venue_id == venue_id,
                DerivativeContractRecord.available_at <= as_of,
                DerivativeContractRecord.ingested_at <= as_of,
            )
            .order_by(DerivativeContractRecord.contract_id)
            .limit(1001)
        ).all()
        if len(rows) > 1000:
            raise ValueError("derivative contract query exceeds bounded limit")
        return tuple(DerivativeContract.model_validate_json(row.payload) for row in rows)
