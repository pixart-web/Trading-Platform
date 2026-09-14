# Phase 15 completion report

## Summary and phase

Phase 15 implements immutable cross-market scans over exact stored Analyze reports, explicit metadata
and economic filters, policy-isolated deterministic rankings, complete exclusions and a validated
responsive web experience. It is the earliest incomplete authorized phase. Phase 16 was not started.
No profitability, recommendation or production-readiness claim is made.

## Assessment, gaps and design

Before this phase, the application could inspect one Analyze report or freeze a watchlist, but could not
resolve a bounded registered-market universe at one timeframe, horizon and UTC instant or compare stored
Opportunity Scores across markets. The scanner now consumes the Phase 13 read model without recalculating
any Phase 3–12 artifact.

Metadata filters narrow registered assets and markets before exact report lookup. Each market is resolved
only against an Analyze report with the requested timeframe and `as_of`; missing or unavailable state is
preserved. Available and eligible opportunities pass explicit direction and economic gates. Ranking reuses
the Phase 12 ordering and never compares different Opportunity policy version/hash identities. Every
universe market appears exactly once as ranked or excluded.

## Acceptance criteria

Completed:

- bounded registered-market universe with asset type, venue, quote currency and market filters;
- canonical sorted/unique filters and fail-closed rejection above 1,000 markets;
- exact timeframe, horizon and UTC as-of identity with no older-report fallback;
- immutable client-supplied scan UUID and idempotent identical replay;
- conflict rejection when a UUID is reused for another request;
- explicit direction, score, net return, liquidity, uncertainty, risk/reward and cost filters;
- full scanner and upstream economic exclusion reasons;
- only available and eligible Opportunity Scores enter rankings;
- separate rankings for every Opportunity policy version and SHA-256 hash;
- Phase 12 deterministic ordering and a bounded per-policy result limit;
- exact universe and Analyze coverage invariants with honest `NO_MATCHES` state;
- canonical SHA-256 fingerprint over request, resolved universe, reports, rankings and exclusions;
- additive append-only persistence and bounded create/read/list API with no-store responses;
- fixed-origin Next.js gateway with path, method, query and 8 KiB body allowlists;
- Zod validation of UUIDs, timestamps, hashes, Decimal strings, identities, coverage and rankings;
- accessible responsive filters, isolated ranking tables and inspectable exclusions;
- no strategy, portfolio, risk, leverage, execution or broker dependency.

## Changed files

- `src/pocket_alpha/scanner/__init__.py`
- `src/pocket_alpha/scanner/api.py`
- `src/pocket_alpha/scanner/models.py`
- `src/pocket_alpha/scanner/service.py`
- `src/pocket_alpha/scanner/storage.py`
- `src/pocket_alpha/main.py`
- `migrations/env.py`
- `migrations/versions/0006_scan_reports.py`
- `tests/test_scanner.py`
- `frontend/lib/scanner.ts`
- `frontend/lib/proxy.ts`
- `frontend/components/scanner-panel.tsx`
- `frontend/components/market-workspace.tsx`
- `frontend/app/globals.css`
- `frontend/tests/scanner.test.ts`
- `frontend/tests/proxy-route.test.ts`
- `frontend/e2e/workspace.spec.ts`
- `docs/architecture/SCANNER.md`
- `docs/architecture/ANALYZE.md`
- `docs/architecture/OPPORTUNITY_SCORE.md`
- `docs/architecture/WATCHLISTS.md`
- `docs/architecture/CHARTING_ARCHITECTURE.md`
- `docs/architecture/INTELLIGENCE_ARCHITECTURE.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_15_COMPLETION_REPORT.md`
- `README.md`

## Migration and compatibility

Migration 0006 is additive and creates `scan_reports` with immutable JSON payloads plus a
`candle_timeframe`, `horizon`, `as_of` lookup index. Existing endpoints and data remain available.

Downgrading 0006 to 0005 removes only the scan index and scan reports. Watchlists, Analyze reports,
forecasts, outcomes, market data and audit history remain. Retained scan history must be exported before
rollback. No dependency or environment-variable change was introduced.

## Validation

Executed locally on Windows with Python 3.12.14, Node 24 and Next.js 16.3.4:

- `ruff check .` - passed.
- `ruff format --check .` - passed; 151 Python files already formatted.
- `mypy .` - passed; 107 source files checked.
- full `pytest -q --disable-warnings` - 430 passed, 98 skipped and 2 warnings in 8.26s.
- focused scanner suite - 9 passed and 8 PostgreSQL-parametrized cases skipped locally.
- focused scanner coverage - 92% across 353 statements; 9 passed and 8 skipped.
- Alembic heads/history - one head at 0006 with a linear 0001 -> 0006 chain.
- Alembic offline upgrade to head - passed and rendered `scan_reports` and its index.
- Alembic offline downgrade 0006:0005 - passed and removed only the Phase 15 index/table.
- `pnpm lint` - passed.
- `pnpm typecheck` - passed.
- `pnpm test` - 56 passed across six files.
- `pnpm build` - passed.
- `pnpm test:e2e` - 13 Playwright Chromium tests passed, including the scanner flow.
- final scanner-only Playwright rerun after the last schema hardening - 1 passed.

Docker Desktop was unavailable, so the disposable PostgreSQL/Redis migration round trip, service
integration and Docker image builds were not executed locally. The 98 full-suite skips include
service-dependent parametrizations. No result is inferred for unexecuted checks.

## Financial coverage and assumptions

The scanner preserves Decimal economic values already calculated by Phase 12. It filters and orders
stored values; it does not calculate prices, forecasts, probabilities, costs, position sizes, allocations
or risk limits. A 0–100 Opportunity Score is an explained index and is never relabelled as probability.
Eligibility only restates the versioned upstream economic policy.

Synthetic tests verify persistence, identity, causality, policy isolation, filtering, API and
presentation contracts. They do not prove accuracy, calibration, profitability, statistical
significance, fills, drawdown control, ruin limits or net compounded growth. No production dataset,
provider, promoted policy or recommendation is included.

## Security, limitations and debt

The gateway uses a fixed server-only origin, explicit method/path/query allowlists, an 8 KiB body cap,
redirect rejection, timeouts and sanitized failures. No secret, broker credential, withdrawal permission,
notification or order route was added. Live execution remains disabled.

Scans are explicit local requests and depend on separately produced exact Analyze reports. There is no
scheduler, background refresh, authentication, ownership, authorization, rate limiting, retention policy,
production orchestration or automatic response to changing data. Intermediate score persistence and
policy governance remain limited. Phase 16 portfolio work remains unimplemented.
