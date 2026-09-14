from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.analysis.models import AnalyzeStatus, HorizonConclusion
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe


class SnapshotStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class AlertEventType(StrEnum):
    ANALYSIS_BECAME_AVAILABLE = "ANALYSIS_BECAME_AVAILABLE"
    ANALYSIS_BECAME_UNAVAILABLE = "ANALYSIS_BECAME_UNAVAILABLE"
    HORIZON_CONCLUSION_CHANGED = "HORIZON_CONCLUSION_CHANGED"


class WatchlistMember(DomainModel):
    member_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    added_at: UTCDateTime


class Watchlist(DomainModel):
    schema_version: Literal["watchlist-1.0.0"] = "watchlist-1.0.0"
    watchlist_id: UUID
    name: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)
    created_at: UTCDateTime
    updated_at: UTCDateTime
    members: tuple[WatchlistMember, ...] = Field(max_length=250)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("watchlist update cannot precede creation")
        if len({member.market_id for member in self.members}) != len(self.members):
            raise ValueError("watchlist markets must be unique")
        if len({member.member_id for member in self.members}) != len(self.members):
            raise ValueError("watchlist member identities must be unique")
        if tuple(sorted(self.members, key=lambda item: (item.added_at, str(item.member_id)))) != (
            self.members
        ):
            raise ValueError("watchlist members must use canonical order")
        return self


class WatchlistHorizonState(DomainModel):
    horizon: ForecastHorizon
    conclusion: HorizonConclusion


class WatchlistSnapshotItem(DomainModel):
    member_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    report_id: UUID | None = None
    report_status: AnalyzeStatus | None = None
    unavailable_reason: Identifier | None = None
    horizons: tuple[WatchlistHorizonState, ...] = Field(min_length=13, max_length=13)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(item.horizon for item in self.horizons) != tuple(ForecastHorizon):
            raise ValueError("snapshot item requires canonical forecast horizons")
        if (self.report_id is None) == (self.unavailable_reason is None):
            raise ValueError("snapshot item requires exactly one report or unavailable reason")
        if self.report_id is None:
            if self.report_status is not None or any(
                item.conclusion != HorizonConclusion.UNAVAILABLE for item in self.horizons
            ):
                raise ValueError("unavailable snapshot item cannot expose analytical conclusions")
        elif self.report_status is None:
            raise ValueError("available snapshot item requires report status")
        return self


class WatchlistSnapshot(DomainModel):
    schema_version: Literal["watchlist-snapshot-1.0.0"] = "watchlist-snapshot-1.0.0"
    snapshot_id: UUID
    watchlist_id: UUID
    watchlist_revision: int = Field(ge=1)
    as_of: UTCDateTime
    generated_at: UTCDateTime
    status: SnapshotStatus
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[WatchlistSnapshotItem, ...] = Field(max_length=250)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("watchlist snapshot cannot be generated before its as-of time")
        if len({item.member_id for item in self.items}) != len(self.items):
            raise ValueError("snapshot members must be unique")
        if len({item.market_id for item in self.items}) != len(self.items):
            raise ValueError("snapshot markets must be unique")
        available = sum(item.report_id is not None for item in self.items)
        expected = (
            SnapshotStatus.UNAVAILABLE
            if not self.items or available == 0
            else SnapshotStatus.COMPLETE
            if available == len(self.items)
            else SnapshotStatus.PARTIAL
        )
        if self.status != expected:
            raise ValueError("snapshot status must match report coverage")
        return self


class AlertEvent(DomainModel):
    schema_version: Literal["watchlist-alert-1.0.0"] = "watchlist-alert-1.0.0"
    event_id: UUID
    watchlist_id: UUID
    snapshot_id: UUID
    previous_snapshot_id: UUID
    member_id: UUID
    market_id: Identifier
    candle_timeframe: Timeframe
    horizon: ForecastHorizon | None = None
    event_type: AlertEventType
    previous_conclusion: HorizonConclusion | None = None
    current_conclusion: HorizonConclusion | None = None
    observed_at: UTCDateTime
    created_at: UTCDateTime
    reason: Identifier

    @model_validator(mode="after")
    def coherent(self) -> Self:
        changed = self.event_type == AlertEventType.HORIZON_CONCLUSION_CHANGED
        if changed:
            if (
                self.horizon is None
                or self.previous_conclusion is None
                or self.current_conclusion is None
                or self.previous_conclusion == self.current_conclusion
            ):
                raise ValueError("conclusion event requires a changed horizon state")
        elif any(
            value is not None
            for value in (self.horizon, self.previous_conclusion, self.current_conclusion)
        ):
            raise ValueError("analysis availability event cannot include a horizon state")
        if self.created_at < self.observed_at:
            raise ValueError("alert creation cannot precede observation")
        return self


class SnapshotResult(DomainModel):
    snapshot: WatchlistSnapshot
    events: tuple[AlertEvent, ...]
