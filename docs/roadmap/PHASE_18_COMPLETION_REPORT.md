# Phase 18 completion report

## Status and scope

Implemented the provider-independent fundamental intelligence boundary, immutable corporate
numerical facts, conservative point-in-time SEC ingestion, read-only queries and descriptive
financial context. This is implementation completion for the documented coverage, not production
readiness, complete worldwide financial coverage or independent release approval.
Next authorized phase: 19, derivatives intelligence. No derivative execution is present here.

## Assessment, design and architecture

The starting repository had no fundamental provider or facts ledger. Existing manual portfolio
and intelligence changes were preserved. A distinct asset/provider mapping and append-only fact
repository were added rather than overloading market candles or forecasts. The module consumes
stored identity/prices and cannot reach strategy, risk, leverage, execution or broker adapters.
Facts and calculated features use frozen versioned domain values, Decimal and UTC timestamps.
Original source concepts are retained; overlapping revenue/debt taxonomies are never summed.
The source reports long-term debt, explicitly distinguished from comprehensive DEBT.

The SEC adapter is real, read-only and opt-in with an operator identifying User-Agent. It bounds
timeouts, retries, bytes, records and per-instance request spacing. CompanyFacts is one document;
generic provider pagination is bounded and rejects cycles. Invalid identity, malformed financial
values and exhausted dependencies fail without synthetic fallback. Tests inject synthetic transport.

The filing-date representation cannot establish exact intraday publication. Actual availability
and ingestion are captured after the provider response. Revision linkage is validated, historical
snapshots require both availability and ingestion by cutoff, and reimport retains original times.
Later restatements cannot replace facts known at an earlier cutoff.

Annual coherent inputs support revenue/EPS growth, gross/operating/net margins and free cash flow.
Negative income and FCF are retained. Nonpositive growth bases and ambiguous taxonomies are unavailable.
P/E additionally requires a stored causal market quote, positive annual diluted EPS, matching currency
and a quote after EPS availability. Quote identity/timestamps and feature input UUIDs/hash are exposed.
80-digit intermediate arithmetic rounds half-even to 18 places. No scores/probabilities are emitted.

## Complete file list

- src/pocket_alpha/fundamentals/__init__.py
- src/pocket_alpha/fundamentals/__main__.py
- src/pocket_alpha/fundamentals/models.py
- src/pocket_alpha/fundamentals/providers.py
- src/pocket_alpha/fundamentals/storage.py
- src/pocket_alpha/fundamentals/service.py
- src/pocket_alpha/fundamentals/context.py
- src/pocket_alpha/fundamentals/api.py
- src/pocket_alpha/main.py
- migrations/env.py
- migrations/versions/0009_fundamentals.py
- tests/test_fundamentals.py
- docs/architecture/FUNDAMENTALS.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_18_COMPLETION_REPORT.md

## Migration and risks

0009 follows 0008 and adds fundamental_mappings and fundamental_facts with source uniqueness,
asset/revision foreign keys and the asset/availability/ingestion index. Decimal JSON strings retain
precision without SQLite float coercion. Upgrade is additive. Downgrade destroys these histories:
back up/export before rollback. No existing portfolio, candle or forecast row is changed.
Actual PostgreSQL upgrade/downgrade and concurrent row-lock behavior remain unexecuted locally.

## Acceptance and self-audit

Implemented: explicit identity, units/currency/periods/provenance, immutable fact IDs, revision
chains, causal snapshots, provider failure states, bounded import, descriptive financial features,
read-only API and explicit operator transaction. No trades, secrets, estimated fills or fabricated
statistics are introduced.

Audit remediation included exact JSON decimal parsing, bounded response reads, removal of unsupported
compression, bounded transport retries, respecting long rate-limit embargoes, CIK response matching,
per-instance spacing, immutable source conflict detection, duplicate-batch validation, asset import
serialization, revision-chain consistency and capturing availability after network I/O.
Regression evidence covers restatement preservation, idempotency, future receipt exclusion, cursor
cycles, delayed-response leakage, matching financial periods, negative results, ambiguous inputs,
nonpositive denominators, valuation currency/time constraints, API unavailable state and CLI transactions.

## Commands and exact results

Windows Python 3.12.14, local .venv. No real provider request or real order was made.

- .venv/Scripts/ruff.exe check .: passed.
- .venv/Scripts/ruff.exe format --check .: passed, 182 files already formatted including this report.
- .venv/Scripts/python.exe -m mypy: passed, 121 source files.
- .venv/Scripts/python.exe -m pytest -q: 464 passed, 117 skipped, 2 dependency warnings.
- .venv/Scripts/python.exe -m pytest tests/test_fundamentals.py --cov=pocket_alpha.fundamentals
  --cov-report=term-missing -q: 20 passed, 6 skipped, 2 warnings, 91% over 563 statements.
  Financial context calculation module: 100%; this is statement coverage, not economic validation.
- .venv/Scripts/python.exe -m pocket_alpha.fundamentals --help: passed.
- .venv/Scripts/python.exe -m alembic heads: single head 0009.
- Alembic upgrade head --sql and downgrade 0009:0008 --sql: generated successfully.
- git diff --check: passed before this report.
- docker info: failed because Docker Desktop Linux daemon pipe is unavailable.
- Attempted full-app lifespan test failed loading psycopg binary: Windows Application Control
  blocked its DLL; no system libpq or psycopg_c alternative was installed. The new API contract
  test uses an isolated FastAPI router and injected repository. It does not validate real app startup.

Unexecuted: real PostgreSQL/Redis integration, database concurrency/migration execution, Docker image
builds, real SEC smoke import, frontend checks (no frontend changes), published GitHub CI (no push yet).
PostgreSQL test variants account for six fundamental skips. Overall skips are explicitly reported,
not successes. Warnings concern Starlette/httpx and anyio deprecated interfaces.

## Financial coverage, assumptions and limitations

No strategy profitability, calibration, probability or investment suitability is claimed.
All test market/provider data are identified synthetic fixtures. Annual 350–380-day comparability
is an engineering bound, not a fitted economic assumption. Features are ratios rather than percents.
No quarterly annualization, FX conversion, total-debt inference or missing-value estimates occur.

Coverage depends on SEC US-GAAP concepts and explicit registered stocks. Corporate fundamentals for
crypto and unmapped assets are unavailable. ROE/ROIC, P/S and EV/EBITDA remain unavailable without
the necessary comparable balance/tax/market-cap/enterprise inputs. Guidance and earnings events
are explicitly unavailable in this adapter. No global provider scheduler, distributed rate limiter,
historical acceptance-time resolver, financial freshness policy or frontend panel is supplied.
P/E exposes quote time and makes no freshness guarantee. Same-day filing ordering cannot claim
verified intraday knowledge. Backfills imported today are never treated as historically available.

The SEC adapter is a legitimate financial-data capability, but does not satisfy the Phase 20 real
price-data acceptance gate. Implement a real market-data adapter by that gate and validate availability.

## Security, debt and release status

Live/derivative execution and Autopilot remain disabled. No broker or withdrawals access is added.
No public import endpoint, provider secret, SEC credential or contact is committed/logged.
Operator imports use existing database configuration and explicit commit/rollback. Existing
production authentication/security hardening remains future release work; this module is not a
deployment approval. PostgreSQL/Docker/driver limitations, provider breadth, acceptance-time resolution,
distributed throttling and missing valuation/context inputs remain recorded debt for final audit.
Phases 19–29 and the final release audits/push/CI verification remain outstanding.
