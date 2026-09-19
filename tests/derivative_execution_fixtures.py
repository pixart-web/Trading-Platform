"""Synthetic-only fixtures for derivative execution mechanism qualification."""

from datetime import timedelta
from decimal import Decimal as D
from typing import Literal
from uuid import UUID

from pocket_alpha.backtesting.models import digest
from pocket_alpha.derivative_execution.models import (
    DerivativeAccountState,
    DerivativeExecutionPolicy,
    DerivativeExecutionRequest,
    DerivativeLocalState,
    DerivativeMarketState,
    DerivativeOrderIntent,
    DerivativePositionState,
    DerivativeStrategyEvidence,
)
from pocket_alpha.leverage.engine import LeverageResearch
from pocket_alpha.leverage.models import ResearchPosition
from tests.leverage_fixtures import AT as LEVERAGE_AT
from tests.leverage_fixtures import CLOCK as LEVERAGE_CLOCK
from tests.leverage_fixtures import SYNTHETIC_HASH
from tests.leverage_fixtures import request as leverage_request

AT = LEVERAGE_AT
CLOCK = LEVERAGE_CLOCK

ACCOUNT_HASH = digest({"synthetic_derivative_account": 1})
STRATEGY_HASH = digest({"synthetic_derivative_strategy": 1})


def policy(**changes: object) -> DerivativeExecutionPolicy:
    values: dict[str, object] = dict(
        version="synthetic-derivative-policy-1",
        mode="SYNTHETIC_QUALIFICATION",
        global_enable=True,
        derivative_enable=True,
        manual_enable=True,
        account_identity_hash=ACCOUNT_HASH,
        contract_ids=("derivative:perp",),
        strategy_hashes=(STRATEGY_HASH,),
        collateral_currency="USD",
        capital_limit=D(10000),
        order_notional_limit=D(1000),
        total_gross_notional_limit=D(5000),
        total_net_notional_limit=D(3000),
        position_notional_limit=D(2000),
        collateral_limit=D(500),
        daily_loss_limit=D(500),
        maximum_drawdown=D("0.1"),
        maximum_collateral_fraction=D("0.1"),
        maximum_leverage=D(3),
        minimum_liquidation_buffer_fraction=D("0.1"),
        maximum_initial_margin_rate=D("0.2"),
        maximum_maintenance_margin_rate=D("0.05"),
        maximum_fee_fraction=D("0.01"),
        maximum_funding_fraction=D("0.01"),
        maximum_spread_fraction=D("0.01"),
        maximum_mark_index_deviation_fraction=D("0.02"),
        maximum_basis_fraction=D("0.02"),
        maximum_price_deviation_fraction=D("0.02"),
        maximum_modeled_loss_fraction=D("0.01"),
        maximum_positions=3,
        maximum_orders_per_minute=2,
        maximum_orders_per_day=10,
        maximum_data_age_seconds=60,
        minimum_expiry_buffer_seconds=3600,
    )
    return DerivativeExecutionPolicy.model_validate(values | changes)


def strategy(position: ResearchPosition, **changes: object) -> DerivativeStrategyEvidence:
    values: dict[str, object] = dict(
        schema_version="derivative-strategy-evidence-1.0.0",
        strategy_id=UUID("00000000-0000-0000-0000-000000000029"),
        strategy_version="synthetic-derivative-shadow-1",
        definition_hash=STRATEGY_HASH,
        proposal_hash=position.upstream_hash,
        leverage_position_hash=digest(position),
        stage="SHADOW",
        origin="SYNTHETIC",
        evaluated_at=AT - timedelta(seconds=1),
        valid_until=AT + timedelta(minutes=5),
        evidence_hash=SYNTHETIC_HASH,
    )
    values.update(changes)
    # fmt: off
    provisional = DerivativeStrategyEvidence.model_construct(
        **values,  # type: ignore[arg-type]
        content_hash="0" * 64,
    )
    # fmt: on
    values["content_hash"] = digest(provisional.model_dump(mode="json", exclude={"content_hash"}))
    return DerivativeStrategyEvidence.model_validate(values)


def execution_request(
    side: Literal["LONG", "SHORT"] = "LONG",
    effect: Literal["OPEN", "CLOSE"] = "OPEN",
    **changes: object,
) -> DerivativeExecutionRequest:
    leverage_input = leverage_request(side)
    assessment = LeverageResearch(CLOCK).assess(leverage_input)
    position = assessment.request.position
    contract = position.contract
    market = DerivativeMarketState(
        origin="SYNTHETIC",
        contract=contract,
        observed_at=AT,
        available_at=AT,
        mark_price=D(100),
        index_price=D(100),
        bid=D("99.9"),
        ask=D("100.1"),
        funding_rate=D("0.001"),
        next_funding_at=AT + timedelta(hours=8),
        initial_margin_rate=D("0.1"),
        maintenance_margin_rate=D("0.01"),
        quantity_step=D(1),
        price_tick=D("0.1"),
        minimum_contracts=D(1),
        maximum_contracts=D(100),
        minimum_notional=D(10),
        maximum_notional=D(10000),
        rules_reference="synthetic conditional model, not venue rules",
        provenance_hash=SYNTHETIC_HASH,
    )
    existing: tuple[DerivativePositionState, ...] = ()
    if effect == "CLOSE":
        existing = (
            DerivativePositionState(
                contract_id=contract.contract_id,
                contract_hash=digest(contract),
                side=side,
                contracts=D(1),
                entry_price=D(100),
                mark_price=D(100),
                notional=D(100),
                initial_margin=D(10),
                maintenance_margin=D(1),
                unrealized_pnl=D(0),
                liquidation_price=D(50) if side == "LONG" else D(150),
            ),
        )
    account = DerivativeAccountState(
        origin="SYNTHETIC",
        account_identity_hash=ACCOUNT_HASH,
        observed_at=AT,
        completed_at=AT,
        collateral_currency="USD",
        equity=D(10000),
        available_collateral=D(1000),
        wallet_balance=D(10000),
        positions=existing,
        open_order_client_ids=(),
        trading_permission=True,
        provenance_hash=SYNTHETIC_HASH,
    )
    order_side: Literal["BUY", "SELL"] = "BUY" if side == "LONG" else "SELL"
    if effect == "CLOSE":
        order_side = "SELL" if side == "LONG" else "BUY"
    intent = DerivativeOrderIntent(
        intent_id=UUID("00000000-0000-0000-0000-000000000129"),
        contract_id=contract.contract_id,
        position_side=side,
        order_side=order_side,
        effect=effect,
        contracts=D(1),
        limit_price=D(100),
        reduce_only=effect == "CLOSE",
        created_at=AT,
        expires_at=AT + timedelta(minutes=5),
        strategy_proposal_hash=position.upstream_hash,
    )
    values: dict[str, object] = dict(
        strategy=strategy(position),
        intent=intent,
        leverage=assessment,
        market=market,
        account=account,
        local_state=DerivativeLocalState(
            account_identity_hash=ACCOUNT_HASH,
            revision=1,
            recorded_at=AT,
            account_state_hash=digest(account),
            independently_reconciled=True,
        ),
        daily_start_equity=D(10000),
        daily_net_flows=D(0),
        high_water_equity=D(10000),
        loss_context_at=AT,
        health_ready=True,
        independent_qualification=True,
    )
    return DerivativeExecutionRequest.model_validate(values | changes)
