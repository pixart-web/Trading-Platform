# Phase 26 completion report

## Summary and pre-edit assessment

Phase 26 implements explicit native Binance Spot private GET observations and account-bound local
reconciliation in the Python modular monolith. Baseline: bf2240a49f3083f78318b4458b70c49f3d005149;
branch: codex/phase-26-live-read-only. The initial worktree was clean and preserved.

Before production edits the assessment reported absent private connectivity and real-account local
expectations, retained missing authenticated qualification and ledger integration debt, and declared
the new observation module, local tool, tests and architecture/policy/roadmap documentation. It
specified no database migration or public account UI/API. Acceptance: GET-only fixed endpoints,
minimum key permissions, Decimal/UTC, explicit identity/product/history binding, exact reconciliation,
fail-closed unknown/stale/changing/missing data, no secrets persisted/logged, no broker mutations and
all four mandatory checks. All implementation acceptance checks pass; authenticated venue operational
qualification remains explicitly unexecuted, not represented as successful.

## Architecture and phase audit

See ../architecture/LIVE_READ_ONLY.md for official provider references, contracts, local request format
and CLI usage. Four new Python module files implement frozen versioned models, native HTTP/HMAC
acquisition, scoped history and local reconciliation. No strategy, simulation or application startup
imports the connector; existing shared intelligence and order-risk boundaries are unchanged.

The observation records all returned account balances, actual externally reported open orders/trades,
spot inventory, full metadata hashes, minimum permissions hash and actual acquisition timestamps.
Local expectations require account binding, declared instruments/cursors, revision and independent
verification attestation; there is no automatic broker-to-ledger adoption. Missing local state blocks
readiness. Matching synthetic responses also remain blocked. Native REAL is acquisition provenance,
not an independent authentication/qualification result.

Phase self-review checked fixed origin/paths/GET, redirect/proxy refusal, secret exclusion and sanitized
errors, permission inspection before/after, numeric/account/product/cursor consistency, all-account
orders, bookend changes, non-atomic REST limitations, local causality/currentness and literal-disabled
execution. Test-driven corrections included rejecting duplicate JSON keys, explicit synthetic CLI
credential fixtures and bounded parametrized test IDs for Windows. Additional economic checks reject
invalid open-order statuses/quantities/prices and inconsistent reported trade quote values. No valid
existing test was weakened. No real order or private-account call was executed.

## Financial coverage, economic assumptions and security

Ninety-nine new tests cover deterministic HMAC requests, endpoint restrictions, all nine prohibited
write/transfer/trading flags, unknown/missing/invalid permission fields, account identity/type,
free/locked balances, exact Decimal inventory under a low global precision context, external open
orders and unsupported states, instrument identity and metadata, histories/cursor monotonicity,
pagination budget, actual commission currency, reported quote consistency, bookend changes, clock
skew/deadlines, invalid/oversized/non-finite/duplicate-key JSON, sanitized secret-bearing upstream
failures, environment-only credentials, schema immutability and all reconciliation components.
Native HTTP is tested with a mocked opener, never network.

Money is Decimal; trade quote consistency permits one explicitly reported quote-precision quantum.
No conversion, cost basis, realized/unrealized P&L, profitability, expected return, calibrated
probability, leverage or fill is invented. Spot free + locked means held inventory, not collateral
for a derivative position. History scope is API-available records for declared symbols/cursors, not
certified account lifetime history. Timings, page sizes and ages are configurable observation bounds,
not recommended financial production thresholds. Caller identity/provenance/verification attestations
and hashes are not cryptographic authenticity proofs.

API key, secret and expected UID are environment-only SecretStr, excluded from dump/repr and never
stored in receipts. Fixed TLS origin, GET-only path/parameter allowlists, no redirects/proxies,
finite body/time/page bounds and no retry enable fail-closed acquisition. Full documented key flags
must explicitly deny writing; scope omissions/schema changes cannot be silently accepted. There are
no withdrawals, transfers, cancellation or order APIs. Financial receipts remain sensitive plaintext
local files; ignored .private/ and O_EXCL prevent Git inclusion/overwrite by normal workflow. Windows
ACLs, encrypted persistence and secure-store provisioning remain operator/integration debt.

## Tests, commands and exact results

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 295 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success, 213 source files checked.
- `.venv/Scripts/python.exe -m pytest tests/test_broker_readonly.py --cov=pocket_alpha.broker_readonly --cov-branch --cov-report=term-missing -q --tb=short`:
  99 passed in 1.53s; combined statement/branch coverage 98% (393 statements, 130 branches;
  five missed statements and five partial branches). Models 99%, native adapter 98%, CLI 95%.
  Uncovered lines are HTTP non-200 guard, redundant finite-amount guard, final post-I/O deadline,
  independently validated schema scope guard and module-entry wrapper. Coverage is not broker qualification.
- `.venv/Scripts/python.exe -m pytest --cov=pocket_alpha.broker_readonly --cov-branch --cov-report=term-missing -q --tb=short`:
  882 passed, 231 skipped, 2 warnings in 275.56s (4m35s). Skips require unconfigured PostgreSQL/Redis
  (`PA_INTEGRATION` is not enabled); existing warnings concern Starlette/httpx TestClient and anyio
  BlockingPortal deprecations. New module coverage remains 98%, with the same five uncovered guards.
- `.venv/Scripts/alembic.exe heads`: `0015 (head)`.
- `.venv/Scripts/python.exe -m pocket_alpha.broker_readonly.cli --help`: exit 0, expected local arguments.
- `git diff --check`: exit 0; Windows LF/CRLF normalization notices only.

Unexecuted: authenticated real-account/venue permissions probe, PostgreSQL/Redis external integration,
frontend build/tests/E2E, Docker/Compose and remote GitHub CI. Frontend/Docker are unchanged and were
not needed for these local Python additions. External-service skips are reported separately from
passed tests. No production deployment or actual economic result is claimed.

## Migrations and compatibility

No DDL, model-table or dependency migration; head remains 0015. Existing migration regression tests
are part of the full suite; a fresh PostgreSQL upgrade/downgrade was not executed without services.
Receipts use new versioned local file schemas and never overwrite. No Phase 16 accounting entry,
PAPER journal/head, sealed research evidence or broker state is modified.

The new Python files change the global PAPER source-tree identity. Existing journal reading/replay
remains supported; processing a new event on an old identity fails RUNTIME_IDENTITY_CHANGED and needs
a matching current configuration/qualified evidence. Old headers/checkpoints must never be rewritten
as a compatibility workaround. This is an intentional financial-safety gate.

## Complete changed-file list

- .gitignore
- README.md
- docs/architecture/LIVE_READ_ONLY.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/research/VALIDATION_POLICY.md
- docs/risk/RISK_POLICY.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_26_COMPLETION_REPORT.md
- src/pocket_alpha/broker_readonly/__init__.py
- src/pocket_alpha/broker_readonly/models.py
- src/pocket_alpha/broker_readonly/binance.py
- src/pocket_alpha/broker_readonly/cli.py
- tests/test_broker_readonly.py

## Limitations, debt and next phase

Retained debt: authenticated native venue qualification/geographic availability, scope-schema review
when Binance changes/omits flags, secure-store adapter, encrypted/tamper-evident private persistence,
access-controlled account UI, independently verified portfolio ledger import with deposit/transfer
accounting, atomic state/stream sequence guarantees, large/history-retention proof, additional venues
and genuine out-of-sample economic qualification. Snapshot bookends cannot prove atomicity or detect
every transient round-trip change. Out-of-scope orders and quote-sized zero-base MARKET orders
conservatively reject. Local attestations can be falsified by a caller; matching a fabricated state
is not independent broker reconciliation.

No probability, profitability or trading readiness is claimed. Read-only MATCHED is always distinct
from order approval: execution_authorized=false and live_trading_enabled=false. Live execution,
Autopilot and derivative execution remain unavailable. Next phase: 27, not started. The implementation
is committed locally as one phase commit; no push, main merge, deployment or final-release audit is
performed by this phase task.
