"""Generate Android golden fixtures from existing Python financial implementations, not replicas."""

import json
import sys
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Literal
from uuid import UUID

from pocket_alpha.backtesting.models import Intent, RunConfig
from pocket_alpha.backtesting.risk import Book, authorize, halt, snapshot
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import _calculate
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.simulation.engine import SimulatedExecution
from tests.backtest_fixtures import config, dataset
from tests.market_fixtures import START


def generate() -> str:
    base = config(initial_cash=Decimal(1000))
    c, r = base.costs, base.risk
    policy = dict(
        version="synthetic-golden-1",
        fee=str(c.fee_bps),
        spread=str(c.spread_bps),
        slippage=str(c.slippage_bps),
        impact=str(c.impact_bps_at_capacity),
        collar=str(c.maximum_price_deviation_fraction),
        participation=str(c.participation),
        step=str(c.quantity_step),
        minimumQuantity=str(c.minimum_quantity),
        minimumNotional=str(c.minimum_notional),
        maximumOrder=str(r.maximum_order_notional),
        maximumExposure=str(r.maximum_exposure_fraction),
        maximumDrawdown=str(r.maximum_drawdown),
        maximumDailyLoss=str(r.maximum_daily_loss),
        maximumAge=r.maximum_data_age_seconds,
        maximumSpread=str(r.maximum_spread_bps),
        lifetime=c.order_lifetime_seconds,
        kill=False,
    )
    risk = []
    cases: list[tuple[Literal["BUY", "SELL"], str, dict[str, object], int]] = [
        ("BUY", "1", {}, 0),
        ("BUY", "1", {"kill_switch": True}, 0),
        ("BUY", "1", {}, r.maximum_data_age_seconds + 1),
        ("BUY", "1", {}, r.maximum_data_age_seconds),
        ("BUY", "0.001", {}, 0),
        ("BUY", "0.01", {"maximum_order_notional": "100"}, 0),
        ("BUY", "1", {"maximum_order_notional": "100"}, 0),
        ("BUY", "1", {"maximum_spread_bps": "1"}, 0),
        ("BUY", "1", {"maximum_exposure_fraction": "0.001"}, 0),
        ("BUY", "10", {}, 0),
        ("SELL", "1", {}, 0),
    ]
    for side, quantity, overrides, age in cases:
        extra_micros = 500 if age == r.maximum_data_age_seconds else 0
        cfg = RunConfig.model_validate(base.model_dump() | {"risk": r.model_dump() | overrides})
        risk.append(
            dict(
                side=side,
                quantity=quantity,
                overrides=overrides,
                age=age,
                extraMicros=extra_micros,
                reason=authorize(
                    Intent(client_id="risk", action=side, quantity=Decimal(quantity)),
                    Book(
                        cash=Decimal(1000),
                        high_water=Decimal(1000),
                        daily_start_equity=Decimal(1000),
                    ),
                    [],
                    Decimal(100),
                    START,
                    START + timedelta(seconds=age, microseconds=extra_micros),
                    cfg,
                ),
            )
        )
    sim = SimulatedExecution(UUID(int=1), base)
    bars = dataset(
        prices=("100", "100", "105", "111", "115", "115", "110", "108", "112", "112"),
        volumes=("10",) * 10,
    ).inputs.candles
    commands: list[dict[str, str]] = []
    expected: list[dict[str, str] | None] = []
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        for index, candle in enumerate(bars[:9]):
            at = candle.close_time
            if index == 0:
                intent = Intent(client_id="buy", action="BUY", quantity=Decimal(3))
                sim.submit(intent, at, candle, at)
                commands.append(
                    dict(
                        id=intent.client_id,
                        at=at.isoformat(),
                        kind="ORDER",
                        side="BUY",
                        quantity="3",
                        price=str(candle.close),
                        quoteClose=at.isoformat(),
                    )
                )
                expected.append(None)
            if index in (2, 3, 4, 6, 7, 8):
                sim.observe_risk(candle.close)
                sim.execute(candle, candle.close)
                sim.observe_risk(candle.close)
                commands.append(
                    dict(
                        id=f"bar-{index}",
                        at=at.isoformat(),
                        kind="BAR",
                        price=str(candle.close),
                        quoteClose=candle.close_time.isoformat(),
                        barOpen=candle.open_time.isoformat(),
                        volume="10",
                    )
                )
                valued = snapshot(sim.book, sim.pending, candle.close)
                expected.append(
                    dict(
                        highWater=str(sim.book.high_water),
                        equity=str(valued.equity),
                        reservedCash=str(valued.reserved_cash),
                        reservedQuantity=str(valued.reserved_quantity),
                        availableCash=str(valued.cash - valued.reserved_cash),
                        unrealized=str(sim.book.quantity * candle.close - sim.book.cost_basis),
                        cash=str(sim.book.cash),
                        quantity=str(sim.book.quantity),
                        basis=str(sim.book.cost_basis),
                        fees=str(sum((f.fee for f in sim.fills), Decimal(0))),
                        realized=str(
                            sum((f.realized_pnl or Decimal(0) for f in sim.fills), Decimal(0))
                        ),
                    )
                )
                if index == 4:
                    sim.submit(
                        Intent(client_id="sell", action="SELL", quantity=Decimal(3)), at, candle, at
                    )
                    commands.append(
                        dict(
                            id="sell",
                            at=at.isoformat(),
                            kind="ORDER",
                            side="SELL",
                            quantity="3",
                            price=str(candle.close),
                            quoteClose=at.isoformat(),
                        )
                    )
                    expected.append(None)
    halt_cases = []
    for cash, high, daily in [
        ("100", "1000", "1000"),
        ("100", "100", "1000"),
        ("0", "1000", "1000"),
    ]:
        book = Book(cash=Decimal(cash), high_water=Decimal(high), daily_start_equity=Decimal(daily))
        halt_cases.append(
            dict(cash=cash, highWater=high, dailyStart=daily, reason=halt(book, Decimal(100), base))
        )
    decimal_cases = []
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        for left, right, operation in [
            ("1", "3", "DIV"),
            ("1" + "0" * 78 + "2", "0.5", "ADD"),
            ("1" + "0" * 78 + "3", "0.5", "ADD"),
        ]:
            a, b = Decimal(left), Decimal(right)
            decimal_cases.append(
                dict(
                    left=left,
                    right=right,
                    operation=operation,
                    expected=str(a / b if operation == "DIV" else a + b),
                )
            )
    technical = []
    history = dataset(
        prices=("101", "99", "103", "98", "107", "102", "110", "105", "100", "112")
    ).inputs.candles
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        for kind in [IndicatorKind.SMA, IndicatorKind.EMA]:
            features = [
                snapshot.results[0].features
                for snapshot in _calculate(
                    tuple(history),
                    dataset().inputs.query,
                    FreshnessPolicy(),
                    (IndicatorSpec(kind=kind, period=3),),
                )
            ]
            technical.append(
                dict(
                    kind=kind.value,
                    period=3,
                    asOf=history[-1].received_at.isoformat(),
                    history=[
                        dict(
                            close=str(c.close),
                            closedAt=c.close_time.isoformat(),
                            receivedAt=c.received_at.isoformat(),
                        )
                        for c in history
                    ],
                    expected=[
                        dict(
                            status=row[0].status.value,
                            value=str(row[0].value) if row[0].value is not None else None,
                            reason=row[0].reason,
                        )
                        for row in features
                    ],
                )
            )
    return (
        json.dumps(
            dict(
                origin="SYNTHETIC_ENGINEERING_FIXTURE",
                technical=technical,
                haltCases=halt_cases,
                decimals=decimal_cases,
                policy=policy,
                capital="1000",
                start=bars[0].close_time.isoformat(),
                risk=risk,
                commands=commands,
                expected=expected,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    rendered = generate()
    for path in [
        Path("android/app/src/test/resources/local-kernel-golden.json"),
        Path("android/app/src/androidTest/assets/local-kernel-golden.json"),
    ]:
        if "--check" in sys.argv:
            if path.read_text() != rendered:
                raise SystemExit(f"Stale financial golden vectors: {path}")
        else:
            path.write_text(rendered)
