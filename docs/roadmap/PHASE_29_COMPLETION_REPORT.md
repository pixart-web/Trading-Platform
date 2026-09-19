# Phase 29 completion report

## Summary, phase and pre-edit assessment

Phase 29 implements a fail-closed derivative execution qualification boundary for isolated linear
cash-settled perpetuals and futures. It supports explicit LONG/SHORT OPEN and exact reduce-only CLOSE
mechanics, reuses Phase 25 leverage assessment, independently rechecks risk and writes a durable
idempotent lifecycle before an injected synthetic broker. Real derivative execution remains
structurally unavailable.

Baseline: afaf8f33cff4d9818bdf500dc14d210ac4c4802b; branch:
codex/phase-29-derivative-execution. The clean pre-edit assessment found causal derivative contracts
and conditional leverage research, but no derivative order contract, independent execution flag,
current account/market admission, durable derivative journal, report reconciliation or broker
boundary. Reusing spot order semantics would have omitted funding, mark/index, margin, liquidation,
multiplier, expiry, reduce-only, collateral and position-mode risks. The accepted design therefore
adds a separate execution package after the shared leverage boundary and no alternative intelligence
layer.

## Architecture and acceptance

See [DERIVATIVE_EXECUTION.md](../architecture/DERIVATIVE_EXECUTION.md). The implemented path is
strategy evidence → portfolio collateral/prior risk → LeverageAssessment → independent derivative
risk → durable execution → BrokerPort. Strategy evidence is immutable, SHADOW and synthetic; proposal
and position hashes bind it to the leverage request. Account, contract and strategy identities are
allowlisted. Current market, margin and account/local state must match exact hashes and timestamps.

Only base-unit linear, cash-settled, single-currency, isolated-margin perpetual/future contracts in
one-way mode qualify. LIMIT/GTC, LONG/SHORT, mark/index, basis, funding, initial/maintenance margin,
margin tier, expiry, multiplier, collateral, gross/net/position notional, position count, liquidation
buffer, modeled loss, fee, spread, daily loss, drawdown, health, freshness and venue steps are
checked. Options, inverse or quote-valued multipliers, physical settlement, cross/portfolio margin,
hedge mode, market orders and currency conversion reject.

OPEN reserves max(venue initial margin, assessed collateral) plus explicit fee and funding budgets.
CLOSE must be reduce-only and match a reconciled position; it reserves fee/funding budgets and is not
blocked by entry leverage, modeled-loss, daily-loss or drawdown limits. It remains subject to identity,
permission, venue, market, reconciliation and independent risk gates. This supports controlled risk
reduction without claiming automatic liquidation or guaranteed exits.

Settings.live_trading_enabled and Settings.derivative_execution_enabled are separate Literal[False]
flags. Fresh environment and Compose values are false, and true fails validation. Local policy also
defaults to DISABLED and has independent global, derivative and manual gates. A REAL broker origin is
always rejected. DisabledNativeDerivativeBroker contains no network, credential or working order
operation. SyntheticDerivativeBroker is the only reachable mechanism adapter.

The derivative-journal-1 SQLite store is account/origin pinned, BEGIN IMMEDIATE serialized,
synchronous=FULL, parameterized, size bounded and append-only hash chained. Client ID derives from
account, strategy and intent identity. Exact replay is idempotent; changed content conflicts.
PREPARED is durable before dispatch. Ambiguous submission/query/report state becomes UNKNOWN and is
queried by the existing client ID without blind retry. One unresolved flow blocks the account.
Cumulative reports cannot regress and all price, fee, funding, realized-P&L and identity constraints
are revalidated.

## Migrations and compatibility

No Alembic or production database model change; head stays 0015. No dependency or lockfile change.
The local derivative journal is a new isolated format and has no migration from other journals.
Account/origin/version mismatch fails closed. Compose and .env.example only add the explicit false
derivative gate. No frontend, public API, CLI, worker or scheduler was introduced.

## Tests, commands and exact results

- .venv/Scripts/ruff.exe format .: 3 files reformatted initially; final format check passed.
- .venv/Scripts/ruff.exe check .: all checks passed.
- .venv/Scripts/ruff.exe format --check .: 323 files already formatted at the final gate run.
- .venv/Scripts/python.exe -m mypy: success; 232 source files checked.
- .venv/Scripts/python.exe -m pytest tests/test_derivative_execution.py --cov=pocket_alpha.derivative_execution --cov-branch --cov-report=term-missing -q --tb=short: 55 passed, 2 existing deprecation warnings; 91% combined coverage, models 100%, risk 88%, engine 85%.
- .venv/Scripts/python.exe -m pytest -q --tb=short: 1067 passed, 231 skipped, 2 warnings in 111.69s. Skips require unconfigured PostgreSQL/Redis integration. Existing warnings concern Starlette/httpx TestClient and anyio BlockingPortal deprecations.
- .venv/Scripts/alembic.exe heads: 0015 (head).
- .venv/Scripts/python.exe -m pip check: no broken requirements found.
- docker compose config --quiet: exit 0.
- git diff --check: exit 0; Windows LF/CRLF notices only.

No migration/integration database service, frontend unit/E2E, Docker image build, authenticated venue,
real account, external dependency vulnerability database, remote CI or real order test was executed.
There was no frontend/API/schema/dependency behavior change requiring a targeted suite. Tests and CI
contain no real-order path.

## Financial and validation coverage

All money, margin, notional, P&L, fee and funding arithmetic uses Decimal; timestamps are aware UTC.
Tests cover supported LONG/SHORT OPEN, LONG/SHORT reduce-only CLOSE, independent settings/policy
gates, unsupported multiplier/settlement/margin conventions, origin and identity binding, stale and
mismatched evidence, margin/collateral/exposure/leverage/liquidation/loss limits, position-mode
conflict, report coherence, idempotency conflict, kill latch, journal tamper detection, ambiguous
submission, query-only reconciliation and account-wide unresolved-flow serialization.

The tests use explicit synthetic inputs and prove mechanics only. They do not establish alpha,
profitability, calibrated probability, SHORT edge, safe leverage, true ruin probability, liquidation
fill quality, insurance/ADL protection, venue funding accuracy, production latency or real drawdown
limits. The finite Phase 25 stress set remains conditional rather than a guarantee.

## Security audit

See [PHASE_26_29_SECURITY_AUDIT.md](../security/PHASE_26_29_SECURITY_AUDIT.md). Phase 29 adds no
credential, network client, API, redirect, CORS, browser, transfer, withdrawal, cancel or shell
surface. Withdrawal permission is fixed false. SQLite is parameterized, reports persist static reason
codes, replay is bound to request/client hashes and exceptions never contain upstream secret text.

Existing analytical APIs are unauthenticated and must remain loopback-only or gain authorization
before public deployment. The private journal is plaintext and locally hash chained, not encrypted or
externally anchored. Production image tags are not digest pinned. An external vulnerability service,
authenticated least-privilege venue scope review and filesystem ACL verification remain release
blockers. No critical issue was found in the new synthetic-only reachable surface; this is not a
whole-application deployment certification.

## Complete changed-file list

- .env.example
- README.md
- compose.yaml
- docs/architecture/DERIVATIVE_EXECUTION.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/research/VALIDATION_POLICY.md
- docs/risk/RISK_POLICY.md
- docs/roadmap/PHASE_29_COMPLETION_REPORT.md
- docs/roadmap/ROADMAP.md
- docs/security/PHASE_26_29_SECURITY_AUDIT.md
- src/pocket_alpha/config.py
- src/pocket_alpha/derivative_execution/__init__.py
- src/pocket_alpha/derivative_execution/engine.py
- src/pocket_alpha/derivative_execution/models.py
- src/pocket_alpha/derivative_execution/qualify.py
- src/pocket_alpha/derivative_execution/risk.py
- tests/derivative_execution_fixtures.py
- tests/test_derivative_execution.py

## Limitations, debt and next phase

Native derivative transport, authenticated read/trade permission qualification, verified venue
contract/filter/margin tiers, independent strategy and account acquisition, portfolio fill booking,
external journal anchoring/encryption, production alerting, operator authorization, sandbox/venue
conformance and incident drills remain absent. A caller supplies synthetic SHADOW and qualification
evidence; it cannot become live evidence. Kill blocks new admission but cannot cancel or liquidate an
in-flight or existing position.

Phase 29 is complete at synthetic foundation scope. The final release readiness audit has not been
started and must treat every residual item above as a blocker rather than infer live readiness.
