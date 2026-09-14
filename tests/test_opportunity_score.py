from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import (
    ComparisonOperator,
    DirectionalAnalysis,
    DirectionalAnalysisRequest,
    DirectionalCaseInput,
    DirectionalCasePolicy,
    DirectionalCriterionDefinition,
    DirectionalMetric,
    DirectionalPolicy,
    DirectionalSide,
    MetricStatus,
)
from pocket_alpha.directional.service import DirectionalAnalysisEngine
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    EvidenceSnapshot,
    Forecast,
    ForecastDirection,
    ForecastStatus,
    ModelStage,
    ProbabilityValue,
)
from pocket_alpha.forecasts.research_models import EconomicCostSpec
from pocket_alpha.forecasts.service import canonical_snapshot
from pocket_alpha.opportunities.models import (
    OpportunityComponentName,
    OpportunityContextMetric,
    OpportunityExclusionReason,
    OpportunityMetricKind,
    OpportunityMetricStatus,
    OpportunityPolicy,
    OpportunityScoreRequest,
    OpportunityStatus,
    OpportunityWeights,
)
from pocket_alpha.opportunities.service import OpportunityScoreEngine

D = Decimal
START = datetime(2025, 1, 1, tzinfo=UTC)
AS_OF = START + timedelta(hours=2)
GENERATED = START + timedelta(hours=3)
CLOCK = FrozenClock(START + timedelta(days=1))
ENGINE = OpportunityScoreEngine(CLOCK)
WEIGHTS = OpportunityWeights(
    net_edge=D(2),
    directional_probability=D(1),
    expected_move=D(1),
    cost_efficiency=D(1),
    liquidity=D(1),
    uncertainty=D(1),
    risk_reward=D(1),
)
POLICY = OpportunityPolicy(
    policy_version="opportunity-policy-v1",
    minimum_net_return=D("0.01"),
    target_net_return=D("0.05"),
    minimum_directional_probability=D("0.50"),
    target_directional_probability=D("0.70"),
    minimum_expected_move=D("0.03"),
    target_expected_move=D("0.10"),
    maximum_total_cost=D("0.01"),
    minimum_liquidity=D("0.50"),
    maximum_uncertainty=D("0.50"),
    minimum_risk_reward=D("2"),
    target_risk_reward=D("5"),
    weights=WEIGHTS,
)
COSTS = EconomicCostSpec(
    version="costs-v1",
    round_trip_fee_bps=D(10),
    round_trip_spread_bps=D(10),
    round_trip_slippage_bps=D(10),
    latency_bps=D(0),
)


def evidence(name: str, available_at: datetime = START) -> EvidenceSnapshot:
    return canonical_snapshot(
        name,
        f"{name}-v1",
        "a" * 64,
        available_at,
        {"value": name},
    )


def directional(decision: DirectionalSide | None = DirectionalSide.LONG) -> DirectionalAnalysis:
    criterion = DirectionalCriterionDefinition(
        criterion="support",
        label="Support",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold=D(1),
        rule_version="rule-v1",
    )
    long_policy = DirectionalCasePolicy(side=DirectionalSide.LONG, criteria=(criterion,))
    short_policy = DirectionalCasePolicy(side=DirectionalSide.SHORT, criteria=(criterion,))
    policy = DirectionalPolicy(
        policy_version="directional-v1",
        long_case=long_policy,
        short_case=short_policy,
    )
    long_value = D(2) if decision in (DirectionalSide.LONG, None) else D(0)
    short_value = D(2) if decision in (DirectionalSide.SHORT, None) else D(0)

    def case(side: DirectionalSide, value: Decimal) -> DirectionalCaseInput:
        return DirectionalCaseInput(
            side=side,
            metrics=(
                DirectionalMetric(
                    criterion="support",
                    status=MetricStatus.AVAILABLE,
                    value=value,
                    source_version="directional-source-v1",
                    available_at=START,
                    evidence=(evidence("directional"),),
                ),
            ),
        )

    request = DirectionalAnalysisRequest(
        analysis_id=UUID(int=1),
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        horizon=ForecastHorizon.H4,
        as_of=AS_OF,
        policy=policy,
        long_case=case(DirectionalSide.LONG, long_value),
        short_case=case(DirectionalSide.SHORT, short_value),
    )
    return DirectionalAnalysisEngine(CLOCK).analyze(request, generated_at=AS_OF)


def forecast(
    direction: DirectionalSide = DirectionalSide.LONG,
    *,
    status: ForecastStatus = ForecastStatus.AVAILABLE,
    calibration: CalibrationStatus = CalibrationStatus.CALIBRATED,
    generated_at: datetime = START + timedelta(hours=1),
) -> Forecast:
    expiry = generated_at + timedelta(hours=4)
    common: dict[str, object] = {
        "forecast_id": UUID(int=2),
        "market_id": "test-market",
        "asset_id": "test-asset",
        "candle_timeframe": Timeframe.H1,
        "horizon": ForecastHorizon.H4,
        "generated_at": generated_at,
        "expires_at": expiry,
        "reference_price": D(100),
        "status": status,
        "model_version": "forecast-v1",
        "model_stage": ModelStage.RESEARCH,
        "feature_version": "features-v1",
        "dataset_hash": "b" * 64,
        "evidence": (evidence("forecast", generated_at),),
    }
    if status == ForecastStatus.UNAVAILABLE:
        common["unavailable_reason"] = "MODEL_INPUT_UNAVAILABLE"
        return Forecast.model_validate(common)
    is_long = direction == DirectionalSide.LONG
    common.update(
        direction=ForecastDirection.UP if is_long else ForecastDirection.DOWN,
        probabilities=(
            ProbabilityValue(
                direction=ForecastDirection.UP, probability=D("0.60" if is_long else "0.25")
            ),
            ProbabilityValue(
                direction=ForecastDirection.DOWN, probability=D("0.25" if is_long else "0.60")
            ),
            ProbabilityValue(direction=ForecastDirection.RANGE, probability=D("0.15")),
        ),
        expected_return=D("0.04" if is_long else "-0.04"),
        expected_move=D("0.08"),
        range_threshold=D("0.01"),
        expected_low_return=D("-0.02" if is_long else "-0.10"),
        expected_high_return=D("0.10" if is_long else "0.02"),
        confidence=D("0.60"),
        probability_calibration=calibration,
        regime="trend",
    )
    return Forecast.model_validate(common)


def context(
    *,
    liquidity: str | None = "0.80",
    uncertainty: str | None = "0.20",
    available_at: datetime = START,
) -> tuple[OpportunityContextMetric, OpportunityContextMetric]:
    def metric(kind: OpportunityMetricKind, value: str | None) -> OpportunityContextMetric:
        if value is None:
            return OpportunityContextMetric(
                kind=kind,
                status=OpportunityMetricStatus.UNAVAILABLE,
                source_version="context-v1",
                unavailable_reason="SOURCE_UNAVAILABLE",
            )
        return OpportunityContextMetric(
            kind=kind,
            status=OpportunityMetricStatus.AVAILABLE,
            value=D(value),
            source_version="context-v1",
            available_at=available_at,
            evidence=(evidence(kind.value.lower(), available_at),),
        )

    return (
        metric(OpportunityMetricKind.LIQUIDITY, liquidity),
        metric(OpportunityMetricKind.UNCERTAINTY, uncertainty),
    )


def request(
    *,
    opportunity_id: int = 3,
    analysis: DirectionalAnalysis | None = None,
    prediction: Forecast | None = None,
    policy: OpportunityPolicy = POLICY,
    costs: EconomicCostSpec = COSTS,
    metrics: tuple[OpportunityContextMetric, OpportunityContextMetric] | None = None,
) -> OpportunityScoreRequest:
    return OpportunityScoreRequest(
        opportunity_id=UUID(int=opportunity_id),
        analysis=analysis or directional(),
        forecast=prediction or forecast(),
        policy=policy,
        costs=costs,
        context=metrics or context(),
    )


def test_long_opportunity_exposes_net_economics_and_every_component() -> None:
    result = ENGINE.calculate(request(), generated_at=GENERATED)
    assert result.status == OpportunityStatus.AVAILABLE
    assert result.direction == DirectionalSide.LONG
    assert result.eligible is True
    assert result.economics is not None
    assert result.economics.directional_probability == D("0.600000000000000000000000000000")
    assert result.economics.directional_expected_return == D("0.040000000000000000000000000000")
    assert result.economics.total_cost_rate == D("0.003000000000000000000000000000")
    assert result.economics.net_expected_return == D("0.037000000000000000000000000000")
    assert result.economics.risk_reward == D("5.000000000000000000000000000000")
    assert tuple(item.component for item in result.components) == tuple(OpportunityComponentName)
    assert result.score == D("73.303571428571428571428571428571")
    assert result.score != result.economics.directional_probability * 100


def test_short_opportunity_signs_expected_return_and_range_for_the_short_side() -> None:
    result = ENGINE.calculate(
        request(
            analysis=directional(DirectionalSide.SHORT), prediction=forecast(DirectionalSide.SHORT)
        ),
        generated_at=GENERATED,
    )
    assert result.direction == DirectionalSide.SHORT
    assert result.economics is not None
    assert result.economics.directional_expected_return == D("0.040000000000000000000000000000")
    assert result.economics.reward_return == D("0.100000000000000000000000000000")
    assert result.economics.loss_return == D("0.020000000000000000000000000000")


def test_economic_limits_make_score_available_but_ineligible() -> None:
    strict = POLICY.model_copy(
        update={
            "minimum_net_return": D("0.05"),
            "target_net_return": D("0.06"),
            "minimum_directional_probability": D("0.65"),
            "minimum_expected_move": D("0.09"),
            "maximum_total_cost": D("0.002"),
            "minimum_liquidity": D("0.90"),
            "maximum_uncertainty": D("0.10"),
            "minimum_risk_reward": D("6"),
            "target_risk_reward": D("7"),
        }
    )
    result = ENGINE.calculate(request(policy=strict), generated_at=GENERATED)
    assert result.status == OpportunityStatus.AVAILABLE
    assert result.eligible is False
    assert result.exclusion_reasons == tuple(OpportunityExclusionReason)
    assert result.score is not None


def test_costs_are_explicit_and_lower_net_edge_and_score() -> None:
    low = ENGINE.calculate(request(), generated_at=GENERATED)
    expensive_costs = COSTS.model_copy(update={"round_trip_slippage_bps": D(60)})
    high = ENGINE.calculate(request(costs=expensive_costs), generated_at=GENERATED)
    assert low.economics is not None and high.economics is not None
    assert high.economics.net_expected_return < low.economics.net_expected_return
    assert high.score is not None and low.score is not None and high.score < low.score
    assert high.input_hash != low.input_hash


@pytest.mark.parametrize(
    ("subject", "reason"),
    (
        (request(analysis=directional(None)), "DIRECTIONAL_NO_TRADE"),
        (request(prediction=forecast(status=ForecastStatus.UNAVAILABLE)), "FORECAST_UNAVAILABLE"),
        (
            request(prediction=forecast(calibration=CalibrationStatus.UNCALIBRATED)),
            "FORECAST_UNCALIBRATED",
        ),
        (request(metrics=context(liquidity=None)), "CONTEXT_UNAVAILABLE"),
    ),
)
def test_incomplete_inputs_fail_closed_without_partial_score(
    subject: OpportunityScoreRequest, reason: str
) -> None:
    result = ENGINE.calculate(subject, generated_at=GENERATED)
    assert result.status == OpportunityStatus.UNAVAILABLE
    assert result.unavailable_reason == reason
    assert result.score is None
    assert result.economics is None
    assert result.eligible is None
    assert result.components == ()


def test_expired_forecast_and_missing_downside_fail_closed() -> None:
    old = forecast(generated_at=START - timedelta(hours=4))
    expired = ENGINE.calculate(request(prediction=old), generated_at=GENERATED)
    assert expired.unavailable_reason == "FORECAST_EXPIRED"
    no_downside = forecast().model_copy(update={"expected_low_return": D("0.01")})
    result = ENGINE.calculate(request(prediction=no_downside), generated_at=GENERATED)
    assert result.unavailable_reason == "DOWNSIDE_ESTIMATE_UNAVAILABLE"


def test_temporal_integrity_rejects_future_inputs_and_outputs() -> None:
    late_forecast = forecast(generated_at=AS_OF + timedelta(seconds=1))
    with pytest.raises(ValueError, match="forecast was unavailable"):
        ENGINE.calculate(request(prediction=late_forecast), generated_at=GENERATED)
    with pytest.raises(ValueError, match="context was unavailable"):
        ENGINE.calculate(
            request(metrics=context(available_at=AS_OF + timedelta(seconds=1))),
            generated_at=GENERATED,
        )
    with pytest.raises(ValueError, match="cannot precede directional analysis"):
        ENGINE.calculate(request(), generated_at=START)
    with pytest.raises(ValueError, match="cannot be in the future"):
        ENGINE.calculate(request(), generated_at=CLOCK.now() + timedelta(seconds=1))


def test_request_and_policy_reject_incoherent_configuration() -> None:
    mismatched = forecast().model_copy(update={"asset_id": "other-asset"})
    with pytest.raises(ValidationError, match="identity must match"):
        request(prediction=mismatched)
    with pytest.raises(ValidationError, match="liquidity and uncertainty in order"):
        values = context()
        request(metrics=(values[1], values[0]))
    with pytest.raises(ValidationError, match="target net return"):
        OpportunityPolicy.model_validate(
            {**POLICY.model_dump(), "target_net_return": POLICY.minimum_net_return}
        )
    with pytest.raises(ValidationError, match="maximum total cost"):
        OpportunityPolicy.model_validate({**POLICY.model_dump(), "maximum_total_cost": D(0)})


def test_context_contract_requires_evidence_and_rejects_plausible_missing_values() -> None:
    with pytest.raises(ValidationError, match="only an explicit reason"):
        OpportunityContextMetric(
            kind=OpportunityMetricKind.LIQUIDITY,
            status=OpportunityMetricStatus.UNAVAILABLE,
            value=D("0.8"),
            source_version="v1",
            unavailable_reason="missing",
        )
    with pytest.raises(ValidationError, match="evidence cannot arrive after"):
        OpportunityContextMetric(
            kind=OpportunityMetricKind.LIQUIDITY,
            status=OpportunityMetricStatus.AVAILABLE,
            value=D("0.8"),
            source_version="v1",
            available_at=START,
            evidence=(evidence("late", START + timedelta(seconds=1)),),
        )


def test_ranking_orders_eligible_scores_and_preserves_exclusions() -> None:
    first = ENGINE.calculate(request(opportunity_id=30), generated_at=GENERATED)
    weaker_forecast = forecast().model_copy(update={"expected_return": D("0.03")})
    weaker = ENGINE.calculate(
        request(opportunity_id=20, prediction=weaker_forecast), generated_at=GENERATED
    )
    excluded = ENGINE.calculate(
        request(opportunity_id=10, metrics=context(liquidity="0.40")),
        generated_at=GENERATED,
    )
    unavailable = ENGINE.calculate(
        request(opportunity_id=5, analysis=directional(None)), generated_at=GENERATED
    )
    ranking = ENGINE.rank(
        UUID(int=50),
        (weaker, excluded, first, unavailable),
        ranked_at=GENERATED + timedelta(hours=1),
    )
    assert tuple(item.opportunity.opportunity_id for item in ranking.entries) == (
        first.opportunity_id,
        weaker.opportunity_id,
    )
    assert tuple(item.rank for item in ranking.entries) == (1, 2)
    assert tuple(item.opportunity_id for item in ranking.excluded) == (
        unavailable.opportunity_id,
        excluded.opportunity_id,
    )


def test_ranking_has_stable_uuid_tie_break_and_rejects_incomparable_scores() -> None:
    higher_id = ENGINE.calculate(request(opportunity_id=9), generated_at=GENERATED)
    lower_id = higher_id.model_copy(update={"opportunity_id": UUID(int=8)})
    ranking = ENGINE.rank(
        UUID(int=50), (higher_id, lower_id), ranked_at=GENERATED + timedelta(hours=1)
    )
    assert tuple(item.opportunity.opportunity_id for item in ranking.entries) == (
        UUID(int=8),
        UUID(int=9),
    )
    with pytest.raises(ValueError, match="share horizon, as-of and policy"):
        ENGINE.rank(
            UUID(int=51),
            (higher_id, lower_id.model_copy(update={"horizon": ForecastHorizon.H8})),
            ranked_at=GENERATED + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="duplicate"):
        ENGINE.rank(UUID(int=52), (higher_id, higher_id), ranked_at=GENERATED + timedelta(hours=1))


def test_output_models_are_immutable() -> None:
    result = ENGINE.calculate(request(), generated_at=GENERATED)
    with pytest.raises(ValidationError, match="frozen"):
        result.score = D(99)
