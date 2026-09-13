# Phase 8 — Forecast infrastructure completion report

## Assessment, gaps and design

The authorized request named phases 8, 9 and 10. The engineering constitution requires one phase
per authorized task and only the earliest incomplete phase, so this change implements Phase 8 only.
Before production edits, the repository contained the forecast horizon enum and a preliminary
architecture note, but no forecast/outcome domain entities, causal evidence contract, append-only
persistence, migration, lifecycle validation, expiry convention or evaluator.

Phase 8 adds a shared Python forecast boundary after intelligence. It accepts externally produced
predictions and stores immutable, versioned snapshots; it does not manufacture a model, probability
or profitability claim. Complete available forecasts require exact Decimal UP/DOWN/RANGE
probabilities, a unique winning direction, matching confidence, explicit calibration label,
expected return/range/move, a classification threshold, versions, lifecycle stage, dataset hash and
one or more canonical availability-timestamped evidence snapshots. Unavailable forecasts fail
closed with a reason and no prediction values.

`ForecastLedger` validates generation time and later outcomes before delegating to the persistence
adapter. Repeated identical writes are idempotent; conflicting content under an existing identity
is rejected. Outcomes are separate, unique per forecast and accepted only after expiry. Their
returns, excursions, directional correctness and optional target/invalidation hits must match the
stored reference and observed prices. RANGE does not receive an invented favorable/adverse side.

Hour/day horizons are exact elapsed UTC durations. 6M/12M use UTC calendar months with month-end
clamping. Candle timeframe and forecast horizon remain independent. Exchange-session semantics are
not inferred because this phase has no authoritative venue calendar.

The deterministic reference evaluator groups by model version and horizon and computes multiclass
Brier score, expected-return MAE/RMSE, directional accuracy and aggregate calibration status. This
is measurement infrastructure and does not establish calibration, economic fitness or production
readiness. Full conventions and examples are in `docs/architecture/FORECAST_ARCHITECTURE.md`.

## Complete changed-file list

Created:

- `src/pocket_alpha/forecasts/__init__.py`
- `src/pocket_alpha/forecasts/horizons.py`
- `src/pocket_alpha/forecasts/models.py`
- `src/pocket_alpha/forecasts/service.py`
- `src/pocket_alpha/forecasts/evaluation.py`
- `src/pocket_alpha/forecasts/storage.py`
- `migrations/versions/0003_forecasts.py`
- `tests/test_forecasts.py`
- `docs/roadmap/PHASE_8_COMPLETION_REPORT.md`

Modified:

- `migrations/env.py`
- `README.md`
- `docs/architecture/FORECAST_ARCHITECTURE.md`
- `docs/architecture/INTELLIGENCE_ARCHITECTURE.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/roadmap/ROADMAP.md`

## Migrations and rollback risk

Migration 0003 adds `forecasts` and `forecast_outcomes`, foreign keys to market and asset metadata,
an index for market/horizon/generated-time retrieval and a unique one-outcome-per-forecast
constraint. Upgrade is additive and has no data conversion. Downgrade drops both new tables and
therefore permanently deletes forecast/outcome history; retained data must be exported first.

`python -m alembic upgrade head --sql` generated the complete PostgreSQL migration SQL successfully.
A real local PostgreSQL/Redis migration round trip was not executed because the Docker engine was
unavailable. The full pytest run includes the integration test but skips it, along with parameterized
PostgreSQL repository cases, unless `PA_INTEGRATION=1` and services are configured.

## Validation and acceptance

Python 3.12.14 in the existing `.venv` with `requirements.lock`:

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed; 99 files already formatted.
- `python -m mypy .`: passed; 69 source files.
- `python -m pytest --cov=pocket_alpha --cov-report=term-missing`: 348 passed, 81 skipped,
  2 upstream deprecation warnings; 99% statement coverage (2,149 statements, 5 missed).
- `python -m pytest -q tests/test_forecasts.py --cov=pocket_alpha.forecasts
  --cov-report=term-missing`: 15 passed, 2 PostgreSQL skips; forecast package 99% statement
  coverage (356 statements, 1 unsupported-dialect branch missed).
- `python -m alembic upgrade head --sql`: passed and emitted migrations 0001 through 0003.
- `git diff --check`: passed before this report; repeated in final verification.

Acceptance coverage includes all 13 horizons, UTC normalization and month-end clamping; canonical
evidence JSON/hash and causal availability; complete/unavailable states; exact probability sums,
unique direction and confidence; target/invalidation conventions; post-expiry outcome timing;
derived returns, UP/DOWN/RANGE excursions and directional correctness; append idempotency,
immutability conflicts, foreign-key fixtures, bounded retrieval and exact JSON round trips; and
independent Brier/MAE/RMSE/accuracy reference values. Tests use explicitly synthetic fixtures only.

Frontend checks were not repeated because no frontend or HTTP code changed. No tests were weakened.

## Financial, security and operational limits

There is no real dataset, forecast generator, fitted model, calibration procedure or claimed edge.
No net return, transaction cost, slippage, liquidity, capacity, drawdown, ruin or leverage assumption
is introduced. Statistical scores are not probabilities and forecast probabilities are not Pocket
Scores. A `CALIBRATED` label is immutable producer metadata; Phase 9 must substantiate it with
temporal out-of-sample calibration and economic evidence before any production promotion.

Live execution remains disabled. No API/UI write path, strategy, portfolio, risk, leverage,
execution or broker connection was added. No credential, secret, withdrawal permission or external
provider dependency is present. Dependency and data failures cannot create fallback forecasts.

Debt: authoritative trading calendars and corporate actions; outcome collection worker; baseline
models; calibration and walk-forward evaluation; cost/net-expectancy metrics; segmentation by asset,
class, regime, confidence and score bucket; registry persistence and promotion controls; drift and
data-quality monitoring; bulk/query pagination; API/UI consumption; real PostgreSQL migration run;
and upstream Starlette/httpx/AnyIO deprecation warnings.

Next phase: 9 — baseline forecast models, calibration and temporal economic evaluation. Not started.
Phase 10 Pocket Score is also not started.
