from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from pocket_alpha.analysis.models import AnalyzeStatus, HorizonConclusion
from pocket_alpha.analysis.service import AnalyzeService
from pocket_alpha.analysis.storage import AnalyzeRepository
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.watchlists.models import (
    AlertEventType,
    SnapshotStatus,
    WatchlistHorizonState,
    WatchlistSnapshot,
    WatchlistSnapshotItem,
)
from pocket_alpha.watchlists.service import WatchlistSnapshotService
from pocket_alpha.watchlists.storage import (
    ConflictingWatchlist,
    StaleWatchlistRevision,
    WatchlistRepository,
)
from tests.test_analyze import full_request
from tests.test_opportunity_score import AS_OF, GENERATED

CLOCK = FrozenClock(AS_OF + timedelta(days=2))
LIST_ID = UUID(int=700)
MEMBER_ID = UUID(int=701)


def create_list(repository: MarketRepository) -> WatchlistRepository:
    watchlists = WatchlistRepository(repository.session)
    watchlists.create(LIST_ID, "Principais", AS_OF - timedelta(days=1))
    return watchlists


def add_member(repository: MarketRepository) -> WatchlistRepository:
    watchlists = create_list(repository)
    watchlists.add_member(LIST_ID, MEMBER_ID, "test-market", "1h", 1, AS_OF - timedelta(hours=1))
    return watchlists


def client_for(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def test_watchlist_crud_is_ordered_idempotent_and_revisioned(repository: MarketRepository) -> None:
    subject = create_list(repository)
    assert subject.create(LIST_ID, "Principais", AS_OF).revision == 1
    with pytest.raises(ConflictingWatchlist):
        subject.create(LIST_ID, "Outra", AS_OF)
    updated = subject.add_member(LIST_ID, MEMBER_ID, "test-market", "1h", 1, AS_OF)
    assert updated.revision == 2
    assert updated.members[0].asset_id == "test-asset"
    assert subject.add_member(LIST_ID, MEMBER_ID, "test-market", "1h", 1, AS_OF).revision == 2
    with pytest.raises(StaleWatchlistRevision):
        subject.rename(LIST_ID, "Nova", 1, AS_OF)
    renamed = subject.rename(LIST_ID, "Nova", 2, AS_OF)
    assert renamed.name == "Nova" and renamed.revision == 3
    removed = subject.remove_member(LIST_ID, "test-market", 3, AS_OF)
    assert removed.revision == 4 and removed.members == ()


def test_watchlist_rejects_unknown_duplicate_and_oversized_inputs(
    repository: MarketRepository,
) -> None:
    subject = create_list(repository)
    with pytest.raises(LookupError, match="market not found"):
        subject.add_member(LIST_ID, MEMBER_ID, "missing", "1h", 1, AS_OF)
    subject.add_member(LIST_ID, MEMBER_ID, "test-market", "1h", 1, AS_OF)
    with pytest.raises(ConflictingWatchlist, match="already belongs"):
        subject.add_member(LIST_ID, UUID(int=702), "test-market", "4h", 2, AS_OF)
    with pytest.raises(ValueError, match="name"):
        subject.rename(LIST_ID, " ", 2, AS_OF)


def test_snapshot_without_analyze_is_explicit_and_idempotent(
    repository: MarketRepository,
) -> None:
    subject = add_member(repository)
    service = WatchlistSnapshotService(subject, CLOCK)
    result = service.capture(LIST_ID, UUID(int=710), AS_OF - timedelta(minutes=1))
    assert result.snapshot.status == SnapshotStatus.UNAVAILABLE
    assert result.snapshot.items[0].unavailable_reason == "NO_ANALYSIS_SNAPSHOT"
    assert set(item.conclusion for item in result.snapshot.items[0].horizons) == {
        HorizonConclusion.UNAVAILABLE
    }
    assert result.events == ()
    repeated = service.capture(LIST_ID, UUID(int=710), AS_OF - timedelta(minutes=1))
    assert repeated == result
    with pytest.raises(ValueError, match="conflicts"):
        service.capture(LIST_ID, UUID(int=710), AS_OF)


def test_exact_analyze_snapshot_is_linked_and_availability_transition_is_emitted(
    repository: MarketRepository,
) -> None:
    subject = add_member(repository)
    service = WatchlistSnapshotService(subject, CLOCK)
    first = service.capture(LIST_ID, UUID(int=711), AS_OF - timedelta(seconds=1))
    report = AnalyzeService(CLOCK).assemble(
        full_request(), generated_at=GENERATED + timedelta(minutes=1)
    )
    AnalyzeRepository(repository.session).put(report)
    second = service.capture(LIST_ID, UUID(int=712), AS_OF)
    assert first.snapshot.status == SnapshotStatus.UNAVAILABLE
    assert second.snapshot.status == SnapshotStatus.COMPLETE
    assert second.snapshot.items[0].report_id == report.report_id
    assert all(
        item.conclusion == HorizonConclusion.ELIGIBLE_LONG
        for item in second.snapshot.items[0].horizons
    )
    assert len(second.events) == 1
    assert second.events[0].event_type == AlertEventType.ANALYSIS_BECAME_AVAILABLE
    assert subject.alerts(LIST_ID) == second.events


def test_conclusion_changes_produce_one_event_per_changed_horizon(
    repository: MarketRepository,
) -> None:
    subject = add_member(repository)
    service = WatchlistSnapshotService(subject, CLOCK)
    base = WatchlistSnapshotItem(
        member_id=MEMBER_ID,
        market_id="test-market",
        asset_id="test-asset",
        candle_timeframe=Timeframe.H1,
        report_id=UUID(int=720),
        report_status=AnalyzeStatus.COMPLETE,
        horizons=tuple(
            WatchlistHorizonState(horizon=horizon, conclusion=HorizonConclusion.NO_TRADE)
            for horizon in ForecastHorizon
        ),
    )
    current_item = base.model_copy(
        update={
            "report_id": UUID(int=721),
            "horizons": (
                WatchlistHorizonState(
                    horizon=ForecastHorizon.H1,
                    conclusion=HorizonConclusion.ELIGIBLE_LONG,
                ),
            )
            + base.horizons[1:],
        }
    )
    previous = WatchlistSnapshot(
        snapshot_id=UUID(int=722),
        watchlist_id=LIST_ID,
        watchlist_revision=2,
        as_of=AS_OF,
        generated_at=AS_OF,
        status=SnapshotStatus.COMPLETE,
        input_hash="a" * 64,
        items=(base,),
    )
    current = WatchlistSnapshot(
        snapshot_id=UUID(int=723),
        watchlist_id=LIST_ID,
        watchlist_revision=2,
        as_of=AS_OF + timedelta(hours=1),
        generated_at=AS_OF + timedelta(hours=1),
        status=SnapshotStatus.COMPLETE,
        input_hash="b" * 64,
        items=(current_item,),
    )
    events = service._events(previous, current)
    assert len(events) == 1
    assert events[0].event_type == AlertEventType.HORIZON_CONCLUSION_CHANGED
    assert events[0].horizon == ForecastHorizon.H1
    assert events[0].previous_conclusion == HorizonConclusion.NO_TRADE
    assert events[0].current_conclusion == HorizonConclusion.ELIGIBLE_LONG


def test_snapshot_models_reject_false_coverage_and_unexplained_absence() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        WatchlistSnapshotItem(
            member_id=MEMBER_ID,
            market_id="test-market",
            asset_id="test-asset",
            candle_timeframe=Timeframe.H1,
            horizons=tuple(
                WatchlistHorizonState(horizon=horizon, conclusion=HorizonConclusion.UNAVAILABLE)
                for horizon in ForecastHorizon
            ),
        )


def test_watchlist_api_manages_members_snapshots_and_conflicts(
    repository: MarketRepository,
) -> None:
    client = client_for(repository)
    created = client.post(
        "/api/v1/watchlists", json={"watchlist_id": str(LIST_ID), "name": "Principais"}
    )
    assert created.status_code == 200 and created.json()["revision"] == 1
    added = client.put(
        f"/api/v1/watchlists/{LIST_ID}/markets/test-market",
        json={"member_id": str(MEMBER_ID), "candle_timeframe": "1h", "expected_revision": 1},
    )
    assert added.status_code == 200 and added.json()["revision"] == 2
    stale = client.patch(
        f"/api/v1/watchlists/{LIST_ID}", json={"name": "Nova", "expected_revision": 1}
    )
    assert stale.status_code == 409
    captured = client.post(
        f"/api/v1/watchlists/{LIST_ID}/snapshots",
        json={"snapshot_id": str(UUID(int=730)), "as_of": AS_OF.isoformat()},
    )
    assert captured.status_code == 200
    assert captured.json()["snapshot"]["status"] == "UNAVAILABLE"
    assert client.get(f"/api/v1/watchlists/{LIST_ID}/snapshots/latest").status_code == 200
    assert client.get(f"/api/v1/watchlists/{LIST_ID}/alerts").json() == []
    assert client.get("/api/v1/watchlists/00000000-0000-0000-0000-000000000999").status_code == 404
    removed = client.delete(
        f"/api/v1/watchlists/{LIST_ID}/markets/test-market", params={"expected_revision": 2}
    )
    assert removed.status_code == 200 and removed.json()["members"] == []
