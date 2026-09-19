# Phase 28 completion report

## Summary, status and pre-edit assessment

Phase 28 implements a fail-closed Autopilot orchestrator over the existing Pocket Alpha stack. It
consumes causal scanner output, immutable model/strategy lifecycle events and complete SpotRequest
candidates; applies a stricter versioned policy and system-health gate; records a durable reasoned
cycle; and delegates at most one unchanged request to SpotExecution. It does not create an alternative
intelligence, portfolio, risk, execution or broker path.

Baseline: `47368cb3ca836f41d98a4e2f8f419f9ae3c9a1f4`; branch:
`codex/phase-28-autopilot`. The clean pre-edit assessment found no autonomous orchestrator, policy,
cycle idempotency, durable cooldown, manual suspension, Autopilot kill propagation or audit trail.
The required upstream evidence and authoritative risk/execution boundary already existed in Scanner,
model/strategy registries, SpotRequest and SpotExecution. The smallest safe design therefore adds a
local orchestration module and journal, without a service worker, public API, UI or production schema.

Accepted scope: disabled fresh installation; explicit synthetic qualification only; sorted asset and
strategy allowlists; capital, exposure, daily loss, drawdown, position, cooldown and freshness limits;
provider/risk/portfolio/reconciliation/execution health; causal SHADOW lifecycle and scan evidence;
reasoned decisions; durable idempotency, suspension, kill and reconciliation; Decimal/UTC; no real
network/order/credential; full repository regression. Native/live Autopilot operation is not accepted
or claimed.

## Architecture and shared-stack integration

See [AUTOPILOT.md](../architecture/AUTOPILOT.md). `AutopilotCycle` carries an immutable ScanReport,
explicit dependency health and complete candidates. Each candidate carries the original SpotRequest
and current hash-validated RegistryEvent/StrategyEvent. Strategy UUID derives from the exact proposal
definition hash and its event must bind the same model artifact/event hash. Only SHADOW/SHADOW evidence
qualifies mechanically. Model/strategy degradation, suspension, retirement or identity corruption is
an exclusion; supplied events remain caller evidence rather than an independently queried registry.

BUY discovery must match an exact eligible LONG scan entry by policy hash, rank, market, asset,
timeframe and horizon. SELL monitoring does not require scan ranking. Exits sort before entries and
rank orders only candidates that passed every hard gate. Rank, Opportunity Score, forecast probability
and confidence never authorize a request, override risk or set quantity. Existing strategy allocation
and a newly reconciled portfolio remain the only sizing inputs. Fresh equity can represent compounding,
but Autopilot adds no reinvestment multiplier, Kelly shortcut or return assumption.

AutopilotPolicy defaults to DISABLED/enabled=false. Its immutable limits must be no looser than the
bound SpotPolicy and its strategy allowlist must be a subset. Even in SYNTHETIC_QUALIFICATION, the
execution stack must have both Phase 27 local flags and a SYNTHETIC broker. The selected SpotRequest is
passed unchanged to SpotExecution; the independent Phase 27 risk decision is authoritative. The native
broker fails the Autopilot stack gate before submission, while existing foundation configuration,
REAL-risk and native transport barriers remain intact.

## Financial, causal and failure coverage

BUY reservation uses quantity × limit × (1 + Phase 27 fee fraction) in a private 80-digit Decimal
context, rounded upward to 18 places. Projected valued exposure must satisfy Autopilot capital and
exposure limits. UTC daily loss uses day-start equity + declared net flows - current equity. Drawdown
uses explicit high-water equity. Position count uses complete valued open positions. These checks add
a stricter orchestration layer and do not replace broker/account reconciliation or Phase 27 risk.
They do not guarantee loss limits for held inventory or estimate profitability, confidence or ruin.

Cycle, health, scan, lifecycle, proposal, quote, loss and portfolio timestamps are checked against UTC
assessment time and declared cycle availability. Later evidence cannot enter an earlier cycle. Stale
or future data, provider failure, unavailable risk state, inconsistent portfolio, unresolved account
reconciliation, unavailable execution, unknown order state, active cooldown, suspension or kill halts.
A backwards audit clock also halts. Candidate overflow halts rather than silently truncating work.

The separate `autopilot-journal-1` uses BEGIN IMMEDIATE, synchronous=FULL, a policy/account identity and
an append-only SHA256 chain. A decision is durable before SpotExecution is invoked. Exact cycle replay
returns its stored result; changed payload conflicts. A crash after SUBMIT decision leaves an orphan
UNKNOWN decision that blocks every later cycle. Replay records UNKNOWN without another submission.
Only known risk rejection or a terminal broker status settles; unexpected events, exceptions, NEW and
PARTIALLY_FILLED stay unknown/unresolved. Explicit `reconcile(cycle_id)` queries only the existing
SpotExecution client ID. Cooldown and suspension survive restart. Kill is irreversible and propagates
to the Phase 27 execution latch; it cannot cancel an in-flight order or liquidate inventory.

## Security audit

No credential, HTTP/network client, withdrawal, transfer, cancel, direct broker import, external API,
frontend control, CORS/CSRF route, redirect, dependency or container privilege was added. SQLite writes
are parameterized and downstream exceptions are replaced with static reason codes. Secrets are absent
from models, events, tests and documentation. Native credential scopes and the no-withdrawal boundary
are unchanged. Replay protection uses full cycle hash plus Phase 27 deterministic client-order IDs.
The 10,000-event journal bound fails closed.

The local journal contains sensitive financial decisions in plaintext. It belongs in ignored
`.private/` with account-holder-only ACLs. Its hash chain detects accidental changes, reorder and gaps,
but cannot resist malicious chain recomputation or tail deletion without an external anchor. There is
no externally authenticated operator or network surface in this phase, so API authentication,
authorization, CSRF and CORS are not applicable to the implemented boundary.

## Migrations and compatibility

No Alembic/model-table migration; main head remains `0015`. No dependency, Docker, Compose, frontend or
deployment change. The new private SQLite format is `autopilot-journal-1`; policy/account/version
mismatch fails closed and there is no migration from another local format. Existing scanner, registry,
portfolio, PAPER and execution persistence is not rewritten. New source changes the global PAPER
runtime identity, so future processing must use matching current identity/evidence; sealed history
must never be rewritten to bypass that control.

## Exact verification

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 313 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success; 225 source files checked.
- `.venv/Scripts/python.exe -m pytest tests/test_autopilot.py -q --tb=short`: 44 passed, 2 existing deprecation warnings in 9.30s after audit remediation.
- `.venv/Scripts/python.exe -m pytest tests/test_autopilot.py tests/test_spot_execution.py tests/test_native_spot.py --cov=pocket_alpha.autopilot --cov-branch --cov-report=term-missing -q --tb=short`: 130 passed, 2 warnings in 26.14s; Autopilot combined coverage 91% (407 statements, 144 branches, 29 missed statements, 23 partial branches); engine 91%, models 91%.
- `.venv/Scripts/python.exe -m pytest -q --tb=short`: 1012 passed, 231 skipped, 2 warnings in 124.36s (2m04s). Skips require unconfigured PostgreSQL/Redis integration. Existing warnings concern Starlette/httpx TestClient and anyio BlockingPortal deprecations. Skips are not counted as passes.
- `.venv/Scripts/alembic.exe heads`: `0015 (head)`.
- `git diff --check`: exit 0 after removing one trailing blank line; Windows LF/CRLF notices only.

Unexecuted: authenticated venue/account qualification, any native order, real Autopilot worker or
operator workflow, disposable PostgreSQL/Redis integration, frontend/E2E, Docker/Compose, dependency
vulnerability service and remote GitHub Actions. No frontend, dependency, production schema, network
or container change required those checks locally. No fill, balance, profitability, probability or
production-autonomy claim was fabricated.

## Complete changed-file list

- `README.md`
- `docs/architecture/AUTOPILOT.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/research/VALIDATION_POLICY.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_28_COMPLETION_REPORT.md`
- `src/pocket_alpha/autopilot/__init__.py`
- `src/pocket_alpha/autopilot/models.py`
- `src/pocket_alpha/autopilot/engine.py`
- `tests/test_autopilot.py`

## Limitations, debt and next phase

The implementation has no scheduler, distributed lock, PostgreSQL coordination, production alerting,
operator authentication, automatic registry repository lookup, portfolio fill booking, encrypted or
externally anchored journal, independently sourced health, authenticated operational qualification or
measured economic performance. Caller-supplied lifecycle events are immutable and cross-linked but
still require trusted acquisition. A crash before/after external effects deliberately blocks for
operator reconciliation. Journal capacity requires audited archival rather than deletion/reset.

Phase 29 has not been started. Native Autopilot, deployment, publication and derivative execution are
outside this phase. Derivative execution remains independently disabled and requires separate
validation and authorization.
