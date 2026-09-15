# Phase 16 completion report

## Summary and phase

Phase 16 implements persistent manual portfolios, immutable accounting entries, exact moving-average
position accounting, causal as-of valuation and a validated responsive dashboard. It is the earliest
incomplete authorized phase. Phase 17 was not started. No profitability, recommendation, fill,
risk-approval or production-readiness claim is made.

## Assessment, gaps and design

Before this phase, the application could analyze and rank stored market opportunities but had no durable
cash or position state. The new portfolio boundary records user-supplied accounting facts independently
of scanner, strategy, risk, leverage, execution and broker modules.

A portfolio fixes its base currency, valuation timeframe and versioned `MOVING_AVERAGE_V1` method.
Deposits, withdrawals, buys and sells are append-only, UUID-idempotent and sequenced under an optimistic
portfolio revision. Accounting uses Decimal quantized to 18 places with round-half-even. Buy fees enter
cost basis; sell fees reduce realized proceeds. Cash cannot become negative and a sale cannot exceed the
owned long quantity.

As-of snapshots include only entries both occurred and recorded by the UTC cutoff. Open positions use
the latest stored candle close in the configured timeframe only when both close and receipt times meet
the cutoff. A missing price produces a `PARTIAL` snapshot and suppresses aggregate market value,
unrealized P&L and equity.

## Acceptance criteria

Completed:

- persistent portfolios with client UUIDs, canonical base currency, valuation timeframe and revisions;
- immutable, ordered deposits, withdrawals, manual buys and manual sells;
- idempotent identical UUID replay and conflict rejection for changed content;
- optimistic concurrency with stale-revision rejection;
- exact `NUMERIC(38,18)` and Decimal accounting with explicit rounding;
- funded-cash, long-only, oversell and single-currency invariants;
- moving-average cost basis, fees, realized P&L and remaining-position accounting;
- causal UTC snapshots protected from late-recorded entries and late-received prices;
- exact configured-timeframe valuation from stored candles;
- explicit partial valuation with no fabricated aggregate totals;
- bounded ledgers, market counts and API listings;
- create/read/list/append/snapshot FastAPI routes with no-store responses;
- allowlisted Next.js gateway methods, paths, queries, body size and sanitized errors;
- runtime-validated responsive dashboard, manual forms, positions and immutable ledger;
- manual entries clearly separated from orders, fills, recommendations and risk approvals;
- additive migration 0007 and documented rollback.

## Changed files

- `src/pocket_alpha/portfolio/__init__.py`
- `src/pocket_alpha/portfolio/api.py`
- `src/pocket_alpha/portfolio/models.py`
- `src/pocket_alpha/portfolio/service.py`
- `src/pocket_alpha/portfolio/storage.py`
- `src/pocket_alpha/main.py`
- `migrations/env.py`
- `migrations/versions/0007_portfolios.py`
- `tests/test_portfolio.py`
- `frontend/lib/portfolio.ts`
- `frontend/lib/proxy.ts`
- `frontend/components/portfolio-panel.tsx`
- `frontend/components/market-workspace.tsx`
- `frontend/app/globals.css`
- `frontend/tests/portfolio.test.ts`
- `frontend/tests/proxy-route.test.ts`
- `frontend/e2e/workspace.spec.ts`
- `docs/architecture/PORTFOLIO.md`
- `docs/architecture/CHARTING_ARCHITECTURE.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_16_COMPLETION_REPORT.md`
- `README.md`

## Migration and compatibility

Migration 0007 is additive. It creates `portfolios` and `portfolio_entries`, exact numeric columns,
foreign keys to registered markets/assets, portfolio-sequence uniqueness, accounting checks and lookup
indexes. Existing APIs and data remain available.

Downgrading 0007 to 0006 drops the portfolio entry indexes, entries and portfolios only. Analyze,
watchlist, scan, forecast, market-data and audit history remain. Retained manual accounting data must be
exported before rollback. No dependency or environment-variable change was introduced.

## Validation

Executed locally on Windows with Python 3.12.14, Node 24 and Next.js 16.3.4:

- `ruff check .` - passed.
- `ruff format --check .` - passed; 161 Python files already formatted.
- `mypy .` - passed; 114 source files checked.
- full `pytest -q --disable-warnings` - 438 passed, 105 skipped and 2 warnings in 17.71s.
- focused portfolio suite - 8 passed and 7 PostgreSQL-parametrized cases skipped locally.
- focused portfolio coverage - 91% across 555 statements; 8 passed and 7 skipped.
- Alembic heads/history - one head at 0007 with a linear 0001 -> 0007 chain.
- Alembic offline upgrade to head - passed and rendered both Phase 16 tables and indexes.
- Alembic offline downgrade 0007:0006 - passed and removed only Phase 16 tables and indexes.
- `pnpm lint` - passed.
- `pnpm typecheck` - passed.
- `pnpm test` - 60 passed across seven files.
- `pnpm build` - passed.
- `pnpm test:e2e` - 14 Playwright Chromium tests passed, including the portfolio flow.
- final portfolio-only Playwright rerun - 1 passed.

Docker Desktop was unavailable: the installed client could not connect to the desktop-linux daemon.
The disposable PostgreSQL/Redis migration round trip, service integration and Docker image builds were
therefore not executed locally. The 105 full-suite skips include service-dependent parametrizations.
No result is inferred for unexecuted checks.

## Financial coverage and assumptions

The implementation records manual long-position accounting in one base currency. A user-supplied buy or
sell is treated as an accounting fact; it is not proof of an exchange fill. Snapshot prices are historical
stored candle closes rather than executable quotes. Fees must be supplied explicitly; spread, slippage,
tax, FX and opportunity cost are not inferred.

Synthetic tests verify persistence, exact arithmetic, cost basis, realized/unrealized P&L, causal price
selection, missing-price behavior, validation, API and presentation contracts. They do not prove market
accuracy, performance, profitability, statistical significance, drawdown control, ruin limits or net
compounded growth.

## Security, limitations and debt

The gateway retains a fixed server-only origin, explicit method/path/query allowlists, an 8 KiB body cap,
redirect rejection, timeouts and sanitized failures. No secret, broker credential, withdrawal permission,
order route or live execution capability was added.

There is no authentication, portfolio ownership, authorization, rate limiting, retention policy or
production orchestration. The ledger does not yet support FX, short positions, tax lots, dividends,
splits, transfers, reversals, broker imports or reconciliation. Portfolio correlations, concentration,
allocation and portfolio-level risk belong to Phase 17, which remains unimplemented.
