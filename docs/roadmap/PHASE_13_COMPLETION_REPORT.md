# Phase 13 completion report

## Summary and phase

Phase 13 implements the shared Analyze experience as immutable full-horizon reports, append-only
persistence, an exact read-only API and a validated responsive web panel. It is the earliest
incomplete authorized phase. Phase 14 was not started. The implementation composes existing
artifacts and makes no claim of profitability, recommendation quality or production readiness.

## Assessment, gaps and design

Before this phase, Pocket Score, forecasts, directional analysis and Opportunity Score existed as
separate contracts. There was no single causal snapshot for users or future application consumers,
no storage for their combined view, and no honest web state for missing analysis.

An Analyze report now binds one market, asset, candle timeframe and UTC as-of time to one Pocket
Score slot and all thirteen forecast horizons in canonical order. Every forecast, directional and
opportunity slot contains either its complete immutable artifact or an explicit unavailable reason.
The assembler derives coverage, presentation conclusions and canonical issues while preserving the
upstream calculations, both directional cases, economics, evidence, opposition, uncertainty,
versions and identifiers unchanged.

Migration 0004 stores the full report JSON append-only and indexes exact market/timeframe/as-of
lookup. A GET-only FastAPI endpoint returns that exact snapshot or explicit NO_ANALYSIS_SNAPSHOT.
The existing restricted Next.js gateway forwards only the allowlisted path and query fields. The
market workspace runtime-validates the response before rendering every horizon.

## Acceptance criteria

Completed:

- exactly thirteen horizons from 1H through 12M in canonical order;
- candle timeframe kept separate from each forecast horizon;
- explicit artifact-or-reason contract for Pocket Score, forecast, directional and opportunity;
- market, asset, timeframe, horizon, as-of and upstream identifier consistency;
- unique forecast, directional and opportunity identifiers across horizons;
- UTC causal checks for forecast availability and report generation;
- deterministic complete-input hash and derived COMPLETE/PARTIAL/UNAVAILABLE coverage;
- ELIGIBLE_LONG, ELIGIBLE_SHORT, INELIGIBLE_LONG, INELIGIBLE_SHORT, NO_TRADE and UNAVAILABLE
  summaries derived from existing artifacts;
- canonical issues for missing, unavailable, expired, uncalibrated, NO_TRADE and ineligible states;
- append-only idempotent persistence with conflict detection and future-time ledger rejection;
- exact lookup without silently substituting an older snapshot;
- explicit unavailable API envelope, no-store caching and no analytical write endpoint;
- gateway path/query allowlist and sanitized upstream failures;
- runtime browser validation of Decimal strings, hashes, horizon order, identities and upstream links;
- accessible loading, error, missing and report states with responsive horizon presentation;
- evidence for both LONG and SHORT cases, uncertainty, exclusions and versions visible;
- explicit UI language that scores are not probabilities or risk approvals;
- no strategy, portfolio, risk, leverage, execution or broker dependency.

## Changed files

- src/pocket_alpha/analysis/__init__.py
- src/pocket_alpha/analysis/api.py
- src/pocket_alpha/analysis/models.py
- src/pocket_alpha/analysis/service.py
- src/pocket_alpha/analysis/storage.py
- src/pocket_alpha/main.py
- migrations/env.py
- migrations/versions/0004_analyze_reports.py
- tests/test_analyze.py
- frontend/lib/analysis.ts
- frontend/lib/proxy.ts
- frontend/components/analysis-panel.tsx
- frontend/components/market-workspace.tsx
- frontend/app/globals.css
- frontend/tests/analysis.test.ts
- frontend/tests/proxy-route.test.ts
- frontend/e2e/workspace.spec.ts
- docs/architecture/ANALYZE.md
- docs/architecture/CHARTING_ARCHITECTURE.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/architecture/OPPORTUNITY_SCORE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_13_COMPLETION_REPORT.md
- README.md

## Migration and compatibility

Migration 0004 is additive. It creates only `analyze_reports` and
`ix_analyze_reports_market_timeframe_as_of`, with foreign keys to existing market and asset
metadata. Existing API and database contracts remain available. The analysis route is a new
read-only endpoint and the frontend gateway adds only its exact allowlist entry.

Downgrading 0004 to 0003 deletes Analyze snapshots and their index while retaining forecasts,
outcomes, market data and audit history. Retained Analyze reports must be exported before rollback.
No dependency or environment-variable change was introduced.

## Validation

Executed locally on Windows with Python 3.12.14, Node 24 and Next.js 16.3.4:

- ruff check . - passed.
- ruff format --check . - passed; 134 files already formatted.
- mypy . - passed; 93 source files checked.
- pytest --cov=pocket_alpha --cov-report=term-missing - 414 passed, 84 skipped, 2 dependency
  deprecation warnings and 97% total coverage.
- focused Analyze suite - 11 passed and 3 PostgreSQL-parametrized cases skipped locally.
- Alembic heads/history - one head at 0004 with a linear 0001 -> 0004 chain.
- Alembic offline upgrade to head - passed and rendered the new table, foreign keys and index.
- Alembic offline downgrade 0004:0003 - passed and removed only the new index/table.
- pnpm lint - passed.
- pnpm typecheck - passed.
- pnpm test - 46 passed across four files.
- pnpm build - passed.
- pnpm test:e2e - 11 Playwright Chromium tests passed, including the stored Analyze snapshot.

Docker Desktop was unavailable, so the destructive disposable PostgreSQL/Redis migration round trip,
service integration and Docker image builds were not executed locally. The 84 pytest skips include
service-dependent parametrizations. No result is inferred for these unexecuted checks.

## Financial coverage and assumptions

Analyze performs no new financial calculation and does not select a preferred horizon. It preserves
upstream calibrated labels, expected ranges, cost assumptions, net expected return, liquidity,
uncertainty, risk/reward, eligibility and exclusions without changing their meaning. COMPLETE means
all artifacts are present; it does not mean profitable, calibrated, validated or tradable.

Synthetic tests verify composition, storage, API and presentation contracts only. They do not prove
accuracy, profitability, statistical significance, fills, drawdown control, ruin limits or net
compounded growth. No production policy, dataset, forecast or recommendation is included.

## Security, limitations and debt

The API is read-only, disables caching and exposes no report upload, strategy, order or broker route.
The gateway keeps a fixed upstream origin, path and query allowlists, redirect rejection, timeout and
sanitized errors. No credential, withdrawal permission or secret was added. Live execution remains
disabled.

There is no scheduled production report producer, authorization or rate limiting. Remaining debt
includes production orchestration from legitimate upstream artifacts, intermediate artifact
persistence, per-use-case freshness policies, policy governance, real temporal validation,
observability, authentication and public-deployment hardening. Watchlists can consume stored Analyze
snapshots in the next phase, but Phase 14 was not started.
