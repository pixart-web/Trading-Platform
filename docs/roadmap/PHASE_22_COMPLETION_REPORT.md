# Phase 22 completion report

## Summary, phase and architecture

Phase 22 implements an offline research factory over shared Phase 21 event-driven simulation,
with immutable experiment plans/results, temporal orchestration, robustness/calibration/drift
diagnostics, durable one-shot final consumption and model evidence lifecycle. Supported execution
remains independent crypto spot LONG windows, not leveraged/multi-asset portfolio execution.
See ../architecture/RESEARCH_FACTORY.md for exact contracts and economic/statistical assumptions.
Implementation is complete for this documented research scope; profitability and production
readiness are not claimed. Phase 23 is next and was not started. No push/main merge is performed.

## Initial assessment, design, gaps and acceptance

The clean preserved baseline was Phase 21 commit f724fb04e9fd396db0eadac4c5a16205f4c75b70.
It lacked experiment matrices, research orchestration and evidence-linked model registration.
The pre-edit assessment declared temporal splits/embargo, bounded baseline/parameter/cost matrices,
walk-forward/rolling evaluation, independent assets/regimes/horizons, descriptive resampling,
calibration/drift, immutable artifacts, one-use final consumption, read-only endpoints and
additive migration 0013. Existing PostgreSQL/Redis and financial-scope debt was preserved.
Acceptance requires training-only fit inputs, fresh strategy instances, no future receipts,
full losing-trial matrices, intact forecasts/outcomes, deterministic hashes and conflict detection,
no repeated final attempt after failure or study renaming, no synthetic/in-sample promotion,
explicit OOS economic gates, revision-controlled registry evidence and disabled production.
Synthetic regressions cover this infrastructure only and never prove economic value.

## Implementation and financial coverage

Plans bind frozen source UUID/hash and origin, ordered train/validation/test folds, final reserve,
maximum label horizon, embargo, versions/code/environment identity, variants, selection rationale,
causal declared regime provenance, horizon labels and bounded matrix/analysis seed. Train helpers
build expanding walk-forward or fixed-width rolling windows. Known receipts are preserved;
subsets require complete aligned coverage and receipt cutoff. fit sees training only and returns
canonical bounded JSON; full fitted artifacts/hashes persist. Every evaluation materializes a
new callback and starts flat. Reports retain validation/test/regime and losing runs separately.
Native crypto assets and horizons are independently labelled; no mixed-currency return aggregate
or continuous-portfolio regime attribution is invented. Factory providers remain responsible for
complete deterministic fitted state and causal features/labels; no new predictive algorithm is added.

Reports retain original Phase 21 net return/CAGR/drawdown/ratios/expectancy/trade counts/costs,
exposure/turnover/bankruptcy/tail metrics with unavailable reasons. Moving-block bootstrap
terminal-return and shuffled-return Monte Carlo drawdown quantiles use explicit seeds/counts/
blocks/quantiles/sample minima. They are descriptive stationary/exchangeable-history scenarios,
not confidence intervals or calibrated ruin probabilities. Drift compares training/evaluation
close-return means and standardized shifts; zero reference variance is unavailable. Optional
predeclared ledger forecasts/outcomes are frozen and financially validated for Brier/top-label
calibration diagnostics, matched to OOS asset/model/horizon and excluded from the final reserve.
Missing inputs are unavailable; missing declared dependencies fail not ready. Trial count records
multiple-testing exposure; no corrected significance, optimizer or automated winner is claimed.

Final consumption requires committed experiments, freezes selection/experiment/plan hashes and
commits all native-symbol economic locks before final callbacks. The trained artifact comes from
the last sealed fold without fitting again. Failed attempts remain consumed; duplicates, renamed
studies/datasets/venues cannot unlock the same symbol. Final reports are readable, not rerunnable.
The internal backtester path is trusted offline Python, not a public broker permission or sandbox.

Model bundles tie to immutable experiment evidence. CHALLENGER requires real OOS net economics,
positive closed-trade expectancy, explicit sample/asset/fold/drawdown criteria, configured cost
stress and positive baseline improvement for complexity. SHADOW additionally requires one-shot
frozen final evidence; it starts no shadow process. DEGRADED/RETIRED retain audit history.
PRODUCTION cannot be entered. No actual real model qualification is claimed by this delivery.
Registry history is hash-linked and transitions use optimistic revision checks.

## Migration and operational risks

0013 follows 0012, adding five tables: research_studies, research_reports,
research_holdout_consumption, research_model_registry and research_model_events. Upgrade,
foreign keys, consumption uniqueness and downgrade are exercised in isolated SQLite. PostgreSQL
upgrade/rollback SQL generation passes; actual PostgreSQL migration/concurrency is unexecuted.
No existing production DB was upgraded. Export all artifacts AND consumed economic locks before
rollback. Downgrade deletes these tables; recreating an empty registry invalidates one-use final
governance and must not be treated as a fresh authorized holdout. There is no application reset API.

## Validation commands and exact results

- `.venv/Scripts/ruff.exe check .`: passed, all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: passed, 253 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: passed, no issues in 179 source files.
- `.venv/Scripts/python.exe -m pytest -q --cov=pocket_alpha.research --cov-report=term-missing`: 613 passed, 171 skipped, 2 warnings, 148.68s; research coverage 88%, 837 statements, 102 missed. This includes 30 passing Phase 22 cases and 10 Phase 22 PostgreSQL skips.
- Previous full suite without coverage: 612 passed, 171 skipped, 2 warnings, 121.16s, before the final registry audit regression.
- `.venv/Scripts/python.exe -m alembic heads`: 0013 (head).
- `.venv/Scripts/python.exe -m alembic upgrade head --sql`: passed, checked process exit; ignored local SQL artifact.
- `.venv/Scripts/python.exe -m alembic downgrade 0013:0012 --sql`: passed, checked process exit; ignored local SQL artifact.
- `git diff --check`: passed; Git emitted LF/CRLF normalization notices only.
- Changed-file/local-data exclusion and UTF-8 integrity checks: passed, 28 files.

Migration 0013 isolated SQLite upgrade/FK/consumption-primary-key uniqueness/downgrade regression passes in the full suite. Holdout tests confirm persistent one-use consumption after callback failure, frozen fitted artifacts, no final refit and renamed-study reuse rejection. API tests include SQL and DataRejected failures returning generic 503. Registry tests prove synthetic promotion rejection, revision/history integrity, explicit economic criteria, disabled production, future-evidence rejection and Decimal precision isolation. Positive real-data qualification and PostgreSQL concurrency are not verified; the uncovered registry promotion branches remain an explicit validation limitation. No valid tests were weakened.

Preexisting warnings are Starlette/httpx and AnyIO deprecations. Skips are not passes.
PostgreSQL/Redis integration, actual PostgreSQL migrations/concurrent writers, Docker build and
remote CI were not executed locally: existing Windows psycopg DLL/application-control and Docker
service limitations remain. Frontend checks were not run because no frontend changes were made.

## Real-data evidence

An isolated offline causal readiness probe used Phase 20 REAL Coinbase BTC-USD H1 dataset
2c1d135b-27e1-4405-8504-b157c769ffc4, SHA256
79c7606a172478a6ac7cd94a0204685c30bf992b373e0be0a0f89b72058c5f44.
Its historical January 2025 candles were locally received in September 2026. Study
829dd2b3-4ee8-5f17-ba1a-474b01dd555d at 2026-09-18T18:04:36.251999+00:00
was rejected with "research window contains data received after its cutoff". fit_calls=0,
incomplete plan rolled back, ready=false and profitability_claim=false. This is causal
readiness evidence, not an economic backtest or promoted strategy. Probe source hash:
2ad66fdfa95d7840ab7ae4fd88eded462058c50600ce82bec8cb85c7e5b406a5;
environment hash f703c156dc2675231b9bf66982d9b9258e16508b2d8fc6557f3cdde2dad4a102.
The probe precedes subsequent API/error-handling and registry audit corrections. A final-source
temporal check at 2026-09-18T18:10:50.737404+00:00 repeated the same refusal with source hash
86664c4562eaccb3c33345f9d42c71cffbeb0e00883be9d4a9a5e8efe650491f. All data,
SQL/evidence artifacts and isolated DBs remain ignored under data/local. No network/broker call.

## Self-audit, limitations, security, assumptions and debt

Corrections preserved financial/quality checks, complete matrices, full fitted/forecast artifacts
and all valid timestamp assertions. Intermediate validation caught missing fixture FK metadata,
an import/type error and a source-tree identity change during active tests; fixes registered
metadata and repeated checks with stable source. The hash mismatch protection was retained.
Registry audit additionally prevents registration/promotion before evidence and isolates
baseline-improvement subtraction at Decimal precision 80. Regression assertions cover both.
API quality/dependency/corruption responses are generic 503, read-only and no-store; no HTTP
run, promotion or holdout reset route was added. Code/environments are verified by Backtester.
Hash integrity is not an authenticated signature, and caller callbacks/raw administrative DB
access are outside the trusted application governance boundary. No secrets, withdrawal rights,
real broker requests or orders were introduced. Live remains Literal[False].

Actual exchange costs, tick/quote rounding, intrabar liquidity and marks remain uncalibrated.
SHORT, derivatives, leverage, borrow/funding, equity/ETF corporate actions and continuous
portfolio execution are unsupported. Close-mark drawdown protection does not guarantee capital
survival. Universe/selection/survivorship bias is explicitly unassessed. Resampling assumes history
is representative; no probability/confidence/profitability or calibrated ruin model is fabricated.
External regime labels require provenance but are not recomputed by a new classifier. Thresholds
are caller-declared research policy, not recommended live risk limits. Statistical multiple-testing
correction, independent economic validation, fresh final-campaign governance, production registry
activation, MLflow/external distributed scheduling and operational drift monitoring remain debt.
Registry states do not operate paper/shadow/live trading. Next: Phase 23 paper trading, not started.

## Complete changed file list

- `docs/architecture/BACKTESTING.md`
- `docs/architecture/RESEARCH_FACTORY.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/research/VALIDATION_POLICY.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/PHASE_22_COMPLETION_REPORT.md`
- `docs/roadmap/ROADMAP.md`
- `migrations/env.py`
- `migrations/versions/0013_research.py`
- `src/pocket_alpha/backtesting/engine.py`
- `src/pocket_alpha/main.py`
- `src/pocket_alpha/research/__init__.py`
- `src/pocket_alpha/research/api.py`
- `src/pocket_alpha/research/diagnostics.py`
- `src/pocket_alpha/research/models.py`
- `src/pocket_alpha/research/registry.py`
- `src/pocket_alpha/research/service.py`
- `src/pocket_alpha/research/storage.py`
- `src/pocket_alpha/research/temporal.py`
- `tests/research_fixtures.py`
- `tests/test_research_api.py`
- `tests/test_research_diagnostics.py`
- `tests/test_research_holdout.py`
- `tests/test_research_migration.py`
- `tests/test_research_registry.py`
- `tests/test_research_service.py`
- `tests/test_research_temporal.py`
