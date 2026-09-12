import hashlib
import json
from itertools import combinations

from pocket_alpha.common.clock import utc
from pocket_alpha.intelligence.multi_timeframe.models import (
    Agreement,
    FrameAnalysis,
    FrameRequest,
    FrameStatus,
    MultiTimeframeRequest,
    MultiTimeframeSnapshot,
    PairRelation,
    TimeframeComparison,
)
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.intelligence.structure.models import Direction, StructureState
from pocket_alpha.intelligence.structure.service import _calculate as structure_calculate
from pocket_alpha.intelligence.technical.service import _calculate as technical_calculate
from pocket_alpha.intelligence.zones.service import _calculate as zones_calculate
from pocket_alpha.market_data.replay import MarketReplay


def _direction(frame: FrameAnalysis) -> Direction | None:
    if frame.status != FrameStatus.READY or frame.structure is None:
        return None
    return {
        StructureState.BULLISH: Direction.UP,
        StructureState.BEARISH: Direction.DOWN,
    }.get(frame.structure.state)


def _compare(lower: FrameAnalysis, higher: FrameAnalysis) -> TimeframeComparison:
    low, high = _direction(lower), _direction(higher)
    if lower.status != FrameStatus.READY or higher.status != FrameStatus.READY:
        relation = PairRelation.UNAVAILABLE
    elif low is None or high is None:
        relation = PairRelation.UNRESOLVED
    else:
        relation = PairRelation.ALIGNED if low == high else PairRelation.OPPOSED
    return TimeframeComparison(
        lower=lower.request.query.timeframe,
        higher=higher.request.query.timeframe,
        relation=relation,
        lower_direction=low,
        higher_direction=high,
        against_higher_timeframe=relation == PairRelation.OPPOSED,
    )


def _aggregate(frames: tuple[FrameAnalysis, ...]) -> tuple[Agreement, Direction | None]:
    if any(frame.status != FrameStatus.READY for frame in frames):
        return Agreement.INCOMPLETE, None
    directions = {_direction(frame) for frame in frames}
    if Direction.UP in directions and Direction.DOWN in directions:
        return Agreement.DIVERGENT, None
    if directions == {Direction.UP}:
        return Agreement.ALIGNED_UP, Direction.UP
    if directions == {Direction.DOWN}:
        return Agreement.ALIGNED_DOWN, Direction.DOWN
    if all(
        frame.structure is not None and frame.structure.state == StructureState.NEUTRAL
        for frame in frames
    ):
        return Agreement.NEUTRAL, None
    return Agreement.MIXED, None


class MultiTimeframeIntelligence:
    """Bounded historical context over trusted native-resolution bars.

    One replay per timeframe feeds all three existing kernels. Caller owns a read
    transaction (repeatable read for a stable cross-timeframe database view).
    Invalid full queries and infrastructure errors propagate; no partial success.
    """

    def __init__(self, replay: MarketReplay) -> None:
        self.replay = replay

    def _analyze_frame(self, frame: FrameRequest, request: MultiTimeframeRequest) -> FrameAnalysis:
        events = self.replay.replay(frame.query, frame.freshness_policy)
        candles = tuple(sorted((event.candle for event in events), key=lambda c: c.open_time))
        pending = any(candle.close_time <= request.as_of < candle.received_at for candle in candles)
        # A delayed earlier bar cannot be skipped to manufacture a continuous history.
        count = 0
        for candle in candles:
            if max(candle.close_time, candle.received_at) > request.as_of:
                break
            count += 1
        prefix = candles[:count]
        if not prefix:
            return FrameAnalysis(
                request=frame,
                status=FrameStatus.EMPTY_SESSION if not candles else FrameStatus.NOT_YET_AVAILABLE,
                pending_input=pending,
            )
        spec = request.spec
        policy, query = frame.freshness_policy, frame.query
        technical = technical_calculate(prefix, query, policy, spec.indicators)[-1]
        structure = structure_calculate(prefix, query, policy, spec.zones.structure)[-1]
        zones = zones_calculate(prefix, query, policy, spec.zones)[-1]
        status = FrameStatus.READY
        if pending:
            status = FrameStatus.NOT_YET_AVAILABLE
        elif (
            frame.max_snapshot_age is not None
            and request.as_of - structure.bar_close > frame.max_snapshot_age
        ):
            status = FrameStatus.STALE
        return FrameAnalysis(
            request=frame,
            status=status,
            pending_input=pending,
            technical=technical,
            structure=structure,
            zones=zones,
        )

    def analyze(self, request: MultiTimeframeRequest) -> MultiTimeframeSnapshot:
        if request.as_of > utc(self.replay.clock.now()):
            raise ValueError("as_of cannot be in the future")
        frames = tuple(
            self._analyze_frame(frame, request)
            for frame in sorted(request.frames, key=lambda f: f.query.timeframe.duration)
        )
        sources = {frame.structure.source for frame in frames if frame.structure is not None}
        if len(sources) > 1:
            raise ValueError("cross-provider context requires an explicit compatibility policy")
        agreement, direction = _aggregate(frames)
        comparisons = tuple(_compare(low, high) for low, high in combinations(frames, 2))
        available = [
            frame.structure.available_at for frame in frames if frame.structure is not None
        ]
        # Exclude unused future query tails. Selected prefixes retain their own hashes;
        # status and freshness choices are part of the analytical identity.
        evidence = [
            {
                **frame.model_dump(mode="json", exclude={"request"}),
                "timeframe": frame.request.query.timeframe.value,
                "input_start": frame.request.query.start.isoformat(),
                "freshness_policy": frame.request.freshness_policy.model_dump(mode="json"),
                "max_snapshot_age": frame.request.model_dump(mode="json")["max_snapshot_age"],
            }
            for frame in frames
        ]
        payload = {
            "engine": "multi-timeframe-1.0.0",
            "market_id": frames[0].request.query.market_id,
            "as_of": request.as_of.isoformat(),
            "spec": request.spec.model_dump(mode="json"),
            "frames": evidence,
        }
        digest = hashlib.sha256(
            json.dumps(canonical(payload), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return MultiTimeframeSnapshot(
            spec=request.spec,
            market_id=frames[0].request.query.market_id,
            as_of=request.as_of,
            available_at=max(available) if available else None,
            frames=frames,
            agreement=agreement,
            direction=direction,
            comparisons=comparisons,
            context_hash=digest,
        )
