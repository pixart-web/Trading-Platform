"""Synthetic reference paths only; event labels are not performance evidence."""

from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.intelligence.structure.models import (
    BreakKind,
    Direction,
    StructureReason,
    StructureSpec,
    StructureState,
    SwingKind,
    SwingRelation,
)
from pocket_alpha.intelligence.structure.service import MarketStructure, _calculate
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import TechnicalIntelligence
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, START, sample

SPEC = StructureSpec(left_bars=1, right_bars=1)
PATH = (10, 14, 10, 16, 12, 18, 14, 20, 13, 15, 9, 12, 7, 10)


def bars(values: tuple[int, ...] = PATH) -> tuple[Candle, ...]:
    return tuple(
        sample(i, open=str(p), close=str(p), high=str(p + 1), low=str(p - 1))
        for i, p in enumerate(values)
    )


def query(count: int) -> CandleQuery:
    return CandleQuery(
        market_id="test-market",
        timeframe=Timeframe.H1,
        start=START,
        end=START + timedelta(hours=max(1, count)),
    )


@pytest.mark.parametrize("mirror", [False, True])
def test_reference_break_sequence_and_reversal(mirror: bool) -> None:
    data = bars(tuple(30 - p for p in PATH) if mirror else PATH)
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    events = [(i, event) for i, s in enumerate(result) for event in s.breaks]
    assert [(i, e.kind) for i, e in events] == [
        (3, BreakKind.INITIAL_BREAK),
        (5, BreakKind.BOS),
        (7, BreakKind.BOS),
        (10, BreakKind.CHOCH),
        (12, BreakKind.BOS),
    ]
    initial = Direction.DOWN if mirror else Direction.UP
    reversal = Direction.UP if mirror else Direction.DOWN
    assert [e.direction for _, e in events] == [initial, initial, initial, reversal, reversal]
    assert events[0][1].prior_bias is None
    assert events[-1][1].reason == StructureReason.REVERSAL_CONFIRMED
    assert result[10].state == result[11].state == StructureState.TRANSITIONING
    assert result[10].pending_reversal == reversal
    assert result[-1].bias == reversal and result[-1].pending_reversal is None
    assert result[-1].state == (StructureState.BULLISH if mirror else StructureState.BEARISH)
    for index, event in events:
        assert event.level.confirmed_on < event.bar_open
        assert event.available_at >= event.level.available_at
        assert event.previous_close == data[index - 1].close
        assert event.close == data[index].close
        assert event.reason != StructureReason.INSUFFICIENT_SWINGS


def test_relations_and_confirmation_evidence() -> None:
    data = bars()
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    high = result[4].confirmed_swings[0]
    assert high.kind == SwingKind.HIGH and high.relation == SwingRelation.HH
    assert high.price == 17 and high.previous_price == 15
    assert high.pivot_open == START + timedelta(hours=3)
    assert high.confirmed_on == START + timedelta(hours=4)
    assert high.available_at == START + timedelta(hours=5)
    assert high.window_start == START + timedelta(hours=2)
    assert high.previous_pivot_open == START + timedelta(hours=1)
    assert result[5].confirmed_swings[0].relation == SwingRelation.HL
    assert result[9].confirmed_swings[0].relation == SwingRelation.LL
    assert result[10].confirmed_swings[0].relation == SwingRelation.LH
    assert not result[0].confirmed_swings and not result[1].confirmed_swings


@pytest.mark.parametrize("left,right", [(1, 1), (2, 2), (1, 3), (3, 1), (100, 100)])
def test_no_repainting_for_all_prefixes(left: int, right: int) -> None:
    data = bars()
    spec = StructureSpec(left_bars=left, right_bars=right)
    full = _calculate(data, query(len(data)), FreshnessPolicy(), spec)
    for length in range(1, len(data) + 1):
        assert _calculate(data[:length], query(length), FreshnessPolicy(), spec) == full[:length]
    changed = (*data[:8], *(sample(i, high="1000", close="900") for i in range(8, len(data))))
    assert _calculate(changed, query(len(data)), FreshnessPolicy(), spec)[:8] == full[:8]
    for i, snapshot in enumerate(full):
        for swing in snapshot.confirmed_swings:
            assert swing.pivot_open == data[i - right].open_time
            assert swing.available_at >= data[i].close_time


def test_strict_ties_and_unconfirmed_edge_pivots() -> None:
    flat = bars((10, 10, 10, 10, 10))
    assert all(
        not s.confirmed_swings and s.state == StructureState.NEUTRAL
        for s in _calculate(flat, query(5), FreshnessPolicy(), SPEC)
    )
    plateau = bars((10, 14, 14, 10))
    assert all(
        not s.confirmed_swings for s in _calculate(plateau, query(4), FreshnessPolicy(), SPEC)
    )
    data = bars((10, 14, 10, 14, 10))
    result = _calculate(data, query(5), FreshnessPolicy(), SPEC)
    assert result[4].last_high is not None
    assert result[4].last_high.relation == SwingRelation.EQUAL
    assert all(not s.breaks for s in result)


def test_wick_touch_and_single_consumption() -> None:
    data = list(bars((10, 14, 10, 12, 15, 16, 17, 13, 16)))
    data[3] = sample(3, open="12", close="12", high="16", low="11")
    data[4] = sample(4, open="15", close="15", high="15", low="14")
    # High 15 at bar 1 is touched at close 4, then strictly crossed at close 5.
    # A newer high 16 (bar 3) is confirmed on bar 4, so bar 5 only touches that.
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    assert not result[3].breaks and not result[4].breaks and not result[5].breaks
    assert len(result[6].breaks) == 1
    broken = result[6].breaks[0].level
    assert sum(e.level == broken for s in result for e in s.breaks) == 1


@pytest.mark.parametrize("mirror", [False, True])
def test_pair_establishes_trend_without_close_break(mirror: bool) -> None:
    ranges = ((12, 8), (16, 9), (13, 7), (18, 10), (14, 9), (20, 11), (16, 10))
    data = tuple(
        sample(
            i,
            open="12" if not mirror else "18",
            close="12" if not mirror else "18",
            high=str(30 - low if mirror else high),
            low=str(30 - high if mirror else low),
        )
        for i, (high, low) in enumerate(ranges)
    )
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    assert all(not s.breaks for s in result)
    assert result[5].state == (StructureState.BEARISH if mirror else StructureState.BULLISH)
    assert result[5].reason == (
        StructureReason.LOWER_HIGHS_AND_LOWS if mirror else StructureReason.HIGHER_HIGHS_AND_LOWS
    )


def test_dual_pivot_is_explicit_not_inferred_intrabar_order() -> None:
    data = (
        sample(0, open="10", close="10", high="11", low="9"),
        sample(1, open="10", close="10", high="20", low="2"),
        sample(2, open="10", close="10", high="11", low="9"),
    )
    result = _calculate(data, query(3), FreshnessPolicy(), SPEC)
    assert [s.kind for s in result[-1].confirmed_swings] == [SwingKind.HIGH, SwingKind.LOW]
    assert result[-1].state == StructureState.NEUTRAL
    assert not result[-1].breaks


@pytest.mark.parametrize(
    "params",
    [
        {"left_bars": 0},
        {"right_bars": 0},
        {"left_bars": 101},
        {"right_bars": True},
        {"left_bars": "2"},
        {"version": "2.0.0"},
        {"pivot_policy": "TIES"},
        {"break_policy": "WICK"},
        {"extra": 1},
    ],
)
def test_bad_specs(params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StructureSpec.model_validate(params)


def test_service_replay_immutability_hashes_and_context(repository: MarketRepository) -> None:
    repository.put(bars())
    replay = MarketReplay(repository, CLOCK)
    engine = MarketStructure(replay)
    first = engine.analyze(query(len(PATH)), FreshnessPolicy(), SPEC)
    with localcontext() as context:
        context.prec = 3
        assert engine.analyze(query(len(PATH)), FreshnessPolicy(), SPEC) == first
    technical = TechnicalIntelligence(replay).analyze(
        query(len(PATH)), FreshnessPolicy(), (IndicatorSpec(kind=IndicatorKind.SMA),)
    )
    assert [s.input_hash for s in first] == [s.input_hash for s in technical]
    assert first[-1].model_validate_json(first[-1].model_dump_json()) == first[-1]
    with pytest.raises(ValidationError):
        first[-1].bias = Direction.UP
    assert engine.analyze(query(8), FreshnessPolicy(), SPEC) == first[:8]


def test_delayed_data_delays_confirmation_and_breaks(repository: MarketRepository) -> None:
    data = list(bars())
    data[0] = sample(
        0,
        **{
            **data[0].model_dump(exclude={"received_at"}),
            "received_at": START + timedelta(hours=20),
        },
    )
    repository.put(tuple(data))
    result = MarketStructure(MarketReplay(repository, CLOCK)).analyze(
        query(len(data)), FreshnessPolicy(), SPEC
    )
    assert all(s.available_at == START + timedelta(hours=20) for s in result)
    assert all(p.available_at == s.available_at for s in result for p in s.confirmed_swings)
    assert all(e.available_at == s.available_at for s in result for e in s.breaks)


def test_service_quality_and_empty_sessions(repository: MarketRepository) -> None:
    engine = MarketStructure(MarketReplay(repository, CLOCK))
    with pytest.raises(DataRejected):
        engine.analyze(query(3), FreshnessPolicy())
    repository.put((bars()[0], bars()[2]))
    with pytest.raises(DataRejected):
        engine.analyze(query(3), FreshnessPolicy())
    scheduled = CandleQuery.model_validate(
        {**query(3).model_dump(), "expected_opens": (START, START + timedelta(hours=2))}
    )
    assert len(engine.analyze(scheduled, FreshnessPolicy())) == 2
    repository.put((bars()[1],))
    with pytest.raises(DataRejected):
        engine.analyze(query(3), FreshnessPolicy(max_age=timedelta(minutes=1)))
    future = MarketStructure(MarketReplay(repository, FrozenClock(START)))
    with pytest.raises(DataRejected):
        future.analyze(query(3), FreshnessPolicy())
    closed = CandleQuery(
        market_id="test-market",
        timeframe=Timeframe.H1,
        start=START + timedelta(hours=10),
        end=START + timedelta(hours=11),
        expected_opens=(),
    )
    assert engine.analyze(closed, FreshnessPolicy()) == ()


def test_exact_subtick_comparison() -> None:
    tiny = Decimal("0.000000000000000001")
    data = (
        sample(0, open="1", close="1", high="1", low="1"),
        sample(1, open="1", close="1", high=str(Decimal(1) + tiny), low="1"),
        sample(2, open="1", close="1", high="1", low="1"),
        sample(3, open="1", close=str(Decimal(1) + 2 * tiny), high="2", low="1"),
    )
    result = _calculate(data, query(4), FreshnessPolicy(), SPEC)
    assert result[-1].breaks[0].level.price == Decimal(1) + tiny
    assert result[-1].breaks[0].close == Decimal(1) + 2 * tiny


@pytest.mark.parametrize("mirror", [False, True])
def test_original_trend_can_resume_after_choch(mirror: bool) -> None:
    path = (*PATH[:11], 22, 23, 24)
    data = bars(tuple(30 - p for p in path) if mirror else path)
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    assert result[10].breaks[0].kind == BreakKind.CHOCH
    assert result[11].breaks[0].kind == BreakKind.BOS
    assert result[11].breaks[0].reason == StructureReason.TREND_CONTINUATION
    assert result[11].pending_reversal is None
    assert result[11].bias == result[9].bias
    assert not result[12].breaks and not result[13].breaks


def test_opposing_swings_do_not_silently_reverse_established_bias() -> None:
    ranges = ((12, 8), (16, 9), (13, 7), (18, 10), (14, 9), (20, 11), (16, 10), (18, 8), (15, 9))
    data = tuple(
        sample(i, open="12", close="12", high=str(high), low=str(low))
        for i, (high, low) in enumerate(ranges)
    )
    result = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    assert result[5].state == StructureState.BULLISH
    assert result[-1].state == StructureState.TRANSITIONING
    assert result[-1].bias == Direction.UP
    assert result[-1].reason == StructureReason.MIXED_OR_EQUAL_SWINGS
    assert all(not s.breaks for s in result)


def test_mixed_swings_without_a_bias_remain_neutral() -> None:
    ranges = ((11, 9), (20, 2), (11, 9), (22, 1), (11, 9))
    data = tuple(
        sample(i, open="10", close="10", high=str(high), low=str(low))
        for i, (high, low) in enumerate(ranges)
    )
    final = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)[-1]
    assert final.state == StructureState.NEUTRAL and final.bias is None
    assert final.reason == StructureReason.MIXED_OR_EQUAL_SWINGS


def test_validated_session_bars_count_observations(repository: MarketRepository) -> None:
    data = (
        sample(0, open="10", close="10", high="11", low="9"),
        sample(4, open="14", close="14", high="15", low="13"),
        sample(9, open="10", close="10", high="11", low="9"),
    )
    repository.put(data)
    scheduled = CandleQuery.model_validate(
        {**query(10).model_dump(), "expected_opens": tuple(c.open_time for c in data)}
    )
    final = MarketStructure(MarketReplay(repository, CLOCK)).analyze(
        scheduled, FreshnessPolicy(), SPEC
    )[-1]
    assert final.confirmed_swings[0].pivot_open == START + timedelta(hours=4)
    assert final.confirmed_swings[0].confirmed_on == START + timedelta(hours=9)
    assert final.confirmed_swings[0].available_at == START + timedelta(hours=10)
