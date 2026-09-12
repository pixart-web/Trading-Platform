from datetime import timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.domain.market import CandleQuery, Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.intelligence.structure.models import Direction, StructureSnapshot
from pocket_alpha.intelligence.technical.models import FeatureSnapshot, IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.zones.models import ZoneSnapshot, ZoneSpec
from pocket_alpha.market_data.quality import FreshnessPolicy


class FrameRequest(DomainModel):
    query: CandleQuery
    freshness_policy: FreshnessPolicy
    # Required explicit choice: None permits historical age; no arbitrary trading threshold.
    max_snapshot_age: timedelta | None = Field(gt=timedelta(0))


class MultiTimeframeSpec(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    indicators: tuple[IndicatorSpec, ...] = Field(
        default=tuple(IndicatorSpec(kind=kind) for kind in IndicatorKind),
        min_length=1,
        max_length=32,
    )
    zones: ZoneSpec = ZoneSpec()
    aggregation: Literal["UNANIMOUS_STRUCTURE"] = "UNANIMOUS_STRUCTURE"

    @model_validator(mode="after")
    def unique_indicators(self) -> Self:
        if len(set(self.indicators)) != len(self.indicators):
            raise ValueError("indicator specifications must be unique")
        return self


class MultiTimeframeRequest(DomainModel):
    as_of: UTCDateTime
    frames: tuple[FrameRequest, ...] = Field(min_length=2, max_length=8)
    spec: MultiTimeframeSpec = MultiTimeframeSpec()

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if len({frame.query.market_id for frame in self.frames}) != 1:
            raise ValueError("all timeframes must belong to the same market")
        if len({frame.query.timeframe for frame in self.frames}) != len(self.frames):
            raise ValueError("timeframes must be unique")
        counts = [len(frame.query.schedule()) for frame in self.frames]
        if any(count > 2000 for count in counts) or sum(counts) > 8000:
            raise ValueError("maximum 2000 bars per timeframe and 8000 per request")
        return self


class FrameStatus(StrEnum):
    READY = "READY"
    EMPTY_SESSION = "EMPTY_SESSION"
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"
    STALE = "STALE"


class FrameAnalysis(DomainModel):
    request: FrameRequest
    status: FrameStatus
    # A closed input not received by as_of blocks this and every subsequent prefix.
    pending_input: bool
    technical: FeatureSnapshot | None = None
    structure: StructureSnapshot | None = None
    zones: ZoneSnapshot | None = None


class Agreement(StrEnum):
    ALIGNED_UP = "ALIGNED_UP"
    ALIGNED_DOWN = "ALIGNED_DOWN"
    DIVERGENT = "DIVERGENT"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    INCOMPLETE = "INCOMPLETE"


class PairRelation(StrEnum):
    ALIGNED = "ALIGNED"
    OPPOSED = "OPPOSED"
    UNRESOLVED = "UNRESOLVED"
    UNAVAILABLE = "UNAVAILABLE"


class TimeframeComparison(DomainModel):
    lower: Timeframe
    higher: Timeframe
    relation: PairRelation
    lower_direction: Direction | None
    higher_direction: Direction | None
    against_higher_timeframe: bool


class MultiTimeframeSnapshot(DomainModel):
    engine_version: Literal["multi-timeframe-1.0.0"] = "multi-timeframe-1.0.0"
    spec: MultiTimeframeSpec
    market_id: Identifier
    as_of: UTCDateTime
    available_at: UTCDateTime | None
    frames: tuple[FrameAnalysis, ...]
    agreement: Agreement
    direction: Direction | None
    comparisons: tuple[TimeframeComparison, ...]
    # Fingerprint of selected evidence, policies and versions; not a dataset registry.
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
