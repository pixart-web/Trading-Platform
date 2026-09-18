from datetime import timedelta
from decimal import Decimal

from pocket_alpha.backtesting.metrics import calculate_metrics
from pocket_alpha.backtesting.models import EquityPoint, RoundTrip
from tests.backtest_fixtures import config
from tests.market_fixtures import START

D = Decimal


def path(values: tuple[str, ...], step: timedelta) -> tuple[EquityPoint, ...]:
    peak = D(10000)
    points = []
    for i, value in enumerate(values):
        equity = D(value)
        peak = max(peak, equity)
        points.append(
            EquityPoint(
                at=START + i * step,
                cash=equity,
                quantity=D(0),
                mark=D(100),
                equity=equity,
                high_water=peak,
                drawdown=(peak - equity) / peak,
            )
        )
    return tuple(points)


def test_known_drawdown_duration_cost_free_metric_path_is_not_execution() -> None:
    # Synthetic equity arithmetic only, not orders/fills or claimed profitable trading.
    points = path(("10000", "12000", "9000", "10000", "12000", "8000"), timedelta(days=100))
    trades = (
        RoundTrip(
            opened_at=START, closed_at=START + timedelta(days=1), quantity=D(1), net_pnl=D(100)
        ),
        RoundTrip(
            opened_at=START, closed_at=START + timedelta(days=2), quantity=D(1), net_pnl=D(-50)
        ),
    )
    metrics = {m.name: m for m in calculate_metrics(points, (), trades, config())}
    assert metrics["net_return"].value == D("-0.2")
    assert metrics["maximum_drawdown"].value == D(1) / 3
    assert metrics["maximum_drawdown_duration_seconds"].value == D(300 * 86400)
    assert metrics["profit_factor"].value == 2
    assert metrics["net_expectancy_per_round_trip"].value == 25
    assert metrics["round_trip_win_fraction"].value == D("0.5")
    assert metrics["CAGR"].value is not None and metrics["CAGR"].value < 0
    assert metrics["Sharpe"].value is not None and metrics["Sortino"].value is not None
    assert metrics["risk_of_ruin_probability"].value is None


def test_flat_irregular_zero_duration_and_bankruptcy_metrics_are_honest() -> None:
    points = path(("10000",) * 5, timedelta(hours=1))
    metrics = {m.name: m for m in calculate_metrics(points, (), (), config())}
    assert metrics["annualized_volatility"].value == 0
    assert metrics["Sharpe"].reason == "ZERO_RETURN_VARIANCE"
    assert metrics["Sortino"].reason == "NO_DOWNSIDE_RETURNS"
    irregular = points[:2] + tuple(
        p.model_copy(update={"at": p.at + timedelta(minutes=1)}) for p in points[2:]
    )
    metrics = {m.name: m for m in calculate_metrics(irregular, (), (), config())}
    assert metrics["Sharpe"].reason == "IRREGULAR_KNOWLEDGE_INTERVALS"
    metrics = {m.name: m for m in calculate_metrics(points[:1], (), (), config())}
    assert metrics["time_weighted_exposure"].reason == "ZERO_KNOWLEDGE_DURATION"
    metrics = {
        m.name: m
        for m in calculate_metrics(path(("10000", "0", "0"), timedelta(days=1)), (), (), config())
    }
    assert metrics["bankruptcy_events"].value == 1 and metrics["CAGR"].value is None


def test_empirical_tail_metrics_have_minimum_sample_and_loss_sign() -> None:
    values = tuple(str(10000 - i * 100) for i in range(25))
    metrics = {
        m.name: m for m in calculate_metrics(path(values, timedelta(hours=1)), (), (), config())
    }
    assert (
        metrics["historical_VaR_return_loss"].value is not None
        and metrics["historical_VaR_return_loss"].value > 0
    )
    assert metrics["historical_expected_shortfall_return_loss"].value is not None
