import hashlib
import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.intelligence.technical.indicators import calculate
from pocket_alpha.intelligence.technical.models import (
    FeatureSnapshot,
    IndicatorKind,
    IndicatorResult,
    IndicatorSpec,
)
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

DEFAULT_SPECS = tuple(IndicatorSpec(kind=kind) for kind in IndicatorKind)


def canonical(value: object) -> object:
    """Stable hashes across SQLite/PostgreSQL decimal scale and caller context."""
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        plain = format(value, "f")
        return plain.rstrip("0").rstrip(".") if "." in plain else plain
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    return value


class TechnicalIntelligence:
    """Shared historical feature service. No raw inspection or execution path.

    The entire bounded query must pass replay quality before computing anything.
    Prefix availability is the maximum receipt of every bar needed since input_start.
    A delayed early bar consequently delays dependent outputs, never backdates them.
    """

    def __init__(self, replay: MarketReplay) -> None:
        self.replay = replay

    def analyze(
        self,
        query: CandleQuery,
        policy: FreshnessPolicy,
        specs: tuple[IndicatorSpec, ...] = DEFAULT_SPECS,
    ) -> tuple[FeatureSnapshot, ...]:
        if not 1 <= len(specs) <= 32 or len(set(specs)) != len(specs):
            raise ValueError("request 1..32 unique indicator specifications")
        events = self.replay.replay(query, policy)
        candles = tuple(sorted((event.candle for event in events), key=lambda c: c.open_time))
        if not candles:
            return ()
        # Fully specified Context, not a copy of ambient precision/rounding/traps.
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            series = [calculate(candles, spec) for spec in specs]
            snapshots: list[FeatureSnapshot] = []
            available = candles[0].received_at
            digest = hashlib.sha256(b"pocket-alpha-candle-prefix-v1")
            for i, candle in enumerate(candles):
                payload = candle.model_dump()
                for key in ("open_time", "close_time", "received_at"):
                    payload[key] = payload[key].isoformat()
                encoded = json.dumps(canonical(payload), sort_keys=True, separators=(",", ":"))
                digest.update(encoded.encode() + b"\n")
                available = max(available, candle.received_at)
                snapshots.append(
                    FeatureSnapshot(
                        market_id=query.market_id,
                        timeframe=query.timeframe,
                        source=candle.source,
                        freshness_policy=policy,
                        input_start=query.start,
                        bar_open=candle.open_time,
                        bar_close=candle.close_time,
                        available_at=available,
                        input_count=i + 1,
                        input_hash=digest.hexdigest(),
                        results=tuple(
                            IndicatorResult(spec=spec, features=values[i])
                            for spec, values in zip(specs, series, strict=True)
                        ),
                    )
                )
            return tuple(snapshots)
