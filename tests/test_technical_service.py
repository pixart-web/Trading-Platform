from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import TechnicalIntelligence, canonical
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import CLOCK, QUERY, START, sample


def engine(repository: MarketRepository) -> TechnicalIntelligence:
    return TechnicalIntelligence(MarketReplay(repository, CLOCK))


def test_reproducibility_immutability_and_prefix_hash(repository: MarketRepository) -> None:
    repository.put(tuple(sample(i) for i in range(4)))
    service = engine(repository)
    first = service.analyze(QUERY, FreshnessPolicy())
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        assert service.analyze(QUERY, FreshnessPolicy()) == first
    extended = CandleQuery.model_validate({**QUERY.model_dump(), "end": START + timedelta(hours=4)})
    assert service.analyze(extended, FreshnessPolicy())[:3] == first
    assert len({s.input_hash for s in first}) == 3
    assert [s.input_count for s in first] == [1, 2, 3]
    assert all(s.available_at >= s.bar_close for s in first)
    with pytest.raises(ValidationError):
        first[0].input_count = 999
    assert first[0].model_validate_json(first[0].model_dump_json()) == first[0]


def test_late_early_bar_delays_every_dependent_feature(repository: MarketRepository) -> None:
    late = START + timedelta(hours=6)
    repository.put((sample(0, received_at=late), sample(1), sample(2)))
    result = engine(repository).analyze(QUERY, FreshnessPolicy())
    assert [s.bar_open for s in result] == list(QUERY.schedule())
    assert all(s.available_at == late for s in result)


def test_late_last_bar_does_not_delay_earlier_features(repository: MarketRepository) -> None:
    repository.put((sample(0), sample(1), sample(2, received_at=START + timedelta(hours=6))))
    result = engine(repository).analyze(QUERY, FreshnessPolicy())
    assert result[0].available_at == START + timedelta(hours=1)
    assert result[1].available_at == START + timedelta(hours=2)
    assert result[2].available_at == START + timedelta(hours=6)


def test_missing_and_stale_data_fail_closed(repository: MarketRepository) -> None:
    repository.put((sample(0), sample(2)))
    with pytest.raises(DataRejected):
        engine(repository).analyze(QUERY, FreshnessPolicy())
    repository.put((sample(1),))
    with pytest.raises(DataRejected):
        engine(repository).analyze(QUERY, FreshnessPolicy(max_age=timedelta(hours=1)))


def test_explicit_session_schedule_and_empty_closed_session(repository: MarketRepository) -> None:
    repository.put((sample(0), sample(2)))
    session = CandleQuery.model_validate(
        {**QUERY.model_dump(), "expected_opens": (START, START + timedelta(hours=2))}
    )
    result = engine(repository).analyze(
        session, FreshnessPolicy(), (IndicatorSpec(kind=IndicatorKind.SMA, period=2),)
    )
    assert len(result) == 2
    assert result[-1].results[0].features[0].value == 101
    empty = CandleQuery(
        market_id="test-market",
        timeframe=QUERY.timeframe,
        start=QUERY.end,
        end=QUERY.end + timedelta(hours=1),
        expected_opens=(),
    )
    assert engine(repository).analyze(empty, FreshnessPolicy()) == ()


def test_specs_are_bounded_unique_and_parameterized(repository: MarketRepository) -> None:
    repository.put(tuple(sample(i) for i in range(3)))
    service = engine(repository)
    spec = IndicatorSpec(kind=IndicatorKind.SMA, period=2)
    for specs in (
        (),
        (spec, spec),
        tuple(IndicatorSpec(kind=IndicatorKind.SMA, period=i + 2) for i in range(33)),
    ):
        with pytest.raises(ValueError):
            service.analyze(QUERY, FreshnessPolicy(), specs)
    specs = (spec, IndicatorSpec(kind=IndicatorKind.SMA, period=3))
    result = service.analyze(QUERY, FreshnessPolicy(), specs)
    assert tuple(r.spec for r in result[-1].results) == specs


def test_canonical_decimal_scales_are_equal() -> None:
    assert canonical([Decimal("0.00"), Decimal("1E+2"), Decimal("1.23000")]) == ["0", "100", "1.23"]
    assert canonical(Decimal("100.000")) == canonical(Decimal("1E+2"))


def test_future_receipt_is_rejected_and_missing_data_not_invented(
    repository: MarketRepository,
) -> None:
    with pytest.raises(DataRejected):
        engine(repository).analyze(QUERY, FreshnessPolicy())
    repository.put(tuple(sample(i) for i in range(3)))
    early = TechnicalIntelligence(MarketReplay(repository, FrozenClock(START + timedelta(hours=2))))
    with pytest.raises(DataRejected):
        early.analyze(QUERY, FreshnessPolicy())


def test_zero_volume_canonical_hash_and_policy_provenance(repository: MarketRepository) -> None:
    repository.put(tuple(sample(i, volume="0") for i in range(3)))
    policy = FreshnessPolicy(max_age=timedelta(days=3))
    result = engine(repository).analyze(QUERY, policy)
    assert all(s.freshness_policy == policy for s in result)
    assert result == engine(repository).analyze(QUERY, policy)
