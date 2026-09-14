# Phase 12 completion report

## Summary and phase

Phase 12 implements an auditable, horizon-specific Opportunity Score and deterministic economic
ranking after immutable forecasts and independent directional analysis. It is the earliest
incomplete authorized phase. Phase 13 was not started. No policy, threshold, dataset or result is
promoted or claimed to have predictive or economic value.

## Assessment, gaps and design

Before this phase, the system could produce calibrated forecast artifacts and a LONG, SHORT or
NO_TRADE analysis, but it had no contract for assessing a specific side and horizon after costs.
It also could not distinguish a calculable but economically ineligible opportunity from one whose
inputs were unavailable.

The new opportunities package binds one directional analysis to one matching forecast, explicit
round-trip costs and causal liquidity and uncertainty metrics. It derives side-specific expected
return, calibrated probability, expected move, interval reward/loss, risk/reward and net expected
return. Seven normalized components use a versioned caller-supplied policy and preserve every raw
value, weight and contribution. Eligibility gates are evaluated separately from score availability.

Rankings accept only unique results with the same horizon, as-of time and policy identity. Available
and eligible opportunities are ordered by score, net expected return and UUID; excluded results are
also retained in stable UUID order. This is an economic comparison, not a strategy intention,
portfolio allocation, risk approval or order.

## Acceptance criteria

Completed:

- matching market, asset, candle timeframe and forecast horizon across upstream artifacts;
- separate candle timeframe and opportunity horizon retained in every result;
- calibrated UP probability for LONG and DOWN probability for SHORT;
- side-specific expected return and forecast-interval reward/loss calculations;
- explicit Decimal fees, spread, slippage and latency deducted from expected return;
- causal, versioned liquidity and uncertainty metrics with immutable evidence;
- seven inspectable normalized components, positive weights and exact contributions;
- versioned policies with no repository-default financial thresholds;
- distinct AVAILABLE/UNAVAILABLE and eligible/ineligible states;
- canonical reasons for every failed economic gate;
- fail-closed results for NO_TRADE, unavailable, expired or uncalibrated forecasts, missing context
  and absent finite downside estimates;
- deterministic policy and complete-input hashes;
- same-snapshot ranking with stable tie breaks and explicit exclusions;
- UTC availability and generation checks preventing future-data use;
- no strategy, portfolio, risk, execution or broker coupling.

## Changed files

- src/pocket_alpha/opportunities/__init__.py
- src/pocket_alpha/opportunities/models.py
- src/pocket_alpha/opportunities/service.py
- tests/test_opportunity_score.py
- docs/architecture/OPPORTUNITY_SCORE.md
- docs/architecture/DIRECTIONAL_ANALYSIS.md
- docs/architecture/POCKET_SCORE.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_12_COMPLETION_REPORT.md
- README.md

## Migrations and compatibility

There is no migration, persistence change, dependency change, API or frontend contract change. The
module is additive and leaves forecast, Pocket Score and directional models unchanged. Future
persistence must retain economics, component explanations, eligibility reasons, cost and policy
versions, hashes, and upstream analysis/forecast identifiers rather than only the final score.

## Validation

Executed locally on Windows with Python 3.12.14:

- ruff check . - passed.
- ruff format --check . - passed; 124 files already formatted.
- mypy . - passed; 86 source files checked.
- pytest --cov=pocket_alpha --cov-report=term-missing - 403 passed, 81 skipped, 2 dependency
  deprecation warnings and 98% total coverage.
- focused Phase 12 suite - 15 passed; 94% opportunities-package coverage.
- pnpm lint - passed.
- pnpm typecheck - passed.
- pnpm test - 41 passed.
- pnpm build - passed with Next.js 16.3.4.

The Docker Desktop daemon was unavailable, so PostgreSQL/Redis integration could not be executed
locally. The 81 skips include service-dependent parametrizations. Phase 12 adds no persistence or
service integration. No result is inferred for an unexecuted check.

## Financial coverage and economic assumptions

Net expected return subtracts the supplied fee, spread, slippage and latency rates from the selected
side's forecast expected return. Reward and loss use the forecast expected interval around zero.
Liquidity and uncertainty are supplied versioned ratios, not invented by this module. Every minimum,
target, maximum and weight is an explicit policy input.

The implementation does not model borrow fees, funding, taxes, nonlinear market impact, fills,
position size, portfolio exposure, correlation, drawdown, ruin or compounding. A score from zero to
one hundred is an index under one named policy, never a calibrated success probability. Synthetic
tests prove arithmetic and contract behavior only; they do not prove profitability, calibration,
statistical significance or validity for any asset, regime, timeframe or horizon.

## Security, limitations and debt

No credential, provider connection, endpoint, order route, broker permission or withdrawal
capability was added. Live execution remains disabled. Frozen models reject unknown fields, inputs
are bounded in count, evidence remains causal and ranking never bypasses ineligibility.

Remaining debt includes production adapters for liquidity and uncertainty, identified research
datasets, temporal and final-holdout evaluation, cost and threshold sensitivity, calibration by
asset/regime/timeframe/horizon, policy governance, drift monitoring, persistence and user-facing
presentation. Later strategy, portfolio and risk phases remain mandatory before execution can be
considered.

The next roadmap phase is Phase 13, Analyze. It was not started.
