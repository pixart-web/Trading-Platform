from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel, Timeframe
from pocket_alpha.intelligence.structure.models import StructureSpec, SwingPoint
from pocket_alpha.market_data.quality import FreshnessPolicy


class ZoneRole(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


class ZoneSpec(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    structure: StructureSpec = StructureSpec()
    minimum_width_bps: Decimal = Field(default=Decimal(10), ge=Decimal("0.01"), le=100)
    range_fraction: Decimal = Field(default=Decimal("0.25"), ge=Decimal("0.001"), le=1)
    max_age_bars: int = Field(default=200, ge=1, le=2000, strict=True)
    max_zones: int = Field(default=24, ge=1, le=32, strict=True)


class StrengthComponents(DomainModel):
    pivots: int = Field(ge=0, le=40)
    contacts: int = Field(ge=0, le=30)
    rejections: int = Field(ge=0, le=10)
    recency: int = Field(ge=0, le=20)


class Zone(DomainModel):
    zone_id: Identifier
    role: ZoneRole
    lower: Decimal = Field(gt=0)
    center: Decimal = Field(gt=0)
    upper: Decimal = Field(gt=0)
    first_seen: UTCDateTime
    visible_from: UTCDateTime
    last_seen: UTCDateTime
    pivot_count: int = Field(ge=1)
    contacts: int = Field(ge=0)
    rejections: int = Field(ge=0)
    flips: int = Field(ge=0)
    age_bars: int = Field(ge=0)
    contact_volume: Decimal = Field(ge=0)
    strength: int = Field(ge=0, le=100)
    components: StrengthComponents
    confidence: None = None
    confidence_reason: Literal["UNCALIBRATED"] = "UNCALIBRATED"
    evidence: tuple[SwingPoint, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.lower < self.center < self.upper:
            raise ValueError("zone bounds must be ordered")
        if not self.first_seen <= self.visible_from <= self.last_seen:
            raise ValueError("zone availability must be ordered")
        if self.strength != sum(self.components.model_dump().values()):
            raise ValueError("strength must equal its explained components")
        return self


class ZoneSnapshot(DomainModel):
    engine_version: Literal["zones-1.0.0"] = "zones-1.0.0"
    spec: ZoneSpec
    market_id: Identifier
    timeframe: Timeframe
    source: Identifier
    freshness_policy: FreshnessPolicy
    input_start: UTCDateTime
    input_count: int = Field(ge=1, le=2000)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bar_close: UTCDateTime
    available_at: UTCDateTime
    zones: tuple[Zone, ...] = Field(max_length=32)
