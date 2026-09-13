from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.forecasts.service import canonical_snapshot
from pocket_alpha.scoring.models import (
    ComponentStatus,
    PocketScore,
    PocketScoreComponentDefinition,
    PocketScoreComponentInput,
    PocketScoreRequest,
    PocketScoreSpec,
    PocketScoreStatus,
)
from pocket_alpha.scoring.service import PocketScoreEngine, fingerprint

D = Decimal
START = datetime(2025, 1, 1, tzinfo=UTC)
CLOCK = FrozenClock(START + timedelta(days=1))
FULL_COVERAGE = D(1)


def definition(
    component: str, weight: str, *, required: bool = True
) -> PocketScoreComponentDefinition:
    return PocketScoreComponentDefinition(
        component=component,
        label=component.replace("-", " ").title(),
        weight=D(weight),
        required=required,
    )


def component(
    name: str,
    value: str | None,
    *,
    available_at: datetime = START,
    reason: str = "SOURCE_UNAVAILABLE",
) -> PocketScoreComponentInput:
    if value is None:
        return PocketScoreComponentInput(
            component=name,
            status=ComponentStatus.UNAVAILABLE,
            normalization_version=f"{name}-normalization-v1",
            unavailable_reason=reason,
        )
    snapshot = canonical_snapshot(
        name,
        f"{name}-v1",
        "a" * 64,
        available_at,
        {"quality": D(value)},
    )
    return PocketScoreComponentInput(
        component=name,
        status=ComponentStatus.AVAILABLE,
        value=D(value),
        normalization_version=f"{name}-normalization-v1",
        available_at=available_at,
        evidence=(snapshot,),
    )


def request(
    inputs: tuple[PocketScoreComponentInput, ...],
    *,
    components: tuple[PocketScoreComponentDefinition, ...] | None = None,
    minimum_coverage: Decimal = FULL_COVERAGE,
) -> PocketScoreRequest:
    declared = components or (
        definition("technical", "2"),
        definition("structure", "1"),
        definition("forecast", "1"),
    )
    return PocketScoreRequest(
        score_id=UUID(int=1),
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        as_of=START + timedelta(hours=1),
        spec=PocketScoreSpec(
            score_version="pocket-score-v1",
            components=declared,
            minimum_coverage=minimum_coverage,
        ),
        inputs=inputs,
    )


def full_inputs() -> tuple[PocketScoreComponentInput, ...]:
    return (
        component("technical", "80"),
        component("structure", "50"),
        component("forecast", "20"),
    )


def test_weighted_score_is_exact_explained_and_versioned() -> None:
    subject = request(full_inputs())
    score = PocketScoreEngine(CLOCK).calculate(subject, generated_at=START + timedelta(hours=2))
    assert score.status == PocketScoreStatus.AVAILABLE
    assert score.score == D("57.5")
    assert score.coverage == 1
    assert (
        sum(
            (item.contribution for item in score.components if item.contribution is not None),
            D(0),
        )
        == score.score
    )
    assert tuple(item.effective_weight for item in score.components) == (
        D("0.5"),
        D("0.25"),
        D("0.25"),
    )
    assert score.config_hash == fingerprint(subject.spec.model_dump())
    assert score.input_hash == fingerprint([item.model_dump() for item in subject.inputs])
    assert score.score_version == "pocket-score-v1"


def test_configuration_changes_are_explicit_and_deterministic() -> None:
    inputs = full_inputs()
    first = PocketScoreEngine(CLOCK).calculate(
        request(inputs), generated_at=START + timedelta(hours=2)
    )
    changed = request(
        inputs,
        components=(
            definition("technical", "1"),
            definition("structure", "1"),
            definition("forecast", "2"),
        ),
    )
    second = PocketScoreEngine(CLOCK).calculate(changed, generated_at=START + timedelta(hours=2))
    repeated = PocketScoreEngine(CLOCK).calculate(changed, generated_at=START + timedelta(hours=2))
    assert second == repeated
    assert first.config_hash != second.config_hash
    assert first.score == D("57.5")
    assert second.score == D("42.5")


def test_optional_missing_component_is_disclosed_and_weights_are_renormalized() -> None:
    subject = request(
        (
            component("technical", "80"),
            component("structure", "50"),
            component("forecast", None),
        ),
        components=(
            definition("technical", "2"),
            definition("structure", "1"),
            definition("forecast", "1", required=False),
        ),
        minimum_coverage=D("0.75"),
    )
    score = PocketScoreEngine(CLOCK).calculate(subject, generated_at=START + timedelta(hours=2))
    assert score.status == PocketScoreStatus.AVAILABLE
    assert score.coverage == D("0.75")
    assert score.score == D("70")
    assert score.components[-1].unavailable_reason == "SOURCE_UNAVAILABLE"
    assert score.components[-1].contribution is None


def test_missing_required_component_fails_closed_without_partial_score() -> None:
    subject = request(
        (
            component("technical", "80"),
            component("structure", None),
            component("forecast", "20"),
        )
    )
    score = PocketScoreEngine(CLOCK).calculate(subject, generated_at=START + timedelta(hours=2))
    assert score.status == PocketScoreStatus.UNAVAILABLE
    assert score.score is None
    assert score.unavailable_reason == "REQUIRED_COMPONENT_UNAVAILABLE"
    assert all(item.contribution is None for item in score.components)
    assert score.components[0].raw_value == D(80)


def test_insufficient_optional_coverage_fails_closed() -> None:
    definitions = (
        definition("technical", "2"),
        definition("structure", "1", required=False),
        definition("forecast", "1", required=False),
    )
    subject = request(
        (
            component("technical", "80"),
            component("structure", None),
            component("forecast", None),
        ),
        components=definitions,
        minimum_coverage=D("0.75"),
    )
    score = PocketScoreEngine(CLOCK).calculate(subject, generated_at=START + timedelta(hours=2))
    assert score.status == PocketScoreStatus.UNAVAILABLE
    assert score.coverage == D("0.5")
    assert score.unavailable_reason == "INSUFFICIENT_COMPONENT_COVERAGE"


def test_component_must_be_available_at_as_of_and_generation_is_bounded() -> None:
    late = component("technical", "80", available_at=START + timedelta(hours=2))
    subject = request((late, *full_inputs()[1:]))
    engine = PocketScoreEngine(CLOCK)
    with pytest.raises(ValueError, match="unavailable at the as-of"):
        engine.calculate(subject, generated_at=START + timedelta(hours=3))
    with pytest.raises(ValueError, match="generation cannot be in the future"):
        engine.calculate(request(full_inputs()), generated_at=CLOCK.now() + timedelta(seconds=1))
    future_request = request(full_inputs()).model_copy(
        update={"as_of": CLOCK.now() + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="as-of time cannot be in the future"):
        engine.calculate(future_request, generated_at=CLOCK.now())


def test_request_requires_exact_declared_component_order() -> None:
    with pytest.raises(ValidationError, match="configured component order exactly"):
        request(tuple(reversed(full_inputs())))
    with pytest.raises(ValidationError, match="identities must be unique"):
        PocketScoreSpec(
            score_version="v",
            components=(definition("same", "1"), definition("same", "2")),
        )


def test_component_status_contract_rejects_plausible_missing_values() -> None:
    with pytest.raises(ValidationError, match="only an explicit reason"):
        PocketScoreComponentInput(
            component="technical",
            status=ComponentStatus.UNAVAILABLE,
            value=D(50),
            normalization_version="v",
            unavailable_reason="missing",
        )
    with pytest.raises(ValidationError, match="requires value"):
        PocketScoreComponentInput(
            component="technical",
            status=ComponentStatus.AVAILABLE,
            normalization_version="v",
        )


def test_result_rejects_unexplained_or_inconsistent_score() -> None:
    score = PocketScoreEngine(CLOCK).calculate(
        request(full_inputs()), generated_at=START + timedelta(hours=2)
    )
    with pytest.raises(ValidationError, match="sum of explained contributions"):
        PocketScore.model_validate({**score.model_dump(), "score": D("99")})
    with pytest.raises(ValidationError, match="weight totals"):
        PocketScore.model_validate({**score.model_dump(), "available_weight": D("3")})
    components = list(score.components)
    components[0] = components[0].model_copy(update={"effective_weight": D("0.4")})
    with pytest.raises(ValidationError, match="sum exactly to one"):
        PocketScore.model_validate({**score.model_dump(), "components": components})


def test_no_available_optional_components_is_explicitly_unavailable() -> None:
    definitions = (
        definition("technical", "1", required=False),
        definition("structure", "1", required=False),
        definition("forecast", "1", required=False),
    )
    subject = request(
        (
            component("technical", None),
            component("structure", None),
            component("forecast", None),
        ),
        components=definitions,
        minimum_coverage=D(0),
    )
    score = PocketScoreEngine(CLOCK).calculate(subject, generated_at=START + timedelta(hours=2))
    assert score.status == PocketScoreStatus.UNAVAILABLE
    assert score.score is None
    assert score.coverage == 0
    assert score.unavailable_reason == "NO_COMPONENTS_AVAILABLE"


def test_aggregate_weight_can_exceed_individual_weight_limit() -> None:
    definitions = (
        definition("technical", "1000"),
        definition("structure", "1000"),
        definition("forecast", "1000"),
    )
    score = PocketScoreEngine(CLOCK).calculate(
        request(full_inputs(), components=definitions),
        generated_at=START + timedelta(hours=2),
    )
    assert score.total_weight == D(3000)
    assert score.score == D(50)


def test_generation_cannot_precede_as_of() -> None:
    with pytest.raises(ValueError, match="before its as-of"):
        PocketScoreEngine(CLOCK).calculate(request(full_inputs()), generated_at=START)


def test_component_evidence_cannot_postdate_component_availability() -> None:
    available_at = START + timedelta(hours=1)
    evidence = canonical_snapshot(
        "technical",
        "technical-v1",
        "a" * 64,
        available_at + timedelta(seconds=1),
        {"quality": D(80)},
    )
    with pytest.raises(ValidationError, match="evidence cannot arrive after"):
        PocketScoreComponentInput(
            component="technical",
            status=ComponentStatus.AVAILABLE,
            value=D(80),
            normalization_version="v",
            available_at=available_at,
            evidence=(evidence,),
        )
