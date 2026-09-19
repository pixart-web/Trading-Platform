# Phase 29: derivative execution qualification

## Scope and authority

The derivative_execution package completes the Phase 29 foundation boundary without enabling real
trading. It consumes immutable derivative strategy evidence, a position proposal already assessed by
Phase 25 leverage research, current derivative market rules, a current account snapshot and exact
local reconciliation. The only permitted dispatch mode is explicitly synthetic mechanism
qualification. There is no public API, UI, worker, scheduler, credential model or network client.

The canonical boundary stays: market data → shared intelligence → forecasts → directional analysis →
strategy → portfolio → risk → leverage assessment → derivative execution → broker. A strategy cannot
import or call a broker. A caller assertion cannot skip portfolio, prior-risk or leverage evidence.
Every request is independently evaluated immediately before synthetic dispatch. The decision fields
execution_authorized, live_trading_enabled and derivative_execution_enabled are structurally false
because this foundation cannot authorize a real order.

## Independent disablement

Settings.live_trading_enabled and Settings.derivative_execution_enabled are separate Literal[False]
settings. Environment strings may restate false; true fails configuration validation.
DerivativeExecutionPolicy adds separate global, derivative and manual gates and defaults to DISABLED.
Those local gates can only exercise an injected SYNTHETIC broker. A broker labelled REAL is rejected
by risk, and the default DisabledNativeDerivativeBroker exposes no working transport, credentials,
transfer or withdrawal capability. A new environment therefore remains disabled even if a policy
file is copied from a qualification run.

## Supported economic model

Qualification is intentionally narrower than general derivative intelligence:

- linear perpetuals and dated futures;
- contract multiplier in base units per contract;
- cash settlement with one currency for quote, settlement, reference index and collateral;
- isolated margin and one-way position mode;
- LIMIT/GTC orders;
- explicit LONG or SHORT position side;
- OPEN with reduce_only=false;
- CLOSE with reduce_only=true and a reconciled matching position.

Options, quote-valued or inverse multiplier conventions, physical settlement, cross/portfolio margin,
hedge mode, market orders and currency conversion fail closed. Dated futures need an explicit expiry
buffer for opening; expired contracts always reject. Perpetuals require a current funding rate and
next-funding timestamp. Dated futures reject unexpected perpetual funding metadata.

Contract, strategy and account identities are pinned by allowlists and SHA-256 hashes. Strategy
evidence is SHADOW, synthetic and immutable; its proposal hash must equal the leverage position
upstream hash. The leverage position hash, derivative contract hash, current margin rules, portfolio,
prior-risk check and account reconciliation must all agree.

## Risk and collateral

All arithmetic is Decimal in an 80-digit local context; all times are aware UTC values.

order notional = contracts × base-units multiplier × limit price

An OPEN reserves the greater of venue initial margin and already assessed collateral, plus explicit
maximum fee and funding budgets. A CLOSE reserves only fee/funding budgets; it does not invent new
initial margin. Reduce-only closes stay eligible when entry leverage, modeled-loss, daily-loss or
drawdown limits are already breached, while still requiring an exact current position, fresh market
and account state, venue steps, permissions and independent risk admission. This prevents entry
controls from trapping a mechanically valid risk reduction. Kill remains a global latch and does not
automatically liquidate or cancel anything.

OPEN checks per-order, per-position, gross and signed-net notional, collateral amount/fraction,
leverage, position count, daily loss, high-water drawdown, modeled stress loss and assessed/current
mark-to-liquidation buffers. All flows check quantity/price steps, venue and margin-tier caps,
initial/maintenance margin rules, spread, mark/index deviation, basis, funding, price deviation and
causal freshness.

Phase 25 must provide all six stress families. OPEN requires an ACCEPTABLE assessment, applicable
margin tiers and no modeled ruin scenario. A finite stress suite is not a guarantee and
ruin_probability remains unavailable. The execution layer does not turn a score, confidence,
forecast probability or backtest result into size or approval.

## Account state, reports and reconciliation

The account snapshot explicitly contains collateral equity/availability, wallet balance, isolated
positions, unresolved client IDs, one-way mode, trading permission and withdrawal permission fixed to
false. A local record must hash the entire account snapshot and attest independent reconciliation at
the exact completion time. Opposite one-way positions, open orders, stale data, unavailable trading
permission or any mismatch block admission.

Broker reports are cumulative observations: identity, LONG/SHORT side, BUY/SELL direction, OPEN/CLOSE
effect, reduce-only flag, original/executed contracts, settlement value, commissions, realized P&L and
funding. Validators reject overfills and incoherent states. Execution rejects identity/time
regressions, terminal-state changes, decreasing quantities/value/fees, limit-price violations,
unvalued commission currencies, fee/funding overruns and realized P&L on OPEN. Reports do not post
fills into portfolio accounting; a fresh independently reconciled snapshot is required before
another order.

## Durable lifecycle

The account-specific derivative-journal-1 SQLite file uses BEGIN IMMEDIATE, synchronous=FULL,
parameterized statements, a 10,000-event bound and an append-only SHA-256 chain. A deterministic
client ID derives from account, strategy definition and intent UUID. Identical replay returns durable
state without another submission; changed content under the same identity is an idempotency conflict.

PREPARED is durable before broker submission. A recovered PREPARED, submission exception, malformed
report, query exception or not-found result becomes UNKNOWN. Not-found is never proof of rejection.
Reconciliation queries only the existing client ID. There is no blind retry, replace, cancel,
transfer or liquidation path. One PREPARED/UNKNOWN/NEW/PARTIALLY_FILLED flow blocks the whole account.
A repeated latest known report may resolve a later UNKNOWN; an older report cannot regress newer
state.

The journal contains sensitive financial state in plaintext and belongs in an ignored private path
with account-holder-only filesystem permissions. Its chain detects accidental row edits, reorder and
gaps, but whole-file rewriting or tail deletion requires an external anchor to detect.

## Validation boundary and prerequisites

SyntheticDerivativeBroker creates only a deterministic synthetic NEW report and stores
caller-published typed synthetic reports. It performs no network call and proves only state-machine
mechanics. Tests do not demonstrate strategy quality, authenticated permissions, venue rules, funding
accuracy, liquidation fills, insurance or ADL behavior, latency, slippage, profitability, drawdown
guarantees or production readiness.

Native derivative execution requires a separately reviewed venue adapter, read-only and trading-scope
qualification with withdrawal/transfer denial, independently sourced lifecycle/account/portfolio
evidence, operational alerting and reconciliation, real venue-rule validation, controlled deployment,
security review and explicit authorization outside this foundation. None is implemented or implied.
