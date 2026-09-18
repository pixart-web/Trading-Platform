# Phase 23 PAPER execution

This phase implements persistent, incremental crypto spot LONG simulation over native complete
candles. It shares the Phase 21 execution, risk, sizing precision, resource reservations and cost
logic through simulation/engine.py. The strategy port remains ResearchStrategy identity/on_event,
extended with a bounded canonical JSON checkpoint/restore contract. Custom strategies are trusted
local Python; Phase 24 lifecycle, predictive strategies and automatic promotions are not implemented.

## Causality and financial model

A session starts in the current aligned native UTC bucket. Only complete contiguous candles from
that start are accepted. Original provider received_at remains immutable. Journal input.at and
all fills use the actual processing clock, so delayed polling cannot execute retrospectively.
Orders can fill only when a complete bar opens strictly after their latency-ready timestamp.
The complete-bar-close price proxy is explicitly the same Phase 21 assumption, not an exchange
order-book simulator or a tick-level fill guarantee. Volume participation is shared FIFO capacity;
partial fills, acknowledgements, expiry, cancellation, precision, minimums, collar and risk
rejections are simulated. Configured fee/spread/slippage/impact rates are versioned assumptions,
not measured quotes. No default cost/risk configuration claims realistic calibration.

Money uses Decimal under a private 80-digit context. Buy fees enter moving-average cost basis;
sells allocate that basis and realize proceeds minus allocated cost. Quote-currency cash,
inventory, basis, equity, reserved cash/quantity, fees and realized/unrealized PnL persist.
The read model independently rebuilds cash, basis and inventory from fills and requires every
fill to have a unique prior risk approval. Net return describes simulated equity versus initial
capital. Existing inventory retains its last genuine mark when the feed stops; freshness becomes
not ready. A halt does not invent an exit or guarantee an existing position's drawdown limit.

The intelligence kernel is shared, with an explicit bounded rolling history. EMA/other recursive
features can differ from a full-prefix offline run once that history truncates. No separate
indicator implementation or probability estimation is added. Forecast horizon remains independent
of candle timeframe; immutable caller-supplied forecasts are journalled and causal availability,
expiry and asset/model/feature versions are checked. No forecasts/outcomes are mutated.

## Persistence, restart and reconciliation

Migration 0014 adds paper_accounts and paper_journal only. A PAPER head freezes config, metadata,
source/environment hashes, genesis checkpoint, revision and state hash. Journal entries freeze
actual processing inputs, submitted intents, strategy checkpoint, outcome hash and previous
content hash. The original request digest supports idempotency even when processing time differs
from request time or invalid market input is converted into a durable rejection/disconnection.
Invalid raw market payload is represented by its request digest, never silently accepted.

Appending journal plus head revision is atomic inside a savepoint with compare-and-swap revision;
DB uniqueness enforces one event UUID per account. The outer transaction owner must commit.
The CLI prints success only after commit; JSON logs identify PAPER and say transaction prepared.
Retries with the same UUID and identical original request return current state without callbacks
or duplicate fills; conflicting input and stale revisions require an explicit reload.

Restart replays stored decisions, never strategy callbacks. Every journal step, hash chain and
final head must reconcile; corrupted/missing journal data is unavailable rather than repaired
with invented balances. Fresh callbacks restore the last committed checkpoint. Callback failure,
invalid checkpoint or conflicting intentions discard tentative submissions and persist suspension,
preserving genuine market-step fills and the last committed strategy checkpoint.

Feed/execution disconnection, unknown order state, gaps, invalid source/receipt and stale data
suspend new orders and cancel known simulated pending orders. These are local simulated orders;
there is no external exchange order state to query. Valid catch-up candles can update suspended
marks/history without fills or strategy callbacks. Explicit reconciliation requires a matching
current accounting hash and fresh market data. Drawdown/daily loss/operator kill remain latched.
CLOSE cancels pending orders and retains existing inventory/accounting. Journal budget exhaustion
is not ready, blocks ordinary events and permits terminal KILL/CLOSE controls. Source/runtime
identity drift blocks processing. Bounded replay is intentionally a foundation, not a production
throughput guarantee or a cryptographic protection against an administrator rewriting all history.

## Explicit public feed and operator workflow

PublicPaperPoller.poll is an explicit bounded one-shot call using the existing unauthenticated
CoinbaseHistoricalProvider. It requests only native completed buckets, up to 299 per call,
requires a complete ordered grid and the frozen REAL mapping, and records unavailability as
PAPER suspension. Repeated calls are operator-owned; there is no startup task, synthetic fallback,
credential acquisition or background worker. Heartbeats advance timers and staleness when no new
complete candle exists. The caller must poll/heartbeat explicitly; this phase makes no continuous
service availability claim.

The local CLI is `python -m pocket_alpha.paper_trading` with create config.json, inspect UUID,
poll UUID, heartbeat UUID, disconnect UUID, reconcile UUID, kill UUID and close UUID.
Apply migrations first. Creation requires a complete PaperConfig JSON containing explicitly
chosen RunConfig costs/risk, current code/environment hashes, initial cash, native aligned current
start, asset/venue/market/mapping and event budget. It registers those explicit metadata through
the existing market repository. The CLI supports only identity strategy_version=paper-observer-1,
model_version=none-observation-1, parameters=[]; its observer emits no orders and claims no model
quality. Custom callbacks must use PaperService within a trusted committed Session transaction.
There is no dynamic strategy import or public trading-write endpoint.

GET /api/v1/paper/accounts and GET /api/v1/paper/accounts/{uuid} are no-store, read-only views.
Unknown accounts return 404; DB/reconciliation failures return sanitized 503. The frontend /paper
renders validated PAPER data, origin, observation time, readiness, simulated accounting and recent
order/fill events. Empty/unavailable data does not create a demonstration balance. The gateway
allowlists only the two PAPER GET routes, with no mode switch or write forwarding.

## Limits and security

REAL labels market-data provenance; all execution/capital/results remain simulated. No real broker
adapter, keys, withdrawal permission, SHORT/leverage/margin, multi-asset allocation, tick/order-book
latency model, exchange reconnect state, stop order or autonomous strategy lifecycle is introduced.
Live stays Literal[False]. Tests use explicit synthetic or mocked provider payloads, never real
orders or network calls. Runtime metadata and journals contain no credentials. PostgreSQL/Redis
integration, calibrated execution assumptions, continuous streaming, incident notifications and
independent financial validation remain debt. A PAPER success does not qualify production.

Upgrade is additive; export headers/journals before downgrading 0014. Downgrade removes only PAPER
heads/journals, never existing market, portfolio, research or forecast records. There is no automatic
migration of manual portfolios into simulated accounts. The next phase is 24 and requires separate
authorization.
