# Market structure — Phase 4

## Scope and application boundary

MarketStructure is a shared Python service under intelligence/structure. It consumes only
MarketReplay.replay(query, policy). The entire bounded query must pass market quality; gaps,
future receipts, stale data and infrastructure failures propagate, without fabricated neutral
analysis. Explicit empty closed-session schedules return an empty tuple. This is historical
analysis, not streaming state, a recommendation, an order or a probabilistic regime model.

The service returns one frozen StructureSnapshot per input bar. It contains newly confirmed swings
and new breaks on that bar, current state/bias, pending reversal, reason and latest high/low evidence.
History is obtained by traversing the snapshots; they do not repeatedly copy the entire event list.
No database migration, API endpoint, frontend computation, overlay or new dependency is introduced.

Usage inside an existing read transaction, with repository, query and clock supplied by the caller:

    from pocket_alpha.intelligence.structure.models import StructureSpec
    from pocket_alpha.intelligence.structure.service import MarketStructure
    from pocket_alpha.market_data.quality import FreshnessPolicy
    from pocket_alpha.market_data.replay import MarketReplay

    snapshots = MarketStructure(MarketReplay(repository, clock)).analyze(
        query,
        FreshnessPolicy(max_age=None),  # explicit historical policy, not live freshness
        StructureSpec(left_bars=2, right_bars=2),
    )

## Version 1 swing convention

StructureSpec version 1.0.0 supports left_bars/right_bars integers in 1..100, default 2/2.
These are reproducible engineering defaults, not optimized financial parameters. Only STRICT pivots
and CLOSE_CROSS breaks are dispatched; unknown policies/versions and extra fields are rejected.

At completed bar i, candidate j=i-right_bars is examined if it has left_bars predecessors. A high
must be strictly above every other high in [j-left_bars, i]; a low strictly below every other low.
Equality on either side disqualifies that candidate. The first left_bars and last unconfirmed
right_bars cannot become pivots without the required evidence. No provisional pivot is emitted.
Counts mean observed scheduled bars, not clock hours, so explicit market closures do not invent bars.

Each confirmed high is compared with the previous confirmed high: FIRST, HH, LH or EQUAL. Lows use
FIRST, HL, LL or EQUAL. A tie between distinct strict pivots is EQUAL, never silently bullish/bearish.
Same-type pivots need not alternate with opposite types. An outside bar may qualify as both high
and low; both facts are emitted, HIGH then LOW solely for deterministic serialization. That order
does NOT assert the intrabar price path. Both relations are computed against their own prior type.

SwingPoint retains price as Decimal, pivot_open, confirmation bar open in confirmed_on,
availability timestamp, window_start, previous pivot time and previous price. The containing
snapshot retains the full spec, market, timeframe and source. No pivot is stamped as known at its
original chart position. Confirmation adds a new event; it never modifies an earlier snapshot.

The general left/right pivot concept was checked against
[TradingView's pivot documentation](https://www.tradingview.com/support/solutions/43000589195-pivot-points-high-low/).
Tie handling, break definitions and the state machine below are this engine's explicit conventions;
they do not claim universal agreement with every discretionary market-structure method.

## Break detection and state machine

Before confirming pivots on bar i, examine only the latest previously confirmed high and low.
UP requires previous_close <= high.price < current_close. DOWN requires
previous_close >= low.price > current_close. Equality and wick-only excursions are not breaks.
A level can break once; recrossing that same pivot cannot emit a duplicate event. A newly confirmed
pivot supersedes the previous same-side level, even if its price is equal. Its consumed flag resets.
This is a latest-pivot model, not a protected-swing, nested structure or liquidity-sweep model.

The engine retains last confirmed directional bias separately from visible state. A CHOCH marks
structural failure of that bias and a pending opposite direction; it does not immediately replace
the bias or claim a reversal will occur.

| Eligible close break | Event | State/bias consequence |
| --- | --- | --- |
| No existing bias | INITIAL_BREAK | Establish UP/BULLISH or DOWN/BEARISH; not called continuation. |
| Same direction as bias | BOS / TREND_CONTINUATION | Restore/retain that directional state and clear any pending reversal. |
| Opposite bias, no matching pending reversal | CHOCH / STRUCTURAL_FAILURE | TRANSITIONING; retain prior bias; record pending opposite direction. |
| Opposite bias, matching pending reversal | BOS / REVERSAL_CONFIRMED | A second distinct pivot break confirms the model's new bias; clear pending reversal. |

Break evidence includes the entire broken SwingPoint, previous and current closes, direction,
kind, prior bias, reason, bar times and availability. There is no interpolated crossing time or
assumption of execution at the broken level. Break events take precedence over swing-based state
updates on their bar; an unresolved CHOCH remains TRANSITIONING until another eligible break.

Without a new break or pending reversal, newly confirmed swings update context:

- Latest HH + HL establish BULLISH when no bias exists, or corroborate an UP bias.
- Latest LH + LL establish BEARISH when no bias exists, or corroborate a DOWN bias.
- A complete opposing pair makes an established bias TRANSITIONING, not silently reversed.
- Mixed/equal pairs remain NEUTRAL without bias, or TRANSITIONING with bias.
- Insufficient initial comparisons remain NEUTRAL/INSUFFICIENT_SWINGS. If a break already
  established bias, incomplete comparisons do not erase its evidence.

The snapshot reason describes the most recent applicable state evidence. NEUTRAL is not proof
of a range, TRANSITIONING is not calibrated uncertainty, and bias is not a LONG/SHORT decision.

## Availability, immutability and provenance

Validated replay bars are processed in chronological bar order. Each snapshot's available_at is
the maximum receipt time of its entire input prefix, at least the current close time. Confirmed
swings and breaks inherit that time. Late earlier receipts conservatively delay every dependent
output, including its right-bar confirmation. Earlier snapshots never gain events after later bars
are appended or altered. Empty/error queries cannot silently bypass this boundary.

This is reconstructed earliest permissible historical availability, not an actual computation or
emission timestamp. Consumers MUST gate research by available_at, never pivot_open/confirmed_on.
Records arriving today cannot be used as if known historically. There is no retained feature/event
database, streaming subscription or incremental restart state in this phase.

Each snapshot records engine/spec versions, input_start/count/hash, source, identity, timeframe
and explicit freshness policy. The shared intelligence/provenance.py encoder preserves Phase 3's
SHA-256 candle-prefix-v1 contract exactly, including UTC times and canonical Decimal scales.
Technical and structural snapshots of identical prefixes have identical input hashes; their engine
versions and parameters remain separate. This is a content fingerprint, not a signed or persistent
dataset registry. Technical service's existing canonical import remains compatible.

Prices are compared directly as Decimal; no float conversion, smoothing or price tolerance is
introduced. Results do not depend on ambient arithmetic precision. Complexity is O(bars *
(left_bars+right_bars)), with O(bars) output memory and the existing 10,000-observation query bound.

## Limits and next work

No real provider, market dataset, profitability validation, confidence percentage, support/resistance
zone, multi-timeframe aggregation, chart overlay or trading path. Query start determines which
prior swings are known; changing the start can change the classification. Explicit schedules and
corporate-action/price-adjustment policy remain caller/provider responsibilities. Durable immutable
datasets, persistent events, incremental processing and protected/nested swing alternatives are debt.
Version any semantic change and retain old dispatch if historical models need it. Next roadmap
phase: support/resistance zones; not implemented here.
