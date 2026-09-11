# Phase 5 — support/resistance zones

SupportResistance consumes MarketReplay once per request, rejecting untrusted, stale, incomplete
or empty input. It reuses the Phase 4 structure kernel after that boundary, with strict confirmed
swings (default two bars left/right). analyze returns immutable prefix snapshots; chart also returns
the exact validated candles used. Canonical hashes, engine/spec versions, source, policy, market,
timeframe, input start/count and causal availability accompany results. No timeframe aggregation.

## Version 1 conventions

A confirmed LOW creates support; HIGH creates resistance. Half-width is
min(price/2, max(price * minimum_width_bps/10000, pivot_bar_range * range_fraction)). Defaults:
10 bps and 0.25 range fraction. Geometry uses an isolated 50-digit Decimal context and never moves.
A same-role pivot inside existing bounds joins the nearest center (creation order breaks ties).
Pivot counts are lifetime totals; only the latest 32 pivot evidence records are retained.

Creation is known only at confirmation-prefix availability, not at pivot time. A contact is entry
into an inclusive wick/band overlap episode, not each consecutive overlapping bar. A rejection is
an entry whose close is back above support's upper bound or below resistance's lower bound.
Contact volume sums entry-bar volume only: it is not a volume profile or inferred intrabar volume.
A close strictly below support or above resistance flips its role immediately. The flip bar is not
also counted as a contact or rejection. Current-role visible_from resets to that availability;
first_seen remains creation availability. Counts and evidence survive flips and describe the zone's
lifetime, not independent evidence for the new role. Intrabar event ordering is never inferred.

Activity means a joined pivot, contact entry or flip. Zones expire before processing a bar if age
exceeds max_age_bars (default 200). At most max_zones (default 24, maximum 32) survive, with oldest
activity evicted first and creation order breaking ties. Earlier snapshots never change.

Strength = 10*min(pivots,4) + 10*min(contacts,3) + 5*min(rejections,2)
+ floor(20*(max_age_bars-age)/max_age_bars). Components total 0–100 and are displayed separately.
This is a versioned descriptive heuristic, not calibrated confidence or probability. Confidence is
always null with UNCALIBRATED reason. No predictive or economic performance is asserted.

## API and chart

GET /api/v1/markets/{market_id}/zones?timeframe=1h&start=...&end=...
uses default ZoneSpec and the existing continuous historical freshness policy. Maximum 1,000
scheduled bars, no pagination or public parameter overrides; internal services cap 2,000 bars.
One replay produces both candles and latest snapshot atomically. Success is no-store; unknown
markets return 404, invalid/rejected data 422, unavailable database 503 with sanitized details.
No write route, migration, persisted analytics or new dependency is introduced.

The optional UI control switches the existing cancellable request; it does not join independently
fetched analytical data. Browser checks preserve exact decimal strings and compare bounds using
scaled integers, then use approximate numbers only for canvas coordinates. Provenance identity,
count, source and availability must match candles. Scores and null confidence are validated.

The chart shows latest active zones, not a historical strategy replay. Bands begin on the first
plotted candle open at/after current-role availability and need two distinct chart points. Late
imports beyond the history therefore have evidence but no band. Native baseline series follow
pan/zoom/resize without changing candle autoscaling. The table exposes exact bounds, components,
counts and availability; expired/evicted zones are absent from the latest view.

## Limitations and validation

Query start defines context; results can differ with different warm-up history. No durable stream
state, empirical strength calibration, session calendar inference, corporate-action adjustment,
volume profile, cross-timeframe confluence or real provider. Public deployment still requires
authentication, rate limits and operational hardening. Live execution remains prohibited.

Synthetic tests cover geometry, confirmations, contacts, flips, expiry, evidence caps, immutable
prefixes/future perturbations, delayed availability, Decimal context, rejected inputs and API/UI
gates. These tests do not establish profitability, fills or sustainable net compounded growth.
Costs, liquidity, drawdown and ruin need later economic research; no assumption of zero costs.
