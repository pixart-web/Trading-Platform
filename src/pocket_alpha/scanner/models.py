from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.directional.models import DirectionalSide
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, AssetType, DomainModel, ForecastHorizon, Timeframe
from pocket_alpha.opportunities.models import OpportunityScore, OpportunityStatus

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Score = Annotated[Decimal, Field(ge=0, le=100, max_digits=38, decimal_places=30)]
Ratio = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=30)]
Return = Annotated[Decimal, Field(max_digits=38, decimal_places=30)]
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=30)]


class ScanStatus(StrEnum):
    RESULTS = "RESULTS"
    NO_MATCHES = "NO_MATCHES"


class ScanExclusionReason(StrEnum):
    NO_ANALYZE_REPORT = "NO_ANALYZE_REPORT"
    REPORT_UNAVAILABLE_AT_SCAN = "REPORT_UNAVAILABLE_AT_SCAN"
    OPPORTUNITY_NOT_PRODUCED = "OPPORTUNITY_NOT_PRODUCED"
    OPPORTUNITY_UNAVAILABLE = "OPPORTUNITY_UNAVAILABLE"
    OPPORTUNITY_INELIGIBLE = "OPPORTUNITY_INELIGIBLE"
    DIRECTION_FILTERED = "DIRECTION_FILTERED"
    SCORE_BELOW_MINIMUM = "SCORE_BELOW_MINIMUM"
    NET_RETURN_BELOW_MINIMUM = "NET_RETURN_BELOW_MINIMUM"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    UNCERTAINTY_ABOVE_MAXIMUM = "UNCERTAINTY_ABOVE_MAXIMUM"
    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"
    COST_ABOVE_MAXIMUM = "COST_ABOVE_MAXIMUM"
    POLICY_RESULT_LIMIT = "POLICY_RESULT_LIMIT"


class ScanFilters(DomainModel):
    asset_types: tuple[AssetType, ...] = ()
    venue_ids: tuple[Identifier, ...] = ()
    quote_currencies: tuple[str, ...] = Field(default=(), max_length=32)
    market_ids: tuple[Identifier, ...] = Field(default=(), max_length=1000)
    directions: tuple[DirectionalSide, ...] = (
        DirectionalSide.LONG,
        DirectionalSide.SHORT,
    )
    minimum_score: Score | None = None
    minimum_net_return: Return | None = None
    minimum_liquidity: Ratio | None = None
    maximum_uncertainty: Ratio | None = None
    minimum_risk_reward: NonNegative | None = None
    maximum_total_cost: NonNegative | None = None
    max_results_per_policy: int = Field(default=100, ge=1, le=250)

    @model_validator(mode="after")
    def canonical(self) -> Self:
        sequences = (
            self.asset_types,
            self.venue_ids,
            self.quote_currencies,
            self.market_ids,
        )
        if any(tuple(sorted(set(values))) != values for values in sequences):
            raise ValueError("scanner universe filters must be unique and sorted")
        expected_directions = tuple(side for side in DirectionalSide if side in self.directions)
        if not self.directions or self.directions != expected_directions:
            raise ValueError("scanner directions must be unique and canonical")
        if any(
            not currency.isupper() or not currency.isalnum() or not 2 <= len(currency) <= 12
            for currency in self.quote_currencies
        ):
            raise ValueError("scanner quote currencies must be canonical")
        return self


class ScanRequest(DomainModel):
    schema_version: Literal["scan-request-1.0.0"] = "scan-request-1.0.0"
    scan_id: UUID
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    as_of: UTCDateTime
    filters: ScanFilters = ScanFilters()
    scanner_version: Literal["scanner-1.0.0"] = "scanner-1.0.0"


class ScanMarket(DomainModel):
    market_id: Identifier
    asset_id: AssetId
    symbol: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    asset_type: AssetType
    venue_id: Identifier
    quote_currency: str = Field(pattern=r"^[A-Z0-9]{2,12}$")


class ScanRankEntry(DomainModel):
    rank: int = Field(ge=1, le=250)
    market: ScanMarket
    report_id: UUID
    opportunity: OpportunityScore


class ScanPolicyGroup(DomainModel):
    policy_version: Identifier
    policy_hash: Hash
    entries: tuple[ScanRankEntry, ...] = Field(max_length=250)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(entry.rank for entry in self.entries) != tuple(range(1, len(self.entries) + 1)):
            raise ValueError("scanner ranks must be contiguous within a policy")
        for entry in self.entries:
            opportunity = entry.opportunity
            if (
                opportunity.status != OpportunityStatus.AVAILABLE
                or not opportunity.eligible
                or opportunity.policy_version != self.policy_version
                or opportunity.policy_hash != self.policy_hash
                or opportunity.market_id != entry.market.market_id
                or opportunity.asset_id != entry.market.asset_id
            ):
                raise ValueError("scanner entry must be an eligible comparable opportunity")
        return self


class ScanExclusion(DomainModel):
    market: ScanMarket
    report_id: UUID | None = None
    opportunity: OpportunityScore | None = None
    reasons: tuple[ScanExclusionReason, ...] = Field(min_length=1, max_length=13)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(dict.fromkeys(self.reasons)) != self.reasons:
            raise ValueError("scanner exclusion reasons must be unique")
        if self.opportunity is not None:
            if self.report_id is None:
                raise ValueError("excluded opportunity requires its Analyze report")
            if (
                self.opportunity.market_id != self.market.market_id
                or self.opportunity.asset_id != self.market.asset_id
            ):
                raise ValueError("excluded opportunity identity must match its market")
        return self


class ScanReport(DomainModel):
    schema_version: Literal["scan-report-1.0.0"] = "scan-report-1.0.0"
    scan_id: UUID
    candle_timeframe: Timeframe
    horizon: ForecastHorizon
    as_of: UTCDateTime
    generated_at: UTCDateTime
    scanner_version: Literal["scanner-1.0.0"] = "scanner-1.0.0"
    filters: ScanFilters
    status: ScanStatus
    universe_size: int = Field(ge=0, le=1000)
    analyze_reports_found: int = Field(ge=0, le=1000)
    groups: tuple[ScanPolicyGroup, ...] = Field(max_length=1000)
    excluded: tuple[ScanExclusion, ...] = Field(max_length=1000)
    input_hash: Hash

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("scan cannot be generated before its as-of time")
        if (
            tuple(sorted(self.groups, key=lambda group: (group.policy_version, group.policy_hash)))
            != self.groups
        ):
            raise ValueError("scanner policy groups must use canonical order")
        ranked = tuple(entry for group in self.groups for entry in group.entries)
        market_ids = tuple(entry.market.market_id for entry in ranked) + tuple(
            item.market.market_id for item in self.excluded
        )
        if len(set(market_ids)) != len(market_ids) or len(market_ids) != self.universe_size:
            raise ValueError("every universe market must appear exactly once in scan results")
        if self.analyze_reports_found > self.universe_size:
            raise ValueError("Analyze report count cannot exceed scan universe")
        reports_found = len(ranked) + sum(item.report_id is not None for item in self.excluded)
        if self.analyze_reports_found != reports_found:
            raise ValueError("Analyze report count must match scan contents")
        expected = ScanStatus.RESULTS if ranked else ScanStatus.NO_MATCHES
        if self.status != expected:
            raise ValueError("scan status must match ranked results")
        for entry in ranked:
            ranked_opportunity = entry.opportunity
            if (
                ranked_opportunity.candle_timeframe != self.candle_timeframe
                or ranked_opportunity.horizon != self.horizon
                or ranked_opportunity.as_of != self.as_of
                or ranked_opportunity.generated_at > self.generated_at
            ):
                raise ValueError("scanner entry must match scan identity and availability")
        for item in self.excluded:
            excluded_opportunity = item.opportunity
            if excluded_opportunity is not None and (
                excluded_opportunity.candle_timeframe != self.candle_timeframe
                or excluded_opportunity.horizon != self.horizon
                or excluded_opportunity.as_of != self.as_of
                or excluded_opportunity.generated_at > self.generated_at
            ):
                raise ValueError("excluded opportunity must match scan identity and availability")
        return self
