import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING

from pocket_alpha.analysis.models import (
    AnalyzeHorizon,
    AnalyzeIssue,
    AnalyzeReport,
    AnalyzeRequest,
    AnalyzeStatus,
    derive_horizon,
)
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.scoring.models import PocketScoreStatus

if TYPE_CHECKING:
    from pocket_alpha.analysis.storage import AnalyzeRepository


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class AnalyzeService:
    """Assemble existing analytical artifacts without recomputing their conclusions."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def assemble(self, request: AnalyzeRequest, *, generated_at: datetime) -> AnalyzeReport:
        generated_at = utc(generated_at)
        now = utc(self.clock.now())
        if request.as_of > now:
            raise ValueError("Analyze as-of time cannot be in the future")
        if generated_at > now:
            raise ValueError("Analyze report cannot be generated in the future")
        if generated_at < request.as_of:
            raise ValueError("Analyze report cannot be generated before its as-of time")

        horizons = tuple(
            AnalyzeHorizon(
                **item.model_dump(),
                status=derive_horizon(item, request.as_of)[0],
                conclusion=derive_horizon(item, request.as_of)[1],
                issues=derive_horizon(item, request.as_of)[2],
            )
            for item in request.horizons
        )
        present = int(request.pocket_score is not None) + sum(
            artifact is not None
            for item in request.horizons
            for artifact in (item.forecast, item.directional, item.opportunity)
        )
        total = 1 + len(request.horizons) * 3
        status = (
            AnalyzeStatus.UNAVAILABLE
            if present == 0
            else AnalyzeStatus.COMPLETE
            if present == total
            else AnalyzeStatus.PARTIAL
        )
        issues = (
            (AnalyzeIssue.POCKET_SCORE_NOT_PRODUCED,)
            if request.pocket_score is None
            else (AnalyzeIssue.POCKET_SCORE_UNAVAILABLE,)
            if request.pocket_score.status == PocketScoreStatus.UNAVAILABLE
            else ()
        )
        return AnalyzeReport(
            report_id=request.report_id,
            market_id=request.market_id,
            asset_id=request.asset_id,
            candle_timeframe=request.candle_timeframe,
            as_of=request.as_of,
            generated_at=generated_at,
            status=status,
            report_version=request.report_version,
            input_hash=fingerprint(
                {
                    "pocket_score": (
                        request.pocket_score.model_dump()
                        if request.pocket_score is not None
                        else None
                    ),
                    "pocket_score_unavailable_reason": request.pocket_score_unavailable_reason,
                    "horizons": [item.model_dump() for item in request.horizons],
                }
            ),
            issues=issues,
            pocket_score=request.pocket_score,
            pocket_score_unavailable_reason=request.pocket_score_unavailable_reason,
            horizons=horizons,
        )


class AnalyzeLedger:
    """Append-only application boundary for assembled Analyze reports."""

    def __init__(self, repository: "AnalyzeRepository", clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def append(self, report: AnalyzeReport) -> bool:
        if report.generated_at > utc(self.clock.now()):
            raise ValueError("Analyze report cannot be persisted from the future")
        return self.repository.put(report)
