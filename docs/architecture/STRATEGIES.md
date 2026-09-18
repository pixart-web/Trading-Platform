# Phase 24 — versioned strategies

## Boundary and supported scope

Market data → shared technical intelligence → immutable forecasts → the existing independent
LONG/SHORT/NO_TRADE directional engine → strategy proposal → portfolio sizing → shared risk →
shared simulated execution. Strategies import no broker and have no execution authority.
Timeframe and forecast horizon remain separate. No SHORT position, leverage or live route is added.
Only SMA_TREND_SPOT_LONG is implemented. Other families require a versioned definition, causal
upstream evidence and an evaluator with acceptance tests; they are not advertised as implemented.
Definition/proposal/registry/allocation contracts are the extension boundaries.

StrategyDefinition freezes market, asset, provider source, technical/model versions, timeframe,
horizon, fast/slow periods, freshness, trend/return thresholds, invalidation and allocation policy.
Its full hash is bound into the existing StrategyIdentity parameters, so changed settings require
another strategy version and another sealed experiment. Feature specs/history must cover both SMAs.

TrendStrategy consumes StrategyView from the validated backtest/PAPER kernels; it does not fetch,
recompute or train forecasts. Shared SMA outputs and one newest compatible unexpired forecast feed
independent AND criteria for LONG and SHORT. Missing, stale, warmup, ambiguous or incompatible
inputs yield NO_TRADE. SHORT invalidates an owned LONG; it never opens a short position. Expected
returns are upstream model estimates, not validated profit. Scores/probabilities do not size orders.

Proposals contain deterministic IDs, content/definition/view hashes, full forecast and directional
evidence, technical provenance, reference price, expiry, invalidation and reason. A proposal is a
RESEARCH_PROPOSAL, not an order. Existing inventory can exit at an observed price stop or holding
expiry without a fresh forecast; stale/missing market prices cannot authorize an exit. Stops are
observed bar-close invalidations, not guaranteed broker stops or intrabar execution prices.

## Portfolio and financial assumptions

StrategyAdapter implements the existing research callback and canonical PAPER checkpoint ports.
It records observed fills rather than assuming proposal fills. Holding horizon begins when inventory
is first observed; cost-basis entry price fixes its invalidation threshold. Partial-entry invalidation
cancels the recorded remaining entry before requesting a sale of unreserved owned inventory.
No pyramiding occurs while inventory or entry cash is reserved. Checkpoints retain the version hash,
observed position, expiry, stop, own pending-entry ID and latest explained proposal.

Portfolio sizing takes the smallest of available cash after reserves/equity cash buffer, configured
equity exposure and proposal notional cap, then reserves worst modeled unit debit and rounds down
to the shared quantity step/minimums. The entry forecast must exceed explicitly modeled round-trip
fee/spread/slippage/impact plus the configured return margin. This is an assumption filter, not an
empirical opportunity or profitability certificate. Decimal uses a private 80-digit context.
The shared simulator independently approves every BUY/SELL through existing risk limits and executes
only eligible future bars. Costs, participation, latency, expiry and drawdown remain Phase 21/23
assumptions. Single-account crypto spot inventory is the supported scope; no cross-account netting,
hedge allocation, funding, derivative liquidation or calibrated probability sizing is claimed.

## Evidence-linked lifecycle and recovery

StrategyRegistry persists immutable hash-addressed definitions and append-only chained events.
Registration requires existing market/source identity and starts RESEARCH. One market/version cannot
be rebound to different settings. Reads revalidate indexes, history, causality and promotion evidence;
transitions use expected revision/CAS and savepoints; callers commit their outer transaction.

RESEARCH → CANDIDATE requires a current CHALLENGER/SHADOW model event, actual REAL sealed temporal
experiment, exactly matching strategy identity/horizon/features and explicit PromotionPolicy.
Phase 22 net OOS, expectancy, drawdown, completed-trade, asset/fold, baseline and cost-stress gates
are reused. PAPER additionally binds an existing REAL PAPER account with exact strategy, source,
market/asset, timeframe, complete run configuration (including capital, history, code/environment
hashes and cost/risk settings) and causal state hash. Model and policy remain frozen.
SHADOW retains that account and requires the model's one-shot final holdout gate under the same
policy plus completed PAPER trades, net return, net expectancy and maximum observed equity drawdown
across the full journal. No synthetic research fixture can qualify production promotion.

CANDIDATE/PAPER/SHADOW may degrade, suspend or retire; RESEARCH can suspend/retire. Degraded/suspended
versions can only retire. Recovery of an execution feed uses Phase 23 reconciliation; lifecycle
requalification requires a new version and sealed evidence. LIVE_SMALL/LIVE are unavailable in both
code and the database CHECK constraint. Historical qualification references remain auditable after
model degradation; current operational readiness requires the model to remain CHALLENGER/SHADOW.

For PAPER orchestration instantiate RegisteredStrategyAdapter(registry, strategy_id, config), create
an account with that checkpoint adapter, qualify/bind its account ID, and pass the same adapter to
PaperService.process. Its preflight runs before market execution; false, exception, changed config,
unqualified model or nonoperational lifecycle becomes a journalled DISCONNECT/STRATEGY_NOT_READY,
cancelling pending orders before fills. KILL/CLOSE remain available. Polling stops when the cursor
cannot advance. Restart replays recorded decisions without invoking strategy or rechecking today's
lifecycle against old events. StrategyAdapter alone remains available for explicitly offline/synthetic
research mechanics; it does not certify lifecycle qualification. No worker or broker is started.

GET /api/v1/strategies and GET /api/v1/strategies/{uuid} expose read-only no-store metadata/history.
Storage, corrupted data or failed qualification returns sanitized 503; missing IDs return 404.
There is no HTTP registration, promotion, trading or live toggle. No dedicated UI is introduced.

## Migration, security and limits

0015 adds strategy_registry and strategy_events after 0014; no previous records are changed.
Export definitions/events before downgrade: downgrade deletes only the two new tables. PostgreSQL
migration/service verification remains infrastructure debt; SQLite checks cannot substitute for it.
No dependencies, credentials, withdrawals, private broker calls or automatic startup are added.
No qualified real research is supplied by this phase; real promotion stays unavailable until genuine
matching evidence passes. Synthetic tests prove contracts and simulated mechanics, not returns.
The journal is bounded by existing PAPER event limits and reads revalidate evidence; large histories
will need separately measured indexing/revalidation performance work.
