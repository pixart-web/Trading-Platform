"""Spot admission only. Research risk approvals never grant native execution."""

from datetime import datetime
from decimal import ROUND_CEILING, Decimal, localcontext

from pocket_alpha.backtesting.models import digest
from pocket_alpha.broker_readonly.models import reconcile
from pocket_alpha.portfolio.models import PortfolioSnapshotStatus, PositionStatus
from pocket_alpha.spot_execution.models import SpotDecision, SpotPolicy, SpotRequest


def evaluate(
    request: SpotRequest,
    policy: SpotPolicy,
    *,
    now: datetime,
    broker_origin: str,
    killed: bool = False,
) -> SpotDecision:
    reasons: list[str] = []
    if broker_origin != "SYNTHETIC":
        reasons.append("FOUNDATION_LIVE_DISABLED")
    if (
        policy.mode != "SYNTHETIC_QUALIFICATION"
        or not policy.global_enable
        or not policy.manual_enable
    ):
        reasons.append("MANUAL_OR_GLOBAL_DISABLED")
    if killed:
        reasons.append("KILL_SWITCH")
    if not request.health_ready:
        reasons.append("DEPENDENCY_NOT_READY")
    if not request.independent_qualification:
        reasons.append("QUALIFICATION_MISSING")
    if request.observation.state.origin != broker_origin:
        reasons.append("ORIGIN_MISMATCH")
    reconciled = reconcile(
        request.observation,
        request.local_state,
        now=now,
        maximum_age_seconds=policy.maximum_data_age_seconds,
    )
    reasons.extend(
        x
        for x in reconciled.reasons
        if not (x == "NON_REAL_OBSERVATION" and broker_origin == "SYNTHETIC")
    )
    state = request.observation.state
    if state.account_identity_hash != policy.account_identity_hash:
        reasons.append("ACCOUNT_NOT_ALLOWED")
    if request.symbol not in policy.symbols:
        reasons.append("SYMBOL_NOT_ALLOWED")
    definition_hash = digest(request.strategy)
    proposal = request.proposal
    if definition_hash not in policy.strategy_hashes:
        reasons.append("STRATEGY_NOT_ALLOWED")
    if proposal.definition_hash != definition_hash or (
        proposal.market_id,
        proposal.asset_id,
        proposal.timeframe,
        proposal.horizon,
    ) != (
        request.strategy.market_id,
        request.strategy.asset_id,
        request.strategy.timeframe,
        request.strategy.horizon,
    ):
        reasons.append("STRATEGY_IDENTITY_MISMATCH")
    if request.intent.action not in {"BUY", "SELL"} or request.intent.quantity is None:
        reasons.append("UNSUPPORTED_INTENT")
    expected_action = "ENTER_LONG" if request.intent.action == "BUY" else "EXIT_LONG"
    if proposal.action != expected_action:
        reasons.append("PROPOSAL_ACTION_MISMATCH")
    if proposal.technical_input_hash is None or (
        request.intent.action == "BUY"
        and (proposal.forecast is None or proposal.directional is None)
    ):
        reasons.append("INTELLIGENCE_EVIDENCE_MISSING")
    if proposal.expires_at is None or not proposal.at <= now < proposal.expires_at:
        reasons.append("PROPOSAL_EXPIRED_OR_FUTURE")
    for at in (
        proposal.at,
        request.quote_at,
        request.loss_context_at,
        request.portfolio.as_of,
        request.portfolio.generated_at,
    ):
        if not 0 <= (now - at).total_seconds() <= policy.maximum_data_age_seconds:
            reasons.append("STALE_OR_FUTURE_INPUT")
    if request.loss_context_at.date() != now.date():
        reasons.append("LOSS_CONTEXT_WRONG_UTC_DAY")
    if state.open_orders:
        reasons.append("EXTERNAL_OPEN_ORDERS")
    instruments = {x.symbol: x for x in state.instruments}
    instrument = instruments.get(request.symbol)
    if instrument is None:
        reasons.append("INSTRUMENT_MISSING")
    elif (instrument.market_id, instrument.asset_id) != (proposal.market_id, proposal.asset_id):
        reasons.append("PRODUCT_IDENTITY_MISMATCH")
    if (
        any(x.quote_asset != policy.quote_asset for x in state.instruments)
        or request.portfolio.base_currency != policy.quote_asset
    ):
        reasons.append("CURRENCY_MISMATCH")
    portfolio = request.portfolio
    positions = {
        x.market.market_id: x for x in portfolio.positions if x.status == PositionStatus.OPEN
    }
    balances = {x.asset: x for x in state.balances}
    quote = balances.get(policy.quote_asset)
    if quote is None or quote.spot_position_quantity != portfolio.cash_balance:
        reasons.append("PORTFOLIO_CASH_MISMATCH")
    represented: set[str] = {policy.quote_asset}
    for product in state.instruments:
        balance = balances.get(product.base_asset)
        position = positions.get(product.market_id)
        quantity = balance.spot_position_quantity if balance else Decimal(0)
        represented.add(product.base_asset)
        if quantity > 0 and (
            position is None
            or position.quantity != quantity
            or position.market.asset_id != product.asset_id
            or position.market.quote_currency != product.quote_asset
            or position.market.asset_type.value != "CRYPTO"
        ):
            reasons.append("PORTFOLIO_POSITION_MISMATCH")
        if position is not None and quantity != position.quantity:
            reasons.append("PORTFOLIO_POSITION_MISMATCH")
    if any(
        x.spot_position_quantity > 0 and x.asset not in represented for x in state.balances
    ) or any(x not in {p.market_id for p in state.instruments} for x in positions):
        reasons.append("UNVALUED_OR_UNKNOWN_HOLDING")
    if len({x.base_asset for x in state.instruments}) != len(state.instruments):
        reasons.append("AMBIGUOUS_BASE_ASSET_MAPPING")
    if (
        portfolio.status != PortfolioSnapshotStatus.COMPLETE
        or portfolio.equity is None
        or portfolio.total_market_value is None
    ):
        reasons.append("PORTFOLIO_NOT_VALUED")
    for position in positions.values():
        if (
            position.price_available_at is None
            or not 0
            <= (now - position.price_available_at).total_seconds()
            <= policy.maximum_data_age_seconds
        ):
            reasons.append("POSITION_MARK_NOT_CURRENT")
    with localcontext() as context:
        context.prec = 80
        quantity = request.intent.quantity or Decimal(0)
        notional = quantity * request.limit_price
        reserve = (notional * (1 + policy.maximum_fee_fraction)).quantize(
            Decimal("1e-18"), rounding=ROUND_CEILING
        )
        if request.ask < request.bid:
            reasons.append("CROSSED_QUOTE")
        elif (request.ask - request.bid) / request.bid > policy.maximum_spread_fraction:
            reasons.append("SPREAD_LIMIT")
        reference = proposal.reference_price
        if (
            reference is None
            or abs(request.limit_price - reference) / reference
            > policy.maximum_price_deviation_fraction
        ):
            reasons.append("PRICE_DEVIATION_LIMIT")
        if instrument is not None and (
            quantity % instrument.quantity_step != 0
            or request.limit_price % instrument.price_tick != 0
        ):
            reasons.append("PRICE_OR_QUANTITY_STEP")
        if notional > policy.order_notional_limit:
            reasons.append("ORDER_NOTIONAL_LIMIT")
        if request.intent.action == "BUY" and (quote is None or reserve > quote.free):
            reasons.append("INSUFFICIENT_CASH")
        if request.intent.action == "SELL" and (
            instrument is None
            or instrument.base_asset not in balances
            or quantity > balances[instrument.base_asset].free
        ):
            reasons.append("SPOT_INVENTORY_LIMIT")
        current = positions.get(instrument.market_id) if instrument else None
        exposure = portfolio.total_market_value or Decimal(0)
        projected = exposure + (reserve if request.intent.action == "BUY" else Decimal(0))
        if projected > policy.capital_limit:
            reasons.append("CAPITAL_LIMIT")
        if projected > policy.total_exposure_limit:
            reasons.append("TOTAL_EXPOSURE_LIMIT")
        position_exposure = (current.market_value or Decimal(0)) if current else Decimal(0)
        if (
            request.intent.action == "BUY"
            and position_exposure + reserve > policy.position_notional_limit
        ):
            reasons.append("POSITION_NOTIONAL_LIMIT")
        if (
            len(positions) + int(request.intent.action == "BUY" and current is None)
            > policy.maximum_positions
        ):
            reasons.append("POSITION_COUNT_LIMIT")
        equity = portfolio.equity or Decimal(0)
        loss = request.daily_start_equity + request.daily_net_flows - equity
        if loss >= policy.daily_loss_limit:
            reasons.append("DAILY_LOSS_LIMIT")
        if equity > request.high_water_equity:
            reasons.append("HIGH_WATER_INCONSISTENT")
        elif (
            request.high_water_equity - equity
        ) / request.high_water_equity >= policy.maximum_drawdown:
            reasons.append("DRAWDOWN_LIMIT")
    return SpotDecision(
        request_hash=digest(request),
        policy_hash=digest(policy),
        assessed_at=now,
        submission_permitted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        reserved_notional=reserve,
    )
