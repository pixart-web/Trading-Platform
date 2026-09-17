from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.contextual.models import ContextEntity, ContextMapping, ContextObservation
from pocket_alpha.database import Base
from pocket_alpha.market_data.storage import AssetRecord, Timestamp


class ContextEntityRecord(Base):
    __tablename__ = "context_entities"
    entity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.asset_id"), nullable=True)
    payload: Mapped[str] = mapped_column(Text)


class ContextMappingRecord(Base):
    __tablename__ = "context_mappings"
    __table_args__ = (
        UniqueConstraint("source", "external_entity_id", name="uq_context_external_entity"),
    )
    source: Mapped[str] = mapped_column(String(128), primary_key=True)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("context_entities.entity_id"), primary_key=True
    )
    external_entity_id: Mapped[str] = mapped_column(String(256))


class ContextObservationRecord(Base):
    __tablename__ = "context_observations"
    __table_args__ = (
        UniqueConstraint(
            "source", "entity_id", "source_record_id", name="uq_context_source_record"
        ),
        UniqueConstraint(
            "source", "entity_id", "event_key", "revision", name="uq_context_revision"
        ),
        ForeignKeyConstraint(
            ["source", "entity_id"],
            ["context_mappings.source", "context_mappings.entity_id"],
            name="fk_context_provider_mapping",
        ),
        CheckConstraint(
            "published_at <= available_at AND available_at <= ingested_at", name="ck_context_time"
        ),
        CheckConstraint(
            "revision >= 1 AND ((revision = 1 AND supersedes_observation_id IS NULL) "
            "OR (revision > 1 AND supersedes_observation_id IS NOT NULL))",
            name="ck_context_revision",
        ),
        Index("ix_context_cutoff", "entity_id", "available_at", "ingested_at"),
    )
    observation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("context_entities.entity_id"))
    source: Mapped[str] = mapped_column(String(128))
    source_record_id: Mapped[str] = mapped_column(String(256))
    event_key: Mapped[str] = mapped_column(String(256))
    revision: Mapped[int]
    published_at: Mapped[datetime] = mapped_column(Timestamp())
    available_at: Mapped[datetime] = mapped_column(Timestamp())
    ingested_at: Mapped[datetime] = mapped_column(Timestamp())
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_observations.observation_id"),
        nullable=True,
    )
    payload: Mapped[str] = mapped_column(Text)


class ConflictingContext(Exception):
    pass


class ContextRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(self, entity: ContextEntity, mapping: ContextMapping) -> None:
        with self.session.begin_nested():
            self._register(entity, mapping)

    def _register(self, entity: ContextEntity, mapping: ContextMapping) -> None:
        if mapping.entity_id != entity.entity_id:
            raise ValueError("context mapping must link the registered entity")
        if entity.asset_id is not None and self.session.get(AssetRecord, entity.asset_id) is None:
            raise LookupError("context asset is not registered")
        previous = self.entity(entity.entity_id)
        if previous is not None and previous != entity:
            raise ConflictingContext("context entity cannot be rewritten")
        if previous is None:
            self.session.add(
                ContextEntityRecord(
                    entity_id=entity.entity_id,
                    asset_id=entity.asset_id,
                    payload=entity.model_dump_json(),
                )
            )
            self.session.flush()
        existing = self.mapping(mapping.source, mapping.entity_id)
        if existing is not None and existing != mapping:
            raise ConflictingContext("context mapping cannot be rewritten")
        if existing is None:
            self.session.add(ContextMappingRecord(**mapping.model_dump()))
            self.session.flush()

    def entity(self, entity_id: str, lock: bool = False) -> ContextEntity | None:
        statement = select(ContextEntityRecord).where(ContextEntityRecord.entity_id == entity_id)
        if lock:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return ContextEntity.model_validate_json(row.payload) if row else None

    def mapping(self, source: str, entity_id: str) -> ContextMapping | None:
        row = self.session.get(ContextMappingRecord, (source, entity_id))
        return (
            ContextMapping(
                source=row.source,
                entity_id=row.entity_id,
                external_entity_id=row.external_entity_id,
            )
            if row
            else None
        )

    def get(self, observation_id: UUID) -> ContextObservation | None:
        row = self.session.get(ContextObservationRecord, observation_id)
        return ContextObservation.model_validate_json(row.payload) if row else None

    def put(self, observation: ContextObservation) -> bool:
        previous = self.get(observation.observation_id)
        if previous is not None:
            if previous != observation:
                raise ConflictingContext("context observation cannot be rewritten")
            return False
        mapping = self.mapping(observation.source, observation.entity_id)
        if mapping is None or mapping.external_entity_id != observation.external_entity_id:
            raise ValueError("context observation requires matching provider mapping")
        if observation.supersedes_observation_id is not None:
            parent = self.get(observation.supersedes_observation_id)
            if parent is None or (
                parent.entity_id,
                parent.source,
                parent.event_key,
                parent.revision + 1,
            ) != (
                observation.entity_id,
                observation.source,
                observation.event_key,
                observation.revision,
            ):
                raise ValueError("context revision does not supersede the same entity/source/event")
            if (
                parent.kind != observation.kind
                or parent.event_at != observation.event_at
                or (parent.unit, parent.currency, parent.period_start, parent.period_end)
                != (
                    observation.unit,
                    observation.currency,
                    observation.period_start,
                    observation.period_end,
                )
                or parent.published_at > observation.published_at
                or parent.available_at > observation.available_at
                or parent.ingested_at > observation.ingested_at
            ):
                raise ValueError("context revision changes identity or temporal ordering")
        self.session.add(
            ContextObservationRecord(
                observation_id=observation.observation_id,
                entity_id=observation.entity_id,
                source=observation.source,
                source_record_id=observation.source_record_id,
                event_key=observation.event_key,
                revision=observation.revision,
                published_at=observation.published_at,
                available_at=observation.available_at,
                ingested_at=observation.ingested_at,
                supersedes_observation_id=observation.supersedes_observation_id,
                payload=observation.model_dump_json(),
            )
        )
        self.session.flush()
        return True

    def history(self, entity_id: str, as_of: datetime) -> tuple[ContextObservation, ...]:
        rows = self.session.scalars(
            select(ContextObservationRecord)
            .where(
                ContextObservationRecord.entity_id == entity_id,
                ContextObservationRecord.published_at <= as_of,
                ContextObservationRecord.available_at <= as_of,
                ContextObservationRecord.ingested_at <= as_of,
            )
            .order_by(ContextObservationRecord.observation_id)
            .limit(10001)
        ).all()
        if len(rows) > 10000:
            raise ValueError("context history exceeds bounded limit")
        return tuple(ContextObservation.model_validate_json(row.payload) for row in rows)
