# Technical intelligence — Phase 3

## Boundary and use

The Python application service TechnicalIntelligence is the shared historical feature engine.
It accepts a MarketReplay instance, CandleQuery, explicit FreshnessPolicy and 1..32 unique
IndicatorSpec values (defaults: all 15 implemented kinds). It calls replay(), never inspect(),
and propagates DataRejected and infrastructure failures without substitute values. The complete
query must be valid before any result is returned. An explicitly empty closed-session query returns
an empty tuple; an empty continuous query is a quality failure. No new HTTP endpoint or frontend
calculation is added. There are no indicators at application startup without legitimate stored data.

Example inside an existing read transaction, with repository/query/clock supplied by the caller:

    from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
    from pocket_alpha.intelligence.technical.service import TechnicalIntelligence
    from pocket_alpha.market_data.quality import FreshnessPolicy
    from pocket_alpha.market_data.replay import MarketReplay

    engine = TechnicalIntelligence(MarketReplay(repository, clock))
    snapshots = engine.analyze(
        query,
        FreshnessPolicy(max_age=None),  # explicit historical use, NOT live freshness
        (IndicatorSpec(kind=IndicatorKind.SMA, period=20),),
    )

The private numerical kernels are not a data-quality boundary; consumers use the service.
They produce features, not votes, trend classifications, probabilities, recommendations or orders.
No dependency points toward strategies, forecasts, risk, execution or brokers.

## Time, reproducibility and identity

Replay events are validated before ordering by bar open time for calculation. Every output at index
i uses only bars 0..i. Its available_at is max(received_at[0..i]), not the candle opening or closing
time. A late earlier observation conservatively delays all dependent snapshots until it arrives.
Outputs are returned in bar order; equal availability ties therefore have deterministic bar order.
Consumers doing temporal research must gate by available_at, never by bar_open or bar_close.
Appending/changing future bars cannot change an already computed prefix. An invalid larger query
fails as a whole; it does not invalidate a separately retained earlier valid snapshot.

available_at is a reconstructed earliest permissible historical availability, not a claim that a
calculation actually ran then. Imports received today do not acquire invented historical availability.
There is no streaming subscription, incremental state store, snapshot database or actual emission
timestamp. Snapshots are frozen, contain immutable tuples, serialize Decimal as strings, and retain
market, timeframe, source, explicit freshness policy, input start/count, bar times, engine version,
numeric policy, every parameter and indicator version. Query start matters for recursive seeds.

Each input_hash is a SHA-256 prefix digest initialized with pocket-alpha-candle-prefix-v1 and updated
with each canonical candle JSON plus a newline. JSON keys are sorted, separators compact, timestamps
UTC ISO strings, and equivalent Decimal scales normalize identically. It includes receipt time and
source. It hashes actual inputs, not future rows or parameter choices; results separately retain the
full specification. This fingerprint is not a durable dataset registry or a security signature.

Arithmetic uses a fresh Decimal context: precision 50, ROUND_HALF_EVEN, standard exponent limits
and traps. Ambient caller precision/rounding does not change service results. Derived irrational
values are rounded by this explicit policy; no claim of infinite precision is made. Monetary input
values keep the domain's existing 38-digit constraints. No NumPy/Polars or new dependency is needed
for this bounded scalar implementation. Query limit remains 10,000 observations, periods 2..500.
Runtime is generally O(specifications * bars * period), memory O(specifications * bars).

## Version 1 conventions

All kinds use version 1.0.0. period defaults to 14; these are reproducible engineering defaults,
not tuned recommendations. MACD instead uses fast_period=12, slow_period=26, signal_period=9,
with fast < slow. Bollinger deviations defaults to 2 (positive, at most 10). Irrelevant non-default
parameters, unsupported versions/kinds, extra fields, duplicate requests and invalid periods fail.

Every named value has READY, WARMUP/INSUFFICIENT_HISTORY, or UNDEFINED/ZERO_DENOMINATOR status.
Unavailable values are null, never zero or NaN. Windows count observed scheduled bars, not elapsed
wall-clock hours; no calendar, annualization, adjustment or resampling is inferred.

| Family / kind | Version 1 calculation and first available sample |
| --- | --- |
| Trend / SMA | Mean of n closes; sample n. |
| Trend / EMA | SMA seed at n; then previous + 2/(n+1) * (close - previous). |
| Trend / WMA | Trailing close weights 1..n, newest highest; sample n. |
| Trend / MACD | Fast EMA minus slow EMA; signal EMA seeded from first signal_period valid MACD values; histogram difference. First signal: slow + signal - 1. |
| Trend / LINEAR_TREND | OLS close slope against bar indices 0..n-1; price units per observed bar; sample n. |
| Momentum / RSI | n close changes, separately SMA-seeded Wilder gains/losses, alpha 1/n. 100*g/(g+l); sample n+1. Flat both-zero is undefined; gain-only 100, loss-only 0. |
| Momentum / STOCHASTIC | Raw %K = 100*(close-low_n)/(high_n-low_n); Williams %R = %K-100; sample n. No %D smoothing claimed. |
| Momentum / ROC | 100*(close/close_n_bars_ago-1) and absolute momentum difference; sample n+1. |
| Momentum / CCI | Typical price (H+L+C)/3, trailing mean and mean absolute deviation, constant 0.015; sample n. Flat deviation undefined. |
| Volatility / ATR | True range from bar 2 includes previous close; first n true ranges seed SMA, then Wilder alpha 1/n; sample n+1. First bar is not given an invented previous close. |
| Volatility / BOLLINGER | SMA plus/minus deviations * population standard deviation (ddof=0), bandwidth (upper-lower)/middle; sample n. No sample-deviation convention. |
| Volatility / REALIZED_VOLATILITY | Root mean squared log return over n changes; sample n+1. Uncentered, per-bar, NOT annualized, not a forecast or sample standard deviation. |
| Volume / VOLUME | Raw volume; OBV starts at zero and uses signed subsequent volume; accumulation/distribution starts with first money-flow contribution, zero-range contributes zero. Relative volume compares current volume to mean of PREVIOUS n bars; sample n+1, zero baseline undefined. |
| Volume / VWAP | Trailing n-bar typical-price volume weighting; sample n, total zero volume undefined. Explicitly rolling OHLCV approximation, NOT trade/session VWAP. |
| Price action / PRICE_ACTION | Simple/log returns and opening gap versus previous close (sample 2); signed body, range, upper/lower wicks (sample 1); close distance as fraction of trailing n highs/lows (sample n). |

Conventional formula references checked during implementation:
[EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema),
[RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI),
[ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr),
[Bollinger Bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands).
The precise initialization, undefined cases and availability contracts above are this engine's
versioned choices, not an assertion of bitwise compatibility with every charting vendor.

## Extension and remaining scope

Add a typed IndicatorKind, validated parameters, causal kernel and documented feature names/units.
Tests enumerate every kind, so each addition automatically exercises empty, flat, zero-volume,
extreme-price and prefix-invariance cases; add independent numerical and warm-up references too.
A semantic change requires a new explicit version, not silently changing stored version 1 meaning.
Only version 1 is dispatched today; retain historical dispatch when introducing further versions.

This is the initial five-family implementation, not every indicator in the master vision. ADX,
Supertrend, Ichimoku, Keltner, Parkinson/Garman-Klass, additional anatomy/acceleration/breakout
features and benchmark relative strength remain catalogue extensions. True session VWAP, volume
profile and aggressor volume delta require suitable trade/session/benchmark inputs; they are not
fabricated from candle volume. No claim of predictive usefulness, net returns or economic fitness
is made. No strategy, costs, fills or holding period exists to measure those yet.

Session calendars, real provider integration, corporate-action/price-adjustment semantics, durable
dataset/snapshot registry, streaming performance and UI overlays remain explicit debt. The next
roadmap phase is market structure; it is not implemented here.
