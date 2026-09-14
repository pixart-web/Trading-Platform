from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.directional.models import DirectionalAnalysis, DirectionalSide
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.forecasts.models import EvidenceSnapshot, Forecast
from pocket_alpha.forecasts.research_models import EconomicCostSpec

D = Decimal
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Ratio = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=30)]
ScoreValue = Annotated[Decimal, Field(ge=0, le=100, max_digits=38, decimal_places=30)]
Weight = Annotated[Decimal, Field(gt=0, le=1000, max_digits=38, decimal_places=30)]
EconomicReturn = Annotated[Decimal, Field(max_digits=38, decimal_places=30)]
NonNegativeReturn = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=30)]
RiskReward = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=30)]


class OpportunityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class OpportunityMetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class OpportunityMetricKind(StrEnum):
    LIQUIDITY = "LIQUIDITY"
    UNCERTAINTY = "UNCERTAINTY"


class OpportunityComponentName(StrEnum):
    NET_EDGE = "NET_EDGE"
    DIRECTIONAL_PROBABILITY = "DIRECTIONAL_PROBABILITY"
    EXPECTED_MOVE = "EXPECTED_MOVE"
    COST_EFFICIENCY = "COST_EFFICIENCY"
    LIQUIDITY = "LIQUIDITY"
    UNCERTAINTY = "UNCERTAINTY"
    RISK_REWARD = "RISK_REWARD"


class OpportunityExclusionReason(StrEnum):
    NET_RETURN_BELOW_MINIMUM = "NET_RETURN_BELOW_MINIMUM"
    PROBABILITY_BELOW_MINIMUM = "PROBABILITY_BELOW_MINIMUM"
    EXPECTED_MOVE_BELOW_MINIMUM = "EXPECTED_MOVE_BELOW_MINIMUM"
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    UNCERTAINTY_LIMIT_EXCEEDED = "UNCERTAINTY_LIMIT_EXCEEDED"
    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"


class OpportunityWeights(DomainModel):
    net_edge: Weight
    directional_probability: Weight
    expected_move: Weight
    cost_efficiency: Weight
    liquidity: Weight
    uncertainty: Weight
    risk_reward: Weight


class OpportunityPolicy(DomainModel):
    schema_version: Literal["opportunity-policy-1.0.0"] = "opportunity-policy-1.0.0"
    policy_version: Identifier
    minimum_net_return: EconomicReturn
    target_net_return: EconomicReturn
    minimum_directional_probability: Ratio
    target_directional_probability: Ratio
    minimum_expected_move: NonNegativeReturn
    target_expected_move: NonNegativeReturn
    maximum_total_cost: NonNegativeReturn
    minimum_liquidity: Ratio
    maximum_uncertainty: Ratio
    minimum_risk_reward: RiskReward
    target_risk_reward: RiskReward
    weights: OpportunityWeights

    @model_validator(mode="after")
    def ordered_thresholds(self) -> Self:
        if self.target_net_return <= self.minimum_net_return:
            raise ValueError("target net return must exceed its minimum")
        if self.target_directional_probability <= self.minimum_directional_probability:
            raise ValueError("target directional probability must exceed its minimum")
        if self.target_expected_move <= self.minimum_expected_move:
            raise ValueError("target expected move must exceed its minimum")
        if self.maximum_total_cost <= 0:
            raise ValueError("maximum total cost must be positive")
        if self.target_risk_reward <= self.minimum_risk_reward:
            raise ValueError("target risk/reward must exceed its minimum")
        return self


class OpportunityContextMetric(DomainModel):
    kind: OpportunityMetricKind
    status: OpportunityMetricStatus
    value: Ratio | None = None
    source_version: Identifier
    available_at: UTCDateTime | None = None
    unavailable_reason: Identifier | None = None
    evidence: tuple[EvidenceSnapshot, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.status == OpportunityMetricStatus.UNAVAILABLE:
            if (
                self.value is not None
                or self.available_at is not None
                or self.unavailable_reason is None
                or self.evidence
            ):
                raise ValueError("unavailable opportunity metric requires only an explicit reason")
            return self
        if (
            self.value is None
            or self.available_at is None
            or self.unavailable_reason is not None
            or not self.evidence
        ):
            raise ValueError("available opportunity metric requires value, time and evidence")
        if any(item.available_at > self.available_at for item in self.evidence):
            raise ValueError("opportunity evidence cannot arrive after metric availability")
        return self


class OpportunityScoreRequest(DomainModel):
    opportunity_id: UUID
    analysis: DirectionalAnalysis
    forecast: Forecast
    policy: OpportunityPolicy
    costs: EconomicCostSpec
    context: tuple[OpportunityContextMetric, OpportunityContextMetric]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        identity = (
            self.analysis.market_id,
            self.analysis.asset_id,
            self.analysis.candle_timeframe,
            self.analysis.horizon,
        )
        forecast_identity = (
            self.forecast.market_id,
            self.forecast.asset_id,
            self.forecast.candle_timeframe,
            self.forecast.horizon,
        )
        if identity != forecast_identity:
            raise ValueError("forecast and directional analysis identity must match")
        kinds = tuple(item.kind for item in self.context)
        if kinds != tuple(OpportunityMetricKind):
            raise ValueError("opportunity context requires liquidity and uncertainty in order")
        return self


class OpportunityEconomics(DomainModel):
    directional_probability: Ratio
    directional_expected_return: EconomicReturn
    expected_move: NonNegativeReturn
    reward_return: NonNegativeReturn
    loss_return: NonNegativeReturn
    risk_reward: RiskReward
    total_cost_rate: NonNegativeReturn
    net_expected_return: EconomicReturn
    liquidity: Ratio
    uncertainty: Ratio


class OpportunityComponentExplanation(DomainModel):
    component: OpportunityComponentName
    raw_value: Decimal
    normalized_score: ScoreValue
    configured_weight: Weight
    effective_weight: Ratio
    contribution: ScoreValue


class OpportunityScore(DomainModel):
    schema_version: Literal["opportunity-score-1.0.0"] = "opportunity-score-1.0.0"
    opportunity_id: UUID
    market_id: Identifier
    asset_id: AssetId
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    as_of: UTCDateTime
    generated_at: UTCDateTime
    direction: DirectionalSide | None = None
    status: OpportunityStatus
    eligible: bool | None = None
    unavailable_reason: Identifier | None = None
    exclusion_reasons: tuple[OpportunityExclusionReason, ...] = ()
    score: ScoreValue | None = None
    economics: OpportunityEconomics | None = None
    components: tuple[OpportunityComponentExplanation, ...] = Field(default=(), max_length=7)
    analysis_id: UUID
    forecast_id: UUID
    policy_version: Identifier
    policy_hash: Hash
    input_hash: Hash
    cost_version: Identifier

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("Opportunity Score cannot be generated before its as-of time")
        calculated = (self.direction, self.eligible, self.score, self.economics)
        if self.status == OpportunityStatus.UNAVAILABLE:
            if any(item is not None for item in calculated) or self.unavailable_reason is None:
                raise ValueError("unavailable Opportunity Score requires only an explicit reason")
            if self.exclusion_reasons or self.components:
                raise ValueError("unavailable Opportunity Score cannot expose partial calculations")
            return self
        if any(item is None for item in calculated) or self.unavailable_reason is not None:
            raise ValueError("available Opportunity Score requires complete economics")
        if tuple(item.component for item in self.components) != tuple(OpportunityComponentName):
            raise ValueError("Opportunity Score explanations must use canonical components")
        if self.eligible != (not self.exclusion_reasons):
            raise ValueError("eligibility must match the exclusion reasons")
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            if sum((item.effective_weight for item in self.components), D(0)) != 1:
                raise ValueError("effective opportunity weights must sum exactly to one")
            if self.score != sum((item.contribution for item in self.components), D(0)):
                raise ValueError("Opportunity Score must equal explained contributions")
        return self


class OpportunityRankEntry(DomainModel):
    rank: int = Field(ge=1, le=1000)
    opportunity: OpportunityScore

    @model_validator(mode="after")
    def eligible_opportunity(self) -> Self:
        if self.opportunity.status != OpportunityStatus.AVAILABLE or not self.opportunity.eligible:
            raise ValueError("ranked opportunity must be available and eligible")
        return self


class OpportunityRanking(DomainModel):
    schema_version: Literal["opportunity-ranking-1.0.0"] = "opportunity-ranking-1.0.0"
    ranking_id: UUID
    horizon: ForecastHorizon
    as_of: UTCDateTime
    ranked_at: UTCDateTime
    policy_version: Identifier
    policy_hash: Hash
    entries: tuple[OpportunityRankEntry, ...] = Field(max_length=1000)
    excluded: tuple[OpportunityScore, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.ranked_at < self.as_of:
            raise ValueError("opportunity ranking cannot precede its as-of time")
        if tuple(item.rank for item in self.entries) != tuple(range(1, len(self.entries) + 1)):
            raise ValueError("opportunity ranking positions must be contiguous")
        all_scores = tuple(item.opportunity for item in self.entries) + self.excluded
        if len({item.opportunity_id for item in all_scores}) != len(all_scores):
            raise ValueError("opportunity ranking cannot contain duplicate opportunities")
        for item in all_scores:
            if (
                item.horizon != self.horizon
                or item.as_of != self.as_of
                or item.policy_version != self.policy_version
                or item.policy_hash != self.policy_hash
            ):
                raise ValueError("ranked opportunities must share horizon, as-of and policy")
        if any(
            item.status == OpportunityStatus.AVAILABLE and item.eligible for item in self.excluded
        ):
            raise ValueError("eligible opportunities cannot be excluded from ranking")
        return self
