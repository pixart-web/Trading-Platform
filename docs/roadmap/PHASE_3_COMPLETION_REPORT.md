# Phase 3 — Technical intelligence

## Assessment and scope

Before production edits: clean main at 71d9126; Phases 0–2 implemented, no intelligence package.
Assessment, gaps, architecture, intended files, migration risk and acceptance criteria were
reported in the task before implementation. Existing work was preserved.

Implemented the first causal, parameterized, versioned feature framework with 15 indicator groups
across all five Phase 3 families. The shared backend service consumes trusted replay, produces
immutable availability-aware snapshots and records prefix hashes and freshness policy. No frontend
changes, HTTP endpoints, new dependency, database schema, migration or deployment configuration.
See ../architecture/TECHNICAL_INTELLIGENCE.md for exact formulas, units and limitations.

## Complete file list

Created:

- src/pocket_alpha/intelligence/__init__.py
- src/pocket_alpha/intelligence/technical/__init__.py
- src/pocket_alpha/intelligence/technical/models.py
- src/pocket_alpha/intelligence/technical/indicators.py
- src/pocket_alpha/intelligence/technical/service.py
- tests/test_technical_indicators.py
- tests/test_technical_service.py
- docs/architecture/TECHNICAL_INTELLIGENCE.md
- docs/roadmap/PHASE_3_COMPLETION_REPORT.md

Modified:

- README.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md

## Validation

New tests include hand-calculated feature references, nonlinear Wilder/EMA recurrence, exact
warm-up, every-kind prefix invariance and future perturbation, flat/zero-volume/extreme-price cases,
bad parameters and value contracts, immutable roundtrip snapshots, fixed arithmetic context,
canonical Decimal scales, session schedules, delayed receipt, future receipt, gaps and staleness.
Repository tests run on SQLite locally and additionally PostgreSQL in CI. Fixtures are synthetic
and test-only; the new module introduces no seeded or network market data.

Required commands: python -m ruff check .; python -m ruff format --check .; python -m mypy .;
python -m pytest --cov=pocket_alpha --cov-report=term-missing.
Local final results: Ruff lint passed; Ruff format checked 61 files; mypy passed on 41 source files;
pytest: 210 passed, 40 skipped, 2 upstream deprecation warnings. Overall statement coverage 99%
(969 statements, 4 missed); all three technical modules have 100% statement coverage.
The 40 skips require PostgreSQL/Redis locally. Docker/service integration and frontend regression
checks are delegated to the existing GitHub CI because neither schema nor frontend changed.
Remote results will be recorded after verification.

Initial checks found formatting issues and three typing errors; these were corrected, with no test
assertions removed or weakened. All numerical reference tests passed on their first execution.

## Financial coverage, security and economic assumptions

Feature arithmetic is tested; statement coverage is not proof of economic correctness or value.
These fixtures form numerical regression baselines, not profitability/backtest evidence. No
empirical predictive evaluation was performed: there is no legitimate reference market dataset,
forecast, strategy, cost model or execution path in this phase. Values are features, not scores,
probabilities, confidence, buy/sell votes or performance claims. Per-bar volatility is not annualized.

No secrets, external credentials, new public route, live trading or broker access. Existing hard
live-trading prohibition remains. Failed quality or dependencies propagate rather than becoming
empty valid analysis. Historical policy is explicit in each snapshot; consumers must gate replay
by availability timestamps, not chart positions.

## Limitations and debt

No real provider or production data. No API/UI indicator overlay, persistent feature registry,
incremental streaming state or forecasting. Calculations are bounded in memory to the existing
10,000-bar query and 32 specifications; periods up to 500. A query's start controls recursive seeds.
Late data conservatively delays every dependent prefix; no output is backdated or silently repaired.
Calendar and price-adjustment semantics remain caller/provider responsibilities.

The 15-group catalogue is a first implementation of all five families, not the entire master
indicator wish-list. Advanced candle indicators and data-dependent benchmark/trade-volume features
remain explicit extensions listed in the architecture document. No predictive importance has been
assigned to any indicator. Existing authentication, observability and upstream deprecation debt
remains unchanged.

Next: Phase 4 — market structure (confirmed swings, HH/HL/LH/LL, BOS, CHOCH). Not started.
