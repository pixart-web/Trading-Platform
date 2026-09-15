# Phase 17 completion report

## Summary and phase

Phase 17 implements immutable, versioned portfolio-intelligence reports over exact Phase 16 state.
It calculates allocation, concentration, effective diversification and supported historical market-risk
metrics from causal stored candles. Unsupported metrics remain explicitly unavailable. Phase 18 was not
started. No recommendation, profitability, probability, risk approval or execution claim is made.

## Assessment, gaps and design

Phase 16 supplied exact manual cash, positions and as-of valuation but no portfolio-level analysis.
Phase 17 consumes that read model without mutating its ledger. A bounded versioned policy controls return
history, minimum aligned observations and maximum valuation-price age.

Allocation covers cash, market, asset class, currency, venue and long direction. Invested-sleeve HHI,
largest weight and inverse HHI describe concentration without treating asset count as diversification.
Sample volatility, pairwise correlations, optional benchmark beta, current-weight portfolio volatility
and Euler variance contributions use Decimal close-to-close returns. Values are per bar and are not
silently annualized.

The asset model has no sector taxonomy, candles do not establish executable liquidity, the application
has no causal NAV history, and manual positions have no regime or forecast-horizon attribution. Those
metrics preserve explicit unavailable reasons. Incomplete or stale valuation and insufficient or
zero-variance history fail closed for dependent metrics.

## Acceptance criteria

Completed:

- exact Phase 16 portfolio revision, ledger sequence and input-hash linkage;
- client UUID idempotency and conflicting identity rejection;
- versioned policy and canonical SHA-256 policy/input hashes;
- bounded causal candle windows filtered by close and receipt time;
- late-received future perturbation protection;
- allocation by market, asset class, currency, venue, direction and cash;
- market, asset-class, currency and venue HHI, largest weight and inverse-HHI effective count;
- non-annualized market and portfolio sample volatility;
- pairwise correlations using only aligned observations;
- beta only with an explicit registered benchmark;
- current-weight Euler variance contributions;
- explicit sector, liquidity, drawdown, regime and horizon unavailability;
- stale valuation suppresses all current-weight metrics;
- explained accounting, diversification, stale-data and insufficient-history observations;
- immutable additive persistence, bounded create/read/list API and no-store responses;
- strict Next.js route/method/query allowlist and runtime schema validation;
- responsive dashboard with exact allocation and unavailable-state presentation;
- no strategy, allocation action, risk approval, leverage, execution or broker dependency.

## Changed files

- src/pocket_alpha/portfolio_intelligence/__init__.py
- src/pocket_alpha/portfolio_intelligence/api.py
- src/pocket_alpha/portfolio_intelligence/models.py
- src/pocket_alpha/portfolio_intelligence/service.py
- src/pocket_alpha/portfolio_intelligence/storage.py
- src/pocket_alpha/main.py
- migrations/env.py
- migrations/versions/0008_portfolio_intelligence.py
- tests/test_portfolio_intelligence.py
- frontend/lib/portfolio-intelligence.ts
- frontend/lib/proxy.ts
- frontend/components/portfolio-intelligence-panel.tsx
- frontend/components/portfolio-panel.tsx
- frontend/app/globals.css
- frontend/tests/portfolio-intelligence.test.ts
- frontend/tests/proxy-route.test.ts
- frontend/e2e/workspace.spec.ts
- docs/architecture/PORTFOLIO_INTELLIGENCE.md
- docs/architecture/PORTFOLIO.md
- docs/architecture/CHARTING_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_17_COMPLETION_REPORT.md
- README.md

## Migration and compatibility

Migration 0008 is additive and creates portfolio_intelligence_reports with a portfolio foreign key,
immutable JSON payload, policy/input hashes and portfolio/as-of lookup indexes. Existing routes and data
remain available.

Downgrading 0008 to 0007 removes only the Phase 17 indexes and report table. Portfolio accounting,
scans, watchlists, Analyze reports, forecasts, market data and audit history remain. Reports must be
exported before rollback. No dependency or environment-variable change was introduced.

## Validation

Executed locally on Windows with Python 3.12.14, Node 24 and Next.js 16.3.4:

- ruff check . - passed.
- ruff format --check . - passed; 170 Python files already formatted.
- mypy . - passed; 121 source files checked.
- full pytest - 444 passed, 111 skipped and 2 warnings in 27.40s.
- focused Phase 17 suite - 6 passed and 6 PostgreSQL-parametrized cases skipped locally.
- focused Phase 17 coverage - 92% across 462 statements; 6 passed and 6 skipped.
- Alembic heads/history - one head at 0008 with a linear 0001 to 0008 chain.
- Alembic offline upgrade to head - passed and rendered the Phase 17 table and indexes.
- Alembic offline downgrade 0008:0007 - passed and removed only the Phase 17 table and indexes.
- pnpm lint - passed.
- pnpm typecheck - passed.
- pnpm test - 63 passed across eight files.
- pnpm build - passed.
- pnpm test:e2e - 14 Playwright Chromium tests passed, including portfolio intelligence.

Docker Desktop was unavailable earlier in the same local session because the client could not connect
to the desktop-linux daemon. Disposable PostgreSQL/Redis migration integration and Docker image builds
were not executed locally. The 111 skips include service-dependent parametrizations. No result is
inferred for unexecuted checks.

## Financial coverage and assumptions

Market-value allocations use Phase 16 historical candle-close valuation. Concentration uses the valued
invested sleeve, while portfolio risk weights use market value divided by total equity so cash dilutes
market volatility. Returns are simple close-to-close returns in the configured timeframe. Covariance
uses the sample denominator. Beta and correlation require sufficient aligned observations and nonzero
variance. Risk contributions explain variance under current weights; they are not loss limits.

These are descriptive historical statistics over synthetic test fixtures. They do not establish
expected returns, future volatility, liquidity, capacity, tail risk, drawdown, ruin probability,
diversification benefit or economic edge.

## Security, limitations and debt

The fixed-origin gateway retains explicit route, method and query allowlists, body limits, timeouts,
redirect rejection and sanitized failures. No secret, credential, order route, withdrawal capability or
live-trading path was added.

The current-weight model does not reconstruct changing historical holdings. Sector classification,
executable liquidity, NAV history, regime attribution and horizon attribution remain unavailable.
There is no authentication, ownership, rate limiting, retention policy or production orchestration.
Phase 18 must introduce provider-independent point-in-time fundamentals without silently rewriting
historical knowledge.
