"""Synthetic native-timeframe fixtures; no trading or economic performance claims."""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.intelligence.multi_timeframe.models import (
    Agreement,
    FrameRequest,
    FrameStatus,
    MultiTimeframeRequest,
    MultiTimeframeSnapshot,
    MultiTimeframeSpec,
    PairRelation,
)
from pocket_alpha.intelligence.multi_timeframe.service import MultiTimeframeIntelligence
from pocket_alpha.intelligence.structure.models import Direction, StructureSpec, StructureState
from pocket_alpha.intelligence.structure.service import MarketStructure
from pocket_alpha.intelligence.technical.models import FeatureStatus, IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import TechnicalIntelligence
from pocket_alpha.intelligence.zones.models import ZoneSpec
from pocket_alpha.intelligence.zones.service import SupportResistance
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay, ReplayEvent
from pocket_alpha.market_data.storage import MappingRecord, MarketRepository
from tests.market_fixtures import START, sample

UP = (10, 14, 10, 16, 12, 18, 14, 20)
DOWN = tuple(30 - p for p in UP)
TRANSITION = (*UP, 13, 15, 9)
CLOCK = FrozenClock(START + timedelta(days=90))
SPEC = MultiTimeframeSpec(zones=ZoneSpec(structure=StructureSpec(left_bars=1, right_bars=1)))


def bars(timeframe: Timeframe, values: tuple[int, ...] = UP) -> tuple[Candle, ...]:
    return tuple(
        sample(
            0,
            timeframe=timeframe,
            open_time=START + i * timeframe.duration,
            close_time=START + (i + 1) * timeframe.duration,
            received_at=START + (i + 1) * timeframe.duration,
            open=str(price),
            close=str(price),
            high=str(price + 1),
            low=str(price - 1),
        )
        for i, price in enumerate(values)
    )


def frame(timeframe: Timeframe, count: int = 8, age: timedelta | None = None) -> FrameRequest:
    return FrameRequest(
        query=CandleQuery(
            market_id="test-market",
            timeframe=timeframe,
            start=START,
            end=START + count * timeframe.duration,
        ),
        freshness_policy=FreshnessPolicy(max_age=None),
        max_snapshot_age=age,
    )


def request(*frames: FrameRequest, as_of: datetime | None = None) -> MultiTimeframeRequest:
    return MultiTimeframeRequest(
        frames=frames or (frame(Timeframe.H1), frame(Timeframe.H4)),
        as_of=as_of or START + timedelta(hours=32),
        spec=SPEC,
    )


def engine(repository: MarketRepository) -> MultiTimeframeIntelligence:
    return MultiTimeframeIntelligence(MarketReplay(repository, CLOCK))


@pytest.mark.parametrize(
    "low,high,agreement,direction,relation",
    [
        (UP, UP, Agreement.ALIGNED_UP, Direction.UP, PairRelation.ALIGNED),
        (DOWN, DOWN, Agreement.ALIGNED_DOWN, Direction.DOWN, PairRelation.ALIGNED),
        (UP, DOWN, Agreement.DIVERGENT, None, PairRelation.OPPOSED),
        (DOWN, UP, Agreement.DIVERGENT, None, PairRelation.OPPOSED),
        ((10,) * 8, (10,) * 8, Agreement.NEUTRAL, None, PairRelation.UNRESOLVED),
        (UP, (10,) * 8, Agreement.MIXED, None, PairRelation.UNRESOLVED),
        (TRANSITION, UP, Agreement.MIXED, None, PairRelation.UNRESOLVED),
        (TRANSITION, TRANSITION, Agreement.MIXED, None, PairRelation.UNRESOLVED),
    ],
)
def test_reference_contexts(
    repository: MarketRepository,
    low: tuple[int, ...],
    high: tuple[int, ...],
    agreement: Agreement,
    direction: Direction | None,
    relation: PairRelation,
) -> None:
    repository.put((*bars(Timeframe.H1, low), *bars(Timeframe.H4, high)))
    result = engine(repository).analyze(
        request(
            frame(Timeframe.H1, len(low)),
            frame(Timeframe.H4, len(high)),
            as_of=START + timedelta(hours=4 * len(high)),
        )
    )
    assert result.agreement == agreement and result.direction == direction
    pair = result.comparisons[0]
    assert pair.lower == Timeframe.H1 and pair.higher == Timeframe.H4
    assert pair.relation == relation
    assert pair.against_higher_timeframe == (relation == PairRelation.OPPOSED)
    if low == TRANSITION:
        structure = result.frames[0].structure
        assert structure is not None and structure.state == StructureState.TRANSITIONING
        assert structure.bias == Direction.UP  # Retained bias must not cast an UP vote.
        assert pair.lower_direction is None


def test_independent_native_analyses_and_single_read(
    repository: MarketRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4, DOWN)))
    replay = MarketReplay(repository, CLOCK)
    calls: list[Timeframe] = []
    original = replay.replay

    def counted(query: CandleQuery, policy: FreshnessPolicy) -> tuple[ReplayEvent, ...]:
        calls.append(query.timeframe)
        return original(query, policy)

    monkeypatch.setattr(replay, "replay", counted)
    result = MultiTimeframeIntelligence(replay).analyze(request())
    assert calls == [Timeframe.H1, Timeframe.H4]
    for analysis in result.frames:
        query, policy = analysis.request.query, analysis.request.freshness_policy
        assert (
            analysis.technical
            == TechnicalIntelligence(replay).analyze(
                query,
                policy,
                SPEC.indicators,
            )[-1]
        )
        assert (
            analysis.structure
            == MarketStructure(replay).analyze(
                query,
                policy,
                SPEC.zones.structure,
            )[-1]
        )
        assert analysis.zones == SupportResistance(replay).analyze(query, policy, SPEC.zones)[-1]
        assert analysis.technical.input_hash == analysis.structure.input_hash
        assert analysis.zones.input_hash == analysis.structure.input_hash
        assert analysis.structure.input_count == 8
    assert result.frames[0].structure != result.frames[1].structure


def test_as_of_uses_closed_received_prefix_and_not_higher_future_bar(
    repository: MarketRepository,
) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4, DOWN)))
    result = engine(repository).analyze(request(as_of=START + timedelta(hours=15)))
    high = result.frames[1]
    assert high.structure is not None and high.structure.input_count == 3
    assert high.structure.bar_close == START + timedelta(hours=12)
    assert high.structure.state == StructureState.NEUTRAL
    assert result.agreement == Agreement.MIXED
    at_close = engine(repository).analyze(request(as_of=START + timedelta(hours=16)))
    assert at_close.frames[1].structure is not None
    assert at_close.frames[1].structure.input_count == 4
    assert at_close.agreement == Agreement.DIVERGENT


@pytest.mark.parametrize("index", [0, 4, 7])
def test_late_receipt_blocks_dependent_prefixes(repository: MarketRepository, index: int) -> None:
    higher = list(bars(Timeframe.H4))
    higher[index] = Candle.model_validate(
        {
            **higher[index].model_dump(),
            "received_at": START + timedelta(hours=40),
        }
    )
    repository.put((*bars(Timeframe.H1), *higher))
    service = engine(repository)
    before = service.analyze(request())
    high = before.frames[1]
    assert before.agreement == Agreement.INCOMPLETE and before.direction is None
    assert high.status == FrameStatus.NOT_YET_AVAILABLE and high.pending_input
    assert before.comparisons[0].relation == PairRelation.UNAVAILABLE
    if index == 0:
        assert high.structure is None
        assert high.technical is None
        assert high.zones is None
    else:
        assert high.structure is not None and high.structure.input_count == index
        assert high.structure.available_at < START + timedelta(hours=40)
    after = service.analyze(request(as_of=START + timedelta(hours=40)))
    assert after.agreement == Agreement.ALIGNED_UP
    assert after.frames[1].structure is not None
    assert after.frames[1].structure.input_count == 8
    assert after.frames[1].structure.available_at == START + timedelta(hours=40)


def test_future_append_does_not_change_selected_evidence(repository: MarketRepository) -> None:
    repository.put((*bars(Timeframe.H1)[:4], *bars(Timeframe.H4)[:4]))
    service = engine(repository)
    before = service.analyze(
        request(frame(Timeframe.H1, 4), frame(Timeframe.H4, 4), as_of=START + timedelta(hours=4))
    )
    repository.put(
        (
            *bars(Timeframe.H1, (*UP[:4], 900, 5, 999, 3))[4:],
            *bars(Timeframe.H4, (*UP[:4], 2, 999, 3, 900))[4:],
        )
    )
    after = service.analyze(request(as_of=START + timedelta(hours=4)))
    assert after.context_hash == before.context_hash
    assert after.agreement == before.agreement
    for old, new in zip(before.frames, after.frames, strict=True):
        assert old.technical == new.technical
        assert old.structure == new.structure
        assert old.zones == new.zones


def test_staleness_uses_close_not_late_receipt_and_boundary(repository: MarketRepository) -> None:
    lower = tuple(
        Candle.model_validate(
            {
                **c.model_dump(),
                "received_at": START + timedelta(hours=32),
            }
        )
        for c in bars(Timeframe.H1)
    )
    repository.put((*lower, *bars(Timeframe.H4)))
    service = engine(repository)
    stale = service.analyze(
        request(frame(Timeframe.H1, age=timedelta(hours=23)), frame(Timeframe.H4))
    )
    assert stale.frames[0].status == FrameStatus.STALE
    assert stale.agreement == Agreement.INCOMPLETE
    assert stale.frames[0].structure is not None
    assert stale.frames[0].structure.available_at == stale.as_of
    fresh = service.analyze(
        request(frame(Timeframe.H1, age=timedelta(hours=24)), frame(Timeframe.H4))
    )
    assert fresh.agreement == Agreement.ALIGNED_UP
    assert fresh.context_hash != stale.context_hash


def test_empty_closed_session_is_unavailable_not_neutral(repository: MarketRepository) -> None:
    closed = tuple(
        FrameRequest(
            query=CandleQuery(
                market_id="test-market",
                timeframe=tf,
                start=START,
                end=START + timedelta(hours=4),
                expected_opens=(),
            ),
            freshness_policy=FreshnessPolicy(),
            max_snapshot_age=None,
        )
        for tf in (Timeframe.H1, Timeframe.H4)
    )
    result = engine(repository).analyze(request(*closed))
    assert result.agreement == Agreement.INCOMPLETE and result.available_at is None
    assert all(f.status == FrameStatus.EMPTY_SESSION and f.structure is None for f in result.frames)
    assert result.comparisons[0].relation == PairRelation.UNAVAILABLE


def test_no_closed_bar_has_no_analytics(repository: MarketRepository) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4)))
    result = engine(repository).analyze(request(as_of=START + timedelta(minutes=30)))
    assert result.available_at is None and result.agreement == Agreement.INCOMPLETE
    assert all(
        f.status == FrameStatus.NOT_YET_AVAILABLE and not f.pending_input for f in result.frames
    )


def test_missing_timeframe_and_gap_fail_closed(repository: MarketRepository) -> None:
    repository.put(bars(Timeframe.H1))
    with pytest.raises(DataRejected):
        engine(repository).analyze(request())
    repository.put(bars(Timeframe.H4)[1:])
    with pytest.raises(DataRejected):
        engine(repository).analyze(request())


def test_replay_freshness_is_not_bypassed(repository: MarketRepository) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4)))
    strict = FrameRequest(
        query=frame(Timeframe.H1).query,
        freshness_policy=FreshnessPolicy(max_age=timedelta(hours=1)),
        max_snapshot_age=None,
    )
    with pytest.raises(DataRejected):
        engine(repository).analyze(request(strict, frame(Timeframe.H4)))


def test_dependency_failure_propagates(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(query: CandleQuery, limit: int = 1000) -> tuple[Candle, ...]:
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(repository, "candles", failed)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        engine(repository).analyze(request())


def test_request_order_immutability_decimal_context_and_roundtrip(
    repository: MarketRepository,
) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4)))
    service = engine(repository)
    expected = service.analyze(request())
    with localcontext() as context:
        context.prec = 3
        actual = service.analyze(request(frame(Timeframe.H4), frame(Timeframe.H1)))
    assert actual == expected
    assert MultiTimeframeSnapshot.model_validate_json(actual.model_dump_json()) == actual
    with pytest.raises(ValidationError):
        actual.direction = Direction.DOWN
    with pytest.raises(ValidationError):
        actual.frames[0].pending_input = True
    assert actual.frames[0].technical is not None
    features = actual.frames[0].technical.results
    assert any(
        f.status == FeatureStatus.WARMUP and f.value is None for r in features for f in r.features
    )
    assert any(isinstance(f.value, Decimal) for r in features for f in r.features)


def test_all_pairs_retain_minority_opposition(repository: MarketRepository) -> None:
    for tf, values in ((Timeframe.H1, UP), (Timeframe.H4, UP), (Timeframe.D1, DOWN)):
        repository.put(bars(tf, values))
    result = engine(repository).analyze(
        request(
            frame(Timeframe.D1),
            frame(Timeframe.H4),
            frame(Timeframe.H1),
            as_of=START + timedelta(days=8),
        )
    )
    assert result.agreement == Agreement.DIVERGENT and result.direction is None
    assert len(result.comparisons) == 3
    assert sum(pair.against_higher_timeframe for pair in result.comparisons) == 2
    assert result.comparisons[0].relation == PairRelation.ALIGNED


def test_explicit_noncontinuous_schedules(repository: MarketRepository) -> None:
    requests: list[FrameRequest] = []
    for tf in (Timeframe.H1, Timeframe.H4):
        data = tuple(
            Candle.model_validate(
                {
                    **c.model_dump(),
                    "open_time": START + i * 2 * tf.duration,
                    "close_time": START + (i * 2 + 1) * tf.duration,
                    "received_at": START + (i * 2 + 1) * tf.duration,
                }
            )
            for i, c in enumerate(bars(tf))
        )
        repository.put(data)
        requests.append(
            FrameRequest(
                query=CandleQuery(
                    market_id="test-market",
                    timeframe=tf,
                    start=START,
                    end=data[-1].close_time,
                    expected_opens=tuple(c.open_time for c in data),
                ),
                freshness_policy=FreshnessPolicy(),
                max_snapshot_age=None,
            )
        )
    result = engine(repository).analyze(request(*requests, as_of=START + timedelta(hours=60)))
    assert result.agreement == Agreement.ALIGNED_UP
    assert all(f.structure is not None and f.structure.input_count == 8 for f in result.frames)


@pytest.mark.parametrize(
    "change",
    [
        {"frames": []},
        {"as_of": "2025-01-01T00:00:00"},
        {"extra": True},
    ],
)
def test_invalid_request_fields(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MultiTimeframeRequest.model_validate({**request().model_dump(), **change})


def test_identity_duplicates_and_resource_bounds() -> None:
    with pytest.raises(ValidationError, match="unique"):
        request(frame(Timeframe.H1), frame(Timeframe.H1))
    other = FrameRequest.model_validate(
        {
            **frame(Timeframe.H4).model_dump(),
            "query": {
                **frame(Timeframe.H4).query.model_dump(),
                "market_id": "other-market",
            },
        }
    )
    with pytest.raises(ValidationError, match="same market"):
        request(frame(Timeframe.H1), other)
    with pytest.raises(ValidationError, match="2000"):
        request(frame(Timeframe.H1, 2001), frame(Timeframe.H4))
    with pytest.raises(ValidationError, match="8000"):
        request(*(frame(tf, 2000) for tf in tuple(Timeframe)[:5]))
    with pytest.raises(ValidationError):
        FrameRequest.model_validate({"query": frame(Timeframe.H1).query, "freshness_policy": {}})
    with pytest.raises(ValidationError):
        frame(Timeframe.H1, age=timedelta(0))
    with pytest.raises(ValidationError):
        MultiTimeframeSpec.model_validate({"version": "2.0.0"})
    with pytest.raises(ValidationError, match="unique"):
        MultiTimeframeSpec(indicators=(IndicatorSpec(kind=IndicatorKind.SMA),) * 2)


def test_future_as_of_is_rejected(repository: MarketRepository) -> None:
    with pytest.raises(ValueError, match="future"):
        engine(repository).analyze(request(as_of=CLOCK.now() + timedelta(seconds=1)))


def test_different_sources_require_compatibility_policy(repository: MarketRepository) -> None:
    repository.session.add(
        MappingRecord(source="other", market_id="test-market", instrument_id="OTHER")
    )
    repository.session.flush()
    repository.put(
        (
            *bars(Timeframe.H1),
            *(
                Candle.model_validate(
                    {
                        **c.model_dump(),
                        "source": "other",
                    }
                )
                for c in bars(Timeframe.H4)
            ),
        )
    )
    with pytest.raises(ValueError, match="cross-provider"):
        engine(repository).analyze(request())


def test_eight_timeframes_and_timezone_normalization(repository: MarketRepository) -> None:
    from datetime import timezone

    for tf in Timeframe:
        repository.put(bars(tf))
    cutoff = START + timedelta(weeks=8)
    frames = tuple(frame(tf) for tf in reversed(Timeframe))
    result = engine(repository).analyze(request(*frames, as_of=cutoff))
    shifted = engine(repository).analyze(
        request(
            *frames,
            as_of=cutoff.astimezone(
                timezone(timedelta(hours=2)),
            ),
        )
    )
    assert result == shifted
    assert result.agreement == Agreement.ALIGNED_UP
    assert len(result.comparisons) == 28
    assert all(pair.relation == PairRelation.ALIGNED for pair in result.comparisons)


def test_parameter_change_retains_inputs_but_changes_context(repository: MarketRepository) -> None:
    repository.put((*bars(Timeframe.H1), *bars(Timeframe.H4)))
    initial = request()
    changed = MultiTimeframeRequest.model_validate(
        {
            **initial.model_dump(),
            "spec": {
                **SPEC.model_dump(),
                "indicators": (IndicatorSpec(kind=IndicatorKind.SMA, period=2),),
            },
        }
    )
    first, second = engine(repository).analyze(initial), engine(repository).analyze(changed)
    assert first.context_hash != second.context_hash
    for left, right in zip(first.frames, second.frames, strict=True):
        assert left.structure == right.structure and left.zones == right.zones
        assert left.technical is not None and right.technical is not None
        assert left.technical.input_hash == right.technical.input_hash
        assert right.technical.results[0].features[0].value == 17
