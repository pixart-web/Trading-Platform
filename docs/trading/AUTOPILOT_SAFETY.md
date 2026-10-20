# Autopilot safety

Autopilot uses the same market data → intelligence → forecast → directional → strategy → portfolio → risk → leverage assessment → execution → broker pipeline. It has no browser or deployment shortcut. Missing/stale evidence, risk rejection, unresolved orders, inconsistent account state, dependency failure or kill latch cause suspension/fail-closed behavior.

Live operation still needs authenticated operator controls, persistent suspension/kill state, strategy assignment, approved risk limits, decision and trade journals, reconciliation status, incident recovery and a restart drill proving it remains disabled. A forecast, score or model stage cannot authorize an order.

`AUTOPILOT_LIVE_READY = NO`

`AUTOPILOT_LIVE_ENABLED = false`
