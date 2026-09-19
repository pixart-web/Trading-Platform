# Phase 28: fail-closed Autopilot orchestration

## Scope and authority

`autopilot` orchestrates the existing Pocket Alpha path; it is not a trading engine. A cycle consumes
an immutable ScanReport for BUY discovery, full SpotRequest candidates produced by the shared
intelligence → forecast → directional → strategy → portfolio path, immutable model/strategy lifecycle
events and explicit system health. It delegates the selected request unchanged to SpotExecution, where
the independent Phase 27 risk decision remains authoritative. Autopilot never imports a broker, creates
an order directly, recomputes intelligence, changes quantities or overrides a risk rejection.

This foundation remains synthetic and disabled by default. AutopilotPolicy defaults to mode DISABLED
and enabled=false. The only accepted active mode is SYNTHETIC_QUALIFICATION and the underlying
SpotExecution must also use its explicit synthetic mode, both local enable flags and a SYNTHETIC broker.
A native/default broker therefore halts with EXECUTION_STACK_NOT_QUALIFIED before SpotExecution is
called. Settings.live_trading_enabled remains Literal[False], strategy lifecycle cannot reach
LIVE_SMALL/LIVE, and Phase 27 retains its independent configuration, risk and transport blockers.
No background worker, startup hook, public API, UI control, deployment or native order path exists.

## Versioned policy and inputs

AutopilotPolicy is immutable and pins its version, sorted asset and strategy-hash allowlists, capital,
exposure, UTC daily-loss, drawdown, simultaneous-position, cooldown, freshness and candidate-count
limits. Construction rejects any Autopilot limit that is less restrictive than the bound SpotPolicy;
its strategy allowlist must be a subset. Changing policy identity requires a separately reviewed local
journal rather than silently reinterpreting old decisions.

An AutopilotCandidate contains the complete SpotRequest plus the current immutable RegistryEvent and
StrategyEvent. Their existing content-hash validators run again at the cycle boundary. The strategy
UUID must derive from the exact proposal definition hash; its event must reference the same model
artifact and event hash; strategy evidence cannot precede model evidence. Only SHADOW model and
SHADOW strategy states qualify mechanically. DEGRADED, SUSPENDED, RETIRED or any other stage is an
explained exclusion. This supplied lifecycle evidence is not an independent database/venue
qualification and cannot grant native execution.

BUY candidates must reference one exact eligible LONG ScanRankEntry by policy hash, rank, market,
asset, timeframe and forecast horizon. SELL monitoring candidates omit scan identity and remain
subject to the same portfolio, risk and execution path. Scan rank decides order only after every hard
gate passes; score, probability and rank never authorize execution or determine size. Exits sort before
entries, followed by scan rank and stable identities. At most one request is handed to execution per
cycle. Candidate overflow halts rather than silently dropping part of the universe.

## Fail-closed decision boundary

Each cycle supplies a UTC request time and a health snapshot for provider, risk, portfolio,
reconciliation and execution readiness. All must be current. Scan generation, lifecycle evidence,
proposal, quote, loss context and portfolio as-of/generation times must already exist at the declared
cycle time and remain within the policy cutoff at assessment time. Future evidence, a backwards journal
clock or stale input halts.

Global halt reasons include disabled policy/stack, provider failure, unavailable risk state,
inconsistent portfolio, unresolved reconciliation, unavailable/unknown execution, cooldown, manual
suspension and kill. Candidate reasons include allowlists, SHADOW lifecycle, stale/causally unavailable
inputs, missing/mismatched scan evidence and all Autopilot financial limits. Every candidate receives an
explicit assessment and a cycle records HALTED, NO_ACTION or SUBMIT. The decision always records
live_trading_enabled=false and execution_authorized=false; SUBMIT means only that the synthetic request
may be presented to the existing risk engine.

With an 80-digit private Decimal context, BUY reservation uses quantity × limit ×
(1 + Phase 27 maximum fee fraction), rounded upward to 18 places. Projected valued exposure must fit
both maximum capital and exposure. UTC daily loss is day-start equity + declared net flows - current
equity. Drawdown uses explicit high-water equity and position count uses complete valued open
positions. Fresh portfolio equity and upstream allocation determine each new request, so compounding is
represented only through newly reconciled portfolio state; Autopilot has no multiplier, Kelly shortcut
or confidence-based sizing. These arithmetic gates do not estimate ruin probability or guarantee loss
limits on already-held inventory.

## Durable cycles, recovery and monitoring

A separate private SQLite `autopilot-journal-1` binds policy and account hashes. BEGIN IMMEDIATE
serializes admission, synchronous=FULL makes the cycle decision durable before SpotExecution is called,
and an append-only SHA256 chain validates sequence, previous hash and payload. The 10,000-event bound
fails closed. The chain detects accidental edits/reorder/gaps but is not tamper-proof against malicious
recomputation or tail deletion without an external anchor; keep the file under ignored `.private/` with
account-holder-only ACLs.

Cycle UUID plus full cycle hash provides idempotency. Exact replay returns the stored result; changed
content conflicts. If a process dies after a durable SUBMIT decision and before its result is recorded,
that orphan decision is UNKNOWN and blocks every later cycle. Replaying it records unknown state but
never calls submit again. Execution exceptions are sanitized, unexpected response kinds are UNKNOWN,
and NEW/PARTIALLY_FILLED are unresolved. Only known risk rejection or terminal broker status settles.

`reconcile(cycle_id)` invokes only SpotExecution.reconcile for the already selected deterministic client
ID and records its result. It never creates another order. Any unknown or unresolved execution blocks
the whole Autopilot flow until existing-order reconciliation becomes terminal. Cooldown starts at the
durable SUBMIT decision and survives restart. Manual suspend/resume is audited. Kill is irreversible,
persists across restart and propagates to the Phase 27 execution kill latch; it does not cancel an
in-flight broker order, liquidate inventory or undo a prior fill.

## Security, migrations and operational debt

The phase adds no credential, network client, withdrawal/transfer/cancel capability, external endpoint,
frontend bundle, CORS/CSRF surface, dependency, container privilege or production database table.
Autopilot holds only domain evidence and sanitized downstream events. Secrets remain confined to the
existing native adapter and native execution remains unreachable. The journal contains sensitive
financial decisions in plaintext and is not suitable for shared storage.

Main Alembic head remains 0015. The local journal has no migration from another format and identity
mismatch blocks opening. There is no autonomous service scheduler, operator authentication, registry
repository read inside the orchestrator, portfolio fill booking, externally anchored audit trail,
distributed lock, PostgreSQL coordination, production alerting or authenticated operational
qualification. Supplied lifecycle and health evidence must be independently sourced and verified before
any future production design. Phase 29 has not been started.
