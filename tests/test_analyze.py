from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from pocket_alpha.analysis.models import (
    AnalyzeHorizonInput,
    AnalyzeIssue,
    AnalyzeReport,
    AnalyzeRequest,
    AnalyzeResponseStatus,
    AnalyzeStatus,
    HorizonConclusion,
    HorizonIssue,
)
from pocket_alpha.analysis.service import AnalyzeLedger, AnalyzeService
from pocket_alpha.analysis.storage import AnalyzeRepository, ConflictingAnalyzeReport
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import DirectionalAnalysis, DirectionalSide
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.opportunities.models import OpportunityScore
from pocket_alpha.opportunities.service import OpportunityScoreEngine
from pocket_alpha.scoring.models import PocketScore
from pocket_alpha.scoring.service import PocketScoreEngine
from tests.test_opportunity_score import (
    AS_OF,
    GENERATED,
    directional,
    forecast,
)
from tests.test_opportunity_score import (
    request as opportunity_request,
)
from tests.test_pocket_score import full_inputs
from tests.test_pocket_score import request as pocket_request

CLOCK = FrozenClock(AS_OF + timedelta(days=1))
SERVICE = AnalyzeService(CLOCK)


def upstream(
    horizon: ForecastHorizon, index: int
) -> tuple[Forecast, DirectionalAnalysis, OpportunityScore]:
    forecast_values = forecast().model_dump()
    generated_at = AS_OF - timedelta(minutes=30)
    forecast_values.update(
        forecast_id=UUID(int=100 + index),
        horizon=horizon,
        generated_at=generated_at,
        expires_at=expires_at(generated_at, horizon),
    )
    prediction = Forecast.model_validate(forecast_values)
    directional_values = directional(DirectionalSide.LONG).model_dump()
    directional_values.update(analysis_id=UUID(int=200 + index), horizon=horizon)
    decision = DirectionalAnalysis.model_validate(directional_values)
    opportunity = OpportunityScoreEngine(CLOCK).calculate(
        opportunity_request(
            opportunity_id=300 + index,
            analysis=decision,
            prediction=prediction,
        ),
        generated_at=GENERATED,
    )
    return prediction, decision, opportunity


def pocket_score() -> PocketScore:
    subject = pocket_request(full_inputs()).model_copy(update={"as_of": AS_OF})
    return PocketScoreEngine(CLOCK).calculate(subject, generated_at=AS_OF)


def full_request() -> AnalyzeRequest:
    horizons = tuple(
        AnalyzeHorizonInput(
            horizon=horizon,
            forecast=(artifacts := upstream(horizon, index))[0],
            directional=artifacts[1],
            opportunity=artifacts[2],
        )
        for index, horizon in enumerate(ForecastHorizon)
    )
    return AnalyzeRequest(
        report_id=UUID(int=500),
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        as_of=AS_OF,
        report_version="analyze-v1",
        pocket_score=pocket_score(),
        horizons=horizons,
    )


def missing_horizon(horizon: ForecastHorizon) -> AnalyzeHorizonInput:
    return AnalyzeHorizonInput(
        horizon=horizon,
        forecast_unavailable_reason="FORECAST_NOT_PRODUCED",
        directional_unavailable_reason="DIRECTIONAL_NOT_PRODUCED",
        opportunity_unavailable_reason="OPPORTUNITY_NOT_PRODUCED",
    )


def unavailable_request() -> AnalyzeRequest:
    return AnalyzeRequest(
        report_id=UUID(int=501),
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        as_of=AS_OF,
        report_version="analyze-v1",
        pocket_score_unavailable_reason="POCKET_SCORE_NOT_PRODUCED",
        horizons=tuple(missing_horizon(horizon) for horizon in ForecastHorizon),
    )


def test_complete_report_covers_every_horizon_and_retains_artifacts() -> None:
    subject = full_request()
    report = SERVICE.assemble(subject, generated_at=GENERATED + timedelta(minutes=1))
    assert report.status == AnalyzeStatus.COMPLETE
    assert report.issues == ()
    assert tuple(item.horizon for item in report.horizons) == tuple(ForecastHorizon)
    assert all(item.status == AnalyzeStatus.COMPLETE for item in report.horizons)
    assert all(item.conclusion == HorizonConclusion.ELIGIBLE_LONG for item in report.horizons)
    assert all(item.forecast is not None for item in report.horizons)
    assert all(item.directional is not None for item in report.horizons)
    assert all(item.opportunity is not None for item in report.horizons)
    assert (
        report.input_hash
        == SERVICE.assemble(subject, generated_at=GENERATED + timedelta(minutes=1)).input_hash
    )


def test_fully_missing_report_is_explicitly_unavailable() -> None:
    report = SERVICE.assemble(unavailable_request(), generated_at=GENERATED)
    assert report.status == AnalyzeStatus.UNAVAILABLE
    assert report.issues == (AnalyzeIssue.POCKET_SCORE_NOT_PRODUCED,)
    assert all(item.status == AnalyzeStatus.UNAVAILABLE for item in report.horizons)
    assert all(item.conclusion == HorizonConclusion.UNAVAILABLE for item in report.horizons)
    assert report.horizons[0].issues == (
        HorizonIssue.FORECAST_NOT_PRODUCED,
        HorizonIssue.DIRECTIONAL_NOT_PRODUCED,
        HorizonIssue.OPPORTUNITY_NOT_PRODUCED,
    )


def test_partial_report_and_no_trade_remain_visible_without_recommendation() -> None:
    subject = full_request()
    values = list(subject.horizons)
    first = values[0]
    values[0] = AnalyzeHorizonInput(
        horizon=first.horizon,
        forecast=first.forecast,
        directional=first.directional,
        opportunity_unavailable_reason="OPPORTUNITY_NOT_PRODUCED",
    )
    prediction = values[1].forecast
    assert prediction is not None
    directional_values = directional(None).model_dump()
    directional_values.update(analysis_id=UUID(int=999), horizon=values[1].horizon)
    no_trade = DirectionalAnalysis.model_validate(directional_values)
    unavailable_opportunity = OpportunityScoreEngine(CLOCK).calculate(
        opportunity_request(
            opportunity_id=998,
            analysis=no_trade,
            prediction=prediction,
        ),
        generated_at=GENERATED,
    )
    values[1] = AnalyzeHorizonInput(
        horizon=values[1].horizon,
        forecast=prediction,
        directional=no_trade,
        opportunity=unavailable_opportunity,
    )
    request = AnalyzeRequest.model_validate({**subject.model_dump(), "horizons": tuple(values)})
    report = SERVICE.assemble(request, generated_at=GENERATED + timedelta(minutes=1))
    assert report.status == AnalyzeStatus.PARTIAL
    assert report.horizons[0].status == AnalyzeStatus.PARTIAL
    assert report.horizons[0].conclusion == HorizonConclusion.UNAVAILABLE
    assert report.horizons[0].issues == (HorizonIssue.OPPORTUNITY_NOT_PRODUCED,)
    assert report.horizons[1].conclusion == HorizonConclusion.NO_TRADE
    assert report.horizons[1].issues == (
        HorizonIssue.DIRECTIONAL_NO_TRADE,
        HorizonIssue.OPPORTUNITY_UNAVAILABLE,
    )


def test_every_layer_requires_an_artifact_or_explicit_reason() -> None:
    with pytest.raises(ValidationError, match="exactly one artifact"):
        AnalyzeHorizonInput(
            horizon=ForecastHorizon.H1,
            directional_unavailable_reason="missing",
            opportunity_unavailable_reason="missing",
        )
    values = unavailable_request().model_dump()
    values["pocket_score_unavailable_reason"] = None
    with pytest.raises(ValidationError, match="exactly one artifact"):
        AnalyzeRequest.model_validate(values)


def test_all_horizons_are_required_in_canonical_order() -> None:
    subject = unavailable_request()
    with pytest.raises(ValidationError, match="every forecast horizon"):
        AnalyzeRequest.model_validate(
            {**subject.model_dump(), "horizons": tuple(reversed(subject.horizons))}
        )


def test_identity_links_and_causal_times_are_enforced() -> None:
    subject = full_request()
    first = subject.horizons[0]
    assert first.forecast is not None
    wrong = first.forecast.model_copy(update={"asset_id": "other-asset"})
    horizons = (first.model_copy(update={"forecast": wrong}),) + subject.horizons[1:]
    invalid = subject.model_copy(update={"horizons": horizons})
    with pytest.raises(ValidationError, match="forecast identity"):
        SERVICE.assemble(invalid, generated_at=GENERATED + timedelta(minutes=1))
    late_at = AS_OF + timedelta(seconds=1)
    late = first.forecast.model_copy(
        update={"generated_at": late_at, "expires_at": expires_at(late_at, first.horizon)}
    )
    invalid = subject.model_copy(
        update={"horizons": (first.model_copy(update={"forecast": late}),) + subject.horizons[1:]}
    )
    with pytest.raises(ValidationError, match="forecast was unavailable"):
        SERVICE.assemble(invalid, generated_at=GENERATED + timedelta(minutes=1))
    with pytest.raises(ValueError, match="cannot be generated in the future"):
        SERVICE.assemble(subject, generated_at=CLOCK.now() + timedelta(seconds=1))


def test_report_rejects_duplicate_artifact_identities_across_horizons() -> None:
    subject = full_request()
    first, second = subject.horizons[:2]
    assert first.forecast is not None and second.forecast is not None
    assert first.opportunity is not None and second.opportunity is not None
    duplicate_forecast = second.forecast.model_copy(
        update={"forecast_id": first.forecast.forecast_id}
    )
    linked_opportunity = second.opportunity.model_copy(
        update={"forecast_id": first.forecast.forecast_id}
    )
    duplicate = second.model_copy(
        update={"forecast": duplicate_forecast, "opportunity": linked_opportunity}
    )
    request = subject.model_copy(update={"horizons": (first, duplicate) + subject.horizons[2:]})
    with pytest.raises(ValidationError, match="unique identities"):
        SERVICE.assemble(request, generated_at=GENERATED + timedelta(minutes=1))


def test_report_rejects_tampered_summary() -> None:
    report = SERVICE.assemble(full_request(), generated_at=GENERATED + timedelta(minutes=1))
    with pytest.raises(ValidationError, match="status must match artifact coverage"):
        AnalyzeReport.model_validate({**report.model_dump(), "status": AnalyzeStatus.PARTIAL})
    changed = report.horizons[0].model_copy(update={"conclusion": HorizonConclusion.NO_TRADE})
    with pytest.raises(ValidationError, match="summary must match"):
        AnalyzeReport.model_validate(
            {**report.model_dump(), "horizons": (changed,) + report.horizons[1:]}
        )


def test_storage_is_append_only_idempotent_and_query_is_exact(
    repository: MarketRepository,
) -> None:
    report = SERVICE.assemble(full_request(), generated_at=GENERATED + timedelta(minutes=1))
    storage = AnalyzeRepository(repository.session)
    ledger = AnalyzeLedger(storage, CLOCK)
    assert ledger.append(report) is True
    assert ledger.append(report) is False
    assert storage.report(report.report_id) == report
    assert storage.at("test-market", "1h", AS_OF) == report
    assert storage.at("test-market", "4h", AS_OF) is None
    changed = report.model_copy(update={"report_version": "changed"})
    with pytest.raises(ConflictingAnalyzeReport):
        ledger.append(changed)
    with pytest.raises(ValueError, match="persisted from the future"):
        ledger.append(
            report.model_copy(update={"generated_at": CLOCK.now() + timedelta(seconds=1)})
        )


def api_client(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def test_read_only_api_returns_honest_absence_and_exact_snapshot(
    repository: MarketRepository,
) -> None:
    client = api_client(repository)
    url = "/api/v1/markets/test-market/analysis"
    params = {"timeframe": "1h", "as_of": AS_OF.isoformat()}
    missing = client.get(url, params=params)
    assert missing.status_code == 200
    assert missing.headers["cache-control"] == "no-store"
    assert missing.json()["status"] == AnalyzeResponseStatus.UNAVAILABLE
    assert missing.json()["unavailable_reason"] == "NO_ANALYSIS_SNAPSHOT"

    report = SERVICE.assemble(full_request(), generated_at=GENERATED + timedelta(minutes=1))
    AnalyzeRepository(repository.session).put(report)
    response = client.get(url, params=params)
    assert response.status_code == 200
    assert response.json()["status"] == AnalyzeResponseStatus.AVAILABLE
    assert response.json()["report"]["report_id"] == str(report.report_id)
    assert len(response.json()["report"]["horizons"]) == 13
    assert client.post(url, params=params, json={}).status_code == 405


def test_api_rejects_unknown_market_invalid_time_and_future(
    repository: MarketRepository,
) -> None:
    client = api_client(repository)
    url = "/api/v1/markets/test-market/analysis"
    assert client.get(url, params={"timeframe": "1h", "as_of": "2025-01-01"}).status_code == 422
    assert (
        client.get(
            url,
            params={"timeframe": "1h", "as_of": (CLOCK.now() + timedelta(days=1000)).isoformat()},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/markets/missing/analysis",
            params={"timeframe": "1h", "as_of": AS_OF.isoformat()},
        ).status_code
        == 404
    )
