from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from pocket_alpha.analysis.models import AnalyzeHorizonInput, AnalyzeRequest
from pocket_alpha.analysis.service import AnalyzeService
from pocket_alpha.analysis.storage import AnalyzeRepository
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import DirectionalSide
from pocket_alpha.domain.market import Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, ForecastHorizon, Timeframe
from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.scanner.models import (
    ScanExclusionReason,
    ScanFilters,
    ScanRequest,
    ScanStatus,
)
from pocket_alpha.scanner.service import ScannerService
from pocket_alpha.scanner.storage import ConflictingScanReport, ScannerRepository
from tests.test_analyze import full_request
from tests.test_opportunity_score import AS_OF, GENERATED

D = Decimal
CLOCK = FrozenClock(AS_OF + timedelta(days=2))
SCAN_ID = UUID(int=800)


def register_second(repository: MarketRepository) -> None:
    repository.register(
        Asset(
            asset_id="other-asset",
            symbol="OTHER",
            name="Other synthetic asset",
            asset_type=AssetType.CRYPTO,
        ),
        Venue(venue_id="test-venue", name="Synthetic venue"),
        Market(
            market_id="other-market",
            asset_id="other-asset",
            venue_id="test-venue",
            symbol="OTHER",
            quote_currency="USD",
        ),
        ProviderMapping(source="fixture", market_id="other-market", instrument_id="PROVIDER-OTHER"),
    )


def analyze_request(
    *,
    market_id: str = "test-market",
    asset_id: str = "test-asset",
    offset: int = 0,
    policy_version: str | None = None,
    policy_hash: str | None = None,
) -> AnalyzeRequest:
    source = full_request()
    assert source.pocket_score is not None
    pocket = source.pocket_score.model_copy(
        update={
            "score_id": UUID(int=source.pocket_score.score_id.int + offset),
            "market_id": market_id,
            "asset_id": asset_id,
        }
    )
    horizons: list[AnalyzeHorizonInput] = []
    for item in source.horizons:
        assert item.forecast is not None
        assert item.directional is not None
        assert item.opportunity is not None
        forecast = item.forecast.model_copy(
            update={
                "forecast_id": UUID(int=item.forecast.forecast_id.int + offset),
                "market_id": market_id,
                "asset_id": asset_id,
            }
        )
        directional = item.directional.model_copy(
            update={
                "analysis_id": UUID(int=item.directional.analysis_id.int + offset),
                "market_id": market_id,
                "asset_id": asset_id,
            }
        )
        opportunity = item.opportunity.model_copy(
            update={
                "opportunity_id": UUID(int=item.opportunity.opportunity_id.int + offset),
                "analysis_id": directional.analysis_id,
                "forecast_id": forecast.forecast_id,
                "market_id": market_id,
                "asset_id": asset_id,
                **({"policy_version": policy_version} if policy_version else {}),
                **({"policy_hash": policy_hash} if policy_hash else {}),
            }
        )
        horizons.append(
            AnalyzeHorizonInput(
                horizon=item.horizon,
                forecast=forecast,
                directional=directional,
                opportunity=opportunity,
            )
        )
    return AnalyzeRequest(
        report_id=UUID(int=source.report_id.int + offset),
        market_id=market_id,
        asset_id=asset_id,
        candle_timeframe=source.candle_timeframe,
        as_of=source.as_of,
        report_version=source.report_version,
        pocket_score=pocket,
        horizons=tuple(horizons),
    )


def persist_report(repository: MarketRepository, request: AnalyzeRequest) -> None:
    report = AnalyzeService(CLOCK).assemble(request, generated_at=GENERATED + timedelta(minutes=1))
    AnalyzeRepository(repository.session).put(report)


def scan_request(*, scan_id: UUID = SCAN_ID, filters: ScanFilters | None = None) -> ScanRequest:
    return ScanRequest(
        scan_id=scan_id,
        candle_timeframe=Timeframe.H1,
        horizon=ForecastHorizon.H1,
        as_of=AS_OF,
        filters=filters or ScanFilters(),
    )


def client_for(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def test_scan_without_reports_is_honest_and_persisted(repository: MarketRepository) -> None:
    subject = ScannerService(ScannerRepository(repository.session), CLOCK)
    result = subject.scan(scan_request())
    assert result.status == ScanStatus.NO_MATCHES
    assert result.universe_size == 1 and result.analyze_reports_found == 0
    assert result.groups == ()
    assert result.excluded[0].reasons == (ScanExclusionReason.NO_ANALYZE_REPORT,)
    assert ScannerRepository(repository.session).get(SCAN_ID) == result
    assert subject.scan(scan_request()) == result


def test_scan_ranks_cross_market_opportunities_with_stable_phase_12_order(
    repository: MarketRepository,
) -> None:
    register_second(repository)
    persist_report(repository, analyze_request(offset=1_000))
    persist_report(
        repository,
        analyze_request(market_id="other-market", asset_id="other-asset"),
    )
    result = ScannerService(ScannerRepository(repository.session), CLOCK).scan(scan_request())
    assert result.status == ScanStatus.RESULTS
    assert result.universe_size == 2 and result.analyze_reports_found == 2
    assert len(result.groups) == 1 and result.excluded == ()
    assert tuple(entry.market.market_id for entry in result.groups[0].entries) == (
        "other-market",
        "test-market",
    )
    assert tuple(entry.rank for entry in result.groups[0].entries) == (1, 2)
    assert all(entry.opportunity.eligible for entry in result.groups[0].entries)


def test_scan_keeps_different_policies_in_separate_rankings(
    repository: MarketRepository,
) -> None:
    register_second(repository)
    persist_report(repository, analyze_request())
    persist_report(
        repository,
        analyze_request(
            market_id="other-market",
            asset_id="other-asset",
            offset=1000,
            policy_version="other-policy",
            policy_hash="b" * 64,
        ),
    )
    result = ScannerService(ScannerRepository(repository.session), CLOCK).scan(scan_request())
    assert len(result.groups) == 2
    assert tuple(group.policy_version for group in result.groups) == (
        "opportunity-policy-v1",
        "other-policy",
    )
    assert all(tuple(entry.rank for entry in group.entries) == (1,) for group in result.groups)


def test_explicit_filters_retain_every_failed_economic_reason(
    repository: MarketRepository,
) -> None:
    persist_report(repository, analyze_request(offset=1_000))
    filters = ScanFilters(
        directions=(DirectionalSide.SHORT,),
        minimum_score=D("99"),
        minimum_net_return=D("0.1"),
        minimum_liquidity=D("0.99"),
        maximum_uncertainty=D("0.01"),
        minimum_risk_reward=D("10"),
        maximum_total_cost=D("0.001"),
    )
    result = ScannerService(ScannerRepository(repository.session), CLOCK).scan(
        scan_request(filters=filters)
    )
    assert result.status == ScanStatus.NO_MATCHES and result.groups == ()
    assert result.excluded[0].reasons == (
        ScanExclusionReason.DIRECTION_FILTERED,
        ScanExclusionReason.SCORE_BELOW_MINIMUM,
        ScanExclusionReason.NET_RETURN_BELOW_MINIMUM,
        ScanExclusionReason.LIQUIDITY_BELOW_MINIMUM,
        ScanExclusionReason.UNCERTAINTY_ABOVE_MAXIMUM,
        ScanExclusionReason.RISK_REWARD_BELOW_MINIMUM,
        ScanExclusionReason.COST_ABOVE_MAXIMUM,
    )
    assert result.excluded[0].opportunity is not None


def test_universe_filters_use_registered_metadata(repository: MarketRepository) -> None:
    register_second(repository)
    filters = ScanFilters(
        asset_types=(AssetType.CRYPTO,),
        venue_ids=("test-venue",),
        quote_currencies=("USD",),
        market_ids=("other-market",),
    )
    result = ScannerService(ScannerRepository(repository.session), CLOCK).scan(
        scan_request(filters=filters)
    )
    assert result.universe_size == 1
    assert result.excluded[0].market.market_id == "other-market"
    assert result.excluded[0].market.asset_type == AssetType.CRYPTO


def test_policy_limit_excludes_overflow_without_cross_policy_comparison(
    repository: MarketRepository,
) -> None:
    register_second(repository)
    persist_report(repository, analyze_request(offset=1_000))
    persist_report(
        repository,
        analyze_request(market_id="other-market", asset_id="other-asset"),
    )
    result = ScannerService(ScannerRepository(repository.session), CLOCK).scan(
        scan_request(filters=ScanFilters(max_results_per_policy=1))
    )
    assert len(result.groups[0].entries) == 1
    assert result.groups[0].entries[0].market.market_id == "other-market"
    assert result.excluded[0].market.market_id == "test-market"
    assert result.excluded[0].reasons == (ScanExclusionReason.POLICY_RESULT_LIMIT,)


def test_scan_identity_conflict_and_future_time_fail_closed(
    repository: MarketRepository,
) -> None:
    subject = ScannerService(ScannerRepository(repository.session), CLOCK)
    subject.scan(scan_request())
    with pytest.raises(ConflictingScanReport):
        subject.scan(scan_request(filters=ScanFilters(minimum_score=D("50"))))
    future = scan_request(scan_id=UUID(int=801)).model_copy(
        update={"as_of": CLOCK.now() + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="future"):
        subject.scan(future)


def test_filter_contract_requires_canonical_values() -> None:
    with pytest.raises(ValidationError, match="unique and sorted"):
        ScanFilters(market_ids=("z", "a"))
    with pytest.raises(ValidationError, match="directions"):
        ScanFilters(directions=())
    with pytest.raises(ValidationError, match="currencies"):
        ScanFilters(quote_currencies=("eur",))
    with pytest.raises(ValidationError):
        ScanFilters(minimum_score=D("101"))


def test_scanner_api_executes_reads_and_rejects_conflicts(repository: MarketRepository) -> None:
    client = client_for(repository)
    payload = scan_request().model_dump(mode="json")
    created = client.post("/api/v1/scans", json=payload)
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["status"] == "NO_MATCHES"
    assert client.get(f"/api/v1/scans/{SCAN_ID}").json()["scan_id"] == str(SCAN_ID)
    assert len(client.get("/api/v1/scans", params={"limit": 1}).json()) == 1
    changed = {**payload, "horizon": "4H"}
    assert client.post("/api/v1/scans", json=changed).status_code == 409
    assert client.get("/api/v1/scans/00000000-0000-0000-0000-000000000999").status_code == 404
    assert client.get("/api/v1/scans", params={"limit": 101}).status_code == 422
