"""Conditional isolated linear mark-margin research. Never an execution/risk approval."""

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.derivatives.models import ContractKind, MultiplierUnit, Settlement
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.leverage.models import (
    AssessmentStatus,
    LeverageAssessment,
    LeverageRequest,
    StressKind,
    StressResult,
)

D = Decimal
ZERO = D(0)


class LeverageResearch:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def assess(self, request: LeverageRequest) -> LeverageAssessment:
        with localcontext(Context(prec=160, rounding=ROUND_HALF_EVEN)):
            request = LeverageRequest.model_validate_json(request.model_dump_json())
            now = utc(self.clock.now())
            if request.as_of > now:
                raise ValueError("leverage research cutoff is in the future")
            reasons = self._inputs(request)
            metrics: dict[str, Any] = dict.fromkeys(
                (
                    "base_units",
                    "position_notional",
                    "required_collateral",
                    "stop_distance_fraction",
                    "liquidation_price",
                    "liquidation_distance_fraction",
                    "volatility",
                    "expected_transaction_costs",
                    "modeled_stop_loss",
                    "maximum_modeled_loss",
                    "portfolio_risk_fraction",
                )
            )
            stresses: tuple[StressResult, ...] = ()
            warnings: tuple[str, ...] = ()
            status = AssessmentStatus.REJECTED
            if not reasons:
                metrics, stresses, reasons, warnings, status = self._evaluate(request)
            data = dict(
                assessment_id=uuid5(NAMESPACE_URL, "pocket-alpha-leverage:" + digest(request)),
                generated_at=now,
                request=request,
                input_hash=digest(request),
                status=status,
                rejection_reasons=tuple(sorted(set(reasons))),
                warnings=warnings,
                stresses=stresses,
                **metrics,
            )
            draft = LeverageAssessment.model_construct(**cast(Any, data), content_hash="0" * 64)
            return LeverageAssessment.model_validate(
                draft.model_dump()
                | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
            )

    def _inputs(self, r: LeverageRequest) -> list[str]:
        p, at = r.position, r.as_of
        contract = p.contract
        reasons: list[str] = []
        if p.proposal_at > at or contract.ingested_at > at:
            reasons.append("FUTURE_PROPOSAL_OR_CONTRACT")
        if contract.expires_at is not None and expires_at(at, p.horizon) >= contract.expires_at:
            reasons.append("CONTRACT_EXPIRES_WITHIN_HORIZON")
        if (
            contract.kind not in {ContractKind.PERPETUAL, ContractKind.FUTURE}
            or contract.multiplier_unit != MultiplierUnit.BASE_UNITS_PER_CONTRACT
            or contract.settlement != Settlement.CASH
            or contract.quote_currency != contract.settlement_currency
            or contract.reference_index_currency != contract.settlement_currency
            or contract.margin_scheme != "ISOLATED"
        ):
            reasons.append("UNSUPPORTED_CONTRACT_OR_MARGIN")
        if (p.side == "LONG" and p.stop >= p.entry) or (p.side == "SHORT" and p.stop <= p.entry):
            reasons.append("INVALID_DIRECTIONAL_STOP")
        if p.proposed_leverage > r.policy.maximum_leverage:
            reasons.append("LEVERAGE_LIMIT")
        age = r.policy.maximum_input_age_seconds
        if (at - p.proposal_at).total_seconds() > age:
            reasons.append("STALE_PROPOSAL")
        portfolio, risk, margin, vol, costs = (
            r.portfolio,
            r.prior_risk,
            r.margin,
            r.volatility,
            r.costs,
        )
        if any(value is None for value in (portfolio, risk, margin, vol, costs)):
            reasons.append("MISSING_REQUIRED_INPUT")
            return reasons
        assert portfolio is not None and risk is not None and margin is not None
        assert vol is not None and costs is not None
        if {portfolio.origin, risk.origin, vol.origin} != {r.origin}:
            reasons.append("MIXED_DATA_ORIGIN")
        if any(
            t > at
            for t in (
                portfolio.available_at,
                risk.assessed_at,
                margin.available_at,
                vol.available_at,
                costs.available_at,
            )
        ):
            reasons.append("FUTURE_EVIDENCE")
        if any(
            (at - t).total_seconds() > age
            for t in (portfolio.at, risk.assessed_at, vol.observed_at, costs.available_at)
        ):
            reasons.append("STALE_EVIDENCE")
        if not risk.passed or risk.valid_until <= at:
            reasons.append("PRIOR_RESEARCH_RISK_NOT_READY")
        if risk.assessed_at < max(p.proposal_at, portfolio.available_at):
            reasons.append("PRIOR_RISK_CAUSALITY")
        if vol.contract_hash != digest(contract) or costs.contract_hash != digest(contract):
            reasons.append("VOLATILITY_OR_COST_CONTRACT_MISMATCH")
        if risk.proposal_hash != digest(p) or risk.portfolio_hash != digest(portfolio):
            reasons.append("PRIOR_RISK_BINDING_MISMATCH")
        if margin.contract_hash != digest(contract) or margin.valid_until < expires_at(
            at, p.horizon
        ):
            reasons.append("MARGIN_IDENTITY_OR_VALIDITY")
        if portfolio.currency != contract.settlement_currency:
            reasons.append("COLLATERAL_CURRENCY_MISMATCH")
        if (vol.timeframe, vol.horizon, costs.horizon) != (p.timeframe, p.horizon, p.horizon):
            reasons.append("HORIZON_OR_TIMEFRAME_MISMATCH")
        if contract.kind == ContractKind.FUTURE and (
            costs.adverse_funding_fraction
            or any(s.additional_funding_fraction for s in r.policy.scenarios)
        ):
            reasons.append("FUNDING_UNSUPPORTED_FOR_DATED_FUTURE")
        if contract.kind == ContractKind.PERPETUAL and any(
            s.kind == StressKind.FUNDING and s.additional_funding_fraction <= 0
            for s in r.policy.scenarios
        ):
            reasons.append("FUNDING_STRESS_NOT_EXERCISED")
        closing = (costs.exit_fee_bps + costs.spread_bps / 2 + costs.slippage_bps) / 10000
        if margin.maintenance_margin_rate + margin.liquidation_fee_rate + closing >= 1:
            reasons.append("INVALID_MARGIN_RESERVE_RATE")
        if any(
            margin.maintenance_margin_rate
            + margin.liquidation_fee_rate
            + closing
            + s.additional_slippage_bps / 10000
            >= 1
            for s in r.policy.scenarios
        ):
            reasons.append("STRESS_MARGIN_RESERVE_UNSUPPORTED")
        if 1 / p.proposed_leverage < margin.initial_margin_rate:
            reasons.append("INITIAL_MARGIN_LEVERAGE_LIMIT")
        return reasons

    def _evaluate(
        self, r: LeverageRequest
    ) -> tuple[
        dict[str, Any], tuple[StressResult, ...], list[str], tuple[str, ...], AssessmentStatus
    ]:
        p, margin, costs, portfolio, vol = r.position, r.margin, r.costs, r.portfolio, r.volatility
        assert (
            margin is not None and costs is not None and portfolio is not None and vol is not None
        )
        units = p.contracts * p.contract.multiplier
        notional = units * p.entry
        collateral = notional / p.proposed_leverage
        stop_distance = abs(p.entry - p.stop) / p.entry
        opening_rate = (costs.entry_fee_bps + costs.spread_bps / 2 + costs.slippage_bps) / 10000
        close_rate = (costs.exit_fee_bps + costs.spread_bps / 2 + costs.slippage_bps) / 10000
        mm = margin.maintenance_margin_rate

        def liquidation(funding: Decimal, additional_slippage: Decimal = ZERO) -> Decimal:
            # Solve isolated equity == maintenance + modeled closing/liquidation reserve.
            remaining = collateral - notional * (opening_rate + funding + additional_slippage)
            reserve = mm + margin.liquidation_fee_rate + close_rate + additional_slippage
            if reserve >= 1:
                raise ValueError("stress closing reserve rate outside linear model")
            if p.side == "LONG":
                return max(D(0), (notional - remaining) / (units * (1 - reserve)))
            return max(D(0), (notional + remaining) / (units * (1 + reserve)))

        base_liq = liquidation(costs.adverse_funding_fraction)
        liq_distance = (
            (p.entry - base_liq) / p.entry if p.side == "LONG" else (base_liq - p.entry) / p.entry
        )
        expected_cost = (
            notional * (opening_rate + costs.adverse_funding_fraction) + units * p.stop * close_rate
        )
        stop_loss = units * abs(p.entry - p.stop) + expected_cost
        reasons: list[str] = []
        if max(notional, units * base_liq) > margin.maximum_mark_notional:
            reasons.append("MARGIN_TIER_UNSUPPORTED")
        if notional > r.policy.maximum_position_notional:
            reasons.append("POSITION_NOTIONAL_LIMIT")
        if collateral > portfolio.available_collateral:
            reasons.append("INSUFFICIENT_COLLATERAL")
        if collateral / portfolio.equity > r.policy.maximum_collateral_fraction:
            reasons.append("COLLATERAL_ALLOCATION_LIMIT")
        if liq_distance <= stop_distance + r.policy.minimum_liquidation_buffer_fraction:
            reasons.append("STOP_LIQUIDATION_BUFFER")
        if liq_distance <= 0:
            reasons.append("INITIAL_MARGIN_EXHAUSTED")
        results: list[StressResult] = []
        for scenario in r.policy.scenarios:
            funding = costs.adverse_funding_fraction + scenario.additional_funding_fraction
            slip = scenario.additional_slippage_bps / 10000
            lp = liquidation(funding, slip)
            adverse = max(
                stop_distance,
                scenario.adverse_gap_fraction + vol.value * scenario.volatility_multiple,
            )
            if scenario.kind == StressKind.LIQUIDATION:
                adverse = max(
                    adverse,
                    1 / p.proposed_leverage + r.policy.forced_liquidation_overshoot_fraction,
                )
            mark = (
                max(D(0), p.entry * (1 - adverse)) if p.side == "LONG" else p.entry * (1 + adverse)
            )
            liquidated = mark <= lp if p.side == "LONG" else mark >= lp
            funding_cost = notional * funding
            transactions = notional * (opening_rate + slip) + units * mark * (
                close_rate + slip + (margin.liquidation_fee_rate if liquidated else D(0))
            )
            position_loss = units * abs(p.entry - mark) + transactions + funding_cost
            correlated = portfolio.equity * scenario.other_portfolio_loss_fraction
            combined = position_loss + correlated
            deficit = max(D(0), position_loss - collateral)
            tier_ok = (
                max(notional, units * mark, units * max(D(0), lp)) <= margin.maximum_mark_notional
            )
            if not tier_ok:
                reasons.append("MARGIN_TIER_UNSUPPORTED")
            if (
                liquidated
                and scenario.kind != StressKind.LIQUIDATION
                and r.policy.reject_standard_liquidation
            ):
                reasons.append("STANDARD_STRESS_LIQUIDATION")
            if deficit > 0 and r.policy.reject_collateral_deficit:
                reasons.append("COLLATERAL_DEFICIT")
            results.append(
                StressResult(
                    name=scenario.name,
                    kind=scenario.kind,
                    adverse_fraction=adverse,
                    exit_mark=mark,
                    liquidation_price=lp,
                    liquidated=liquidated,
                    transaction_costs=transactions,
                    funding_cost=funding_cost,
                    modeled_position_loss=position_loss,
                    correlated_loss=correlated,
                    combined_portfolio_loss=combined,
                    portfolio_loss_fraction=combined / portfolio.equity,
                    collateral_deficit=deficit,
                    projected_portfolio_equity=portfolio.equity - combined,
                    ruin_scenario=combined >= portfolio.equity,
                    tier_applicable=tier_ok,
                )
            )
        maximum_loss = max([stop_loss] + [s.combined_portfolio_loss for s in results])
        fraction = maximum_loss / portfolio.equity
        if fraction >= r.policy.maximum_loss_fraction:
            reasons.append("PORTFOLIO_LOSS_LIMIT")
        if any(s.ruin_scenario for s in results):
            reasons.append("MODELED_PORTFOLIO_RUIN")
        status = (
            AssessmentStatus.REJECTED
            if reasons
            else (
                AssessmentStatus.HIGH_RISK
                if fraction >= r.policy.high_loss_fraction
                else AssessmentStatus.ELEVATED
                if fraction >= r.policy.elevated_loss_fraction
                else AssessmentStatus.ACCEPTABLE
            )
        )
        metrics = dict(
            base_units=units,
            position_notional=notional,
            required_collateral=collateral,
            stop_distance_fraction=stop_distance,
            liquidation_price=base_liq,
            liquidation_distance_fraction=liq_distance,
            volatility=vol.value,
            expected_transaction_costs=expected_cost,
            modeled_stop_loss=stop_loss,
            maximum_modeled_loss=maximum_loss,
            portfolio_risk_fraction=fraction,
        )
        warnings = (
            "CONDITIONAL_MARGIN_MODEL",
            "STRESS_NOT_PROBABILITY",
            "STOP_FILL_NOT_GUARANTEED",
            "NO_EXECUTION_AUTHORIZATION",
        )
        return metrics, tuple(results), reasons, warnings, status
