# Phase 21 completion report

## Summary and phase

Phase 21 implements offline causal event-driven backtesting for one crypto spot LONG market.
Implementation is complete within the documented scope, not universally across asset classes.
Architecture and economic assumptions are in ../architecture/BACKTESTING.md. Phase 22 is next
and has not been started. No push or main integration is performed by this task.

## Assessment, gaps, design and acceptance

The preserved clean baseline was Phase 20 commit 78cc21d7a21c1f45dce561b6a84a2b6a81e511b8.
It supplied frozen real datasets and shared intelligence but no event-driven fill ledger.
Before production edits the assessment declared immutable manifests, recorded receipt causality,
shared technical computation, explicit spot LONG scope, independent risk reservations,
complete future-bar-close fills, additive migration and read-only report retrieval.
Known PostgreSQL/Redis integration debt was retained rather than reported as ready.

Acceptance covers no future-prefix leakage, forecast generation/expiry/version checks,
no same-bar execution, latency/expiry sequencing, fee/spread/slippage/impact accounting,
shared bar liquidity and partial fills, cancellation/reservation release, cash/inventory
conservation, idempotent intent/fill identity, reproducible report conflicts, immutable
forecast persistence, missing-metric reasons and disabled live execution. Regression tests
passed for this scope. No protections are claimed for an unsupported universe or asset class.
Final holdout runs are blocked until protected research authorization exists.

Self-review isolated callback Decimal context, revalidated entry inputs and preserved full
forecast snapshots and timestamp assertions. Automatic review rejected an intermediate
proposal interpreted as weakening assertions/artifacts; the accepted correction retained
both and changed serialization/check ordering. No valid tests were weakened.

## Architecture and financial coverage

The Python modular monolith reuses the shared technical kernel and immutable forecast inputs.
Strategies receive known immutable views; risk approvals and cash/quantity reservations
precede simulated execution. No strategy broker dependency or real order route was added.
UTC events and Decimal precision 80 reconcile fills, marked equity and closed inventory cohorts.
Metrics include net return, CAGR, drawdown/duration, volatility, Sharpe/Sortino/Calmar,
profit factor, net expectancy, win/loss counts, turnover, exposure, costs, bankruptcy,
drawdown breaches and empirical tail loss. Insufficient samples, irregular intervals or
zero denominators yield unavailable metrics with reasons. Ruin probability remains unavailable.

## Migration and operational risk

Migration 0012 follows 0011 and adds backtest_reports with dataset foreign key and indexes.
Isolated SQLite upgrade/constraints/downgrade tests pass. PostgreSQL upgrade/downgrade SQL
was generated successfully. Downgrade deletes backtest reports only: export them first.
Actual PostgreSQL migration and concurrent writer integration were not executed locally.
No existing production database was upgraded; empirical evidence used an isolated SQLite DB.

## Exact validation results

- `.venv/Scripts/ruff.exe check .`: passed, all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: passed, 234 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: passed, no issues in 163 source files.
- `.venv/Scripts/python.exe -m pytest -q`: 583 passed, 161 skipped, 2 warnings, 41.22s.
- `.venv/Scripts/python.exe -m pytest -q tests/test_backtesting_engine.py tests/test_backtesting_inputs.py tests/test_backtesting_metrics.py tests/test_backtesting_migration.py tests/test_backtesting_risk.py tests/test_backtesting_storage.py --cov=pocket_alpha.backtesting --cov-report=term-missing`: 39 passed, 2 skipped, 2 warnings, 27.48s; 94% coverage, 779 statements, 43 missed.
- `.venv/Scripts/python.exe -m alembic heads`: 0012 (head).
- `.venv/Scripts/python.exe -m alembic upgrade head --sql`: passed; local ignored SQL artifact.
- `.venv/Scripts/python.exe -m alembic downgrade 0012:0011 --sql`: passed; local ignored SQL artifact.
- `git diff --check`: passed; Git emitted LF/CRLF normalization notices only.

The two warnings are existing Starlette/httpx and AnyIO deprecations. Skips are not passes.
PostgreSQL/Redis integration, real PostgreSQL migration/concurrency, Docker build and CI were
not executed here; existing Windows psycopg DLL/application-control and Docker daemon
limitations remain. Frontend checks were not run because this phase changes no frontend.

## Real-data causal evidence

An offline probe used the Phase 20 frozen REAL Coinbase BTC-USD H1 dataset
2c1d135b-27e1-4405-8504-b157c769ffc4, SHA256
79c7606a172478a6ac7cd94a0204685c30bf992b373e0be0a0f89b72058c5f44.
Its 24 January 2025 candles were received in September 2026; knowledge timestamps were
preserved. The final-source probe generated report 13ca2342-efba-59e5-986a-f7b8a2a2a43e
at 2026-09-18T07:23:12.684596+00:00. It produced zero fills and STALE_DATA, with
INSUFFICIENT_CAUSAL_EXECUTION_WINDOW. Reload in a fresh session equalled the stored report.
Source-tree hash: 8b54bc57f2f3f5301bcdd394ec71eb95f09bd2bf5878a014fa43906adc9c4a81.
Environment hash: f703c156dc2675231b9bf66982d9b9258e16508b2d8fc6557f3cdde2dad4a102.
The manifest records the baseline git revision plus verified uncommitted implementation hash.
Evidence/report/database files remain ignored under data/local; no network or broker call was used.
An initial smoke invocation failed because of an incorrect import path; the corrected probe
passed. Probe cost assumptions are explicit but unvalidated and imply no economic result.

## Economic assumptions, limitations, security and debt

Complete future-bar CLOSE approximates execution; it is not an observed midquote or fill.
Participation, latency, fees, spread, slippage and linear cumulative impact are configurable
research assumptions, not calibrated exchange data. Price ticks, quote rounding and actual
fee schedules are not reproduced. Close marks miss intrabar drawdowns; halting new orders
cannot guarantee capital protection on existing inventory. No forced liquidation is invented.
Single-market selection/survivorship bias remains unassessed. SHORT, derivatives, leverage,
borrow/funding, stock/ETF corporate actions and universe research are unsupported.
Synthetic tests establish mechanics only; profitability_claim and live_ready remain false.
Callbacks are trusted code, not sandboxed; callers must provide deterministic versioned logic.
Hashes detect corruption and are not signatures. GET is read-only with generic dependency
errors and no-store; there is no write HTTP endpoint. Live configuration remains Literal[False].
No credentials, withdrawal rights, broker orders or secrets were added. Dependency failures
are not ready. Debt includes infrastructure validation, independently calibrated execution
costs, protected research registry/holdout authorization, richer asset support and strategy
lifecycle validation. Those are future work; Phase 22 was not started.

## Complete changed file list

- `docs/architecture/BACKTESTING.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/research/VALIDATION_POLICY.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/PHASE_21_COMPLETION_REPORT.md`
- `docs/roadmap/ROADMAP.md`
- `migrations/env.py`
- `migrations/versions/0012_backtests.py`
- `src/pocket_alpha/backtesting/__init__.py`
- `src/pocket_alpha/backtesting/api.py`
- `src/pocket_alpha/backtesting/engine.py`
- `src/pocket_alpha/backtesting/execution.py`
- `src/pocket_alpha/backtesting/inputs.py`
- `src/pocket_alpha/backtesting/metrics.py`
- `src/pocket_alpha/backtesting/models.py`
- `src/pocket_alpha/backtesting/risk.py`
- `src/pocket_alpha/backtesting/service.py`
- `src/pocket_alpha/backtesting/storage.py`
- `src/pocket_alpha/main.py`
- `tests/backtest_fixtures.py`
- `tests/test_backtesting_engine.py`
- `tests/test_backtesting_inputs.py`
- `tests/test_backtesting_metrics.py`
- `tests/test_backtesting_migration.py`
- `tests/test_backtesting_risk.py`
- `tests/test_backtesting_storage.py`
