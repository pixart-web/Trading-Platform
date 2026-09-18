from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from random import Random

from pocket_alpha.backtesting.models import BacktestReport
from pocket_alpha.common.clock import FrozenClock, utc
from pocket_alpha.forecasts.models import (
    Forecast,
    ForecastDirection,
    ForecastOutcome,
    ForecastStatus,
)
from pocket_alpha.forecasts.service import validate_outcome
from pocket_alpha.research.models import AnalysisPolicy, Diagnostic

D = Decimal


def _item(name: str, value: Decimal | None, reason: str = "INSUFFICIENT_SAMPLE") -> Diagnostic:
    return Diagnostic(name=name, value=value, reason=reason if value is None else None)


def _path(returns: tuple[Decimal, ...]) -> tuple[Decimal, Decimal]:
    equity, peak, drawdown = D(1), D(1), D(0)
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    return equity - 1, drawdown


def resample(report: BacktestReport, policy: AnalysisPolicy) -> tuple[Diagnostic, ...]:
    report = BacktestReport.model_validate_json(report.model_dump_json())
    policy = AnalysisPolicy.model_validate_json(policy.model_dump_json())
    names = (
        "BLOCK_BOOTSTRAP_RETURN_LOWER",
        "BLOCK_BOOTSTRAP_RETURN_UPPER",
        "PERMUTATION_DRAWDOWN_LOWER",
        "PERMUTATION_DRAWDOWN_UPPER",
    )
    points = report.equity
    intervals = {b.at - a.at for a, b in zip(points, points[1:], strict=False)}
    if len(points) - 1 < max(policy.minimum_returns, policy.block_length) or len(intervals) != 1:
        return tuple(_item(n, None, "INSUFFICIENT_REGULAR_RETURNS") for n in names)
    if any(p.equity == 0 for p in points[:-1]):
        return tuple(_item(n, None, "ZERO_EQUITY_DENOMINATOR") for n in names)
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        returns = tuple(b.equity / a.equity - 1 for a, b in zip(points, points[1:], strict=False))
        rng = Random(policy.seed)
        boot, shuffled = [], []
        for _ in range(policy.simulations):
            sample: list[Decimal] = []
            while len(sample) < len(returns):
                start = rng.randrange(len(returns) - policy.block_length + 1)
                sample.extend(returns[start : start + policy.block_length])
            boot.append(_path(tuple(sample[: len(returns)]))[0])
            perm = list(returns)
            rng.shuffle(perm)
            shuffled.append(_path(tuple(perm))[1])
        boot.sort()
        shuffled.sort()
        low = int(policy.lower_quantile * D(policy.simulations - 1))
        high = int(policy.upper_quantile * D(policy.simulations - 1))
        return tuple(
            _item(n, v)
            for n, v in zip(
                names, (boot[low], boot[high], shuffled[low], shuffled[high]), strict=True
            )
        )


def drift(reference: tuple[Decimal, ...], observed: tuple[Decimal, ...]) -> tuple[Diagnostic, ...]:
    if (
        len(reference) > 10000
        or len(observed) > 10000
        or any(not x.is_finite() for x in (*reference, *observed))
    ):
        raise ValueError("drift samples must be bounded and finite")
    if min(len(reference), len(observed)) < 2:
        return (_item("MEAN_SHIFT", None), _item("STANDARDIZED_MEAN_SHIFT", None))
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        mean = sum(reference, D(0)) / len(reference)
        delta = sum(observed, D(0)) / len(observed) - mean
        std = (sum(((v - mean) ** 2 for v in reference), D(0)) / (len(reference) - 1)).sqrt()
        return (
            _item("MEAN_SHIFT", delta),
            _item(
                "STANDARDIZED_MEAN_SHIFT", delta / std if std else None, "ZERO_REFERENCE_VARIANCE"
            ),
        )


def calibration(
    pairs: tuple[tuple[Forecast, ForecastOutcome], ...], evaluated_at: object
) -> tuple[Diagnostic, ...]:
    from datetime import datetime

    if not isinstance(evaluated_at, datetime):
        raise ValueError("calibration cutoff must be a UTC datetime")
    cutoff = utc(evaluated_at)
    if not pairs:
        return (_item("BRIER_SCORE", None), _item("TOP_LABEL_CALIBRATION_GAP", None))
    if len(pairs) > 10000 or len({f.forecast_id for f, _ in pairs}) != len(pairs):
        raise ValueError("calibration pairs must be bounded and unique")
    brier, confidence, correct = D(0), D(0), D(0)
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        for raw_f, raw_o in pairs:
            f = Forecast.model_validate_json(raw_f.model_dump_json())
            o = ForecastOutcome.model_validate_json(raw_o.model_dump_json())
            if (
                f.status != ForecastStatus.AVAILABLE
                or o.forecast_id != f.forecast_id
                or (
                    max(o.recorded_at, o.observation_available_at) > cutoff
                    or o.end_price_at < f.expires_at
                )
            ):
                raise ValueError("calibration requires matching mature available outcomes")
            validate_outcome(f, o, FrozenClock(cutoff))
            assert f.range_threshold is not None and f.confidence is not None
            direction = (
                ForecastDirection.UP
                if o.actual_return > f.range_threshold
                else ForecastDirection.DOWN
                if o.actual_return < -f.range_threshold
                else ForecastDirection.RANGE
            )
            brier += sum(
                ((p.probability - D(p.direction == direction)) ** 2 for p in f.probabilities), D(0)
            )
            confidence += f.confidence
            correct += D(f.direction == direction)
        return (
            _item("BRIER_SCORE", brier / len(pairs)),
            _item("TOP_LABEL_CALIBRATION_GAP", abs(confidence - correct) / len(pairs)),
        )
