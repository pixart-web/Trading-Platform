from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.intelligence.structure.models import SwingKind
from pocket_alpha.intelligence.structure.service import _calculate as structure_calculate
from pocket_alpha.intelligence.zones.models import (
    StrengthComponents,
    Zone,
    ZoneRole,
    ZoneSnapshot,
    ZoneSpec,
)
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

DEFAULT_SPEC = ZoneSpec()


@dataclass
class _Active:
    zone: Zone
    last_index: int
    touching: bool


def _calculate(
    candles: tuple[Candle, ...], query: CandleQuery, policy: FreshnessPolicy, spec: ZoneSpec
) -> tuple[ZoneSnapshot, ...]:
    """Internal: validated observations only; reuse the Phase 4 pivot implementation."""
    if len(candles) > 2000:
        raise ValueError("zone analysis is bounded to 2000 bars")
    structure = structure_calculate(candles, query, policy, spec.structure)
    by_open = {c.open_time: c for c in candles}
    active: list[_Active] = []
    snapshots: list[ZoneSnapshot] = []
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        for i, (candle, context) in enumerate(zip(candles, structure, strict=True)):
            now = context.available_at
            active = [item for item in active if i - item.last_index <= spec.max_age_bars]
            for item in active:
                z = item.zone
                changes: dict[str, object] = {}
                overlap = candle.low <= z.upper and candle.high >= z.lower
                broken = (
                    candle.close < z.lower if z.role == ZoneRole.SUPPORT else candle.close > z.upper
                )
                if broken:
                    changes.update(
                        role=ZoneRole.RESISTANCE
                        if z.role == ZoneRole.SUPPORT
                        else ZoneRole.SUPPORT,
                        flips=z.flips + 1,
                        visible_from=now,
                        last_seen=now,
                    )
                    item.last_index = i
                elif overlap and not item.touching:
                    rejection = (
                        candle.close > z.upper
                        if z.role == ZoneRole.SUPPORT
                        else candle.close < z.lower
                    )
                    changes.update(
                        contacts=z.contacts + 1,
                        rejections=z.rejections + int(rejection),
                        contact_volume=z.contact_volume + candle.volume,
                        last_seen=now,
                    )
                    item.last_index = i
                item.touching = overlap
                item.zone = Zone.model_validate({**z.model_dump(), **changes})

            for pivot in context.confirmed_swings:
                role = ZoneRole.SUPPORT if pivot.kind == SwingKind.LOW else ZoneRole.RESISTANCE
                matches = [
                    item
                    for item in active
                    if item.zone.role == role and item.zone.lower <= pivot.price <= item.zone.upper
                ]
                if matches:
                    # Nearest center; creation-order ties are deterministic. Bounds never expand.
                    item = min(matches, key=lambda item: abs(item.zone.center - pivot.price))
                    z = item.zone
                    item.zone = Zone.model_validate(
                        {
                            **z.model_dump(),
                            "pivot_count": z.pivot_count + 1,
                            "last_seen": now,
                            "evidence": (*z.evidence, pivot)[-32:],
                        }
                    )
                    item.last_index = i
                    continue
                seed = by_open[pivot.pivot_open]
                half = min(
                    pivot.price / 2,
                    max(
                        pivot.price * spec.minimum_width_bps / 10000,
                        (seed.high - seed.low) * spec.range_fraction,
                    ),
                )
                components = StrengthComponents(pivots=10, contacts=0, rejections=0, recency=20)
                z = Zone(
                    zone_id=f"{pivot.kind.value}:{pivot.pivot_open.strftime('%Y%m%dT%H%M%S.%f')}",
                    role=role,
                    lower=pivot.price - half,
                    center=pivot.price,
                    upper=pivot.price + half,
                    first_seen=now,
                    visible_from=now,
                    last_seen=now,
                    pivot_count=1,
                    contacts=0,
                    rejections=0,
                    flips=0,
                    age_bars=0,
                    contact_volume=Decimal(0),
                    strength=30,
                    components=components,
                    evidence=(pivot,),
                )
                if len(active) == spec.max_zones:
                    oldest = min(range(len(active)), key=lambda index: active[index].last_index)
                    active.pop(oldest)
                active.append(_Active(z, i, candle.low <= z.upper and candle.high >= z.lower))

            for item in active:
                z, age = item.zone, i - item.last_index
                components = StrengthComponents(
                    pivots=min(z.pivot_count, 4) * 10,
                    contacts=min(z.contacts, 3) * 10,
                    rejections=min(z.rejections, 2) * 5,
                    recency=20 * (spec.max_age_bars - age) // spec.max_age_bars,
                )
                item.zone = Zone.model_validate(
                    {
                        **z.model_dump(),
                        "age_bars": age,
                        "components": components,
                        "strength": sum(components.model_dump().values()),
                    }
                )
            snapshots.append(
                ZoneSnapshot(
                    spec=spec,
                    market_id=query.market_id,
                    timeframe=query.timeframe,
                    source=context.source,
                    freshness_policy=policy,
                    input_start=query.start,
                    input_count=i + 1,
                    input_hash=context.input_hash,
                    bar_close=candle.close_time,
                    available_at=now,
                    zones=tuple(item.zone for item in active),
                )
            )
    return tuple(snapshots)


class SupportResistance:
    def __init__(self, replay: MarketReplay) -> None:
        self.replay = replay

    def analyze(
        self, query: CandleQuery, policy: FreshnessPolicy, spec: ZoneSpec = DEFAULT_SPEC
    ) -> tuple[ZoneSnapshot, ...]:
        return self.chart(query, policy, spec)[1]

    def chart(
        self, query: CandleQuery, policy: FreshnessPolicy, spec: ZoneSpec = DEFAULT_SPEC
    ) -> tuple[tuple[Candle, ...], tuple[ZoneSnapshot, ...]]:
        if len(query.schedule()) > 2000:
            raise ValueError("zone analysis is bounded to 2000 bars")
        events = self.replay.replay(query, policy)
        candles = tuple(sorted((event.candle for event in events), key=lambda c: c.open_time))
        return candles, _calculate(candles, query, policy, spec)
