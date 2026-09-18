from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.models import Intent
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import AssetType, ForecastHorizon
from pocket_alpha.forecasts.horizons import expires_at
from tests.backtest_fixtures import Plan, config, dataset
from tests.market_fixtures import START
from tests.test_forecasts import forecast

D = Decimal


def test_forecasts_enter_only_after_generation_and_leave_at_expiry() -> None:
    data = dataset()
    policy = config()
    generated = START + timedelta(hours=4)
    value = forecast(
        market_id=data.inputs.market.market_id,
        asset_id=data.inputs.asset.asset_id,
        model_version=policy.strategy.model_version,
        feature_version=policy.feature_version,
        horizon=ForecastHorizon.H1,
        generated_at=generated,
        expires_at=expires_at(generated, ForecastHorizon.H1),
    )
    plan = Plan({})
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(data, policy, plan, (value,))
    assert all(
        v.forecasts == () for v in plan.views if v.as_of < generated or v.as_of >= value.expires_at
    )
    assert next(v for v in plan.views if v.as_of == generated).forecasts == (value,)
    assert (
        report.forecast_input_hash
        != Backtester(FrozenClock(data.inputs.captured_at))
        .run(data, policy, Plan({}))
        .forecast_input_hash
    )
    with pytest.raises(ValueError, match="unique"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(data, policy, Plan({}), (value, value))
    with pytest.raises(ValueError, match="identity/version"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(
            data,
            policy,
            Plan({}),
            (value.model_copy(update={"forecast_id": UUID(int=99), "model_version": "wrong"}),),
        )


def test_delayed_prefix_blocks_later_feature_knowledge_until_missing_bar_arrives() -> None:
    data = dataset(delayed={0: 5})
    plan = Plan({})
    Backtester(FrozenClock(data.inputs.captured_at)).run(data, config(), plan)
    assert min(v.as_of for v in plan.views) == START + timedelta(hours=5)
    assert plan.views[0].technical.available_at == START + timedelta(hours=5)
    assert len(plan.views[0].history) == 5
    data = dataset(delayed={1: 8})
    plan = Plan({5: (Intent(client_id="old-feature", action="BUY", quantity=D(1)),)})
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(data, config(), plan)
    assert "STALE_DATA" in {e.reason for e in report.orders}
    assert report.fills == ()


def test_future_revision_cannot_replace_frozen_dataset_and_nonspot_is_rejected() -> None:
    data = dataset()
    corrupted = data.model_copy(
        update={
            "inputs": data.inputs.model_copy(
                update={
                    "candles": tuple(
                        c.model_copy(update={"close": D(105)}) for c in data.inputs.candles
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="hash"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(corrupted, config(), Plan({}))
    inputs = data.inputs.model_copy(
        update={"asset": data.inputs.asset.model_copy(update={"asset_type": AssetType.STOCK})}
    )
    nonspot = data.model_copy(update={"inputs": inputs, "content_hash": inputs.digest()})
    with pytest.raises(ValueError, match="crypto spot"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(nonspot, config(), Plan({}))


def test_late_execution_bar_is_rejected_without_backdating() -> None:
    data = dataset(delayed={i: 20 for i in range(2, 10)})
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(
        data, config(), Plan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    )
    # Check fill timestamps before narrowing the tuple type to empty; all checks remain.
    assert all(f.at != START + timedelta(hours=3) for f in report.fills)
    assert all(f.bar_open != START + timedelta(hours=2) for f in report.fills)
    assert report.fills == ()
    assert "STALE_EXECUTION_DATA" in {e.reason for e in report.orders}


def test_future_forecast_artifact_cannot_be_claimed_as_captured_input() -> None:
    data = dataset()
    policy = config()
    generated = data.inputs.captured_at + timedelta(hours=1)
    value = forecast(
        market_id=data.inputs.market.market_id,
        asset_id=data.inputs.asset.asset_id,
        model_version=policy.strategy.model_version,
        feature_version=policy.feature_version,
        generated_at=generated,
        expires_at=expires_at(generated, ForecastHorizon.H1),
    )
    with pytest.raises(ValueError, match="after dataset capture"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(data, policy, Plan({}), (value,))
