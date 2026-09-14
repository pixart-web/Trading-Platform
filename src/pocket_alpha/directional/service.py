import hashlib
import json
from datetime import datetime

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.directional.models import (
    CaseStatus,
    ComparisonOperator,
    DirectionalAnalysis,
    DirectionalAnalysisRequest,
    DirectionalCaseAnalysis,
    DirectionalCaseInput,
    DirectionalCasePolicy,
    DirectionalCriterionResult,
    DirectionalDecision,
    DirectionalReason,
    MetricStatus,
)
from pocket_alpha.intelligence.provenance import canonical


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _analyze_case(
    policy: DirectionalCasePolicy,
    case: DirectionalCaseInput,
) -> DirectionalCaseAnalysis:
    results = []
    for definition, metric in zip(policy.criteria, case.metrics, strict=True):
        if metric.status == MetricStatus.UNAVAILABLE:
            results.append(
                DirectionalCriterionResult(
                    criterion=definition.criterion,
                    label=definition.label,
                    operator=definition.operator,
                    threshold=definition.threshold,
                    rule_version=definition.rule_version,
                    status=metric.status,
                    source_version=metric.source_version,
                    unavailable_reason=metric.unavailable_reason,
                )
            )
            continue
        assert metric.value is not None
        assert metric.available_at is not None
        passed = (
            metric.value >= definition.threshold
            if definition.operator == ComparisonOperator.GREATER_THAN_OR_EQUAL
            else metric.value <= definition.threshold
        )
        results.append(
            DirectionalCriterionResult(
                criterion=definition.criterion,
                label=definition.label,
                operator=definition.operator,
                threshold=definition.threshold,
                rule_version=definition.rule_version,
                status=metric.status,
                value=metric.value,
                passed=passed,
                source_version=metric.source_version,
                available_at=metric.available_at,
                evidence=metric.evidence,
            )
        )
    frozen = tuple(results)
    failed = tuple(
        item.criterion
        for item in frozen
        if item.status == MetricStatus.AVAILABLE and item.passed is False
    )
    unavailable = tuple(
        item.criterion for item in frozen if item.status == MetricStatus.UNAVAILABLE
    )
    return DirectionalCaseAnalysis(
        side=case.side,
        status=CaseStatus.UNAVAILABLE if unavailable else CaseStatus.COMPLETE,
        qualifies=None if unavailable else not failed,
        results=frozen,
        failed_criteria=failed,
        unavailable_criteria=unavailable,
    )


class DirectionalAnalysisEngine:
    """Evaluate LONG and SHORT policies independently and fail closed to NO_TRADE."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def analyze(
        self, request: DirectionalAnalysisRequest, *, generated_at: datetime
    ) -> DirectionalAnalysis:
        generated_at = utc(generated_at)
        now = utc(self.clock.now())
        if request.as_of > now:
            raise ValueError("directional analysis as-of time cannot be in the future")
        if generated_at > now:
            raise ValueError("directional analysis generation cannot be in the future")
        if generated_at < request.as_of:
            raise ValueError("directional analysis cannot be generated before its as-of time")
        for case in (request.long_case, request.short_case):
            for metric in case.metrics:
                if metric.available_at is not None and metric.available_at > request.as_of:
                    raise ValueError("directional metric was unavailable at the as-of time")

        long_case = _analyze_case(request.policy.long_case, request.long_case)
        short_case = _analyze_case(request.policy.short_case, request.short_case)
        if (
            long_case.status == CaseStatus.UNAVAILABLE
            or short_case.status == CaseStatus.UNAVAILABLE
        ):
            decision = DirectionalDecision.NO_TRADE
            reason = DirectionalReason.INCOMPLETE_EVIDENCE
        elif long_case.qualifies and short_case.qualifies:
            decision = DirectionalDecision.NO_TRADE
            reason = DirectionalReason.CONFLICTING_CASES
        elif long_case.qualifies:
            decision = DirectionalDecision.LONG
            reason = DirectionalReason.LONG_CASE_ONLY
        elif short_case.qualifies:
            decision = DirectionalDecision.SHORT
            reason = DirectionalReason.SHORT_CASE_ONLY
        else:
            decision = DirectionalDecision.NO_TRADE
            reason = DirectionalReason.NO_CASE_PASSED
        return DirectionalAnalysis(
            analysis_id=request.analysis_id,
            market_id=request.market_id,
            asset_id=request.asset_id,
            candle_timeframe=request.candle_timeframe,
            horizon=request.horizon,
            as_of=request.as_of,
            generated_at=generated_at,
            policy_version=request.policy.policy_version,
            policy_hash=fingerprint(request.policy.model_dump()),
            input_hash=fingerprint(
                {
                    "long_case": request.long_case.model_dump(),
                    "short_case": request.short_case.model_dump(),
                }
            ),
            decision=decision,
            reason=reason,
            long_case=long_case,
            short_case=short_case,
        )
