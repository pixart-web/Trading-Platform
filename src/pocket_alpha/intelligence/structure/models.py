from enum import StrEnum
from typing import Literal

from pydantic import Field

from pocket_alpha.domain.market import Identifier, Price, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.market_data.quality import FreshnessPolicy


class StructureSpec(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    left_bars: int = Field(default=2, ge=1, le=100, strict=True)
    right_bars: int = Field(default=2, ge=1, le=100, strict=True)
    pivot_policy: Literal["STRICT"] = "STRICT"
    break_policy: Literal["CLOSE_CROSS"] = "CLOSE_CROSS"


class SwingKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class SwingRelation(StrEnum):
    FIRST = "FIRST"
    HH = "HH"
    LH = "LH"
    HL = "HL"
    LL = "LL"
    EQUAL = "EQUAL"


class Direction(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class StructureState(StrEnum):
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    TRANSITIONING = "TRANSITIONING"


class StructureReason(StrEnum):
    INSUFFICIENT_SWINGS = "INSUFFICIENT_SWINGS"
    HIGHER_HIGHS_AND_LOWS = "HIGHER_HIGHS_AND_LOWS"
    LOWER_HIGHS_AND_LOWS = "LOWER_HIGHS_AND_LOWS"
    MIXED_OR_EQUAL_SWINGS = "MIXED_OR_EQUAL_SWINGS"
    INITIAL_BREAK = "INITIAL_BREAK"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    STRUCTURAL_FAILURE = "STRUCTURAL_FAILURE"
    REVERSAL_CONFIRMED = "REVERSAL_CONFIRMED"


class BreakKind(StrEnum):
    INITIAL_BREAK = "INITIAL_BREAK"
    BOS = "BOS"
    CHOCH = "CHOCH"


class SwingPoint(DomainModel):
    kind: SwingKind
    relation: SwingRelation
    price: Price
    pivot_open: UTCDateTime
    confirmed_on: UTCDateTime
    available_at: UTCDateTime
    window_start: UTCDateTime
    previous_pivot_open: UTCDateTime | None
    previous_price: Price | None


class StructureBreak(DomainModel):
    kind: BreakKind
    direction: Direction
    level: SwingPoint
    bar_open: UTCDateTime
    bar_close: UTCDateTime
    available_at: UTCDateTime
    previous_close: Price
    close: Price
    prior_bias: Direction | None
    reason: StructureReason


class StructureSnapshot(DomainModel):
    engine_version: Literal["structure-1.0.0"] = "structure-1.0.0"
    spec: StructureSpec
    market_id: Identifier
    timeframe: Timeframe
    source: Identifier
    freshness_policy: FreshnessPolicy
    input_start: UTCDateTime
    input_count: int = Field(ge=1, le=10000)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bar_open: UTCDateTime
    bar_close: UTCDateTime
    available_at: UTCDateTime
    state: StructureState
    bias: Direction | None
    pending_reversal: Direction | None
    reason: StructureReason
    last_high: SwingPoint | None
    last_low: SwingPoint | None
    high_consumed: bool
    low_consumed: bool
    confirmed_swings: tuple[SwingPoint, ...]
    breaks: tuple[StructureBreak, ...]
