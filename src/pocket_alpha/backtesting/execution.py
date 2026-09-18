"""Explicit bar-close fill approximation, not observed market execution."""

from decimal import ROUND_FLOOR, Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pocket_alpha.backtesting.models import CostPolicy, SimulatedFill
from pocket_alpha.backtesting.risk import PendingOrder
from pocket_alpha.domain.market import Candle

D = Decimal


def stepped(quantity: Decimal, step: Decimal) -> Decimal:
    return (quantity / step).to_integral_value(rounding=ROUND_FLOOR) * step


def capacity(candle: Candle, costs: CostPolicy) -> Decimal:
    return stepped(candle.volume * costs.participation, costs.quantity_step)


def estimate(
    order: PendingOrder,
    candle: Candle,
    quantity: Decimal,
    consumed: Decimal,
    costs: CostPolicy,
    run_id: UUID,
) -> SimulatedFill:
    total_capacity = candle.volume * costs.participation
    spread = candle.close * costs.spread_bps / 20000
    slippage = candle.close * costs.slippage_bps / 10000
    impact = (
        candle.close
        * costs.impact_bps_at_capacity
        / 10000
        * (consumed + quantity / 2)
        / total_capacity
    )
    direction = 1 if order.intent.action == "BUY" else -1
    price = candle.close + direction * (spread + slippage + impact)
    return SimulatedFill(
        fill_id=uuid5(
            NAMESPACE_URL, f"{run_id}:{order.intent.client_id}:{candle.open_time.isoformat()}"
        ),
        client_id=order.intent.client_id,
        risk_id=order.risk_id,
        at=candle.received_at,
        bar_open=candle.open_time,
        side="BUY" if direction == 1 else "SELL",
        quantity=quantity,
        price=price,
        reference_price=candle.close,
        fee=price * quantity * costs.fee_bps / 10000,
        spread_cost=spread * quantity,
        slippage_cost=slippage * quantity,
        impact_cost=impact * quantity,
    )
