import hashlib
from collections.abc import Sequence

from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.intelligence.provenance import candle_bytes
from pocket_alpha.intelligence.structure.models import (
    BreakKind,
    Direction,
    StructureBreak,
    StructureReason,
    StructureSnapshot,
    StructureSpec,
    StructureState,
    SwingKind,
    SwingPoint,
    SwingRelation,
)
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

DEFAULT_SPEC = StructureSpec()


def _relation(kind: SwingKind, candle: Candle, previous: SwingPoint | None) -> SwingRelation:
    price = candle.high if kind == SwingKind.HIGH else candle.low
    if previous is None:
        return SwingRelation.FIRST
    if price == previous.price:
        return SwingRelation.EQUAL
    if kind == SwingKind.HIGH:
        return SwingRelation.HH if price > previous.price else SwingRelation.LH
    return SwingRelation.HL if price > previous.price else SwingRelation.LL


def _state(direction: Direction) -> StructureState:
    return StructureState.BULLISH if direction == Direction.UP else StructureState.BEARISH


def _calculate(
    candles: Sequence[Candle], query: CandleQuery, policy: FreshnessPolicy, spec: StructureSpec
) -> tuple[StructureSnapshot, ...]:
    """Internal kernel. Caller must enforce the trusted replay boundary first."""
    result: list[StructureSnapshot] = []
    high: SwingPoint | None = None
    low: SwingPoint | None = None
    high_consumed = low_consumed = False
    bias: Direction | None = None
    pending: Direction | None = None
    state = StructureState.NEUTRAL
    reason = StructureReason.INSUFFICIENT_SWINGS
    digest = hashlib.sha256(b"pocket-alpha-candle-prefix-v1")
    available = query.start
    for i, candle in enumerate(candles):
        available = max(available, candle.received_at)
        digest.update(candle_bytes(candle))
        events: list[StructureBreak] = []
        # Only levels known BEFORE this bar are eligible. Wicks and touches do not break.
        if i:
            previous_close = candles[i - 1].close
            for direction, level, consumed in (
                (Direction.UP, high, high_consumed),
                (Direction.DOWN, low, low_consumed),
            ):
                if level is None or consumed:
                    continue
                crossed = (
                    previous_close <= level.price < candle.close
                    if direction == Direction.UP
                    else previous_close >= level.price > candle.close
                )
                if not crossed:
                    continue
                prior_bias = bias
                if bias is None:
                    kind, reason = BreakKind.INITIAL_BREAK, StructureReason.INITIAL_BREAK
                    bias, pending, state = direction, None, _state(direction)
                elif direction == bias:
                    kind, reason = BreakKind.BOS, StructureReason.TREND_CONTINUATION
                    pending, state = None, _state(direction)
                elif pending == direction:
                    kind, reason = BreakKind.BOS, StructureReason.REVERSAL_CONFIRMED
                    bias, pending, state = direction, None, _state(direction)
                else:
                    kind, reason = BreakKind.CHOCH, StructureReason.STRUCTURAL_FAILURE
                    pending, state = direction, StructureState.TRANSITIONING
                events.append(
                    StructureBreak(
                        kind=kind,
                        direction=direction,
                        level=level,
                        bar_open=candle.open_time,
                        bar_close=candle.close_time,
                        available_at=available,
                        previous_close=previous_close,
                        close=candle.close,
                        prior_bias=prior_bias,
                        reason=reason,
                    )
                )
                if direction == Direction.UP:
                    high_consumed = True
                else:
                    low_consumed = True

        confirmed: list[SwingPoint] = []
        pivot_index = i - spec.right_bars
        if pivot_index >= spec.left_bars:
            pivot = candles[pivot_index]
            window_start = pivot_index - spec.left_bars
            neighbors = (*candles[window_start:pivot_index], *candles[pivot_index + 1 : i + 1])
            for swing_kind, previous in ((SwingKind.HIGH, high), (SwingKind.LOW, low)):
                qualifies = (
                    all(pivot.high > c.high for c in neighbors)
                    if swing_kind == SwingKind.HIGH
                    else all(pivot.low < c.low for c in neighbors)
                )
                if not qualifies:
                    continue
                point = SwingPoint(
                    kind=swing_kind,
                    relation=_relation(swing_kind, pivot, previous),
                    price=pivot.high if swing_kind == SwingKind.HIGH else pivot.low,
                    pivot_open=pivot.open_time,
                    confirmed_on=candle.open_time,
                    available_at=available,
                    window_start=candles[window_start].open_time,
                    previous_pivot_open=previous.pivot_open if previous else None,
                    previous_price=previous.price if previous else None,
                )
                confirmed.append(point)
                if swing_kind == SwingKind.HIGH:
                    high, high_consumed = point, False
                else:
                    low, low_consumed = point, False

        # Event evidence wins on its bar; unresolved CHOCH stays transitioning.
        if confirmed and not events and pending is None:
            pair = (high.relation if high else None, low.relation if low else None)
            proposed = (
                Direction.UP
                if pair == (SwingRelation.HH, SwingRelation.HL)
                else Direction.DOWN
                if pair == (SwingRelation.LH, SwingRelation.LL)
                else None
            )
            if proposed is not None:
                if bias is None or bias == proposed:
                    bias, state = proposed, _state(proposed)
                    reason = (
                        StructureReason.HIGHER_HIGHS_AND_LOWS
                        if proposed == Direction.UP
                        else StructureReason.LOWER_HIGHS_AND_LOWS
                    )
                else:
                    state, reason = (
                        StructureState.TRANSITIONING,
                        StructureReason.MIXED_OR_EQUAL_SWINGS,
                    )
            elif (
                high is not None
                and low is not None
                and all(relation != SwingRelation.FIRST for relation in pair)
            ):
                state = StructureState.TRANSITIONING if bias else StructureState.NEUTRAL
                reason = StructureReason.MIXED_OR_EQUAL_SWINGS

        result.append(
            StructureSnapshot(
                spec=spec,
                market_id=query.market_id,
                timeframe=query.timeframe,
                source=candle.source,
                freshness_policy=policy,
                input_start=query.start,
                input_count=i + 1,
                input_hash=digest.hexdigest(),
                bar_open=candle.open_time,
                bar_close=candle.close_time,
                available_at=available,
                state=state,
                bias=bias,
                pending_reversal=pending,
                reason=reason,
                last_high=high,
                last_low=low,
                high_consumed=high_consumed,
                low_consumed=low_consumed,
                confirmed_swings=tuple(confirmed),
                breaks=tuple(events),
            )
        )
    return tuple(result)


class MarketStructure:
    """Shared historical structure service. Invalid data and dependencies fail closed."""

    def __init__(self, replay: MarketReplay) -> None:
        self.replay = replay

    def analyze(
        self, query: CandleQuery, policy: FreshnessPolicy, spec: StructureSpec = DEFAULT_SPEC
    ) -> tuple[StructureSnapshot, ...]:
        events = self.replay.replay(query, policy)
        candles = tuple(sorted((event.candle for event in events), key=lambda c: c.open_time))
        return _calculate(candles, query, policy, spec)
