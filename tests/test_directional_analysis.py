from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import (
    CaseStatus,
    ComparisonOperator,
    DirectionalAnalysis,
    DirectionalAnalysisRequest,
    DirectionalCaseInput,
    DirectionalCasePolicy,
    DirectionalCriterionDefinition,
    DirectionalDecision,
    DirectionalMetric,
    DirectionalPolicy,
    DirectionalReason,
    DirectionalSide,
    MetricStatus,
)
from pocket_alpha.directional.service import DirectionalAnalysisEngine, fingerprint
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.forecasts.service import canonical_snapshot

D = Decimal
START = datetime(2025, 1, 1, tzinfo=UTC)
CLOCK = FrozenClock(START + timedelta(days=1))


def criterion(
    name: str, operator: ComparisonOperator, threshold: str
) -> DirectionalCriterionDefinition:
    return DirectionalCriterionDefinition(
        criterion=name,
        label=name.replace("-", " ").title(),
        operator=operator,
        threshold=D(threshold),
        rule_version=f"{name}-rule-v1",
    )


LONG_POLICY = DirectionalCasePolicy(
    side=DirectionalSide.LONG,
    criteria=(
        criterion("up-support", ComparisonOperator.GREATER_THAN_OR_EQUAL, "60"),
        criterion("long-opposition", ComparisonOperator.LESS_THAN_OR_EQUAL, "30"),
    ),
)
SHORT_POLICY = DirectionalCasePolicy(
    side=DirectionalSide.SHORT,
    criteria=(
        criterion("down-support", ComparisonOperator.GREATER_THAN_OR_EQUAL, "55"),
        criterion("short-opposition", ComparisonOperator.LESS_THAN_OR_EQUAL, "40"),
    ),
)
POLICY = DirectionalPolicy(
    policy_version="directional-policy-v1",
    long_case=LONG_POLICY,
    short_case=SHORT_POLICY,
)


def metric(
    name: str,
    value: str | None,
    *,
    available_at: datetime = START,
    reason: str = "SOURCE_UNAVAILABLE",
) -> DirectionalMetric:
    if value is None:
        return DirectionalMetric(
            criterion=name,
            status=MetricStatus.UNAVAILABLE,
            source_version=f"{name}-source-v1",
            unavailable_reason=reason,
        )
    evidence = canonical_snapshot(
        name,
        f"{name}-source-v1",
        "a" * 64,
        available_at,
        {"value": D(value)},
    )
    return DirectionalMetric(
        criterion=name,
        status=MetricStatus.AVAILABLE,
        value=D(value),
        source_version=f"{name}-source-v1",
        available_at=available_at,
        evidence=(evidence,),
    )


def case(side: DirectionalSide, first: str | None, second: str | None) -> DirectionalCaseInput:
    names = (
        ("up-support", "long-opposition")
        if side == DirectionalSide.LONG
        else ("down-support", "short-opposition")
    )
    return DirectionalCaseInput(
        side=side,
        metrics=(metric(names[0], first), metric(names[1], second)),
    )


def request(
    long_case: DirectionalCaseInput,
    short_case: DirectionalCaseInput,
    *,
    policy: DirectionalPolicy = POLICY,
) -> DirectionalAnalysisRequest:
    return DirectionalAnalysisRequest(
        analysis_id=UUID(int=1),
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        horizon=ForecastHorizon.H4,
        as_of=START + timedelta(hours=1),
        policy=policy,
        long_case=long_case,
        short_case=short_case,
    )


def analyze(
    long_values: tuple[str | None, str | None],
    short_values: tuple[str | None, str | None],
) -> DirectionalAnalysis:
    return DirectionalAnalysisEngine(CLOCK).analyze(
        request(
            case(DirectionalSide.LONG, *long_values),
            case(DirectionalSide.SHORT, *short_values),
        ),
        generated_at=START + timedelta(hours=2),
    )


def test_only_long_case_qualifies() -> None:
    result = analyze(("70", "20"), ("40", "20"))
    assert result.decision == DirectionalDecision.LONG
    assert result.reason == DirectionalReason.LONG_CASE_ONLY
    assert result.long_case.qualifies is True
    assert result.short_case.qualifies is False
    assert result.short_case.failed_criteria == ("down-support",)


def test_only_short_case_qualifies() -> None:
    result = analyze(("50", "20"), ("70", "20"))
    assert result.decision == DirectionalDecision.SHORT
    assert result.reason == DirectionalReason.SHORT_CASE_ONLY
    assert result.long_case.failed_criteria == ("up-support",)
    assert result.short_case.qualifies is True


def test_two_qualifying_cases_fail_closed_to_no_trade() -> None:
    result = analyze(("70", "20"), ("70", "20"))
    assert result.decision == DirectionalDecision.NO_TRADE
    assert result.reason == DirectionalReason.CONFLICTING_CASES
    assert result.long_case.qualifies is result.short_case.qualifies is True


def test_two_failed_cases_are_no_trade() -> None:
    result = analyze(("50", "50"), ("40", "50"))
    assert result.decision == DirectionalDecision.NO_TRADE
    assert result.reason == DirectionalReason.NO_CASE_PASSED
    assert result.long_case.failed_criteria == ("up-support", "long-opposition")
    assert result.short_case.failed_criteria == ("down-support", "short-opposition")


def test_unavailable_evidence_is_no_trade_even_if_other_case_passes() -> None:
    result = analyze(("70", "20"), (None, "20"))
    assert result.decision == DirectionalDecision.NO_TRADE
    assert result.reason == DirectionalReason.INCOMPLETE_EVIDENCE
    assert result.long_case.qualifies is True
    assert result.short_case.status == CaseStatus.UNAVAILABLE
    assert result.short_case.qualifies is None
    assert result.short_case.unavailable_criteria == ("down-support",)


def test_thresholds_are_inclusive_and_sides_remain_independent() -> None:
    result = analyze(("60", "30"), ("55", "40"))
    assert result.reason == DirectionalReason.CONFLICTING_CASES
    assert all(item.passed for item in result.long_case.results)
    assert all(item.passed for item in result.short_case.results)


def test_hashes_versions_timeframe_and_horizon_are_retained() -> None:
    subject = request(
        case(DirectionalSide.LONG, "70", "20"),
        case(DirectionalSide.SHORT, "40", "20"),
    )
    result = DirectionalAnalysisEngine(CLOCK).analyze(
        subject, generated_at=START + timedelta(hours=2)
    )
    assert result.policy_hash == fingerprint(subject.policy.model_dump())
    assert result.input_hash == fingerprint(
        {
            "long_case": subject.long_case.model_dump(),
            "short_case": subject.short_case.model_dump(),
        }
    )
    assert result.policy_version == "directional-policy-v1"
    assert result.candle_timeframe == Timeframe.H1
    assert result.horizon == ForecastHorizon.H4


def test_request_requires_exact_metric_order_and_canonical_sides() -> None:
    long_case = case(DirectionalSide.LONG, "70", "20")
    reversed_long = DirectionalCaseInput(
        side=DirectionalSide.LONG,
        metrics=tuple(reversed(long_case.metrics)),
    )
    with pytest.raises(ValidationError, match="criterion order exactly"):
        request(reversed_long, case(DirectionalSide.SHORT, "40", "20"))
    with pytest.raises(ValidationError, match="canonical LONG and SHORT"):
        DirectionalPolicy(
            policy_version="invalid",
            long_case=SHORT_POLICY,
            short_case=LONG_POLICY,
        )
    with pytest.raises(ValidationError, match="identities must be unique"):
        DirectionalCasePolicy(
            side=DirectionalSide.LONG,
            criteria=(
                LONG_POLICY.criteria[0],
                LONG_POLICY.criteria[0],
            ),
        )


def test_metric_availability_and_generation_are_causal() -> None:
    late = metric("up-support", "70", available_at=START + timedelta(hours=2))
    long_case = DirectionalCaseInput(
        side=DirectionalSide.LONG,
        metrics=(late, metric("long-opposition", "20")),
    )
    subject = request(long_case, case(DirectionalSide.SHORT, "40", "20"))
    engine = DirectionalAnalysisEngine(CLOCK)
    with pytest.raises(ValueError, match="unavailable at the as-of"):
        engine.analyze(subject, generated_at=START + timedelta(hours=3))
    with pytest.raises(ValueError, match="generation cannot be in the future"):
        engine.analyze(
            request(
                case(DirectionalSide.LONG, "70", "20"),
                case(DirectionalSide.SHORT, "40", "20"),
            ),
            generated_at=CLOCK.now() + timedelta(seconds=1),
        )
    future = subject.model_copy(update={"as_of": CLOCK.now() + timedelta(seconds=1)})
    with pytest.raises(ValueError, match="as-of time cannot be in the future"):
        engine.analyze(future, generated_at=CLOCK.now())


def test_generation_cannot_precede_as_of() -> None:
    with pytest.raises(ValueError, match="before its as-of"):
        DirectionalAnalysisEngine(CLOCK).analyze(
            request(
                case(DirectionalSide.LONG, "70", "20"),
                case(DirectionalSide.SHORT, "40", "20"),
            ),
            generated_at=START,
        )


def test_metric_contract_rejects_plausible_unavailable_value_and_late_evidence() -> None:
    with pytest.raises(ValidationError, match="only an explicit reason"):
        DirectionalMetric(
            criterion="up-support",
            status=MetricStatus.UNAVAILABLE,
            value=D(70),
            source_version="v",
            unavailable_reason="missing",
        )
    available_at = START
    late_evidence = canonical_snapshot(
        "up-support",
        "source-v1",
        "a" * 64,
        available_at + timedelta(seconds=1),
        {"value": D(70)},
    )
    with pytest.raises(ValidationError, match="evidence cannot arrive after"):
        DirectionalMetric(
            criterion="up-support",
            status=MetricStatus.AVAILABLE,
            value=D(70),
            source_version="v",
            available_at=available_at,
            evidence=(late_evidence,),
        )


def test_result_rejects_a_decision_that_disagrees_with_cases() -> None:
    result = analyze(("70", "20"), ("40", "20"))
    with pytest.raises(ValidationError, match="must match independent case results"):
        DirectionalAnalysis.model_validate(
            {
                **result.model_dump(),
                "decision": DirectionalDecision.SHORT,
                "reason": DirectionalReason.SHORT_CASE_ONLY,
            }
        )
