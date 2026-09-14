from datetime import datetime
from uuid import UUID, uuid5

from pocket_alpha.analysis.models import HorizonConclusion
from pocket_alpha.analysis.storage import AnalyzeRepository
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.models import ForecastHorizon
from pocket_alpha.watchlists.models import (
    AlertEvent,
    AlertEventType,
    SnapshotResult,
    SnapshotStatus,
    WatchlistHorizonState,
    WatchlistSnapshot,
    WatchlistSnapshotItem,
)
from pocket_alpha.watchlists.storage import WatchlistRepository

ALERT_NAMESPACE = UUID("7404bcaf-7ab8-43a8-9dd8-9ea8f3da908c")


class WatchlistSnapshotService:
    def __init__(self, repository: WatchlistRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def capture(self, watchlist_id: UUID, snapshot_id: UUID, as_of: datetime) -> SnapshotResult:
        requested_at = utc(as_of)
        generated_at = utc(self.clock.now())
        if requested_at > generated_at:
            raise ValueError("watchlist snapshot as-of time cannot be in the future")
        stored = self.repository.snapshot(snapshot_id)
        if stored is not None:
            if stored.watchlist_id != watchlist_id or stored.as_of != requested_at:
                raise ValueError("snapshot identity conflicts with watchlist or as-of time")
            return SnapshotResult(
                snapshot=stored,
                events=self.repository.events_for_snapshot(snapshot_id),
            )
        watchlist = self.repository.get(watchlist_id)
        analysis = AnalyzeRepository(self.repository.session)
        items: list[WatchlistSnapshotItem] = []
        for member in watchlist.members:
            report = analysis.at(member.market_id, member.candle_timeframe.value, requested_at)
            items.append(
                WatchlistSnapshotItem(
                    member_id=member.member_id,
                    market_id=member.market_id,
                    asset_id=member.asset_id,
                    candle_timeframe=member.candle_timeframe,
                    report_id=report.report_id if report else None,
                    report_status=report.status if report else None,
                    unavailable_reason=None if report else "NO_ANALYSIS_SNAPSHOT",
                    horizons=(
                        tuple(
                            WatchlistHorizonState(horizon=item.horizon, conclusion=item.conclusion)
                            for item in report.horizons
                        )
                        if report
                        else tuple(
                            WatchlistHorizonState(
                                horizon=horizon, conclusion=HorizonConclusion.UNAVAILABLE
                            )
                            for horizon in ForecastHorizon
                        )
                    ),
                )
            )
        available = sum(item.report_id is not None for item in items)
        status = (
            SnapshotStatus.UNAVAILABLE
            if not items or available == 0
            else SnapshotStatus.COMPLETE
            if available == len(items)
            else SnapshotStatus.PARTIAL
        )
        snapshot = WatchlistSnapshot(
            snapshot_id=snapshot_id,
            watchlist_id=watchlist.watchlist_id,
            watchlist_revision=watchlist.revision,
            as_of=requested_at,
            generated_at=generated_at,
            status=status,
            input_hash=self.repository.snapshot_fingerprint(watchlist, requested_at, items),
            items=tuple(items),
        )
        previous = self.repository.latest_snapshot(watchlist_id, before=requested_at)
        events = self._events(previous, snapshot)
        self.repository.put_snapshot(snapshot, events)
        return SnapshotResult(snapshot=snapshot, events=events)

    def _events(
        self, previous: WatchlistSnapshot | None, current: WatchlistSnapshot
    ) -> tuple[AlertEvent, ...]:
        if previous is None:
            return ()
        old = {item.member_id: item for item in previous.items}
        events: list[AlertEvent] = []
        for item in current.items:
            prior = old.get(item.member_id)
            if prior is None:
                continue
            if prior.report_id is None and item.report_id is not None:
                events.append(self._availability_event(previous, current, item, True))
            elif prior.report_id is not None and item.report_id is None:
                events.append(self._availability_event(previous, current, item, False))
            if prior.report_id is None or item.report_id is None:
                continue
            for prior_state, current_state in zip(prior.horizons, item.horizons, strict=True):
                if prior_state.horizon != current_state.horizon:
                    raise ValueError("snapshot horizons cannot be compared")
                if prior_state.conclusion != current_state.conclusion:
                    events.append(
                        self._conclusion_event(
                            previous,
                            current,
                            item,
                            current_state.horizon,
                            prior_state.conclusion,
                            current_state.conclusion,
                        )
                    )
        return tuple(events)

    def _event_id(self, current: WatchlistSnapshot, member_id: UUID, suffix: str) -> UUID:
        return uuid5(ALERT_NAMESPACE, f"{current.snapshot_id}:{member_id}:{suffix}")

    def _availability_event(
        self,
        previous: WatchlistSnapshot,
        current: WatchlistSnapshot,
        item: WatchlistSnapshotItem,
        available: bool,
    ) -> AlertEvent:
        kind = (
            AlertEventType.ANALYSIS_BECAME_AVAILABLE
            if available
            else AlertEventType.ANALYSIS_BECAME_UNAVAILABLE
        )
        return AlertEvent(
            event_id=self._event_id(current, item.member_id, kind.value),
            watchlist_id=current.watchlist_id,
            snapshot_id=current.snapshot_id,
            previous_snapshot_id=previous.snapshot_id,
            member_id=item.member_id,
            market_id=item.market_id,
            candle_timeframe=item.candle_timeframe,
            event_type=kind,
            observed_at=current.as_of,
            created_at=current.generated_at,
            reason=kind.value,
        )

    def _conclusion_event(
        self,
        previous: WatchlistSnapshot,
        current: WatchlistSnapshot,
        item: WatchlistSnapshotItem,
        horizon: ForecastHorizon,
        prior: HorizonConclusion,
        value: HorizonConclusion,
    ) -> AlertEvent:
        suffix = f"{AlertEventType.HORIZON_CONCLUSION_CHANGED}:{horizon.value}:{prior}:{value}"
        return AlertEvent(
            event_id=self._event_id(current, item.member_id, suffix),
            watchlist_id=current.watchlist_id,
            snapshot_id=current.snapshot_id,
            previous_snapshot_id=previous.snapshot_id,
            member_id=item.member_id,
            market_id=item.market_id,
            candle_timeframe=item.candle_timeframe,
            horizon=horizon,
            event_type=AlertEventType.HORIZON_CONCLUSION_CHANGED,
            previous_conclusion=prior,
            current_conclusion=value,
            observed_at=current.as_of,
            created_at=current.generated_at,
            reason="ANALYZE_CONCLUSION_TRANSITION",
        )
