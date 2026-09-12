from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.intelligence.regimes.models import (
    RegimeLabel,
    RegimeModel,
    RegimeObservation,
    RegimeSnapshot,
    RegimeSpec,
    TrendReason,
    VolatilityRegime,
)
from pocket_alpha.intelligence.regimes.probability import infer
from pocket_alpha.intelligence.technical.indicators import feature
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import _calculate as technical_calculate
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

D = Decimal
DEFAULT_SPEC = RegimeSpec()


def _calculate(
    candles: tuple[Candle, ...],
    query: CandleQuery,
    policy: FreshnessPolicy,
    spec: RegimeSpec,
) -> tuple[RegimeObservation, ...]:
    """Internal only: the public service enforces trusted replay before this kernel."""
    technical = technical_calculate(
        candles,
        query,
        policy,
        (
            IndicatorSpec(kind=IndicatorKind.REALIZED_VOLATILITY, period=spec.period),
            IndicatorSpec(kind=IndicatorKind.VOLUME, period=spec.period),
        ),
    )
    result: list[RegimeObservation] = []
    volatilities: list[Decimal] = []
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        changes = [candles[i].close - candles[i - 1].close for i in range(1, len(candles))]
        for i, context in enumerate(technical):
            efficiency = None
            trend = None
            trend_reason = TrendReason.WARMUP
            flat = False
            if i >= spec.period:
                path = sum((abs(change) for change in changes[i - spec.period : i]), D(0))
                flat = path == 0
                if flat:
                    trend, trend_reason = RegimeLabel.RANGE, TrendReason.FLAT_CLOSES
                else:
                    efficiency = (candles[i].close - candles[i - spec.period].close) / path
                    if abs(efficiency) >= spec.trend_efficiency:
                        trend = RegimeLabel.TREND_UP if efficiency > 0 else RegimeLabel.TREND_DOWN
                        trend_reason = TrendReason.EFFICIENT_MOVE
                    elif abs(efficiency) <= spec.range_efficiency:
                        trend, trend_reason = RegimeLabel.RANGE, TrendReason.LOW_EFFICIENCY
                    else:
                        trend, trend_reason = RegimeLabel.TRANSITION, TrendReason.MIXED_PATH
            vol = context.results[0].features[0].value
            volume = next(
                f.value for f in context.results[1].features if f.name == "relative_volume"
            )
            baseline = (
                sum(volatilities[-spec.baseline_period :], D(0)) / spec.baseline_period
                if len(volatilities) >= spec.baseline_period
                else None
            )
            ratio = vol / baseline if vol is not None and baseline else None
            volatility = None
            if ratio is not None:
                volatility = (
                    VolatilityRegime.LOW
                    if ratio <= spec.low_volatility_ratio
                    else VolatilityRegime.HIGH
                    if ratio >= spec.high_volatility_ratio
                    else VolatilityRegime.NORMAL
                )
            if vol is not None:
                volatilities.append(vol)  # Baseline excludes the current observation.
            vector = (
                (efficiency, vol, (1 + volume).ln())
                if efficiency is not None and vol is not None and volume is not None
                else None
            )
            result.append(
                RegimeObservation(
                    spec=spec,
                    technical=context,
                    signed_efficiency=feature("signed_efficiency", efficiency, undefined=flat),
                    volatility_ratio=feature("volatility_ratio", ratio, undefined=baseline == 0),
                    trend=trend,
                    trend_reason=trend_reason,
                    volatility=volatility,
                    vector=vector,
                )
            )
    return tuple(result)


class RegimeEngine:
    """Shared historical regimes; no model is fitted implicitly or shipped by default."""

    def __init__(self, replay: MarketReplay) -> None:
        self.replay = replay

    def analyze(
        self,
        query: CandleQuery,
        policy: FreshnessPolicy,
        spec: RegimeSpec = DEFAULT_SPEC,
        model: RegimeModel | None = None,
    ) -> tuple[RegimeSnapshot, ...]:
        events = self.replay.replay(query, policy)
        candles = tuple(sorted((event.candle for event in events), key=lambda c: c.open_time))
        observations = _calculate(candles, query, policy, spec)
        return tuple(
            RegimeSnapshot(observation=o, probability=infer(o, model)) for o in observations
        )
