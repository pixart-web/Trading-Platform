import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.opportunities.models import OpportunityScore, OpportunityStatus
from pocket_alpha.opportunities.service import OpportunityScoreEngine
from pocket_alpha.scanner.models import (
    ScanExclusion,
    ScanExclusionReason,
    ScanMarket,
    ScanPolicyGroup,
    ScanRankEntry,
    ScanReport,
    ScanRequest,
    ScanStatus,
)
from pocket_alpha.scanner.storage import ConflictingScanReport, ScannerRepository


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class ScannerService:
    def __init__(self, repository: ScannerRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def scan(self, request: ScanRequest) -> ScanReport:
        stored = self.repository.find(request.scan_id)
        if stored is not None:
            identity = (
                stored.candle_timeframe,
                stored.horizon,
                stored.as_of,
                stored.filters,
                stored.scanner_version,
            )
            expected = (
                request.candle_timeframe,
                request.horizon,
                request.as_of,
                request.filters,
                request.scanner_version,
            )
            if identity != expected:
                raise ConflictingScanReport("scan identity conflicts with its request")
            return stored
        generated_at = utc(self.clock.now())
        if request.as_of > generated_at:
            raise ValueError("scan as-of time cannot be in the future")
        universe = self.repository.universe(request.filters)
        reports = self.repository.reports(
            tuple(item.market_id for item in universe),
            request.candle_timeframe.value,
            request.as_of,
        )
        candidates: dict[tuple[str, str], list[tuple[ScanMarket, UUID, OpportunityScore]]] = (
            defaultdict(list)
        )
        excluded: list[ScanExclusion] = []
        for market in universe:
            analysis_report = reports.get(market.market_id)
            if analysis_report is None:
                excluded.append(
                    ScanExclusion(market=market, reasons=(ScanExclusionReason.NO_ANALYZE_REPORT,))
                )
                continue
            if analysis_report.generated_at > generated_at:
                excluded.append(
                    ScanExclusion(
                        market=market,
                        report_id=analysis_report.report_id,
                        reasons=(ScanExclusionReason.REPORT_UNAVAILABLE_AT_SCAN,),
                    )
                )
                continue
            horizon = next(
                item for item in analysis_report.horizons if item.horizon == request.horizon
            )
            opportunity = horizon.opportunity
            if opportunity is None:
                excluded.append(
                    ScanExclusion(
                        market=market,
                        report_id=analysis_report.report_id,
                        reasons=(ScanExclusionReason.OPPORTUNITY_NOT_PRODUCED,),
                    )
                )
                continue
            reasons = self._filter(opportunity, request)
            if reasons:
                excluded.append(
                    ScanExclusion(
                        market=market,
                        report_id=analysis_report.report_id,
                        opportunity=opportunity,
                        reasons=reasons,
                    )
                )
                continue
            candidates[(opportunity.policy_version, opportunity.policy_hash)].append(
                (market, analysis_report.report_id, opportunity)
            )

        groups: list[ScanPolicyGroup] = []
        for (policy_version, policy_hash), values in sorted(candidates.items()):
            ranking = OpportunityScoreEngine(self.clock).rank(
                uuid5(NAMESPACE_URL, f"{request.scan_id}:{policy_version}:{policy_hash}"),
                tuple(value[2] for value in values),
                ranked_at=generated_at,
            )
            references = {value[2].opportunity_id: value[:2] for value in values}
            limit = request.filters.max_results_per_policy
            entries: list[ScanRankEntry] = []
            for ranked in ranking.entries[:limit]:
                market, report_id = references[ranked.opportunity.opportunity_id]
                entries.append(
                    ScanRankEntry(
                        rank=ranked.rank,
                        market=market,
                        report_id=report_id,
                        opportunity=ranked.opportunity,
                    )
                )
            for ranked in ranking.entries[limit:]:
                market, report_id = references[ranked.opportunity.opportunity_id]
                excluded.append(
                    ScanExclusion(
                        market=market,
                        report_id=report_id,
                        opportunity=ranked.opportunity,
                        reasons=(ScanExclusionReason.POLICY_RESULT_LIMIT,),
                    )
                )
            groups.append(
                ScanPolicyGroup(
                    policy_version=policy_version,
                    policy_hash=policy_hash,
                    entries=tuple(entries),
                )
            )
        groups = [group for group in groups if group.entries]
        excluded.sort(key=lambda item: item.market.market_id)
        payload = {
            "request": request.model_dump(),
            "universe": [item.model_dump() for item in universe],
            "reports": [
                reports[item.market_id].model_dump() if item.market_id in reports else None
                for item in universe
            ],
            "groups": [group.model_dump() for group in groups],
            "excluded": [item.model_dump() for item in excluded],
        }
        scan_report = ScanReport(
            scan_id=request.scan_id,
            candle_timeframe=request.candle_timeframe,
            horizon=request.horizon,
            as_of=request.as_of,
            generated_at=generated_at,
            scanner_version=request.scanner_version,
            filters=request.filters,
            status=ScanStatus.RESULTS if groups else ScanStatus.NO_MATCHES,
            universe_size=len(universe),
            analyze_reports_found=len(reports),
            groups=tuple(groups),
            excluded=tuple(excluded),
            input_hash=fingerprint(payload),
        )
        self.repository.put(scan_report)
        return scan_report

    def _filter(
        self, opportunity: OpportunityScore, request: ScanRequest
    ) -> tuple[ScanExclusionReason, ...]:
        if opportunity.status == OpportunityStatus.UNAVAILABLE:
            return (ScanExclusionReason.OPPORTUNITY_UNAVAILABLE,)
        if not opportunity.eligible:
            return (ScanExclusionReason.OPPORTUNITY_INELIGIBLE,)
        assert opportunity.direction is not None
        assert opportunity.score is not None
        assert opportunity.economics is not None
        filters = request.filters
        economics = opportunity.economics
        checks: tuple[tuple[bool, ScanExclusionReason], ...] = (
            (
                opportunity.direction not in filters.directions,
                ScanExclusionReason.DIRECTION_FILTERED,
            ),
            (
                self._below(opportunity.score, filters.minimum_score),
                ScanExclusionReason.SCORE_BELOW_MINIMUM,
            ),
            (
                self._below(economics.net_expected_return, filters.minimum_net_return),
                ScanExclusionReason.NET_RETURN_BELOW_MINIMUM,
            ),
            (
                self._below(economics.liquidity, filters.minimum_liquidity),
                ScanExclusionReason.LIQUIDITY_BELOW_MINIMUM,
            ),
            (
                self._above(economics.uncertainty, filters.maximum_uncertainty),
                ScanExclusionReason.UNCERTAINTY_ABOVE_MAXIMUM,
            ),
            (
                self._below(economics.risk_reward, filters.minimum_risk_reward),
                ScanExclusionReason.RISK_REWARD_BELOW_MINIMUM,
            ),
            (
                self._above(economics.total_cost_rate, filters.maximum_total_cost),
                ScanExclusionReason.COST_ABOVE_MAXIMUM,
            ),
        )
        return tuple(reason for failed, reason in checks if failed)

    @staticmethod
    def _below(value: Decimal, limit: Decimal | None) -> bool:
        return limit is not None and value < limit

    @staticmethod
    def _above(value: Decimal, limit: Decimal | None) -> bool:
        return limit is not None and value > limit
