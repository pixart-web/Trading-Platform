# Multi-timeframe intelligence — Phase 6

## Shared application boundary

`MultiTimeframeIntelligence` combines independently computed technical indicators, market
structure and support/resistance for 2..8 unique native candle timeframes of one market.
It is an application service in the Python modular monolith. It does not resample bars, average
prices or indicator values across resolutions, infer calendars, generate forecasts, issue trade
intentions or connect to a broker. Forecast horizon remains a separate domain concept.
The Analyze user experience belongs to Phase 13; this phase adds no HTTP or frontend surface.

Each frame requires a `CandleQuery`, an explicit replay `FreshnessPolicy` and an explicit
`max_snapshot_age` (positive duration or `None` for historical age). Requests cap each schedule
at 2,000 bars and total scheduled bars at 8,000, including future tails. All eight existing
Timeframe values work, ordered by duration, regardless of caller order. Invalid parameters,
duplicate timeframes, mixed markets, unsupported versions and extra fields fail validation.

One trusted `MarketReplay.replay` call per frame supplies all three kernels. The technical
kernel is extracted from the existing service without changing its interface or mathematics;
structure and zone kernels are reused. The same `ZoneSpec.structure` controls structural and zone
analysis. Indicators retain their own READY/WARMUP/UNDEFINED fields; indicator warm-up does not
turn a valid structural observation into missing market data or a vote. Default indicators are
the existing 15 kinds, with the same versioned engineering parameters.

The entire input query must pass replay quality before use. Missing native timeframes, missing
bars, malformed/future/stale records and infrastructure failures propagate rather than yielding a
partial success or fabricated neutral result. Explicit empty closed-session schedules are valid
but unavailable for aggregation. Selected snapshots from different providers are rejected until
an explicit cross-provider adjustment/compatibility policy exists. Even matching provider names
do not establish corporate-action compatibility; that remains an ingestion responsibility.

Caller owns the transaction. Use PostgreSQL REPEATABLE READ for one stable database view across
frame reads when concurrent imports are possible. The service neither commits nor changes
transaction isolation. It reads each frame once but does not claim that an ordinary READ COMMITTED
transaction provides a database-wide atomic snapshot. No new persistence or migration is needed.

## Causal cutoff and freshness

`as_of` is mandatory, timezone-aware and normalized to UTC; it cannot exceed the replay clock.
For each validated, open-time-ordered series, only its longest contiguous prefix with every close
and receipt at or before `as_of` is calculated. This selects the most recent usable bar separately
for each resolution: e.g. at 15:00 a four-hour series anchored at 00:00 uses the 12:00 close, never
the 16:00 close. Exact close/receipt equality is eligible. No forming candle or interpolated higher
bar is manufactured. Confirmed swings and zones still obey their original confirmation delays.

A delayed earlier receipt blocks every later dependent prefix, even if later candles have already
arrived. If any requested closed candle is still awaiting receipt, `pending_input` is true and
status is NOT_YET_AVAILABLE. An older usable prefix remains visible as diagnostic evidence, but
cannot participate in the aggregate direction or a pairwise opposition claim. Historical imports
never acquire invented past availability. This reconstruction is not an actual emission timestamp.

| Frame status | Meaning and treatment |
| --- | --- |
| READY | A usable prefix exists, no closed input is pending, and snapshot age is allowed. |
| EMPTY_SESSION | Explicit schedule contains no bars; snapshots are null. |
| NOT_YET_AVAILABLE | No usable prefix at cutoff, or a closed input receipt is pending. |
| STALE | Usable last close exceeds the caller's maximum snapshot age; evidence is retained. |

Snapshot age is `as_of - bar_close`, not time since receipt. Equality to the limit is valid.
`max_snapshot_age=None` explicitly permits old historical context, never future information.
Replay freshness remains independent: its existing max_age tests every queried candle against
the replay clock, so callers normally allow historical warm-up there and bound the selected last
close separately. There is no invented universal trading freshness limit.

An invalid larger query still fails as a whole, even if the defect is after the cutoff. A previously
retained snapshot from a separately valid prefix is unaffected. Appending valid future bars with
the same warm-up start does not change selected evidence or its context hash. Query start and
explicit session schedule are caller choices; changing warm-up history can change the analysis.
Fixed 24h/7d daily/weekly semantics and session/adjustment limitations of Phase 1 still apply.

## Explained aggregation, without a voting score

Version 1 uses `UNANIMOUS_STRUCTURE`. Only BULLISH and BEARISH structure states provide UP and
DOWN context. NEUTRAL and TRANSITIONING supply no direction. In particular, the retained old
bias of a transitioning structure cannot silently vote for the former trend.

| Agreement | Condition |
| --- | --- |
| INCOMPLETE | Any requested frame is not READY; aggregate direction is null. |
| DIVERGENT | All ready, and at least one UP and one DOWN, including when other states are unresolved. |
| ALIGNED_UP / ALIGNED_DOWN | Every requested frame has the same resolved structural direction. |
| NEUTRAL | All ready and every structure is NEUTRAL; this does not prove a ranging regime. |
| MIXED | Remaining ready combinations, including neutral/directional or transitioning states. |

Only the two aligned outcomes carry aggregate `direction`. There are no majority weights, scores,
confidence percentages or probability claims. Higher resolutions do not erase lower opposition.

Every lower/higher pair is retained (at most 28). Relations are ALIGNED, OPPOSED, UNRESOLVED or
UNAVAILABLE. `against_higher_timeframe` is true only for two ready, resolved, opposing structures.
This flags a lower-timeframe move against higher structure; it is not a trade approval, entry,
LONG/SHORT/NO_TRADE engine or risk check. Pair evidence remains visible even when a third missing
frame makes the aggregate incomplete. Zones remain separate per timeframe; geometric cross-frame
zone merging and predictive confluence scoring are not asserted.

## Immutable evidence and reproducibility

Frozen output contains the request per frame, technical/structure/zone snapshots, versions,
parameters, original policies, prefix hashes/counts, source and causal availability. The top-level
`available_at` is the maximum availability of the selected evidence, or null without evidence;
`as_of` is the aggregation cutoff. Consumers must check frame status and aggregate agreement.

`context_hash` is SHA-256 over a deterministic, sorted JSON description of the engine, market,
cutoff, specification, selected snapshots, input starts, timeframe, statuses and freshness choices.
Unused future query tails and caller frame order are excluded. Full requests are retained separately.
Existing per-frame candle hashes retain the Phase 3 canonical Decimal/UTC contract. This fingerprint
is not a signature, durable dataset registry or evidence that an analysis ran in production.
Arithmetic reuses the existing isolated 50-digit Decimal kernels, without float conversion.

Work is bounded by the sum of the existing engines' per-frame costs plus at most 28 comparisons.
Kernels currently calculate prefix histories before selecting their latest result; this is a bounded
batch implementation, not a streaming or constant-memory engine. Persistent/incremental snapshots
and performance work require a separate measured task.

## Usage

Inside a caller-owned read transaction, with legitimate stored native candles and an injected clock:

```python
from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.intelligence.multi_timeframe.models import (
    FrameRequest,
    MultiTimeframeRequest,
)
from pocket_alpha.intelligence.multi_timeframe.service import MultiTimeframeIntelligence
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

# start_1h, end_1h, start_4h, end_4h and cutoff are aware datetimes.
# Query ends must fit their own schedules; use expected_opens for explicit sessions.
frames = tuple(
    FrameRequest(
        query=CandleQuery(market_id=market_id, timeframe=tf, start=start, end=end),
        freshness_policy=FreshnessPolicy(max_age=None),
        max_snapshot_age=None,  # explicit historical use; not a live-data threshold
    )
    for tf, start, end in (
        (Timeframe.H1, start_1h, end_1h),
        (Timeframe.H4, start_4h, end_4h),
    )
)
snapshot = MultiTimeframeIntelligence(MarketReplay(repository, clock)).analyze(
    MultiTimeframeRequest(as_of=cutoff, frames=frames)
)
```

## Validation and remaining scope

Synthetic tests check independent-engine parity, one replay per frame, all aggregation outcomes,
minority opposition, all eight timeframes, close/receipt cutoffs, delayed prefixes, future append
invariance, staleness, empty sessions, gaps, dependency failures, mixed providers, UTC normalization,
parameters, resource limits, JSON round-trip and immutable Decimal results. PostgreSQL variants use
the existing integration fixture. Test/coverage results are in PHASE_6_COMPLETION_REPORT.md.

No real provider or empirical economic validation is introduced. No returns, fills, costs, liquidity,
drawdown or ruin probabilities are inferred from structural agreement. Code coverage is not financial
validation. Existing live-execution prohibition and credential boundaries remain intact. Debt includes
real data, corporate actions, calendars, durable datasets, streaming, empirical validation and UI/API
consumption. Next roadmap phase: 7, regime engine; not implemented here.
