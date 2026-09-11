"""Internal kernels. All windows end at the current bar; no centered/shifted output.

Call through TechnicalIntelligence, which enforces trusted replay and numeric policy.
"""

from collections.abc import Sequence
from decimal import Decimal

from pocket_alpha.domain.market import Candle
from pocket_alpha.intelligence.technical.models import (
    FeatureStatus,
    FeatureValue,
    IndicatorKind,
    IndicatorSpec,
)

D = Decimal
Series = list[Decimal | None]


def mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, D(0)) / len(values)


def smooth(values: Sequence[Decimal], period: int, *, wilder: bool = False) -> Series:
    result: Series = [None] * len(values)
    if len(values) >= period:
        current = mean(values[:period])
        result[period - 1] = current
        alpha = D(1) / period if wilder else D(2) / (period + 1)
        for i in range(period, len(values)):
            current += alpha * (values[i] - current)
            result[i] = current
    return result


def feature(name: str, value: Decimal | None, *, undefined: bool = False) -> FeatureValue:
    if value is not None:
        return FeatureValue(name=name, value=value, status=FeatureStatus.READY)
    return FeatureValue(
        name=name,
        value=None,
        status=FeatureStatus.UNDEFINED if undefined else FeatureStatus.WARMUP,
        reason="ZERO_DENOMINATOR" if undefined else "INSUFFICIENT_HISTORY",
    )


def calculate(candles: Sequence[Candle], spec: IndicatorSpec) -> list[tuple[FeatureValue, ...]]:
    """Bounded causal series, with explicit warm-up and undefined denominators."""
    close = [c.close for c in candles]
    volume = [c.volume for c in candles]
    typical = [(c.high + c.low + c.close) / 3 for c in candles]
    n, kind = spec.period, spec.kind
    output: list[tuple[FeatureValue, ...]] = []
    ema = smooth(close, n) if kind == IndicatorKind.EMA else []
    tr = [
        max(c.high - c.low, abs(c.high - close[i - 1]), abs(c.low - close[i - 1]))
        for i, c in enumerate(candles)
        if i > 0
    ]
    atr = [None, *smooth(tr, n, wilder=True)]
    changes = [close[i] - close[i - 1] for i in range(1, len(close))]
    gains = smooth([max(x, D(0)) for x in changes], n, wilder=True)
    losses = smooth([max(-x, D(0)) for x in changes], n, wilder=True)
    macd: Series = []
    signal: Series = []
    if kind == IndicatorKind.MACD:
        fast, slow = smooth(close, spec.fast_period), smooth(close, spec.slow_period)
        macd = [
            a - b if a is not None and b is not None else None
            for a, b in zip(fast, slow, strict=True)
        ]
        signal = [None] * (spec.slow_period - 1)
        signal.extend(smooth([x for x in macd if x is not None], spec.signal_period))
    log_returns = (
        [(close[j] / close[j - 1]).ln() for j in range(1, len(close))]
        if kind == IndicatorKind.REALIZED_VOLATILITY
        else []
    )
    obv, accumulation = D(0), D(0)
    for i, candle in enumerate(candles):
        window = candles[max(0, i - n + 1) : i + 1]
        prices = close[max(0, i - n + 1) : i + 1]
        ready = i + 1 >= n
        values: tuple[FeatureValue, ...]
        if kind == IndicatorKind.SMA:
            values = (feature("sma", mean(prices) if ready else None),)
        elif kind == IndicatorKind.EMA:
            values = (feature("ema", ema[i]),)
        elif kind == IndicatorKind.WMA:
            value = sum((D(j + 1) * p for j, p in enumerate(prices)), D(0)) / (n * (n + 1) / D(2))
            values = (feature("wma", value if ready else None),)
        elif kind == IndicatorKind.MACD:
            m, s = macd[i], signal[i]
            values = (
                feature("macd", m),
                feature("signal", s),
                feature("histogram", m - s if m is not None and s is not None else None),
            )
        elif kind == IndicatorKind.RSI:
            gain = gains[i - 1] if i > 0 else None
            loss = losses[i - 1] if i > 0 else None
            denominator = gain + loss if gain is not None and loss is not None else None
            values = (
                feature(
                    "rsi",
                    100 * gain / denominator if gain is not None and denominator else None,
                    undefined=denominator == 0,
                ),
            )
        elif kind == IndicatorKind.STOCHASTIC:
            high, low = max(c.high for c in window), min(c.low for c in window)
            k = 100 * (candle.close - low) / (high - low) if ready and high != low else None
            values = (
                feature("percent_k", k, undefined=ready and high == low),
                feature(
                    "williams_r",
                    k - 100 if k is not None else None,
                    undefined=ready and high == low,
                ),
            )
        elif kind == IndicatorKind.ROC:
            values = (
                feature("roc_percent", 100 * (candle.close / close[i - n] - 1) if i >= n else None),
                feature("momentum", candle.close - close[i - n] if i >= n else None),
            )
        elif kind == IndicatorKind.CCI:
            tp = typical[max(0, i - n + 1) : i + 1]
            average = mean(tp)
            deviation = mean([abs(p - average) for p in tp])
            values = (
                feature(
                    "cci",
                    (typical[i] - average) / (D("0.015") * deviation)
                    if ready and deviation
                    else None,
                    undefined=ready and deviation == 0,
                ),
            )
        elif kind == IndicatorKind.ATR:
            values = (feature("atr", atr[i]),)
        elif kind == IndicatorKind.BOLLINGER:
            middle = mean(prices)
            std = mean([(p - middle) ** 2 for p in prices]).sqrt()
            spread = spec.deviations * std
            values = tuple(
                feature(name, value if ready else None)
                for name, value in (
                    ("middle", middle),
                    ("upper", middle + spread),
                    ("lower", middle - spread),
                    ("bandwidth", 2 * spread / middle),
                )
            )
        elif kind == IndicatorKind.REALIZED_VOLATILITY:
            returns = log_returns[max(0, i - n) : i]
            volatility = mean([r * r for r in returns]).sqrt() if i >= n else None
            values = (feature("rms_log_return", volatility),)
        elif kind == IndicatorKind.VWAP:
            total = sum((c.volume for c in window), D(0))
            weighted = sum(((c.high + c.low + c.close) / 3 * c.volume for c in window), D(0))
            values = (
                feature(
                    "rolling_typical_vwap",
                    weighted / total if ready and total else None,
                    undefined=ready and total == 0,
                ),
            )
        elif kind == IndicatorKind.VOLUME:
            if i:
                obv += candle.volume * (
                    (candle.close > close[i - 1]) - (candle.close < close[i - 1])
                )
            width = candle.high - candle.low
            # A zero-range candle has neutral money-flow contribution, not an invented price.
            if width:
                accumulation += (
                    (2 * candle.close - candle.high - candle.low) / width * candle.volume
                )
            baseline = mean(volume[i - n : i]) if i >= n else None
            values = (
                feature("raw_volume", candle.volume),
                feature("obv", obv),
                feature("accumulation_distribution", accumulation),
                feature(
                    "relative_volume",
                    candle.volume / baseline if baseline else None,
                    undefined=baseline == 0,
                ),
            )
        elif kind == IndicatorKind.LINEAR_TREND:
            xmean = D(n - 1) / 2
            price_mean = mean(prices)
            slope = (
                sum(((D(j) - xmean) * (p - price_mean) for j, p in enumerate(prices)), D(0))
                / sum(((D(j) - xmean) ** 2 for j in range(n)), D(0))
                if ready
                else None
            )
            values = (feature("slope_per_bar", slope),)
        else:
            assert kind == IndicatorKind.PRICE_ACTION
            previous = close[i - 1] if i else None
            high, low = max(c.high for c in window), min(c.low for c in window)
            values = (
                feature("return", candle.close / previous - 1 if previous else None),
                feature("log_return", (candle.close / previous).ln() if previous else None),
                feature("gap_return", candle.open / previous - 1 if previous else None),
                feature("range", candle.high - candle.low),
                feature("body", candle.close - candle.open),
                feature("upper_wick", candle.high - max(candle.open, candle.close)),
                feature("lower_wick", min(candle.open, candle.close) - candle.low),
                feature("distance_from_high", candle.close / high - 1 if ready else None),
                feature("distance_from_low", candle.close / low - 1 if ready else None),
            )
        output.append(values)
    return output
