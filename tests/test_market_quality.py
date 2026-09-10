from datetime import timedelta

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.market_data.quality import FreshnessPolicy, ReasonCode, inspect_candles
from tests.market_fixtures import CLOCK, QUERY, START, raw


def test_valid_series() -> None:
    candles, quality = inspect_candles(
        [raw(i) for i in range(3)], QUERY, "fixture", FreshnessPolicy(), CLOCK
    )
    assert quality.valid and len(candles) == 3
    assert not quality.reason_codes


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ([raw(0), raw(0), raw(1), raw(2)], ReasonCode.DUPLICATE_RECORD),
        ([raw(0), raw(2)], ReasonCode.MISSING_INTERVAL),
        ([raw(1), raw(0), raw(2)], ReasonCode.OUT_OF_ORDER),
        ([raw(high="95")], ReasonCode.INVALID_OHLC),
        ([raw(open="0")], ReasonCode.INVALID_PRICE),
        ([raw(volume="-1")], ReasonCode.INVALID_VOLUME),
        ([raw(open_time="nonsense")], ReasonCode.INVALID_TIMESTAMP),
        ([raw(received_at=START)], ReasonCode.INVALID_TIMESTAMP),
        ([raw(timeframe="wrong")], ReasonCode.MALFORMED_VALUE),
        ([raw(source="other")], ReasonCode.UNEXPECTED_RECORD),
        ([raw(market_id="other")], ReasonCode.UNEXPECTED_RECORD),
        ([raw(4)], ReasonCode.UNEXPECTED_RECORD),
    ],
)
def test_quality_failures(records: list[dict[str, object]], reason: ReasonCode) -> None:
    _, result = inspect_candles(records, QUERY, "fixture", FreshnessPolicy(), CLOCK)
    assert not result.valid
    assert reason in result.reason_codes


def test_exact_gap_and_no_fabrication() -> None:
    candles, quality = inspect_candles([raw(0), raw(2)], QUERY, "fixture", FreshnessPolicy(), CLOCK)
    assert len(candles) == 2
    assert quality.missing_intervals == (START + timedelta(hours=1),)
    assert quality.timestamp == CLOCK.now()


def test_freshness_contexts() -> None:
    records = [raw(i) for i in range(3)]
    _, research = inspect_candles(records, QUERY, "fixture", FreshnessPolicy(), CLOCK)
    _, live = inspect_candles(
        records, QUERY, "fixture", FreshnessPolicy(max_age=timedelta(minutes=5)), CLOCK
    )
    assert research.valid
    assert ReasonCode.STALE_DATA in live.reason_codes
    assert live.affected_records == (0, 1, 2)


def test_future_tolerance() -> None:
    query = CandleQuery.model_validate({**QUERY.model_dump(), "end": START + timedelta(hours=1)})
    clock = FrozenClock(START + timedelta(minutes=59))
    _, rejected = inspect_candles([raw()], query, "fixture", FreshnessPolicy(), clock)
    _, accepted = inspect_candles(
        [raw()], query, "fixture", FreshnessPolicy(future_tolerance=timedelta(minutes=1)), clock
    )
    assert ReasonCode.INVALID_TIMESTAMP in rejected.reason_codes
    assert accepted.valid


def test_closed_sessions_are_explicit() -> None:
    query = CandleQuery.model_validate({**QUERY.model_dump(), "expected_opens": (START,)})
    _, result = inspect_candles([raw()], query, "fixture", FreshnessPolicy(), CLOCK)
    assert result.valid


def test_policy_rejects_negative_tolerances() -> None:
    with pytest.raises(ValidationError):
        FreshnessPolicy(future_tolerance=timedelta(seconds=-1))
    with pytest.raises(ValidationError):
        FreshnessPolicy(max_age=timedelta(0))
