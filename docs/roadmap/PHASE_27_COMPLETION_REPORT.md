# Phase 27 completion report

## Summary, status and pre-edit assessment

Phase 27 is complete at the authorized foundation boundary. It provides explicit spot risk admission,
an account-pinned durable execution journal, idempotent dispatch/recovery, synthetic mechanical
qualification and a narrowly allowlisted native Binance Spot protocol for read-only qualification and
query reconciliation. Native order submission remains unreachable. `Settings.live_trading_enabled`
is `Literal[False]`, REAL risk never grants `execution_authorized`, and `NativeTransport` separately
refuses POST while that foundation flag is false. No real order, deployment or live enablement occurred.

Preserved baseline: `8342bea99d9cc297ad04eb03eb21ec7f8a41d334`; branch:
`codex/phase-27-spot-execution`. The initial assessment identified the missing operational adapter,
authenticated account/key-scope qualification, native order reconciliation and hard separation between
read permissions and the smallest future trading-key scope. The design retains every earlier blocker,
adds only fixed Spot endpoints and fails closed on unknown broker state. Acceptance required Decimal/UTC,
strategy → portfolio → risk → execution → broker boundaries, durable preparation before dispatch, no
blind retry, no secrets or real test orders, read-only local qualification, exact identity/permission
checks, trade-history fee reconciliation and all mandatory repository checks.

## Architecture and financial coverage

See [SPOT_EXECUTION.md](../architecture/SPOT_EXECUTION.md). `spot_execution` consumes the shared
StrategyDefinition/StrategyProposal/Intent, PortfolioSnapshot and Phase 26 broker Observation/LocalState.
Strategies do not access brokers and no second intelligence layer was introduced. Every dispatched
synthetic order has a current immutable risk approval; research approval cannot authorize execution.

Explicit limits cover capital, order/position/total exposure, inventory, daily loss, drawdown, position
and rate counts, freshness, spread, price deviation and fee budget. Account, symbol, strategy and
instrument identity are pinned. BUY reserves quantity × limit × (1 + fee fraction), rounded upward
with private high-precision Decimal arithmetic. SELL cannot short or borrow. All holdings must reconcile
in the native quote currency. Daily loss uses UTC day-start equity and declared external flows;
drawdown uses explicit high-water equity. These inputs are not profitability, probability or loss
guarantees and were not independently qualified for live operation.

Client IDs are deterministic account/strategy/intent hashes. PREPARED is durable before any broker
call; an identical retry reads durable state and altered content conflicts. PREPARED recovery becomes
UNKNOWN. An unresolved order reserves the whole account and only query recovery by the original
client ID can settle it. Not-found, timeout, malformed responses, regressions and inconsistent fills
never cause a blind resubmit. Cumulative base/quote quantities and commission by reported asset are
reconciled without invented conversion or zero-fee assumptions. No fill is posted automatically to
the Phase 16 ledger.

## Native protocol and operational gate

`BinanceSpotBroker` is fixed to `https://api.binance.com` with ambient proxies and redirects disabled.
The allowlist contains server time, account, API restrictions, one client-order lookup and order-scoped
trade history. The only planned order envelope is LIMIT/GTC/FULL. There is no cancel, withdrawal,
transfer, margin, futures, options, FIX, portfolio-margin or universal-transfer operation.

Requests use HMAC signing, a 5-second receive window, bounded responses, duplicate-key rejection,
finite numeric parsing, fixed methods/paths/parameter sets, sanitized errors and a policy-bounded
query deadline. Credentials are excluded SecretStr settings under `PA_BINANCE_SPOT_` and are never
journaled or written to qualification receipts. Read-only qualification checks the expected UID hash,
SPOT account identity, server clock and exact no-write permissions. The separately tested future
writing-key scope accepts reading plus spot trading only and rejects every other known write/transfer
flag, but still returns `live_trading_enabled=false` and `execution_authorized=false`.

Native query bookends permissions and order state, then reconciles actual cumulative execution against
paginated `myTrades` records and actual commission assets. Missing, changing, duplicate, future or
financially inconsistent evidence fails closed. Injected transports are labelled SYNTHETIC and cannot
produce a native read-only qualification. The local CLI performs qualification GETs only, refuses
receipt overwrite and exposes no order command.

Authenticated venue qualification was not run because no production credentials were supplied or
needed for this code task. Therefore account ownership, real key scopes, latency, exchange availability,
venue filters and operational acceptance remain unverified. Code and synthetic transport tests are not
broker qualification or permission to trade.

## Security, failure handling and limitations

Secrets are absent from domain requests, journals, receipts and sanitized exceptions. The private
SQLite journal uses serialized admission, synchronous durable writes and a consecutive SHA256 chain.
It should live in ignored `.private/` with account-holder-only ACLs. The chain detects accidental
modification, reorder and gaps, but does not resist malicious chain recomputation or tail deletion
without an external anchor. Capacity is 10,000 events and requires separately audited archival.

Kill is a durable irreversible latch in this foundation. It blocks new admissions but cannot cancel an
already in-flight request or liquidate inventory. There is no automatic startup, public execution API,
operator authentication, live strategy promotion, complete exchange metadata-filter certification,
atomic broker stream, externally anchored/encrypted journal, verified persistent daily-flow/high-water
state, portfolio fill booking or PostgreSQL coordination. Dependency or broker uncertainty remains
not-ready. The source contains parsing for a future FULL response, but all current authorization layers
make the POST path unreachable and its unexecuted guards are reported in coverage.

## Migrations and compatibility

There is no main Alembic/model-table migration; head remains `0015`. The private local format remains
`spot-journal-1`, with identity/events tables and fail-closed account/origin/version mismatch. There is
no upgrade from an unrelated execution journal. Existing portfolio and PAPER ledgers are not rewritten.
Source changes alter the global PAPER runtime identity, so new processing requires matching current
identity/evidence; historical sealed records must never be rewritten to bypass that gate.

## Exact checks and results

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 307 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success; 221 source files checked.
- `.venv/Scripts/python.exe -m pytest tests/test_native_spot.py tests/test_spot_execution.py --cov=pocket_alpha.spot_execution --cov-branch --cov-report=term-missing -q --tb=short`: 86 passed in 17.60s; 89% combined coverage (678 statements, 264 branches, 59 missed statements, 32 partial branches). Module coverage: binance 79%, engine 94%, models 95%, qualify 89%, risk 96%.
- `.venv/Scripts/python.exe -m pytest --cov=pocket_alpha.spot_execution --cov-branch --cov-report=term-missing -q --tb=short`: 968 passed, 231 skipped, 2 warnings in 28,830.29s (8:00:30); 89% combined coverage. Skips require unconfigured PostgreSQL/Redis integration. Existing warnings concern Starlette/httpx TestClient and anyio BlockingPortal deprecations. External-service skips are not counted as passes.
- `.venv/Scripts/alembic.exe heads`: `0015 (head)`.
- `.venv/Scripts/python.exe -m pocket_alpha.spot_execution.qualify --help`: exit 0; only required `--policy` and `--output` arguments.
- `git diff --check`: exit 0; Git reported Windows LF/CRLF normalization notices only.

Unexecuted checks: authenticated Binance account/key qualification, any native POST/order, disposable
PostgreSQL/Redis integration, frontend build/tests/E2E, Docker/Compose and remote GitHub Actions. There
are no frontend, deployment, production-schema or dependency changes in this isolated Python phase.
No profitable strategy, calibrated probability, fill, fee, balance or operational readiness was
fabricated.

## Complete changed-file list

- `README.md`
- `docs/architecture/SPOT_EXECUTION.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/research/VALIDATION_POLICY.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_27_COMPLETION_REPORT.md`
- `src/pocket_alpha/spot_execution/__init__.py`
- `src/pocket_alpha/spot_execution/models.py`
- `src/pocket_alpha/spot_execution/risk.py`
- `src/pocket_alpha/spot_execution/engine.py`
- `src/pocket_alpha/spot_execution/binance.py`
- `src/pocket_alpha/spot_execution/qualify.py`
- `tests/test_spot_execution.py`
- `tests/test_native_spot.py`

## Debt and next phase

Operational live-small acceptance remains blocked pending a separately authorized change to foundation
enablement, authenticated read/trade-key qualification, operator access control, genuine SHADOW/
LIVE_SMALL strategy evidence, complete venue sizing filters, atomic reconciliation, persistent verified
flows/high water, portfolio booking, latency/timeout/fee qualification and externally protected state.
Deleting or replacing the local journal cannot be used to evade reservations or continuity review.
No measured profitability or ruin probability follows from synthetic tests.

Phase 28 has not been started. This phase is concluded locally; publication, main integration,
deployment and live trading are outside this task.
