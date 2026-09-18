from datetime import timedelta
from decimal import Decimal

import pytest

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.research.diagnostics import calibration, drift, resample
from tests.backtest_fixtures import Plan, config, dataset
from tests.market_fixtures import START
from tests.research_fixtures import plan
from tests.test_forecasts import forecast, outcome

D = Decimal


def test_seeded_resampling_flat_known_result_and_short_samples() -> None:
    data = dataset()
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(data, config(), Plan({}))
    analysis = plan().analysis
    first = resample(report, analysis)
    assert first == resample(report, analysis)
    assert all(d.value == 0 for d in first)
    short = dataset(("100",) * 2)
    unavailable = resample(
        Backtester(FrozenClock(short.inputs.captured_at)).run(short, config(), Plan({})), analysis
    )
    assert all(d.value is None and d.reason == "INSUFFICIENT_REGULAR_RETURNS" for d in unavailable)


def test_drift_known_arithmetic_and_degenerate_reference() -> None:
    result = drift((D(1), D(2), D(3)), (D(2), D(3), D(4)))
    assert result[0].value == 1 and result[1].value == 1
    assert drift((D(1), D(1)), (D(2), D(2)))[1].reason == "ZERO_REFERENCE_VARIANCE"
    assert all(v.value is None for v in drift((), ()))
    with pytest.raises(ValueError):
        drift((D("NaN"),), ())


def test_calibration_reuses_forecast_outcome_financial_validation() -> None:
    metrics = calibration(((forecast(), outcome()),), START + timedelta(days=1))
    assert metrics[0].value == D("0.14") and metrics[1].value == D("0.3")
    assert all(m.value is None for m in calibration((), START))
    with pytest.raises(ValueError):
        calibration(((forecast(), outcome()),), START)
    with pytest.raises(ValueError):
        calibration(((forecast(), outcome(actual_return=D("0.1"))),), START + timedelta(days=1))
    with pytest.raises(ValueError):
        calibration(((forecast(), outcome()), (forecast(), outcome())), START + timedelta(days=1))
