# Phase 27: safety-gated spot execution architecture

## Scope and authority

`spot_execution` extends the Python modular monolith with spot risk admission, an account-pinned
durable execution journal and idempotent broker dispatch/reconciliation. It consumes the existing
StrategyDefinition/StrategyProposal/Intent, Phase 16 PortfolioSnapshot and Phase 26 Observation and
LocalState. Strategies never import brokers or this executor. No second intelligence engine exists.

The foundation constitution still forbids enabling real execution. Settings.live_trading_enabled
remains Literal[False]. The default BinanceSpotBroker implements a narrowly allowlisted native Spot
protocol, but submission is unreachable: Settings rejects it, REAL risk admission never grants
execution_authorized, and NativeTransport independently refuses POST while the foundation flag is
false. No authenticated venue qualification, live strategy promotion or operational real-order
acceptance is claimed. There is no CLI/API/startup route that activates submission, no production
enablement was performed and no real order was sent.

The only dispatch mode available remains explicit SYNTHETIC_QUALIFICATION with an injected SYNTHETIC
BrokerPort. Defaults are DISABLED, global_enable=false, manual_enable=false. These policy controls
exercise the synthetic architecture; they cannot override the separate immutable foundation flag.
Caller-controlled provenance/qualification attestations are not genuine research or broker proof.
RESEARCH_PROPOSAL and simulated risk receipts are never converted into live approval.

Official failure semantics consulted on 2026-09-18:
[Binance Spot REST API](https://developers.binance.com/en/docs/products/spot/rest-api) documents
indeterminate timeout/server-error results; the architecture therefore queries an existing client
order ID rather than repeating a submission. The native adapter implements that query-only recovery.

## Native protocol boundary and local qualification

BinanceSpotBroker is pinned to `https://api.binance.com`, disables ambient proxies and redirects,
and permits only time, account, API-restriction, order-status and scoped trade-history GETs plus the
single LIMIT/GTC/FULL order envelope. It exposes no cancel, withdrawal, transfer, margin, futures,
options, FIX, portfolio-margin or universal-transfer operation. Requests use HMAC signing, a 5-second
receive window, bounded responses, unique JSON keys, a fixed host/path/parameter allowlist, sanitized
errors and a policy-bounded query deadline. Credentials come only from excluded SecretStr settings
under `PA_BINANCE_SPOT_`; requests and secrets are never serialized into the journal or receipt.

Read-only qualification binds the expected UID hash, SPOT account type, server-clock skew and an
exact permission set. A future writing-key scope inspection accepts reading plus spot trading only
and rejects every other documented write/transfer flag. That inspection does not authorize an order:
the returned contract fixes live_trading_enabled and execution_authorized to false. Permissions are
bookended to detect changes during qualification and again during order reconciliation. Injected
transports are labelled SYNTHETIC and cannot produce native read-only qualification.

The only native CLI is GET-only qualification; it has no order command. Given a private explicit
policy, run `.venv/Scripts/python.exe -m pocket_alpha.spot_execution.qualify --policy
.private/spot-policy.json --output .private/spot-native-qualification.json`. It refuses to overwrite
the receipt and creates it with private mode where supported. Successful mocked tests do not replace
an authenticated run; no credentialed venue qualification was performed in this phase.

Native query recovery looks up the deterministic client ID, bookends the order, and reconciles actual
cumulative base/quote quantities against paginated order-scoped trade history. Commission is summed
by its reported asset without conversion. Missing, changing, duplicated, future, over-budget or
economically inconsistent evidence fails closed; a no-fill order has no invented commission.

## Explicit policy and financial admission

All monetary limits are required caller inputs, not invented trading thresholds: capital allocation,
per-order notional, total exposure, per-position exposure and daily loss. Position/day/minute counts,
maximum drawdown, data ages, fee budget, spread and price deviation are also explicit. Policy identity
and account/symbol/strategy definition hashes are pinned; policy allowlists must be unique and limit
hierarchy coherent. Live-small capital recommendations or statistically profitable sizing are absent.

Risk checks origin, current exact local broker reconciliation, allowlisted account/symbol/strategy,
proposal identity/action/expiry, required technical/forecast/directional evidence, health and explicit
qualification attestation. It rejects cancellation and unsupported intentions. Strategy timeframe and
forecast horizon remain separate. The current request is revalidated before dispatch; model_copy
cannot bypass proposal/schema integrity at that boundary.

Every nonzero broker asset must be represented in the portfolio's native quote currency. Quote free
+ locked must equal portfolio cash. Spot quantities and asset/market/quote identity must match the
instrument bindings; unknown holdings, mixed currencies, ambiguous base-asset mappings, incomplete
valuation and stale marks block. No automatic FX conversion, external deposit/transfer attribution,
PAPER substitution, native metadata-filter certification or cost-basis repair is performed.

BUY reserves quantity × limit price × (1 + explicit maximum fee fraction), rounded upward at 18
Decimal places in a private 80-digit context. Cash must cover the reservation. SELL requires existing
free base inventory; it cannot short or borrow. Tick and quantity-step rules apply. Exposure tests
conservatively add the full BUY reservation; SELL never receives an assumed exposure reduction before
a confirmed result. Existing exposure above limits blocks even an exit. Only cryptocurrency spot
inventory represented by the Phase 26 native spot identity is considered; derivatives/leverage are
unsupported. No collateral or ruin probability is inferred from confidence or a score.

Daily loss is UTC-day start equity + declared net external flows - current equity. Drawdown uses the
explicit high-water equity. Both require current caller loss context and coherent high water. They
are accounting/mark inputs, not authenticated evidence; native operation would require independently
verified deposits, marks and loss-state continuity before any enablement. Stale/future proposal,
quote, portfolio, loss context or position valuation blocks. Crossing the loss/drawdown boundary
blocks all new intents, without claiming liquidation, guaranteed drawdown caps or profit protection.

## Durable dispatch and recovery

A dedicated private SQLite file stores `spot-journal-1` account/origin identity and append-only events,
separate from the main PostgreSQL schema. BEGIN IMMEDIATE serializes admission, synchronous=FULL
makes PREPARED durable before dispatch, and a consecutive SHA256 chain detects accidental row
modification, reorder and sequence gaps. Each preparation retains the full typed request, request/
policy hashes, immutable risk decision, actual UTC time and client ID. Financial data is sensitive;
use the ignored .private/ directory with account-holder-only ACLs. No credentials are in the models,
journal or exceptions. SQLite timeout is five seconds. Journal capacity is 10,000 events; exceeding
it fails closed and needs separately audited archival. Deleting the log/tail or recomputing a chain
cannot be detected without an external trusted anchor: this is not tamper-proof storage.

The broker client ID is `pa` plus 32 hex digits derived from account identity, full strategy definition
hash and the shared Intent.client_id. It is deterministic and 34 characters long. Reuse with any
changed request hash rejects as IDEMPOTENCY_CONFLICT; retries of an identical request return durable
state without another broker submission. A recovered PREPARED becomes UNKNOWN. The reservation is
never released merely because a process crashed, a query timed out or the broker returned no order.

One unresolved PREPARED/UNKNOWN/NEW/PARTIALLY_FILLED order blocks the entire account. This is stricter
than per-symbol blocking and avoids cross-symbol cash/exposure races. All durable preparations count
against minute/day submission limits across restarts and policy changes. A newer reconciled account
snapshot is required after an order event; refreshing only an intention cannot bypass the gate.

Submission exceptions, identity mismatches, overfills, price violations, unknown/inconsistent states
and ambiguous queries become UNKNOWN and retain reported evidence. Reconciliation calls only
BrokerPort.query using the original client ID/symbol. Not-found is not proof of rejection. No blind
retry, replace or cancellation path exists. A qualified known rejected/filled/cancelled/expired result
can settle that order, followed by a new independent account snapshot before another intent.

Reports contain cumulative executed base/quote quantities and cumulative commissions by asset. NEW,
PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED and EXPIRED must be structurally coherent. Executed
quantities, cumulative quote, fees, order identity and time cannot regress; changed quote for identical
executed quantity blocks. Exact duplicates do not append another financial event, and older recorded
duplicates do not regress later state. Repeated current known evidence can resolve a subsequent
UNKNOWN. Reported BUY execution cannot exceed its limit price; SELL cannot be below its limit.
Positive non-quote fees or fees above the declared budget require further reconciliation, never an
invented FX valuation or zero-fee assumption. Reports are cumulative observations, not additional
fills on every callback and not automatically posted to the Phase 16 ledger.

Kill is an irreversible journal latch for this foundation: no automatic reset or re-enable exists.
It survives restart and blocks new admissions. A second check can stop a prepared order before its
dispatch; a kill arriving after the dispatch point cannot revoke an in-flight operation. No existing
order cancellation, forced liquidation or protection of existing inventory is claimed.

## Usage, verification, migrations and debt

Construct SpotExecution with a private journal path and explicit SpotPolicy. The default native
broker can perform explicit reads but cannot trade. For isolated mechanical qualification, inject a
clearly labelled synthetic BrokerPort,
select SYNTHETIC_QUALIFICATION and explicitly set both local enable flags. BrokerPort receives only
risk-approved synthetic requests; it has submit/query, no withdrawal/transfer methods. No native
network access occurs in tests. Inspect typed decisions and journal events instead of trading claims.

Main Alembic head stays 0015: no new production DDL or dependencies. The private SQLite schema is a
new separate local persistence format; no migration from old journals is supported. Account/origin
mismatch blocks opening a journal. New source changes the PAPER runtime identity; old journals can
be read/replayed but new processing needs matching current configuration/evidence. Never rewrite
old PAPER headers or sealed qualification to bypass that gate.

Native broker execution, manual real enablement, authenticated read/trade-key qualification,
operator authentication, genuine SHADOW/LIVE_SMALL promotion evidence, complete venue metadata filters,
atomic broker-state streams, externally anchored/encrypted journals, verified daily-flow/high-water
persistence, portfolio fill booking, execution economics and production PostgreSQL coordination remain
remain operationally unqualified/unimplemented. They are prerequisites, not permission granted by this phase.
No profitable strategy, live spot acceptance, Autopilot or derivative execution is claimed. Phase 28
has not been started. See the Phase 27 completion report for exact checks and known coverage gaps.
