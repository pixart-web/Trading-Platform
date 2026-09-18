"""Explicit synthetic strategy fixtures, never economic/model evidence."""

from decimal import Decimal as D
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.backtesting.models import PortfolioState, RunConfig, StrategyView
from pocket_alpha.domain.models import ForecastHorizon
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import _calculate
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.strategies.models import AllocationPolicy, StrategyDefinition, TrendParameters
from tests.backtest_fixtures import config, dataset
from tests.test_forecasts import forecast


def definition() -> StrategyDefinition:
    data = dataset().inputs
    return StrategyDefinition(
        version="synthetic-sma-trend-1",
        model_version="synthetic-model-1",
        market_id=data.market.market_id,
        asset_id=data.asset.asset_id,
        source=data.mapping.source,
        timeframe=data.query.timeframe,
        horizon=ForecastHorizon.H4,
        parameters=TrendParameters(
            fast_period=2,
            slow_period=3,
            minimum_trend_fraction=D("0.001"),
            minimum_expected_return=D("0.001"),
            invalidation_fraction=D("0.1"),
        ),
        allocation=AllocationPolicy(
            version="synthetic-allocation-1",
            target_exposure_fraction=D("0.1"),
            cash_buffer_fraction=D("0.2"),
            maximum_proposal_notional=D(1000),
        ),
        maximum_data_age_seconds=60,
    )


def run_config() -> RunConfig:
    value = definition()
    return config(
        strategy=value.identity(),
        feature_specs=tuple(IndicatorSpec(kind=IndicatorKind.SMA, period=p) for p in (2, 3)),
    )


def evidence(at: object, expected: str = "0.04") -> Forecast:
    from datetime import datetime

    assert isinstance(at, datetime)
    value = definition()
    return forecast(
        forecast_id=uuid5(NAMESPACE_URL, "synthetic-strategy:" + at.isoformat() + expected),
        market_id=value.market_id,
        asset_id=value.asset_id,
        model_version=value.model_version,
        feature_version=value.feature_version,
        horizon=value.horizon,
        generated_at=at,
        expires_at=expires_at(at, value.horizon),
        expected_return=D(expected),
    )


def view(
    prices: tuple[str, ...] = ("100", "102", "104", "106"),
    quantity: str = "0",
    cash: str = "10000",
    reserved: str = "0",
    with_forecast: bool = True,
) -> StrategyView:
    data = dataset(prices).inputs
    features = _calculate(data.candles, data.query, FreshnessPolicy(), run_config().feature_specs)
    at = data.captured_at
    state = PortfolioState(
        cash=D(cash),
        quantity=D(quantity),
        cost_basis=D(quantity) * 100,
        reserved_cash=D(reserved),
        reserved_quantity=D(0),
        equity=D(cash) + D(quantity) * data.candles[-1].close,
    )
    return StrategyView(
        as_of=at,
        history=data.candles,
        technical=features[-1],
        forecasts=(evidence(at),) if with_forecast else (),
        portfolio=state,
    )
