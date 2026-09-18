"""Explicitly synthetic mechanism fixtures; no financial qualification or execution approval."""

from datetime import timedelta
from decimal import Decimal as D

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.derivatives.models import DerivativeContract
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.leverage.models import (
    HorizonVolatility,
    LeveragePolicy,
    LeverageRequest,
    MarginAssumptions,
    PortfolioCollateral,
    PriorRiskCheck,
    ResearchPosition,
    StressKind,
    StressScenario,
    TransactionAssumptions,
)
from tests.test_derivatives import T0, spec

AT = T0 + timedelta(hours=1)
CLOCK = FrozenClock(AT)
SYNTHETIC_HASH = digest({"explicitly_synthetic": True})


def request(side: str = "LONG") -> LeverageRequest:
    contract = DerivativeContract.model_validate(
        spec(margin_scheme="ISOLATED", multiplier="1").model_dump()
        | dict(available_at=T0, ingested_at=T0)
    )
    position = ResearchPosition.model_validate(
        dict(
            version="synthetic-position-1",
            contract=contract,
            side=side,
            contracts="1",
            entry="100",
            stop="98" if side == "LONG" else "102",
            proposed_leverage="2",
            timeframe=Timeframe.H1,
            horizon=ForecastHorizon.H4,
            proposal_at=AT,
            upstream_hash=SYNTHETIC_HASH,
        )
    )
    portfolio = PortfolioCollateral(
        version="synthetic-portfolio-1",
        origin="SYNTHETIC",
        at=AT,
        available_at=AT,
        currency="USD",
        equity=D(10000),
        available_collateral=D(1000),
        provenance_hash=SYNTHETIC_HASH,
    )
    risk = PriorRiskCheck(
        version="synthetic-prior-risk-1",
        origin="SYNTHETIC",
        proposal_hash=digest(position),
        portfolio_hash=digest(portfolio),
        passed=True,
        assessed_at=AT,
        valid_until=AT + timedelta(minutes=5),
        provenance_hash=SYNTHETIC_HASH,
    )
    margin = MarginAssumptions(
        version="synthetic-single-tier-1",
        contract_hash=digest(contract),
        available_at=T0,
        valid_until=AT + timedelta(days=1),
        initial_margin_rate=D("0.1"),
        maintenance_margin_rate=D("0.01"),
        liquidation_fee_rate=D("0.005"),
        maximum_mark_notional=D(100000),
        rules_reference="synthetic conditional model, not venue rules",
        provenance_hash=SYNTHETIC_HASH,
    )
    vol = HorizonVolatility(
        version="synthetic-volatility-1",
        contract_hash=digest(contract),
        origin="SYNTHETIC",
        timeframe=Timeframe.H1,
        horizon=ForecastHorizon.H4,
        observed_at=AT,
        available_at=AT,
        value=D("0.01"),
        input_hash=SYNTHETIC_HASH,
    )
    costs = TransactionAssumptions(
        version="synthetic-costs-1",
        contract_hash=digest(contract),
        available_at=AT,
        horizon=ForecastHorizon.H4,
        entry_fee_bps=D(10),
        exit_fee_bps=D(10),
        spread_bps=D(10),
        slippage_bps=D(10),
        adverse_funding_fraction=D("0.001"),
        provenance_hash=SYNTHETIC_HASH,
    )
    scenarios = tuple(
        StressScenario(
            name="synthetic-" + kind.value.lower(),
            kind=kind,
            adverse_gap_fraction=D("0.04") if kind == StressKind.GAP else D(0),
            volatility_multiple=D(3) if kind == StressKind.VOLATILITY else D(0),
            additional_slippage_bps=D(50) if kind == StressKind.SLIPPAGE else D(0),
            additional_funding_fraction=D("0.01") if kind == StressKind.FUNDING else D(0),
            other_portfolio_loss_fraction=D("0.005") if kind == StressKind.CORRELATED else D(0),
        )
        for kind in StressKind
    )
    policy = LeveragePolicy(
        version="synthetic-policy-1",
        maximum_input_age_seconds=60,
        maximum_leverage=D(10),
        maximum_position_notional=D(10000),
        maximum_collateral_fraction=D("0.1"),
        elevated_loss_fraction=D("0.01"),
        high_loss_fraction=D("0.03"),
        maximum_loss_fraction=D("0.1"),
        minimum_liquidation_buffer_fraction=D("0.01"),
        forced_liquidation_overshoot_fraction=D("0.05"),
        reject_standard_liquidation=True,
        reject_collateral_deficit=False,
        scenarios=scenarios,
    )
    return LeverageRequest(
        origin="SYNTHETIC",
        as_of=AT,
        position=position,
        portfolio=portfolio,
        prior_risk=risk,
        margin=margin,
        volatility=vol,
        costs=costs,
        policy=policy,
    )


def bound(value: LeverageRequest) -> LeverageRequest:
    assert value.prior_risk is not None and value.portfolio is not None
    return value.model_copy(
        update={
            "prior_risk": value.prior_risk.model_copy(
                update={
                    "proposal_hash": digest(value.position),
                    "portfolio_hash": digest(value.portfolio),
                }
            )
        }
    )
