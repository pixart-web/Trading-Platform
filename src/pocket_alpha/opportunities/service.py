import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import UUID

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.directional.models import DirectionalDecision, DirectionalSide
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    ForecastDirection,
    ForecastStatus,
)
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.opportunities.models import (
    OpportunityComponentExplanation,
    OpportunityComponentName,
    OpportunityEconomics,
    OpportunityExclusionReason,
    OpportunityMetricKind,
    OpportunityMetricStatus,
    OpportunityPolicy,
    OpportunityRankEntry,
    OpportunityRanking,
    OpportunityScore,
    OpportunityScoreRequest,
    OpportunityStatus,
)

D = Decimal
RESOLUTION = D("1e-30")


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _published(value: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return value.quantize(RESOLUTION)


def _normalized(value: Decimal, minimum: Decimal, target: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        ratio = (value - minimum) / (target - minimum)
        return _published(min(max(ratio, D(0)), D(1)) * 100)


def _unavailable(
    request: OpportunityScoreRequest,
    generated_at: datetime,
    reason: str,
) -> OpportunityScore:
    return OpportunityScore(
        opportunity_id=request.opportunity_id,
        market_id=request.analysis.market_id,
        asset_id=request.analysis.asset_id,
        candle_timeframe=request.analysis.candle_timeframe,
        horizon=request.analysis.horizon,
        as_of=request.analysis.as_of,
        generated_at=generated_at,
        status=OpportunityStatus.UNAVAILABLE,
        unavailable_reason=reason,
        analysis_id=request.analysis.analysis_id,
        forecast_id=request.forecast.forecast_id,
        policy_version=request.policy.policy_version,
        policy_hash=fingerprint(request.policy.model_dump()),
        input_hash=fingerprint(
            {
                "analysis": request.analysis.model_dump(),
                "forecast": request.forecast.model_dump(),
                "costs": request.costs.model_dump(),
                "context": [item.model_dump() for item in request.context],
            }
        ),
        cost_version=request.costs.version,
    )


def _probability(request: OpportunityScoreRequest, direction: DirectionalSide) -> Decimal:
    forecast_direction = (
        ForecastDirection.UP if direction == DirectionalSide.LONG else ForecastDirection.DOWN
    )
    for item in request.forecast.probabilities:
        if item.direction == forecast_direction:
            return item.probability
    raise ValueError("available forecast is missing a directional probability")


def _economics(
    request: OpportunityScoreRequest, direction: DirectionalSide
) -> OpportunityEconomics | None:
    forecast = request.forecast
    assert forecast.expected_return is not None
    assert forecast.expected_move is not None
    assert forecast.expected_low_return is not None
    assert forecast.expected_high_return is not None
    context = {item.kind: item.value for item in request.context}
    liquidity = context[OpportunityMetricKind.LIQUIDITY]
    uncertainty = context[OpportunityMetricKind.UNCERTAINTY]
    assert liquidity is not None
    assert uncertainty is not None
    if direction == DirectionalSide.LONG:
        directional_return = forecast.expected_return
        reward = max(forecast.expected_high_return, D(0))
        loss = max(-forecast.expected_low_return, D(0))
    else:
        directional_return = -forecast.expected_return
        reward = max(-forecast.expected_low_return, D(0))
        loss = max(forecast.expected_high_return, D(0))
    if loss == 0:
        return None
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        total_cost = request.costs.total_rate
        return OpportunityEconomics(
            directional_probability=_published(_probability(request, direction)),
            directional_expected_return=_published(directional_return),
            expected_move=_published(forecast.expected_move),
            reward_return=_published(reward),
            loss_return=_published(loss),
            risk_reward=_published(reward / loss),
            total_cost_rate=_published(total_cost),
            net_expected_return=_published(directional_return - total_cost),
            liquidity=_published(liquidity),
            uncertainty=_published(uncertainty),
        )


def _exclusions(
    economics: OpportunityEconomics, policy: OpportunityPolicy
) -> tuple[OpportunityExclusionReason, ...]:
    reasons = []
    if economics.net_expected_return < policy.minimum_net_return:
        reasons.append(OpportunityExclusionReason.NET_RETURN_BELOW_MINIMUM)
    if economics.directional_probability < policy.minimum_directional_probability:
        reasons.append(OpportunityExclusionReason.PROBABILITY_BELOW_MINIMUM)
    if economics.expected_move < policy.minimum_expected_move:
        reasons.append(OpportunityExclusionReason.EXPECTED_MOVE_BELOW_MINIMUM)
    if economics.total_cost_rate > policy.maximum_total_cost:
        reasons.append(OpportunityExclusionReason.COST_LIMIT_EXCEEDED)
    if economics.liquidity < policy.minimum_liquidity:
        reasons.append(OpportunityExclusionReason.LIQUIDITY_BELOW_MINIMUM)
    if economics.uncertainty > policy.maximum_uncertainty:
        reasons.append(OpportunityExclusionReason.UNCERTAINTY_LIMIT_EXCEEDED)
    if economics.risk_reward < policy.minimum_risk_reward:
        reasons.append(OpportunityExclusionReason.RISK_REWARD_BELOW_MINIMUM)
    return tuple(reasons)


def _components(
    economics: OpportunityEconomics, policy: OpportunityPolicy
) -> tuple[OpportunityComponentExplanation, ...]:
    values = (
        (
            OpportunityComponentName.NET_EDGE,
            economics.net_expected_return,
            _normalized(
                economics.net_expected_return,
                policy.minimum_net_return,
                policy.target_net_return,
            ),
            policy.weights.net_edge,
        ),
        (
            OpportunityComponentName.DIRECTIONAL_PROBABILITY,
            economics.directional_probability,
            _normalized(
                economics.directional_probability,
                policy.minimum_directional_probability,
                policy.target_directional_probability,
            ),
            policy.weights.directional_probability,
        ),
        (
            OpportunityComponentName.EXPECTED_MOVE,
            economics.expected_move,
            _normalized(
                economics.expected_move,
                policy.minimum_expected_move,
                policy.target_expected_move,
            ),
            policy.weights.expected_move,
        ),
        (
            OpportunityComponentName.COST_EFFICIENCY,
            economics.total_cost_rate,
            _published(
                max(D(0), D(1) - economics.total_cost_rate / policy.maximum_total_cost) * 100
            ),
            policy.weights.cost_efficiency,
        ),
        (
            OpportunityComponentName.LIQUIDITY,
            economics.liquidity,
            _published(economics.liquidity * 100),
            policy.weights.liquidity,
        ),
        (
            OpportunityComponentName.UNCERTAINTY,
            economics.uncertainty,
            _published((D(1) - economics.uncertainty) * 100),
            policy.weights.uncertainty,
        ),
        (
            OpportunityComponentName.RISK_REWARD,
            economics.risk_reward,
            _normalized(
                economics.risk_reward,
                policy.minimum_risk_reward,
                policy.target_risk_reward,
            ),
            policy.weights.risk_reward,
        ),
    )
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        total_weight = sum((item[3] for item in values), D(0))
        score = _published(sum((item[2] * item[3] for item in values), D(0)) / total_weight)
        effective: list[Decimal] = []
        contributions: list[Decimal] = []
        for index, item in enumerate(values):
            if index == len(values) - 1:
                effective.append(D(1) - sum(effective, D(0)))
                contributions.append(score - sum(contributions, D(0)))
            else:
                effective.append(_published(item[3] / total_weight))
                contributions.append(_published(item[2] * item[3] / total_weight))
    return tuple(
        OpportunityComponentExplanation(
            component=item[0],
            raw_value=item[1],
            normalized_score=item[2],
            configured_weight=item[3],
            effective_weight=effective[index],
            contribution=contributions[index],
        )
        for index, item in enumerate(values)
    )


class OpportunityScoreEngine:
    """Calculate auditable net economics without producing a probability or risk approval."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def calculate(
        self, request: OpportunityScoreRequest, *, generated_at: datetime
    ) -> OpportunityScore:
        generated_at = utc(generated_at)
        now = utc(self.clock.now())
        if request.analysis.as_of > now:
            raise ValueError("Opportunity Score as-of time cannot be in the future")
        if generated_at > now:
            raise ValueError("Opportunity Score generation cannot be in the future")
        if generated_at < request.analysis.generated_at:
            raise ValueError("Opportunity Score cannot precede directional analysis")
        if request.forecast.generated_at > request.analysis.as_of:
            raise ValueError("forecast was unavailable at the Opportunity Score as-of time")
        for item in request.context:
            if item.available_at is not None and item.available_at > request.analysis.as_of:
                raise ValueError("opportunity context was unavailable at the as-of time")

        if request.analysis.decision == DirectionalDecision.NO_TRADE:
            return _unavailable(request, generated_at, "DIRECTIONAL_NO_TRADE")
        if request.forecast.status == ForecastStatus.UNAVAILABLE:
            return _unavailable(request, generated_at, "FORECAST_UNAVAILABLE")
        if request.forecast.expires_at <= request.analysis.as_of:
            return _unavailable(request, generated_at, "FORECAST_EXPIRED")
        if request.forecast.probability_calibration != CalibrationStatus.CALIBRATED:
            return _unavailable(request, generated_at, "FORECAST_UNCALIBRATED")
        if any(item.status == OpportunityMetricStatus.UNAVAILABLE for item in request.context):
            return _unavailable(request, generated_at, "CONTEXT_UNAVAILABLE")

        direction = DirectionalSide(request.analysis.decision.value)
        economics = _economics(request, direction)
        if economics is None:
            return _unavailable(request, generated_at, "DOWNSIDE_ESTIMATE_UNAVAILABLE")
        components = _components(economics, request.policy)
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            score = sum((item.contribution for item in components), D(0))
        exclusions = _exclusions(economics, request.policy)
        return OpportunityScore(
            opportunity_id=request.opportunity_id,
            market_id=request.analysis.market_id,
            asset_id=request.analysis.asset_id,
            candle_timeframe=request.analysis.candle_timeframe,
            horizon=request.analysis.horizon,
            as_of=request.analysis.as_of,
            generated_at=generated_at,
            direction=direction,
            status=OpportunityStatus.AVAILABLE,
            eligible=not exclusions,
            exclusion_reasons=exclusions,
            score=score,
            economics=economics,
            components=components,
            analysis_id=request.analysis.analysis_id,
            forecast_id=request.forecast.forecast_id,
            policy_version=request.policy.policy_version,
            policy_hash=fingerprint(request.policy.model_dump()),
            input_hash=fingerprint(
                {
                    "analysis": request.analysis.model_dump(),
                    "forecast": request.forecast.model_dump(),
                    "costs": request.costs.model_dump(),
                    "context": [item.model_dump() for item in request.context],
                }
            ),
            cost_version=request.costs.version,
        )

    def rank(
        self,
        ranking_id: UUID,
        scores: tuple[OpportunityScore, ...],
        *,
        ranked_at: datetime,
    ) -> OpportunityRanking:
        if not 1 <= len(scores) <= 1000:
            raise ValueError("opportunity ranking requires 1..1000 scores")
        ranked_at = utc(ranked_at)
        if ranked_at > utc(self.clock.now()):
            raise ValueError("opportunity ranking cannot be generated in the future")
        first = scores[0]
        if len({item.opportunity_id for item in scores}) != len(scores):
            raise ValueError("opportunity ranking cannot contain duplicate opportunities")
        if any(
            (
                item.horizon,
                item.as_of,
                item.policy_version,
                item.policy_hash,
            )
            != (first.horizon, first.as_of, first.policy_version, first.policy_hash)
            for item in scores
        ):
            raise ValueError("ranked opportunities must share horizon, as-of and policy")
        if any(item.generated_at > ranked_at for item in scores):
            raise ValueError("opportunity score was unavailable at ranking time")
        eligible = tuple(
            item for item in scores if item.status == OpportunityStatus.AVAILABLE and item.eligible
        )
        excluded = tuple(
            sorted(
                (item for item in scores if item not in eligible),
                key=lambda item: str(item.opportunity_id),
            )
        )

        def order(item: OpportunityScore) -> tuple[Decimal, Decimal, str]:
            assert item.score is not None
            assert item.economics is not None
            return (-item.score, -item.economics.net_expected_return, str(item.opportunity_id))

        ordered = tuple(sorted(eligible, key=order))
        return OpportunityRanking(
            ranking_id=ranking_id,
            horizon=first.horizon,
            as_of=first.as_of,
            ranked_at=ranked_at,
            policy_version=first.policy_version,
            policy_hash=first.policy_hash,
            entries=tuple(
                OpportunityRankEntry(rank=index, opportunity=item)
                for index, item in enumerate(ordered, start=1)
            ),
            excluded=excluded,
        )
