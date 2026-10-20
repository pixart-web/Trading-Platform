# Phase 30: persistent live control plane

## Boundary and authority

The live control plane records the operator-selected mode, broker, market, account identity and
versioned risk policy. It sits above risk and execution; it cannot create an order and is never a
substitute for an order-specific risk decision. The authoritative path remains market data → shared
intelligence → forecasts → directional analysis → strategy → portfolio → risk → leverage assessment
→ execution → broker.

`PA_LIVE_TRADING_ENABLED` and `PA_DERIVATIVE_EXECUTION_ENABLED` are deployment gates. They are
configurable booleans and default to false. A true deployment gate alone grants no authority.
`LIVE_ACTIVE` additionally requires an explicit operator transition from `LIVE_ARMED`, a persisted
policy/account binding, a clear kill switch and fresh complete qualification evidence. Native order
dispatch remains outside this phase and no public order endpoint was added.

## State machine

The persisted states are `OFF`, `PAPER`, `LIVE_ARMED`, `LIVE_ACTIVE`, `HALTED` and `KILL_SWITCH`.
Transitions use optimistic revisions and an exact action confirmation. Policy changes are rejected
while armed or active. `HALT_NEW_ORDERS` leaves positions untouched. `ACTIVATE_KILL_SWITCH` latches
immediately; reset always returns to `OFF`, removes readiness evidence and requires a new explicit
arm/activation sequence. No action liquidates or cancels positions implicitly.

## Risk policy and readiness

The policy contains operator-defined Decimal limits for capital, orders, total/position/strategy/
broker/asset exposure, daily loss, drawdown, leverage, position and order rates, slippage, spread,
price deviation and market/account freshness. Coherence constraints prevent an order limit above a
position limit, component exposure above total exposure and total exposure above leveraged capital.
No currency amount is embedded in source defaults.

Activation evidence records credential, account, risk, strategy, market-data, infrastructure,
reconciliation and execution gates. Evidence must be produced by an internal qualification service,
must all pass and must be current under the configured data-age bound. The browser has no endpoint to
manufacture this evidence.

## Persistence, audit and authentication

Migration `0016` creates the singleton `live_control` row and append-only `live_control_events`.
Each event contains the actor, correlation ID, revision, previous hash, content hash and a payload
that excludes credentials and secret material. The general audit ledger also receives the applicable
configuration, readiness or transition reason. Database constraints restrict enumerated state,
broker and market values.

The public web application remains behind the deployment's HTTPS authentication. Browser mutations
also require a same-origin custom header. Next.js injects a separate server-only random control token
and operator identity before calling the internal API; the token is mounted as a Docker secret and is
never exposed to browser state. Production configuration rejects a missing or short token.

## Limits and next phase

Phase 30 does not claim authenticated broker qualification, credential vaulting, KuCoin support,
native futures transport, unified OMS, continuous broker reconciliation, cancellation or real-order
acceptance. The existing native Binance Spot write path remains independently blocked by its risk
contract. Phase 31 is broker/credential architecture and authenticated read-only qualification; it
must not weaken this state machine or let credentials reach the frontend, database plaintext or logs.
