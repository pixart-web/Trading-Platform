"""Synthetic, hand-checkable numerical regression fixtures; no market performance claims."""

from decimal import Context, Decimal, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.domain.market import Candle
from pocket_alpha.intelligence.technical.indicators import calculate
from pocket_alpha.intelligence.technical.models import (
    FeatureStatus,
    FeatureValue,
    IndicatorKind,
    IndicatorSpec,
)
from tests.market_fixtures import sample

D = Decimal


def bars(count: int = 8, *, flat: bool = False, zero_volume: bool = False) -> tuple[Candle, ...]:
    return tuple(
        sample(
            i,
            open=str(10 if flat else 10 + i),
            close=str(10 if flat else 10 + i),
            high=str(10 if flat else 11 + i),
            low=str(10 if flat else 9 + i),
            volume="0" if zero_volume else str(i + 1),
        )
        for i in range(count)
    )


def spec_for(kind: IndicatorKind) -> IndicatorSpec:
    if kind == IndicatorKind.MACD:
        return IndicatorSpec(kind=kind, fast_period=2, slow_period=3, signal_period=2)
    return IndicatorSpec(kind=kind, period=3)


def last(kind: IndicatorKind, data: tuple[Candle, ...] | None = None) -> dict[str, Decimal | None]:
    with localcontext(Context(prec=50)):
        result = calculate(bars() if data is None else data, spec_for(kind))
    return {f.name: f.value for f in result[-1]}


@pytest.mark.parametrize(
    "kind,name,expected",
    [
        (IndicatorKind.SMA, "sma", "16"),
        (IndicatorKind.EMA, "ema", "16"),
        (IndicatorKind.WMA, "wma", "16.333333333333333333333333333333333333333333333333"),
        (IndicatorKind.MACD, "macd", "0.5"),
        (IndicatorKind.MACD, "signal", "0.5"),
        (IndicatorKind.MACD, "histogram", "0"),
        (IndicatorKind.RSI, "rsi", "100"),
        (IndicatorKind.STOCHASTIC, "percent_k", "75"),
        (IndicatorKind.STOCHASTIC, "williams_r", "-25"),
        (IndicatorKind.ROC, "momentum", "3"),
        (IndicatorKind.CCI, "cci", "100"),
        (IndicatorKind.ATR, "atr", "2"),
        (IndicatorKind.BOLLINGER, "middle", "16"),
        (IndicatorKind.VOLUME, "raw_volume", "8"),
        (IndicatorKind.VOLUME, "obv", "35"),
        (IndicatorKind.VOLUME, "accumulation_distribution", "0"),
        (IndicatorKind.LINEAR_TREND, "slope_per_bar", "1"),
        (IndicatorKind.PRICE_ACTION, "body", "0"),
        (IndicatorKind.PRICE_ACTION, "range", "2"),
        (IndicatorKind.PRICE_ACTION, "upper_wick", "1"),
        (IndicatorKind.PRICE_ACTION, "lower_wick", "1"),
    ],
)
def test_hand_calculated_reference(kind: IndicatorKind, name: str, expected: str) -> None:
    assert last(kind)[name] == D(expected)


def test_reference_ratios_bands_and_volatility() -> None:
    with localcontext(Context(prec=50)):
        assert last(IndicatorKind.ROC)["roc_percent"] == 100 * (D(17) / 14 - 1)
        assert last(IndicatorKind.VWAP)["rolling_typical_vwap"] == D(338) / 21
        assert last(IndicatorKind.VOLUME)["relative_volume"] == D(8) / 6
        band = last(IndicatorKind.BOLLINGER)
        deviation = (D(2) / 3).sqrt()
        assert band["upper"] == 16 + 2 * deviation
        assert band["lower"] == 16 - 2 * deviation
        assert band["bandwidth"] == 4 * deviation / 16
        expected = sum(((D(j) / (j - 1)).ln() ** 2 for j in (15, 16, 17)), D(0)) / 3
        assert last(IndicatorKind.REALIZED_VOLATILITY)["rms_log_return"] == expected.sqrt()
        action = last(IndicatorKind.PRICE_ACTION)
        assert action["return"] == D(17) / 16 - 1
        assert action["log_return"] == (D(17) / 16).ln()
        assert action["gap_return"] == D(17) / 16 - 1
        assert action["distance_from_high"] == D(17) / 18 - 1
        assert action["distance_from_low"] == D(17) / 14 - 1


@pytest.mark.parametrize("kind", list(IndicatorKind))
def test_every_prefix_is_invariant_to_future_bars(kind: IndicatorKind) -> None:
    data = bars(12)
    spec = spec_for(kind)
    with localcontext(Context(prec=50)):
        full = calculate(data, spec)
        for length in range(1, len(data) + 1):
            assert calculate(data[:length], spec) == full[:length]
        changed = (*data[:6], *(sample(i, high="999", close="998") for i in range(6, 12)))
        assert calculate(changed, spec)[:6] == full[:6]


@pytest.mark.parametrize("kind", list(IndicatorKind))
def test_empty_input_and_finite_results(kind: IndicatorKind) -> None:
    assert calculate((), spec_for(kind)) == []
    for data in (bars(), bars(flat=True), bars(zero_volume=True)):
        for row in calculate(data, spec_for(kind)):
            assert all(f.value is None or f.value.is_finite() for f in row)


@pytest.mark.parametrize(
    "kind,name,first_ready",
    [
        (IndicatorKind.SMA, "sma", 2),
        (IndicatorKind.EMA, "ema", 2),
        (IndicatorKind.WMA, "wma", 2),
        (IndicatorKind.MACD, "signal", 3),
        (IndicatorKind.RSI, "rsi", 3),
        (IndicatorKind.ATR, "atr", 3),
        (IndicatorKind.ROC, "momentum", 3),
        (IndicatorKind.STOCHASTIC, "percent_k", 2),
        (IndicatorKind.CCI, "cci", 2),
        (IndicatorKind.BOLLINGER, "middle", 2),
        (IndicatorKind.REALIZED_VOLATILITY, "rms_log_return", 3),
        (IndicatorKind.VWAP, "rolling_typical_vwap", 2),
        (IndicatorKind.VOLUME, "relative_volume", 3),
        (IndicatorKind.PRICE_ACTION, "return", 1),
        (IndicatorKind.LINEAR_TREND, "slope_per_bar", 2),
    ],
)
def test_exact_warmup(kind: IndicatorKind, name: str, first_ready: int) -> None:
    values = [next(f for f in row if f.name == name) for row in calculate(bars(), spec_for(kind))]
    assert all(f.status == FeatureStatus.WARMUP and f.value is None for f in values[:first_ready])
    assert values[first_ready].status == FeatureStatus.READY


def test_flat_and_zero_volume_are_explicit() -> None:
    for kind in (
        IndicatorKind.RSI,
        IndicatorKind.STOCHASTIC,
        IndicatorKind.CCI,
        IndicatorKind.VWAP,
    ):
        result = calculate(bars(flat=True, zero_volume=True), spec_for(kind))[-1]
        assert all(
            f.status == FeatureStatus.UNDEFINED and f.reason == "ZERO_DENOMINATOR" for f in result
        )
    assert last(IndicatorKind.ATR, bars(flat=True))["atr"] == 0
    assert last(IndicatorKind.REALIZED_VOLATILITY, bars(flat=True))["rms_log_return"] == 0
    assert last(IndicatorKind.VOLUME, bars(zero_volume=True))["relative_volume"] is None


def test_downward_rsi_obv_and_gap_atr() -> None:
    data = tuple(
        sample(
            i, open=str(20 - i), close=str(20 - i), high=str(21 - i), low=str(19 - i), volume="2"
        )
        for i in range(8)
    )
    assert last(IndicatorKind.RSI, data)["rsi"] == 0
    assert last(IndicatorKind.VOLUME, data)["obv"] == -14
    gap = (
        sample(0, open="10", high="10", low="10", close="10"),
        sample(1, open="20", high="21", low="19", close="20"),
        sample(2, open="20", high="21", low="19", close="20"),
    )
    result = calculate(gap, IndicatorSpec(kind=IndicatorKind.ATR, period=2))
    assert result[-1][0].value == D("6.5")


@pytest.mark.parametrize(
    "change",
    [
        {"period": 0},
        {"period": 501},
        {"period": True},
        {"period": "14"},
        {"version": "2.0.0"},
        {"kind": "UNKNOWN"},
        {"deviations": "NaN"},
        {"deviations": "3"},
        {"fast_period": 3},
        {"extra": 1},
        {"kind": "MACD", "fast_period": 26},
        {"kind": "MACD", "period": 3},
    ],
)
def test_bad_parameters_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        IndicatorSpec.model_validate({"kind": "SMA", **change})


def test_feature_contract_rejects_nan_and_false_ready() -> None:
    for value, status, reason in [
        ("NaN", "READY", None),
        (None, "READY", None),
        ("1", "WARMUP", "INSUFFICIENT_HISTORY"),
        (None, "UNDEFINED", "INSUFFICIENT_HISTORY"),
    ]:
        with pytest.raises(ValidationError):
            FeatureValue.model_validate(
                dict(name="test", value=value, status=status, reason=reason)
            )


def test_nonlinear_smoothing_reference() -> None:
    # Independent recurrence: EMA(3) seed 12; alpha 1/2 => 10, 13.
    data = tuple(
        sample(i, open=str(p), high=str(p), low=str(p), close=str(p))
        for i, p in enumerate((10, 12, 14, 8, 16))
    )
    assert last(IndicatorKind.EMA, data)["ema"] == 13
    # Wilder RSI(3): initial gains 4/3, losses 2; next gains 32/9, losses 4/3.
    with localcontext(Context(prec=50)):
        expected = 100 * (D(32) / 9) / (D(44) / 9)
        actual = last(IndicatorKind.RSI, data)["rsi"]
        assert actual is not None and abs(actual - expected) < D("1e-45")
    # Wilder ATR(3): TR 2,2,6 gives 10/3; next TR 8 gives 44/9.
    with localcontext(Context(prec=50)):
        actual = last(IndicatorKind.ATR, data)["atr"]
        assert actual is not None and abs(actual - D(44) / 9) < D("1e-45")


def test_nonzero_accumulation_and_unchanged_close_obv() -> None:
    data = (
        sample(0, open="10", close="12", high="12", low="8", volume="5"),
        sample(1, open="12", close="12", high="14", low="12", volume="3"),
    )
    values = last(IndicatorKind.VOLUME, data)
    assert values["obv"] == 0
    assert values["accumulation_distribution"] == 2


@pytest.mark.parametrize("kind", list(IndicatorKind))
def test_extreme_supported_prices_stay_finite(kind: IndicatorKind) -> None:
    points = ("0.000000000000000001", "99999999999999999999", "1", "100")
    data = tuple(
        sample(i, open=p, close=p, high=p, low=p, volume="0") for i, p in enumerate(points)
    )
    with localcontext(Context(prec=50)):
        for row in calculate(data, spec_for(kind)):
            assert all(f.value is None or f.value.is_finite() for f in row)
