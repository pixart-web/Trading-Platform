from datetime import timedelta
from decimal import Context, Decimal, getcontext, localcontext

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.engine import Backtester, StrategyError
from pocket_alpha.backtesting.models import BacktestReport, Intent
from pocket_alpha.common.clock import FrozenClock
from tests.backtest_fixtures import Plan, config, dataset
from tests.market_fixtures import START

D = Decimal


def run(
    plan: Plan, prices: tuple[str, ...] = ("100",) * 10, volumes: tuple[str, ...] | None = None
) -> BacktestReport:
    data = dataset(prices, volumes)
    return Backtester(FrozenClock(data.inputs.captured_at)).run(data, config(), plan)


def test_causal_round_trip_costs_cash_and_reproducibility() -> None:
    decisions = {
        1: (Intent(client_id="buy", action="BUY", quantity=D(2)),),
        5: (Intent(client_id="sell", action="SELL", quantity=D(2)),),
    }
    plan = Plan(decisions)
    report = run(plan)
    assert len(report.fills) == 2 and len(report.round_trips) == 1
    assert report.fills[0].bar_open == START + timedelta(hours=2)
    assert report.fills[0].at == START + timedelta(hours=3)
    assert report.fills[1].bar_open == START + timedelta(hours=6)
    assert report.final_portfolio.quantity == 0 and report.final_portfolio.cost_basis == 0
    assert report.final_portfolio.cash < report.config.initial_cash
    for fill in report.fills:
        assert (
            fill.fee > 0
            and fill.spread_cost > 0
            and fill.slippage_cost > 0
            and fill.impact_cost > 0
        )
        approval = next(
            e for e in report.orders if e.client_id == fill.client_id and e.state == "APPROVED"
        )
        assert approval.at < fill.bar_open and approval.risk_id == fill.risk_id
    assert all(
        all(c.received_at <= v.as_of for c in v.history) and v.technical.available_at <= v.as_of
        for v in plan.views
    )
    assert run(Plan(decisions)).content_hash == report.content_hash
    metrics = {m.name: m for m in report.metrics}
    assert metrics["net_return"].value is not None and metrics["net_return"].value < 0
    assert metrics["net_expectancy_per_round_trip"].value == report.round_trips[0].net_pnl
    assert metrics["CAGR"].value is None
    assert not report.profitability_claim and not report.live_ready
    with pytest.raises(ValidationError, match="hash"):
        BacktestReport.model_validate(report.model_dump() | {"content_hash": "0" * 64})


def test_shared_liquidity_partial_fills_and_no_duplicate_client_order() -> None:
    buy = Intent(client_id="first", action="BUY", quantity=D(3))
    report = run(
        Plan({1: (buy, Intent(client_id="second", action="BUY", quantity=D(3))), 2: (buy,)}),
        volumes=("10",) * 10,
    )
    assert any(e.state == "PARTIALLY_FILLED" for e in report.orders)
    for opened in {f.bar_open for f in report.fills}:
        assert sum(f.quantity for f in report.fills if f.bar_open == opened) <= 1
    assert sum(e.state == "APPROVED" and e.client_id == "first" for e in report.orders) == 1
    assert len({f.fill_id for f in report.fills}) == len(report.fills)
    assert sum(f.quantity for f in report.fills) == 6


def test_conflicting_id_and_strategy_failure_do_not_produce_report() -> None:
    with pytest.raises(StrategyError, match="conflicting"):
        run(
            Plan(
                {
                    1: (Intent(client_id="same", action="BUY", quantity=D(1)),),
                    2: (Intent(client_id="same", action="BUY", quantity=D(2)),),
                }
            )
        )

    class Broken(Plan):
        def on_event(self, view: object) -> tuple[Intent, ...]:
            raise RuntimeError("synthetic failure")

    with pytest.raises(StrategyError, match="failed"):
        run(Broken({}))


def test_short_and_cash_rejections_and_cancellation_release_reserves() -> None:
    report = run(
        Plan(
            {
                1: (
                    Intent(client_id="short", action="SELL", quantity=D(1)),
                    Intent(client_id="huge", action="BUY", quantity=D(100)),
                    Intent(client_id="buy", action="BUY", quantity=D(2)),
                ),
                2: (Intent(client_id="cancel", action="CANCEL", cancel_client_id="buy"),),
            }
        )
    )
    reasons = {e.reason for e in report.orders}
    assert (
        "SHORT_NOT_SUPPORTED" in reasons
        and "ORDER_NOTIONAL_LIMIT" in reasons
        and "STRATEGY_CANCEL" in reasons
    )
    assert report.fills == () and report.final_portfolio.reserved_cash == 0


def test_zero_volume_cannot_fill_and_pending_orders_end_explicitly() -> None:
    report = run(
        Plan({1: (Intent(client_id="buy", action="BUY", quantity=D(1)),)}), volumes=("0",) * 10
    )
    assert report.fills == ()
    assert report.orders[-1].state == "CANCELLED" and report.orders[-1].reason == "END_OF_DATA"


def test_decimal_results_are_independent_of_ambient_context() -> None:
    decisions = {1: (Intent(client_id="buy", action="BUY", quantity=D(2)),)}
    first = run(Plan(decisions))
    with localcontext(Context(prec=6)):
        second = run(Plan(decisions))
    assert second.content_hash == first.content_hash


def test_imported_past_bars_cannot_create_retroactive_fills() -> None:
    data = dataset(delayed={i: 20 for i in range(10)})
    report = Backtester(FrozenClock(data.inputs.captured_at)).run(
        data, config(), Plan({20: (Intent(client_id="buy", action="BUY", quantity=D(1)),)})
    )
    assert report.fills == ()
    assert "INSUFFICIENT_CAUSAL_EXECUTION_WINDOW" in report.warnings
    assert "STALE_DATA" in {e.reason for e in report.orders}


def test_strategy_numeric_context_cannot_change_accounting_precision() -> None:
    from pocket_alpha.backtesting.models import StrategyView

    class NumericSideEffect(Plan):
        def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
            getcontext().prec = 6
            return super().on_event(view)

    decisions = {1: (Intent(client_id="fractional", action="BUY", quantity=D("1.23")),)}
    assert run(NumericSideEffect(decisions)).content_hash == run(Plan(decisions)).content_hash
