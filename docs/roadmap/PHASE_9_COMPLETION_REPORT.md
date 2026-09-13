# Phase 9 completion report

## Summary and phase

Phase 9 implements research-only baseline forecast fitting, probability calibration and temporal
economic evaluation. The earliest incomplete authorized phase was 9; Phase 10 was not started.
No model was fitted to real market data and no profitability or calibration claim is made.

## Assessment, gaps and design

Phase 8 supplied immutable forecasts and separate outcomes but had no forecast producer,
calibration procedure or cost-aware temporal evaluation. Phase 9 fills that narrow gap with a
deterministic three-class Gaussian naive Bayes baseline, temperature scaling on a separate later
partition and a one-unit economic reference over non-overlapping periods.

The design preserves the mandatory path from intelligence evidence into forecasts. It does not
connect strategies, portfolios, risk, leverage, execution or brokers. Predictions are Phase 8
Forecast values in RESEARCH stage and retain causal evidence, separate candle timeframe and forecast
horizon, immutable artifact hashes and explicit availability times.

## Acceptance criteria

Completed:

- explicit TRAIN, CALIBRATION, VALIDATION and FINAL_HOLDOUT partitions;
- training, calibration and evaluation reject future or unavailable outcomes and temporal overlap;
- deterministic interpretable class statistics with complete parameters and version identity;
- model artifacts record code, environment, model, schema, feature and dataset versions/hashes;
- temperature calibration includes the unchanged baseline and cannot worsen its fitting Brier score;
- Phase 8 forecast output preserves exact Decimal probabilities and fails closed on an ambiguous tie;
- economic evaluation includes explicit round-trip fee, spread, slippage and latency;
- reports include net expectancy, compounded return, drawdown, Sharpe, Sortino, Calmar, profit
  factor, exposure, turnover, costs, losing periods and observed ruin;
- synthetic tests exercise deterministic results, causal guards, cost sensitivity and loss/ruin paths;
- live execution remains disabled and no execution boundary is reachable.

## Changed files

- src/pocket_alpha/forecasts/research_models.py
- src/pocket_alpha/forecasts/baseline.py
- src/pocket_alpha/forecasts/calibration.py
- src/pocket_alpha/forecasts/economic.py
- tests/test_baseline_forecasts.py
- docs/architecture/BASELINE_FORECAST_MODELS.md
- docs/architecture/FORECAST_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_9_COMPLETION_REPORT.md
- README.md

## Migrations and compatibility

There is no database migration and no dependency change. Phase 9 adds research modules without
changing the Phase 8 ledger schema or existing API. Model and evaluation artifacts use explicit
schema versions. Adding persistence later requires an additive registry design and a data-retention
plan; these in-memory artifacts are not a persistence substitute.

## Validation

Executed locally on Windows with Python 3.12.14:

- ruff check . - passed.
- ruff format --check . - passed; 107 files already formatted at the time of the check.
- mypy . - passed; 74 source files checked.
- pytest --cov=pocket_alpha --cov-report=term-missing - 363 passed, 81 skipped, 2 dependency
  deprecation warnings, 99% total coverage.
- Focused Phase 9 suite - 15 passed.
- pnpm lint - passed.
- pnpm typecheck - passed.
- pnpm test - passed.
- pnpm build - passed with Next.js 16.3.4.

PostgreSQL/Redis integration was not executed locally because the Docker Desktop daemon was
unavailable. The 81 skipped tests include service-dependent parametrizations. This phase adds no
persistence or service integration, but CI with services remains the authoritative integration
check after publication. No result is inferred from an unexecuted command.

## Financial coverage and economic assumptions

The evaluator models one unit long for UP, one unit short for DOWN and zero exposure for RANGE.
Each active period pays the complete configured round-trip cost once. Turnover is two units per
active period. Compounding is sequential and only accepts non-overlapping forecast periods. Ratios
are per-period diagnostics and are not annualized.

It does not model position sizing, liquidity/capacity, funding, borrow availability, partial fills,
rejections, taxes, corporate actions, exchange sessions or tail dependence. Synthetic fixtures are
not evidence of real economic value. Probability scores are separate from confidence and Pocket
Score remains absent.

## Security, limitations and debt

No credentials, network provider, order route or withdrawal capability was added. Live execution
remains disabled by configuration and architecture. Inputs and artifacts are bounded and validated,
but no durable model registry, authorization layer or public endpoint exists.

Remaining research debt includes identified real datasets, outcome collection, rolling walk-forward
orchestration, bootstrap/Monte Carlo, parameter and cost stress, cross-asset/regime/confidence
stratification, liquidity-aware event-driven fills, artifact persistence and drift monitoring. These
must precede any claim of readiness or promotion.

The next roadmap phase is Phase 10, the configurable explained Pocket Score. It was not started.
