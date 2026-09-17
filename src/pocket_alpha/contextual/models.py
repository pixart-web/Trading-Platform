import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, Currency, DomainModel

Value = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]


class ContextKind(StrEnum):
    NEWS = "NEWS"
    SENTIMENT = "SENTIMENT"
    MACRO = "MACRO"


class ContextEntity(DomainModel):
    entity_id: Identifier
    name: str = Field(min_length=1, max_length=256)
    kind: Literal["ASSET", "MACRO", "TOPIC"]
    asset_id: AssetId | None = None

    @model_validator(mode="after")
    def linked(self) -> Self:
        if (self.kind == "ASSET") != (self.asset_id is not None):
            raise ValueError("only asset entities require an explicit asset link")
        return self


class ContextMapping(DomainModel):
    source: Identifier
    entity_id: Identifier
    external_entity_id: str = Field(min_length=1, max_length=256)


class ContextSample(DomainModel):
    schema_version: Literal["context-observation-1.0.0"] = "context-observation-1.0.0"
    external_entity_id: str = Field(min_length=1, max_length=256)
    source_record_id: str = Field(min_length=1, max_length=256)
    event_key: str = Field(min_length=1, max_length=256)
    revision: int = Field(default=1, ge=1, le=2147483647)
    kind: ContextKind
    event_at: UTCDateTime
    event_status: Literal["OCCURRED", "SCHEDULED"] = "OCCURRED"
    published_at: UTCDateTime
    title: str | None = Field(default=None, min_length=1, max_length=512)
    url: HttpUrl | None = None
    value: Value | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=64)
    currency: Currency | None = None
    method_version: Identifier | None = None
    period_start: date | None = None
    period_end: date | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.url is not None and self.url.scheme != "https":
            raise ValueError("context source links require HTTPS")
        if self.event_at > self.published_at and (
            self.kind != ContextKind.NEWS or self.event_status != "SCHEDULED"
        ):
            raise ValueError("future events cannot be represented as observed context")
        if self.kind == ContextKind.NEWS:
            if self.title is None or self.url is None:
                raise ValueError("news requires source title and link")
            if any(
                v is not None for v in (self.value, self.unit, self.currency, self.method_version)
            ):
                raise ValueError("news cannot invent sentiment or numeric values")
        else:
            if self.event_status != "OCCURRED" or self.value is None or self.unit is None:
                raise ValueError("numeric context requires observed values and units")
            if self.kind == ContextKind.SENTIMENT:
                if self.unit != "normalized-score" or self.method_version is None:
                    raise ValueError("sentiment requires explicit normalized score method version")
                if not Decimal("-1") <= self.value <= Decimal("1") or self.currency is not None:
                    raise ValueError("sentiment score is bounded and is not money/probability")
            elif self.method_version is not None:
                raise ValueError("macro values cannot carry an inferred sentiment model")
        if self.currency is not None and self.unit != self.currency:
            raise ValueError("monetary macro currency must match unit")
        if self.unit in {"USD", "EUR", "GBP", "JPY", "CAD"} and self.currency is None:
            raise ValueError("monetary macro observation requires currency")
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("effective reporting periods require both boundaries")
        if self.period_start is not None and self.period_end is not None:
            if self.period_start > self.period_end or self.period_end > self.event_at.date():
                raise ValueError("reporting period cannot end after observed release event")
        return self


class ContextObservation(ContextSample):
    observation_id: UUID
    entity_id: Identifier
    source: Identifier
    available_at: UTCDateTime
    ingested_at: UTCDateTime
    supersedes_observation_id: UUID | None = None

    @model_validator(mode="after")
    def available(self) -> Self:
        if not self.published_at <= self.available_at <= self.ingested_at:
            raise ValueError("context publication, availability and ingestion must be ordered")
        if (self.revision == 1) != (self.supersedes_observation_id is None):
            raise ValueError("context revision requires coherent supersession")
        return self


def context_digest(
    entity: ContextEntity, as_of: datetime, observations: tuple[ContextObservation, ...]
) -> str:
    payload = json.dumps(
        [
            "context-snapshot-1.0.0",
            as_of.isoformat(),
            entity.model_dump(mode="json"),
            [o.model_dump(mode="json") for o in observations],
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ContextSnapshot(DomainModel):
    feature_version: Literal["context-snapshot-1.0.0"] = "context-snapshot-1.0.0"
    entity: ContextEntity
    as_of: UTCDateTime
    generated_at: UTCDateTime
    observations: tuple[ContextObservation, ...] = Field(max_length=1000)
    unavailable_kinds: tuple[ContextKind, ...]
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def causal(self) -> Self:
        if self.generated_at < self.as_of or any(
            o.entity_id != self.entity.entity_id
            or max(o.published_at, o.available_at, o.ingested_at) > self.as_of
            for o in self.observations
        ):
            raise ValueError("context snapshot contains future or incompatible records")
        if self.input_hash != context_digest(self.entity, self.as_of, self.observations):
            raise ValueError("context snapshot hash does not match inputs")
        present = {o.kind for o in self.observations}
        if set(self.unavailable_kinds) != set(ContextKind) - present:
            raise ValueError("context coverage must honestly reflect available observations")
        return self
