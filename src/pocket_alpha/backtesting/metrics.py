"""Descriptive simulated economics, with explicit unavailable ratio/tail estimates."""

from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.backtesting.models import EquityPoint, Metric, RoundTrip, RunConfig, SimulatedFill

D = Decimal


def seconds(value: timedelta) -> Decimal:
    return D(value.days * 86400 + value.seconds) + D(value.microseconds) / 1000000


def _calculate_metrics(
    points: tuple[EquityPoint, ...],
    fills: tuple[SimulatedFill, ...],
    trades: tuple[RoundTrip, ...],
    config: RunConfig,
) -> tuple[Metric, ...]:
    metrics: list[Metric] = []

    def add(name: str, value: Decimal | None, reason: str = "UNAVAILABLE") -> None:
        metrics.append(Metric(name=name, value=value, reason=reason if value is None else None))

    elapsed = seconds(points[-1].at - points[0].at)
    final = points[-1].equity
    net = final / config.initial_cash - 1
    maximum_dd = max(p.drawdown for p in points)
    add("net_return", net)
    add("maximum_drawdown", maximum_dd)
    add("elapsed_seconds", elapsed)
    annual = D(config.annualization_seconds)
    cagr = (
        ((final / config.initial_cash).ln() * annual / elapsed).exp() - 1
        if elapsed >= annual and final > 0
        else None
    )
    add("CAGR", cagr, "LESS_THAN_ONE_YEAR_OR_BANKRUPTCY")
    add(
        "Calmar",
        cagr / maximum_dd if cagr is not None and maximum_dd else None,
        "CAGR_UNAVAILABLE_OR_ZERO_DRAWDOWN",
    )
    durations = [seconds(b.at - a.at) for a, b in zip(points[:-1], points[1:], strict=True)]
    returns = [
        b.equity / a.equity - 1
        for a, b in zip(points[:-1], points[1:], strict=True)
        if a.equity > 0
    ]
    reason = "INSUFFICIENT_RETURN_OBSERVATIONS"
    supported = len(returns) >= config.minimum_ratio_returns and len(returns) == len(durations)
    if supported and (not durations or durations[0] <= 0 or len(set(durations)) != 1):
        supported, reason = False, "IRREGULAR_KNOWLEDGE_INTERVALS"
    if supported:
        count = D(len(returns))
        mean = sum(returns, D(0)) / count
        std = (sum(((r - mean) ** 2 for r in returns), D(0)) / (count - 1)).sqrt()
        periods = annual / durations[0]
        risk_free = ((1 + config.annual_risk_free_rate).ln() / periods).exp() - 1
        excess = [r - risk_free for r in returns]
        excess_mean = sum(excess, D(0)) / count
        downside = (sum((min(D(0), r) ** 2 for r in excess), D(0)) / count).sqrt()
        add("annualized_volatility", std * periods.sqrt())
        add("Sharpe", excess_mean / std * periods.sqrt() if std else None, "ZERO_RETURN_VARIANCE")
        add(
            "Sortino",
            excess_mean / downside * periods.sqrt() if downside else None,
            "NO_DOWNSIDE_RETURNS",
        )
    else:
        for name in ("annualized_volatility", "Sharpe", "Sortino"):
            add(name, None, reason)
    gains = sum((t.net_pnl for t in trades if t.net_pnl > 0), D(0))
    losses = -sum((t.net_pnl for t in trades if t.net_pnl < 0), D(0))
    add("profit_factor", gains / losses if losses else None, "NO_LOSING_COMPLETED_ROUND_TRIPS")
    add(
        "net_expectancy_per_round_trip",
        sum((t.net_pnl for t in trades), D(0)) / len(trades) if trades else None,
        "NO_COMPLETED_ROUND_TRIPS",
    )
    add("completed_round_trips", D(len(trades)))
    add("winning_round_trips", D(sum(t.net_pnl > 0 for t in trades)))
    add("losing_round_trips", D(sum(t.net_pnl < 0 for t in trades)))
    add("breakeven_round_trips", D(sum(t.net_pnl == 0 for t in trades)))
    add(
        "round_trip_win_fraction",
        D(sum(t.net_pnl > 0 for t in trades)) / len(trades) if trades else None,
        "NO_COMPLETED_ROUND_TRIPS",
    )
    add(
        "realized_net_pnl", sum((f.realized_pnl for f in fills if f.realized_pnl is not None), D(0))
    )
    add(
        "one_way_turnover_initial_capital",
        sum((f.price * f.quantity for f in fills), D(0)) / config.initial_cash,
    )
    for name, values in (
        ("fees", (f.fee for f in fills)),
        ("spread_cost", (f.spread_cost for f in fills)),
        ("slippage_cost", (f.slippage_cost for f in fills)),
        ("impact_cost", (f.impact_cost for f in fills)),
    ):
        add(name, sum(values, D(0)))
    add(
        "total_modeled_cost",
        sum((f.fee + f.spread_cost + f.slippage_cost + f.impact_cost for f in fills), D(0)),
    )
    exposure = invested = D(0)
    for p, duration in zip(points[:-1], durations, strict=True):
        exposure += (p.quantity * p.mark / p.equity if p.equity else D(0)) * duration
        invested += D(p.quantity > 0) * duration
    add(
        "time_weighted_exposure", exposure / elapsed if elapsed else None, "ZERO_KNOWLEDGE_DURATION"
    )
    add(
        "time_in_market_fraction",
        invested / elapsed if elapsed else None,
        "ZERO_KNOWLEDGE_DURATION",
    )
    peak_at = points[0].at
    longest = D(0)
    underwater = False
    previous_high_water = D(0)
    for p in points:
        if p.high_water > previous_high_water or p.drawdown == 0:
            if underwater:
                longest = max(longest, seconds(p.at - peak_at))
            peak_at, underwater = p.at, False
        if p.drawdown > 0:
            underwater = True
            longest = max(longest, seconds(p.at - peak_at))
        previous_high_water = p.high_water
    add("maximum_drawdown_duration_seconds", longest)
    add(
        "bankruptcy_events",
        D(
            sum(
                p.equity == 0 and (i == 0 or points[i - 1].equity > 0) for i, p in enumerate(points)
            )
        ),
    )
    add(
        "drawdown_limit_breach_events",
        D(
            sum(
                p.drawdown >= config.risk.maximum_drawdown
                and (i == 0 or points[i - 1].drawdown < config.risk.maximum_drawdown)
                for i, p in enumerate(points)
            )
        ),
    )
    add("risk_of_ruin_probability", None, "NO_VALIDATED_RUIN_MODEL")
    tail_min = int((D(1) / config.tail_fraction).to_integral_value(rounding=ROUND_CEILING))
    if (
        supported
        and len(returns) >= max(tail_min, config.minimum_ratio_returns)
        and len(returns) == len(durations)
    ):
        tail_count = max(
            1,
            int((D(len(returns)) * config.tail_fraction).to_integral_value(rounding=ROUND_CEILING)),
        )
        tail = sorted(returns)[:tail_count]
        add("historical_VaR_return_loss", max(D(0), -tail[-1]))
        add("historical_expected_shortfall_return_loss", max(D(0), -sum(tail, D(0)) / tail_count))
    else:
        add("historical_VaR_return_loss", None, "INSUFFICIENT_TAIL_OBSERVATIONS")
        add("historical_expected_shortfall_return_loss", None, "INSUFFICIENT_TAIL_OBSERVATIONS")
    return tuple(metrics)


def calculate_metrics(
    points: tuple[EquityPoint, ...],
    fills: tuple[SimulatedFill, ...],
    trades: tuple[RoundTrip, ...],
    config: RunConfig,
) -> tuple[Metric, ...]:
    if not points:
        raise ValueError("metrics require a nonempty equity path")
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return _calculate_metrics(points, fills, trades, config)
