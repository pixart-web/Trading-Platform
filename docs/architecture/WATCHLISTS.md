# Watchlist architecture

Phase 14 adds persistent local watchlists, immutable analytical snapshots and append-only alert events.
A watchlist organizes markets for observation. It does not rank markets, recommend trades, emit a
strategy intention, approve risk or contact an execution system.

## Mutable list contract

A watchlist has a client-supplied UUID, a trimmed name, UTC creation/update times and a monotonically
increasing revision. A member has its own UUID, one registered market, the market asset identity, a
candle timeframe and an immutable addition time. Markets are unique within a list and each list is
limited to 250 members. Member order is deterministic by addition time and UUID.

Create is idempotent for the same UUID and name. Rename, add and remove require the caller's expected
revision. The database advances the revision with a conditional update; stale writers receive a
conflict instead of silently overwriting newer state. Repeating the same add with the same member UUID,
market and timeframe returns the current list without another revision. Lists cannot be deleted through
the Phase 14 API, which prevents application code from cascading into retained snapshot history.

This phase implements a single local scope. It does not claim multi-user ownership, authentication or
public deployment safety.

## Immutable snapshots

A caller supplies a snapshot UUID and UTC `as_of`. The service freezes the exact current list revision
and resolves each member through the Phase 13 Analyze repository using the same market, candle timeframe
and exact as-of instant. It never substitutes the latest older analysis.

Every snapshot item contains the member, market, asset and timeframe identity plus exactly one Analyze
report UUID/status or `NO_ANALYSIS_SNAPSHOT`. It includes all thirteen forecast horizons in canonical
order with the conclusion copied from that report. Missing Analyze reports expose UNAVAILABLE for every
horizon; no plausible analytical value is generated.

Snapshot status is COMPLETE when every member has an exact report, PARTIAL when only some do, and
UNAVAILABLE for an empty list or no exact reports. These values describe coverage only. A COMPLETE
snapshot can contain NO_TRADE, ineligible or unavailable horizon conclusions. The input hash covers list
identity/revision, membership, exact as-of time and item contents through the shared canonical encoder.

Snapshots and their item rows are append-only. Repeating one UUID with the same list and as-of returns
the stored result; reusing it for another identity is rejected. Historical membership is embedded in
the snapshot and remains inspectable after a member is removed from the mutable list.

## Alert events

The first snapshot establishes a baseline and emits no event. A later snapshot compares only with the
latest earlier as-of snapshot of the same list. Members absent from either side do not create synthetic
changes. The service emits:

- ANALYSIS_BECAME_AVAILABLE when an exact Analyze report replaces explicit absence;
- ANALYSIS_BECAME_UNAVAILABLE when explicit absence replaces an available report;
- HORIZON_CONCLUSION_CHANGED for each canonical horizon whose stored Analyze conclusion changed.

Each event records deterministic UUID identity, both snapshot IDs, member/market/timeframe, observation
and creation times, an explicit reason and, for conclusion changes, horizon and previous/current values.
Deterministic UUIDv5 identities and append-only persistence make event generation idempotent. Events are
facts about stored snapshot transitions. They are not configured price alerts, push notifications,
recommendations or risk approvals. No email, webhook or external message is sent.

## Persistence and API

Migration 0005 adds `watchlists`, `watchlist_members`, `watchlist_snapshots`,
`watchlist_snapshot_items` and `watchlist_alert_events`. Foreign keys bind members to registered market
metadata, snapshot items to exact Analyze reports when available, and events to their current snapshot.
Indexes cover member uniqueness, list/as-of snapshot lookup and list/time event lookup.

The local API exposes:

- `GET/POST /api/v1/watchlists`;
- `GET/PATCH /api/v1/watchlists/{watchlist_id}`;
- `PUT/DELETE /api/v1/watchlists/{watchlist_id}/markets/{market_id}`;
- `POST /api/v1/watchlists/{watchlist_id}/snapshots`;
- `GET /api/v1/watchlists/{watchlist_id}/snapshots/latest`;
- `GET /api/v1/watchlists/{watchlist_id}/alerts?limit=100`.

Responses disable caching. Validation errors are 422, missing resources 404 and revision/identity
conflicts 409. The Next.js gateway allowlists only these path/method pairs, bounded query keys and an
8 KiB mutation body before forwarding to its fixed server-only origin.

## Web experience and limits

The market workspace can create a watchlist, select a list, add/remove the selected market, capture the
current chart-end snapshot and inspect members, coverage and recent transition events. Runtime Zod
schemas validate UUIDs, UTC timestamps, hashes, list revisions, explicit report-or-reason state and
canonical horizons. Loading, error, empty and unavailable states remain distinct and accessible.

There is no scheduler, notification delivery, alert acknowledgement, retention policy, list deletion,
user ownership, authorization, rate limiting or production Analyze producer. Snapshots are captured only
on an explicit local request. The Phase 15 scanner is a separate read model over comparable stored
Analyze state; it does not alter watchlists or their snapshots. Strategy, portfolio, risk, leverage, execution and broker boundaries remain
disconnected, and live trading stays disabled.

## Migration

Upgrade from 0004 is additive. Downgrade from 0005 removes alert events, snapshot items, snapshots,
members and lists in dependency order. Analyze reports, forecasts, outcomes, market data and audit history
remain intact. Export retained watchlist history before rollback.
