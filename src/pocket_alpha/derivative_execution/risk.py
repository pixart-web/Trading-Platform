"""Independent derivative pre-trade risk checks for synthetic qualification only."""

from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Literal

from pocket_alpha.backtesting.models import digest
from pocket_alpha.derivative_execution.models import (
    DerivativeExecutionPolicy,
    DerivativeExecutionRequest,
    DerivativeRiskDecision,
)
from pocket_alpha.derivatives.models import ContractKind, MultiplierUnit, Settlement
from pocket_alpha.leverage.models import AssessmentStatus


def evaluate(
    request: DerivativeExecutionRequest,
    policy: DerivativeExecutionPolicy,
    *,
    now: datetime,
    broker_origin: Literal["REAL", "SYNTHETIC"],
    killed: bool,
) -> DerivativeRiskDecision:
    reasons: list[str] = []
    position = request.leverage.request.position
    contract = position.contract
    margin = request.leverage.request.margin
    portfolio = request.leverage.request.portfolio
    prior_risk = request.leverage.request.prior_risk
    intent = request.intent
    market = request.market
    account = request.account

    if policy.mode != "SYNTHETIC_QUALIFICATION":
        reasons.append("DERIVATIVE_EXECUTION_DISABLED")
    if not policy.global_enable:
        reasons.append("GLOBAL_ENABLE_REQUIRED")
    if not policy.derivative_enable:
        reasons.append("DERIVATIVE_ENABLE_REQUIRED")
    if not policy.manual_enable:
        reasons.append("MANUAL_ENABLE_REQUIRED")
    if broker_origin != "SYNTHETIC":
        reasons.append("NATIVE_DERIVATIVE_EXECUTION_UNQUALIFIED")
    if killed:
        reasons.append("KILL_SWITCH_LATCHED")
    if not request.health_ready:
        reasons.append("SYSTEM_HEALTH_NOT_READY")
    if not request.independent_qualification:
        reasons.append("INDEPENDENT_QUALIFICATION_REQUIRED")

    if any(
        origin != "SYNTHETIC"
        for origin in (
            request.strategy.origin,
            request.leverage.request.origin,
            market.origin,
            account.origin,
        )
    ):
        reasons.append("SYNTHETIC_ORIGIN_REQUIRED")
    if contract.contract_id not in policy.contract_ids:
        reasons.append("CONTRACT_NOT_ALLOWED")
    if request.strategy.definition_hash not in policy.strategy_hashes:
        reasons.append("STRATEGY_NOT_ALLOWED")
    if account.account_identity_hash != policy.account_identity_hash:
        reasons.append("ACCOUNT_IDENTITY_MISMATCH")
    if account.collateral_currency != policy.collateral_currency:
        reasons.append("COLLATERAL_CURRENCY_MISMATCH")
    if not account.trading_permission:
        reasons.append("TRADING_PERMISSION_UNAVAILABLE")
    if account.withdrawal_permission:
        reasons.append("WITHDRAWAL_PERMISSION_FORBIDDEN")
    if account.open_order_client_ids:
        reasons.append("BROKER_OPEN_ORDERS_UNRESOLVED")

    if contract.kind not in {ContractKind.PERPETUAL, ContractKind.FUTURE}:
        reasons.append("UNSUPPORTED_CONTRACT_KIND")
    if contract.multiplier_unit != MultiplierUnit.BASE_UNITS_PER_CONTRACT:
        reasons.append("UNSUPPORTED_MULTIPLIER_UNIT")
    if contract.settlement != Settlement.CASH:
        reasons.append("UNSUPPORTED_SETTLEMENT")
    if contract.margin_scheme.upper() != "ISOLATED":
        reasons.append("UNSUPPORTED_MARGIN_SCHEME")
    if not (
        contract.quote_currency
        == contract.settlement_currency
        == contract.reference_index_currency
        == policy.collateral_currency
    ):
        reasons.append("UNSUPPORTED_CURRENCY_CONVENTION")
    if contract.kind == ContractKind.PERPETUAL and market.funding_rate is None:
        reasons.append("FUNDING_UNAVAILABLE")
    if contract.kind == ContractKind.FUTURE and market.funding_rate is not None:
        reasons.append("UNEXPECTED_FUTURE_FUNDING")
    if contract.expires_at is not None:
        if contract.expires_at <= now:
            reasons.append("CONTRACT_EXPIRED")
        elif intent.effect == "OPEN" and contract.expires_at <= now + timedelta(
            seconds=policy.minimum_expiry_buffer_seconds
        ):
            reasons.append("EXPIRY_BUFFER_LIMIT")

    if request.leverage.rejection_reasons:
        reasons.append("LEVERAGE_ASSESSMENT_REJECTED")
    if intent.effect == "OPEN":
        if request.leverage.status != AssessmentStatus.ACCEPTABLE:
            reasons.append("LEVERAGE_ASSESSMENT_NOT_ACCEPTABLE")
        if any(result.ruin_scenario for result in request.leverage.stresses):
            reasons.append("LEVERAGE_RUIN_SCENARIO")
        if any(not result.tier_applicable for result in request.leverage.stresses):
            reasons.append("MARGIN_TIER_NOT_APPLICABLE")
    if any(
        value is None
        for value in (
            request.leverage.position_notional,
            request.leverage.required_collateral,
            request.leverage.liquidation_distance_fraction,
            request.leverage.maximum_modeled_loss,
        )
    ):
        reasons.append("LEVERAGE_METRICS_UNAVAILABLE")

    if digest(contract) != digest(market.contract):
        reasons.append("MARKET_CONTRACT_MISMATCH")
    if intent.contract_id != contract.contract_id:
        reasons.append("INTENT_CONTRACT_MISMATCH")
    if intent.position_side != position.side:
        reasons.append("POSITION_SIDE_MISMATCH")
    if intent.contracts != position.contracts:
        reasons.append("ASSESSED_QUANTITY_MISMATCH")
    if intent.strategy_proposal_hash != request.strategy.proposal_hash:
        reasons.append("STRATEGY_PROPOSAL_MISMATCH")
    if position.upstream_hash != request.strategy.proposal_hash:
        reasons.append("LEVERAGE_STRATEGY_MISMATCH")
    if request.strategy.leverage_position_hash != digest(position):
        reasons.append("STRATEGY_LEVERAGE_BINDING_MISMATCH")
    if not request.strategy.evaluated_at <= position.proposal_at <= request.strategy.valid_until:
        reasons.append("STRATEGY_EVIDENCE_TIME_MISMATCH")
    if not request.strategy.evaluated_at <= now <= request.strategy.valid_until:
        reasons.append("STRATEGY_EVIDENCE_EXPIRED")
    if intent.created_at < position.proposal_at or intent.expires_at <= now:
        reasons.append("INTENT_EXPIRED_OR_PRECAUSAL")

    if portfolio is None:
        reasons.append("PORTFOLIO_COLLATERAL_UNAVAILABLE")
    else:
        if (
            portfolio.origin != "SYNTHETIC"
            or portfolio.currency != account.collateral_currency
            or portfolio.equity != account.equity
            or portfolio.available_collateral != account.available_collateral
        ):
            reasons.append("PORTFOLIO_ACCOUNT_MISMATCH")
        if (
            not 0
            <= (now - portfolio.available_at).total_seconds()
            <= (policy.maximum_data_age_seconds)
        ):
            reasons.append("PORTFOLIO_COLLATERAL_STALE")
    if prior_risk is None:
        reasons.append("PRIOR_RISK_UNAVAILABLE")
    else:
        if (
            not prior_risk.passed
            or prior_risk.origin != "SYNTHETIC"
            or prior_risk.proposal_hash != digest(position)
            or portfolio is None
            or prior_risk.portfolio_hash != digest(portfolio)
        ):
            reasons.append("PRIOR_RISK_BINDING_INVALID")
        if not prior_risk.assessed_at <= now <= prior_risk.valid_until:
            reasons.append("PRIOR_RISK_EXPIRED")

    if margin is None:
        reasons.append("MARGIN_RULES_UNAVAILABLE")
    else:
        if (
            margin.contract_hash != digest(contract)
            or margin.initial_margin_rate != market.initial_margin_rate
            or margin.maintenance_margin_rate != market.maintenance_margin_rate
            or margin.rules_reference != market.rules_reference
            or margin.provenance_hash != market.provenance_hash
        ):
            reasons.append("MARGIN_RULES_MISMATCH")
        if not margin.available_at <= now <= margin.valid_until:
            reasons.append("MARGIN_RULES_EXPIRED")

    if request.local_state.account_identity_hash != account.account_identity_hash:
        reasons.append("LOCAL_ACCOUNT_IDENTITY_MISMATCH")
    if request.local_state.account_state_hash != digest(account):
        reasons.append("LOCAL_BROKER_STATE_MISMATCH")
    if not request.local_state.independently_reconciled:
        reasons.append("ACCOUNT_NOT_RECONCILED")
    if request.local_state.recorded_at != account.completed_at:
        reasons.append("LOCAL_STATE_TIME_MISMATCH")
    for available_at, reason in (
        (market.available_at, "MARKET_STATE_STALE"),
        (account.completed_at, "ACCOUNT_STATE_STALE"),
        (request.loss_context_at, "LOSS_CONTEXT_STALE"),
    ):
        if not 0 <= (now - available_at).total_seconds() <= policy.maximum_data_age_seconds:
            reasons.append(reason)

    same = [
        item
        for item in account.positions
        if item.contract_id == contract.contract_id and item.side == intent.position_side
    ]
    opposite = [
        item
        for item in account.positions
        if item.contract_id == contract.contract_id and item.side != intent.position_side
    ]
    if opposite:
        reasons.append("ONE_WAY_POSITION_CONFLICT")
    current = same[0] if same else None
    if intent.effect == "CLOSE" and (
        current is None or intent.contracts > current.contracts or not intent.reduce_only
    ):
        reasons.append("REDUCE_ONLY_POSITION_MISMATCH")
    if intent.effect == "OPEN" and intent.reduce_only:
        reasons.append("OPEN_CANNOT_REDUCE_ONLY")

    with localcontext() as context:
        context.prec = 80
        notional = intent.contracts * contract.multiplier * intent.limit_price
        initial_margin_rate = market.initial_margin_rate
        fee_reserve = notional * policy.maximum_fee_fraction
        funding_reserve = notional * policy.maximum_funding_fraction
        margin_reserve = Decimal(0)
        if intent.effect == "OPEN":
            assessed_reserve = request.leverage.required_collateral or Decimal(0)
            margin_reserve = max(notional * initial_margin_rate, assessed_reserve)
        reserve = (margin_reserve + fee_reserve + funding_reserve).quantize(
            Decimal("1e-18"), rounding=ROUND_CEILING
        )
        gross = sum((item.notional for item in account.positions), start=Decimal(0))
        signed_net = sum(
            (
                item.notional if item.side == "LONG" else -item.notional
                for item in account.positions
            ),
            start=Decimal(0),
        )
        direction = Decimal(1) if intent.position_side == "LONG" else Decimal(-1)
        delta = direction * notional * (Decimal(-1) if intent.effect == "CLOSE" else Decimal(1))
        projected_gross = gross + (notional if intent.effect == "OPEN" else -notional)
        projected_net = signed_net + delta
        current_notional = current.notional if current is not None else Decimal(0)
        projected_position = current_notional + (notional if intent.effect == "OPEN" else -notional)

        if not market.minimum_contracts <= intent.contracts <= market.maximum_contracts:
            reasons.append("CONTRACT_QUANTITY_LIMIT")
        if intent.contracts % market.quantity_step != 0:
            reasons.append("CONTRACT_QUANTITY_STEP")
        if intent.limit_price % market.price_tick != 0:
            reasons.append("PRICE_TICK")
        if not market.minimum_notional <= notional <= market.maximum_notional:
            reasons.append("VENUE_NOTIONAL_LIMIT")
        if margin is not None and notional > margin.maximum_mark_notional:
            reasons.append("MARGIN_TIER_LIMIT")
        if intent.effect == "OPEN":
            if notional > policy.order_notional_limit:
                reasons.append("ORDER_NOTIONAL_LIMIT")
            if projected_position > policy.position_notional_limit:
                reasons.append("POSITION_NOTIONAL_LIMIT")
            if projected_gross > policy.total_gross_notional_limit:
                reasons.append("GROSS_NOTIONAL_LIMIT")
            if abs(projected_net) > policy.total_net_notional_limit:
                reasons.append("NET_NOTIONAL_LIMIT")
            if len(account.positions) + int(current is None) > policy.maximum_positions:
                reasons.append("POSITION_COUNT_LIMIT")
        if reserve > account.available_collateral or reserve > policy.collateral_limit:
            reasons.append("COLLATERAL_LIMIT")
        if (
            intent.effect == "OPEN"
            and reserve > account.equity * policy.maximum_collateral_fraction
        ):
            reasons.append("COLLATERAL_FRACTION_LIMIT")
        if intent.effect == "OPEN" and position.proposed_leverage > policy.maximum_leverage:
            reasons.append("LEVERAGE_LIMIT")
        if market.initial_margin_rate > policy.maximum_initial_margin_rate:
            reasons.append("INITIAL_MARGIN_RATE_LIMIT")
        if market.maintenance_margin_rate > policy.maximum_maintenance_margin_rate:
            reasons.append("MAINTENANCE_MARGIN_RATE_LIMIT")
        if (market.ask - market.bid) / market.bid > policy.maximum_spread_fraction:
            reasons.append("SPREAD_LIMIT")
        if abs(market.mark_price - market.index_price) / market.index_price > (
            policy.maximum_mark_index_deviation_fraction
        ):
            reasons.append("MARK_INDEX_DEVIATION_LIMIT")
        if abs(market.mark_price - market.index_price) / market.index_price > (
            policy.maximum_basis_fraction
        ):
            reasons.append("BASIS_LIMIT")
        if abs(intent.limit_price - market.mark_price) / market.mark_price > (
            policy.maximum_price_deviation_fraction
        ):
            reasons.append("PRICE_DEVIATION_LIMIT")
        if market.funding_rate is not None and abs(market.funding_rate) > (
            policy.maximum_funding_fraction
        ):
            reasons.append("FUNDING_LIMIT")
        if intent.effect == "OPEN":
            if (
                request.leverage.liquidation_distance_fraction is not None
                and request.leverage.liquidation_distance_fraction
                < policy.minimum_liquidation_buffer_fraction
            ):
                reasons.append("LIQUIDATION_BUFFER_LIMIT")
            if (
                request.leverage.liquidation_price is not None
                and abs(market.mark_price - request.leverage.liquidation_price) / market.mark_price
                < policy.minimum_liquidation_buffer_fraction
            ):
                reasons.append("CURRENT_LIQUIDATION_BUFFER_LIMIT")
        if (
            intent.effect == "OPEN"
            and request.leverage.maximum_modeled_loss is not None
            and request.leverage.maximum_modeled_loss / account.equity
            > policy.maximum_modeled_loss_fraction
        ):
            reasons.append("MODELED_LOSS_LIMIT")
        if (
            request.leverage.position_notional is not None
            and request.leverage.position_notional != notional
        ):
            reasons.append("ASSESSED_NOTIONAL_MISMATCH")
        if (
            intent.effect == "OPEN"
            and request.leverage.required_collateral is not None
            and request.leverage.required_collateral > account.available_collateral
        ):
            reasons.append("ASSESSED_COLLATERAL_UNAVAILABLE")
        loss = request.daily_start_equity + request.daily_net_flows - account.equity
        if intent.effect == "OPEN" and loss >= policy.daily_loss_limit:
            reasons.append("DAILY_LOSS_LIMIT")
        if account.equity > request.high_water_equity:
            reasons.append("HIGH_WATER_INCONSISTENT")
        elif (
            intent.effect == "OPEN"
            and (request.high_water_equity - account.equity) / request.high_water_equity
            >= policy.maximum_drawdown
        ):
            reasons.append("DRAWDOWN_LIMIT")

    return DerivativeRiskDecision(
        request_hash=digest(request),
        policy_hash=digest(policy),
        assessed_at=now,
        submission_permitted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        order_notional=notional,
        reserved_collateral=reserve,
        projected_gross_notional=max(projected_gross, Decimal(0)),
        projected_net_notional=projected_net,
    )
