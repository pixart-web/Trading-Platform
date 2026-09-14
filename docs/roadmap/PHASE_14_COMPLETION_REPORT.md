# Phase 14 completion report

## Summary and phase

Phase 14 implements persistent local watchlists, revision-protected membership, immutable exact-time
Analyze snapshots and append-only alert events, with a validated responsive web experience. It is the
earliest incomplete authorized phase. Phase 15 was not started. No profitability, recommendation or
production-readiness claim is made.

## Assessment, gaps and design

Before this phase, the application could inspect one stored Analyze report but could not retain a set
of markets, freeze their analytical state or explain changes between observations. Phase 14 adds a
watchlist boundary over registered market metadata and the Phase 13 Analyze repository.

Mutable list changes use expected revisions and atomic conditional updates. Each snapshot freezes one
list revision and resolves every member only at the requested UTC as-of instant. A snapshot item stores
an exact Analyze report reference or an explicit `NO_ANALYSIS_SNAPSHOT`, plus all thirteen canonical
horizon conclusions. The first snapshot is a baseline; later snapshots derive availability and changed
conclusion events from the latest earlier snapshot. Snapshot and event identities are immutable and
idempotent.

## Acceptance criteria

Completed:

- persistent named local watchlists with a 250-member bound;
- one unique registered market per list and deterministic member order;
- optimistic revisions for rename, add and remove operations;
- idempotent create/add behavior and explicit identity/revision conflicts;
- immutable snapshots bound to list revision, UTC as-of and generation times;
- exact market/timeframe/as-of Analyze lookup without older fallback;
- explicit report-or-unavailability state for every snapshot member;
- all thirteen self-describing forecast horizons in canonical order;
- COMPLETE/PARTIAL/UNAVAILABLE coverage derived from report presence only;
- canonical SHA-256 input fingerprint over membership and snapshot contents;
- baseline suppression and derived availability/conclusion transition events;
- deterministic event UUIDs and append-only idempotent event persistence;
- local CRUD/snapshot/event API with bounded input and no-store responses;
- method/path/query/body allowlists in the Next.js gateway;
- runtime Zod validation and accessible loading/error/empty states;
- responsive member, snapshot and event presentation;
- explicit UI language that events are not price alerts, recommendations or risk approval;
- no scanner, strategy, portfolio, risk, leverage, execution or broker dependency.

## Changed files

- `src/pocket_alpha/watchlists/__init__.py`
- `src/pocket_alpha/watchlists/api.py`
- `src/pocket_alpha/watchlists/models.py`
- `src/pocket_alpha/watchlists/service.py`
- `src/pocket_alpha/watchlists/storage.py`
- `src/pocket_alpha/main.py`
- `migrations/env.py`
- `migrations/versions/0005_watchlists.py`
- `tests/test_watchlists.py`
- `frontend/lib/watchlists.ts`
- `frontend/lib/proxy.ts`
- `frontend/app/api/market-data/[...path]/route.ts`
- `frontend/components/watchlist-panel.tsx`
- `frontend/components/market-workspace.tsx`
- `frontend/app/globals.css`
- `frontend/tests/watchlists.test.ts`
- `frontend/tests/proxy-route.test.ts`
- `frontend/e2e/workspace.spec.ts`
- `docs/architecture/WATCHLISTS.md`
- `docs/architecture/CHARTING_ARCHITECTURE.md`
- `docs/architecture/INTELLIGENCE_ARCHITECTURE.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_14_COMPLETION_REPORT.md`
- `README.md`

## Migration and compatibility

Migration 0005 is additive and creates `watchlists`, `watchlist_members`, `watchlist_snapshots`,
`watchlist_snapshot_items` and `watchlist_alert_events`, with foreign keys and indexes for list
membership, exact snapshots and chronological events. Existing data and endpoints remain available.

Downgrading 0005 to 0004 removes only Phase 14 lists, members, snapshots and events. Analyze reports,
forecasts, outcomes, market data and audit history remain. Retained watchlist history must be exported
before rollback. No dependency or environment-variable change was introduced.

## Validation

Executed locally on Windows with Python 3.12.14, Node 24 and Next.js 16.3.4:

- `ruff check .` - passed.
- `ruff format --check .` - passed; 143 Python files already formatted.
- `mypy .` - passed; 100 source files checked.
- full `pytest -q --disable-warnings` - 421 passed, 90 skipped and 2 warnings in 9.32s.
- focused watchlist suite - 7 passed and 6 PostgreSQL-parametrized cases skipped locally.
- focused watchlist coverage - 88% across 476 statements; 7 passed and 6 skipped.
- Alembic heads/history - one head at 0005 with a linear 0001 -> 0005 chain.
- Alembic offline upgrade to head - passed and rendered all five Phase 14 tables and indexes.
- Alembic offline downgrade 0005:0004 - passed and removed only Phase 14 schema in dependency order.
- `pnpm lint` - passed.
- `pnpm typecheck` - passed.
- `pnpm test` - 52 passed across five files.
- `pnpm build` - passed.
- `pnpm test:e2e` - 12 Playwright Chromium tests passed, including the watchlist flow.

A full instrumented coverage run could not complete under the host application-control policy; the
coverage C tracer DLL was blocked, and the slower Python tracer process ended before completing the
suite. Full tests without instrumentation and focused coverage both completed. Docker Desktop was
unavailable, so the disposable PostgreSQL/Redis migration round trip, service integration and Docker
image builds were not executed locally. The 90 full-suite skips include service-dependent
parametrizations. No result is inferred for unexecuted checks.

## Financial coverage and assumptions

Watchlists perform no price calculation, forecast, score, economic ranking, position sizing or risk
decision. Snapshot conclusions are copied from exact stored Analyze reports without reinterpretation.
Coverage status states only whether exact reports exist. An alert event states only that stored
availability or a horizon conclusion changed between two observations.

Synthetic tests verify persistence, identity, causality, transitions, API and presentation contracts.
They do not prove accuracy, calibration, profitability, statistical significance, fills, drawdown
control, ruin limits or net compounded growth. No production dataset or recommendation is included.

## Security, limitations and debt

The gateway uses a fixed server-only origin, explicit method/path/query allowlists, an 8 KiB body cap,
redirect rejection, timeouts and sanitized failures. No secret, broker credential, withdrawal
permission, external notification or order route was added. Live execution remains disabled.

This is a local single-scope feature without authentication, user ownership, authorization, rate
limiting, list deletion, scheduling, notification delivery, acknowledgement or retention policy.
Snapshots require an explicit request and depend on separately produced exact Analyze reports. Phase 15
can add cross-market scanning over comparable stored state, but was not started.