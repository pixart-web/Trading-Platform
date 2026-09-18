from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.models import BacktestReport, Intent, RunConfig, StrategyIdentity
from pocket_alpha.common.clock import FrozenClock
from tests.backtest_fixtures import Plan, config, dataset
from tests.market_fixtures import START

D = Decimal


def simulated(
    decisions: dict[int, tuple[Intent, ...]],
    costs: dict[str, object] | None = None,
    risk: dict[str, object] | None = None,
    **kwargs: object,
) -> BacktestReport:
    base = config()
    policy = RunConfig.model_validate(
        base.model_dump()
        | {
            "costs": base.costs.model_dump() | (costs or {}),
            "risk": base.risk.model_dump() | (risk or {}),
        }
        | kwargs
    )
    data = dataset()
    return Backtester(FrozenClock(data.inputs.captured_at)).run(data, policy, Plan(decisions))


@pytest.mark.parametrize(
    "risk,quantity,reason",
    [
        ({"kill_switch": True}, "1", "KILL_SWITCH"),
        ({"maximum_spread_bps": "1"}, "1", "SPREAD_LIMIT"),
        ({"maximum_exposure_fraction": "0.001"}, "1", "EXPOSURE_LIMIT"),
        ({"maximum_order_notional": "100"}, "1", "ORDER_NOTIONAL_LIMIT"),
        ({}, "0.001", "INVALID_QUANTITY"),
        ({}, "0.01", "MINIMUM_NOTIONAL"),
    ],
)
def test_risk_rejection_is_explicit_and_has_no_fill(
    risk: dict[str, object], quantity: str, reason: str
) -> None:
    report = simulated(
        {1: (Intent(client_id="buy", action="BUY", quantity=D(quantity)),)},
        risk=risk,
        costs={"minimum_notional": "2"},
    )
    assert report.fills == () and reason in {e.reason for e in report.orders}


def test_pending_cash_and_position_reservations_prevent_double_spending() -> None:
    report = simulated(
        {
            1: (
                Intent(client_id="first", action="BUY", quantity=D(30)),
                Intent(client_id="second", action="BUY", quantity=D(30)),
                Intent(client_id="third", action="BUY", quantity=D(30)),
            )
        }
    )
    assert "INSUFFICIENT_UNRESERVED_CASH" in {e.reason for e in report.orders}
    assert report.final_portfolio.cash >= 0
    report = simulated(
        {
            1: (Intent(client_id="buy", action="BUY", quantity=D(2)),),
            4: (
                Intent(client_id="sell1", action="SELL", quantity=D(2)),
                Intent(client_id="sell2", action="SELL", quantity=D(2)),
            ),
        }
    )
    assert "SHORT_NOT_SUPPORTED" in {e.reason for e in report.orders}
    assert report.final_portfolio.quantity == 0


def test_latency_expiry_and_end_cancel_follow_event_order() -> None:
    report = simulated(
        {1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)},
        costs={"latency_seconds": 3600, "order_lifetime_seconds": 7200},
    )
    assert report.fills == ()
    events = [e for e in report.orders if e.client_id == "buy"]
    assert [e.state for e in events] == ["APPROVED", "ACKNOWLEDGED", "EXPIRED"]
    assert events[1].at == START + timedelta(hours=2) and events[2].at == START + timedelta(hours=3)
    report = simulated(
        {1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)},
        costs={"latency_seconds": 3600, "order_lifetime_seconds": 20000},
    )
    assert report.fills[0].bar_open == START + timedelta(hours=3)


def test_price_collar_and_drawdown_halt_do_not_force_fills() -> None:
    data = dataset(("100", "100", "200") + ("200",) * 7)
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(
        data, config(), Plan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    )
    assert report.fills == () and "PRICE_COLLAR" in {e.reason for e in report.orders}
    data = dataset(("100",) * 4 + ("40",) * 6)
    base = config()
    policy = RunConfig.model_validate(
        base.model_dump() | {"risk": base.risk.model_dump() | {"maximum_drawdown": "0.001"}}
    )
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(
        data,
        policy,
        Plan(
            {
                1: (Intent(client_id="buy", action="BUY", quantity=D(2)),),
                5: (Intent(client_id="exit", action="SELL", quantity=D(2)),),
            }
        ),
    )
    assert "RISK_HALT_NO_FORCED_FILL" in report.warnings
    assert report.final_portfolio.quantity == 2 and len(report.fills) == 1


def test_intention_budget_and_code_environment_identity_fail_closed() -> None:
    from pocket_alpha.backtesting.engine import StrategyError

    with pytest.raises(StrategyError, match="budget"):
        simulated(
            {
                1: (
                    Intent(client_id="a", action="BUY", quantity=D(1)),
                    Intent(client_id="b", action="BUY", quantity=D(1)),
                )
            },
            maximum_intents=1,
        )
    for changes in ({"code_tree_hash": "0" * 64}, {"environment_hash": "0" * 64}):
        with pytest.raises(ValueError, match="identity"):
            data = dataset()
            Backtester(FrozenClock(data.inputs.captured_at)).run(data, config(**changes), Plan({}))
    data = dataset()
    with pytest.raises(ValueError, match="future"):
        Backtester(FrozenClock(START)).run(data, config(), Plan({}))
    base = config()
    different = base.model_copy(
        update={
            "strategy": StrategyIdentity(
                strategy_version="other", model_version="other", parameters=()
            )
        }
    )
    with pytest.raises(ValueError, match="identity"):
        Backtester(FrozenClock(data.inputs.captured_at)).run(data, different, Plan({}))


def test_split_orders_preserve_aggregate_impact() -> None:
    one = simulated({1: (Intent(client_id="one", action="BUY", quantity=D(2)),)})
    split = simulated(
        {
            1: (
                Intent(client_id="a", action="BUY", quantity=D(1)),
                Intent(client_id="b", action="BUY", quantity=D(1)),
            )
        }
    )
    assert sum(f.impact_cost for f in one.fills) == sum(f.impact_cost for f in split.fills)
    assert one.final_portfolio.cash == split.final_portfolio.cash


@pytest.mark.parametrize(
    "bad",
    [
        {"fee_bps": "0"},
        {"spread_bps": "0"},
        {"quantity_step": "0"},
        {"participation": "1.1"},
        {"fee_bps": "NaN"},
        {"order_lifetime_seconds": 0},
        {"slippage_bps": "10000"},
    ],
)
def test_costs_cannot_silently_assume_free_or_invalid_execution(bad: dict[str, object]) -> None:
    base = config()
    with pytest.raises(ValidationError):
        RunConfig.model_validate(base.model_dump() | {"costs": base.costs.model_dump() | bad})


def test_daily_loss_halt_is_distinct_from_drawdown_and_pending_limit() -> None:
    data = dataset(("100",) * 4 + ("40",) * 6)
    base = config()
    policy = RunConfig.model_validate(
        base.model_dump() | {"risk": base.risk.model_dump() | {"maximum_daily_loss": "0.001"}}
    )
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(
        data,
        policy,
        Plan(
            {
                1: (Intent(client_id="buy", action="BUY", quantity=D(2)),),
                5: (Intent(client_id="exit", action="SELL", quantity=D(2)),),
            }
        ),
    )
    assert "DAILY_LOSS_LIMIT" in {e.reason for e in report.orders}
    report = simulated(
        {
            1: (
                Intent(client_id="a", action="BUY", quantity=D(1)),
                Intent(client_id="b", action="BUY", quantity=D(1)),
            )
        },
        risk={"maximum_pending_orders": 1},
    )
    assert "PENDING_ORDER_LIMIT" in {e.reason for e in report.orders}


def test_final_holdout_is_not_available_for_iterative_phase21_tuning() -> None:
    with pytest.raises(ValueError, match="final holdout"):
        simulated({}, evaluation_split="FINAL_HOLDOUT")
