"""Synthetic arithmetic/contract regressions only; never venue estimates or profitability."""

from datetime import timedelta
from decimal import Context, localcontext
from decimal import Decimal as D
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.derivatives.models import ContractKind, DerivativeContract
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.leverage.engine import LeverageResearch
from pocket_alpha.leverage.models import (
    AssessmentStatus,
    LeverageAssessment,
    StressKind,
)
from tests.leverage_fixtures import AT, CLOCK, bound, request
from tests.test_derivatives import spec


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_isolated_linear_equity_equation_and_costs(side: str) -> None:
    value = request(side)
    report = LeverageResearch(CLOCK).assess(value)
    assert report.status == AssessmentStatus.ACCEPTABLE and not report.rejection_reasons
    assert (
        report.base_units == 1
        and report.position_notional == 100
        and report.required_collateral == 50
    )
    assert report.stop_distance_fraction == D("0.02") and report.volatility == D("0.01")
    assert report.liquidation_price is not None
    # Independent accounting oracle: opening fee+spread/slip=.25; funding=.10;
    # reserve = maintenance .01 + liquidation .005 + closing execution .0025.
    with localcontext(Context(prec=160)):
        lp = report.liquidation_price
        remaining = D("49.65")
        equity = remaining + (lp - 100 if side == "LONG" else 100 - lp)
        assert abs(equity - lp * D("0.0175")) < D("1e-150")
    expected_cost = D("0.35") + value.position.stop * D("0.0025")
    assert report.expected_transaction_costs == expected_cost
    assert report.modeled_stop_loss == 2 + expected_cost
    assert {s.kind for s in report.stresses} == set(StressKind)
    forced = next(s for s in report.stresses if s.kind == StressKind.LIQUIDATION)
    assert forced.liquidated and forced.collateral_deficit > 0
    assert report.maximum_modeled_loss == max(s.combined_portfolio_loss for s in report.stresses)
    with localcontext(Context(prec=160)):
        for result in report.stresses:
            assert (
                result.modeled_position_loss
                == abs(D(100) - result.exit_mark) + result.transaction_costs + result.funding_cost
            )
            assert (
                result.combined_portfolio_loss
                == result.modeled_position_loss + result.correlated_loss
            )
            assert result.projected_portfolio_equity == D(10000) - result.combined_portfolio_loss
    assert (
        report.ruin_probability is None
        and not report.execution_authorized
        and not report.live_ready
    )


@pytest.mark.parametrize("field", ["portfolio", "prior_risk", "margin", "volatility", "costs"])
def test_missing_required_evidence_has_no_fabricated_metrics(field: str) -> None:
    report = LeverageResearch(CLOCK).assess(request().model_copy(update={field: None}))
    assert (
        report.status == AssessmentStatus.REJECTED
        and "MISSING_REQUIRED_INPUT" in report.rejection_reasons
    )
    assert (
        report.maximum_modeled_loss is None
        and report.liquidation_price is None
        and report.stresses == ()
    )


@pytest.mark.parametrize(
    "case,reason",
    [
        ("proposal-future", "FUTURE_PROPOSAL_OR_CONTRACT"),
        ("contract-future", "FUTURE_PROPOSAL_OR_CONTRACT"),
        ("stop", "INVALID_DIRECTIONAL_STOP"),
        ("leverage", "LEVERAGE_LIMIT"),
        ("proposal-stale", "STALE_PROPOSAL"),
        ("origin", "MIXED_DATA_ORIGIN"),
        ("evidence-future", "FUTURE_EVIDENCE"),
        ("evidence-stale", "STALE_EVIDENCE"),
        ("risk-failed", "PRIOR_RESEARCH_RISK_NOT_READY"),
        ("risk-expired", "PRIOR_RESEARCH_RISK_NOT_READY"),
        ("risk-binding", "PRIOR_RISK_BINDING_MISMATCH"),
        ("risk-before-proposal", "PRIOR_RISK_CAUSALITY"),
        ("margin-binding", "MARGIN_IDENTITY_OR_VALIDITY"),
        ("margin-expired", "MARGIN_IDENTITY_OR_VALIDITY"),
        ("vol-binding", "VOLATILITY_OR_COST_CONTRACT_MISMATCH"),
        ("cost-binding", "VOLATILITY_OR_COST_CONTRACT_MISMATCH"),
        ("currency", "COLLATERAL_CURRENCY_MISMATCH"),
        ("horizon", "HORIZON_OR_TIMEFRAME_MISMATCH"),
        ("timeframe", "HORIZON_OR_TIMEFRAME_MISMATCH"),
        ("reserve", "INVALID_MARGIN_RESERVE_RATE"),
        ("initial-margin", "INITIAL_MARGIN_LEVERAGE_LIMIT"),
        ("stress-reserve", "STRESS_MARGIN_RESERVE_UNSUPPORTED"),
        ("funding-inactive", "FUNDING_STRESS_NOT_EXERCISED"),
    ],
)
def test_causal_identity_and_readiness_guards(case: str, reason: str) -> None:
    value = request()
    portfolio, risk, margin, vol, costs = (
        value.portfolio,
        value.prior_risk,
        value.margin,
        value.volatility,
        value.costs,
    )
    assert portfolio is not None and risk is not None and margin is not None
    assert vol is not None and costs is not None
    updates: dict[str, object]
    if case.startswith("proposal-"):
        delta = 1 if case == "proposal-future" else -61
        value = value.model_copy(
            update={
                "position": value.position.model_copy(
                    update={"proposal_at": AT + timedelta(seconds=delta)}
                )
            }
        )
    elif case == "contract-future":
        contract = value.position.contract.model_copy(
            update={"ingested_at": AT + timedelta(seconds=1)}
        )
        value = value.model_copy(
            update={"position": value.position.model_copy(update={"contract": contract})}
        )
    elif case in {"stop", "leverage"}:
        value = value.model_copy(
            update={
                "position": value.position.model_copy(
                    update={"stop": D(101)} if case == "stop" else {"proposed_leverage": D(11)}
                )
            }
        )
    elif case in {"origin", "evidence-future", "evidence-stale", "currency"}:
        updates = (
            {"origin": "REAL"}
            if case == "origin"
            else {"currency": "EUR"}
            if case == "currency"
            else {"available_at": AT + timedelta(seconds=1)}
            if case == "evidence-future"
            else {"at": AT - timedelta(seconds=61)}
        )
        value = value.model_copy(update={"portfolio": portfolio.model_copy(update=updates)})
    elif case.startswith("risk-"):
        updates = (
            {"passed": False}
            if case == "risk-failed"
            else {"valid_until": AT, "assessed_at": AT - timedelta(seconds=1)}
            if case == "risk-expired"
            else {"portfolio_hash": "a" * 64}
            if case == "risk-binding"
            else {"assessed_at": AT - timedelta(seconds=1)}
        )
        value = value.model_copy(update={"prior_risk": risk.model_copy(update=updates)})
    elif case in {"margin-binding", "margin-expired", "initial-margin", "reserve"}:
        updates = (
            {"contract_hash": "a" * 64}
            if case == "margin-binding"
            else {"valid_until": AT + timedelta(hours=1)}
            if case == "margin-expired"
            else {"initial_margin_rate": D("0.6")}
            if case == "initial-margin"
            else {
                "initial_margin_rate": D(1),
                "maintenance_margin_rate": D("0.9"),
                "liquidation_fee_rate": D("0.2"),
            }
        )
        value = value.model_copy(update={"margin": margin.model_copy(update=updates)})
    elif case in {"vol-binding", "horizon", "timeframe"}:
        updates = (
            {"contract_hash": "a" * 64}
            if case == "vol-binding"
            else {"horizon": ForecastHorizon.H1}
            if case == "horizon"
            else {"timeframe": Timeframe.M1}
        )
        value = value.model_copy(update={"volatility": vol.model_copy(update=updates)})
    elif case == "cost-binding":
        value = value.model_copy(
            update={"costs": costs.model_copy(update={"contract_hash": "a" * 64})}
        )
    else:
        scenarios = tuple(
            s.model_copy(update={"additional_slippage_bps": D(10000)})
            if case == "stress-reserve"
            else s.model_copy(update={"additional_funding_fraction": D(0)})
            if s.kind == StressKind.FUNDING
            else s
            for s in value.policy.scenarios
        )
        value = value.model_copy(
            update={"policy": value.policy.model_copy(update={"scenarios": scenarios})}
        )
    report = LeverageResearch(CLOCK).assess(value)
    assert report.status == AssessmentStatus.REJECTED and reason in report.rejection_reasons
    assert report.stresses == () and report.maximum_modeled_loss is None


@pytest.mark.parametrize(
    "change", ["cross", "inverse", "physical", "currency", "index", "option", "expiry"]
)
def test_unsupported_instrument_models_reject(change: str) -> None:
    value = request()
    contract = value.position.contract
    updates: dict[str, object] = {}
    if change == "option":
        contract = DerivativeContract.model_validate(
            spec(kind=ContractKind.OPTION).model_dump() | {"available_at": AT, "ingested_at": AT}
        )
    elif change == "expiry":
        contract = DerivativeContract.model_validate(
            spec(
                kind=ContractKind.FUTURE,
                margin_scheme="ISOLATED",
                expires_at=AT + timedelta(hours=4),
            ).model_dump()
            | {"available_at": AT, "ingested_at": AT}
        )
    else:
        updates = (
            {"margin_scheme": "CROSS"}
            if change == "cross"
            else {"multiplier_unit": "QUOTE_CURRENCY_PER_CONTRACT"}
            if change == "inverse"
            else {"settlement": "PHYSICAL"}
            if change == "physical"
            else {"settlement_currency": "EUR"}
            if change == "currency"
            else {"reference_index_currency": "EUR"}
        )
        contract = DerivativeContract.model_validate(contract.model_dump() | updates)
    report = LeverageResearch(CLOCK).assess(
        bound(
            value.model_copy(
                update={"position": value.position.model_copy(update={"contract": contract})}
            )
        )
    )
    assert report.status == AssessmentStatus.REJECTED
    assert (
        "CONTRACT_EXPIRES_WITHIN_HORIZON"
        if change == "expiry"
        else "UNSUPPORTED_CONTRACT_OR_MARGIN"
    ) in report.rejection_reasons


@pytest.mark.parametrize(
    "case,reason",
    [
        ("notional", "POSITION_NOTIONAL_LIMIT"),
        ("collateral", "INSUFFICIENT_COLLATERAL"),
        ("allocation", "COLLATERAL_ALLOCATION_LIMIT"),
        ("buffer", "STOP_LIQUIDATION_BUFFER"),
        ("exhausted", "INITIAL_MARGIN_EXHAUSTED"),
        ("tier", "MARGIN_TIER_UNSUPPORTED"),
        ("gap", "STANDARD_STRESS_LIQUIDATION"),
        ("deficit", "COLLATERAL_DEFICIT"),
        ("loss", "PORTFOLIO_LOSS_LIMIT"),
        ("ruin", "MODELED_PORTFOLIO_RUIN"),
    ],
)
def test_financial_limits_and_stress_rejections(case: str, reason: str) -> None:
    value = request()
    portfolio, margin, costs = value.portfolio, value.margin, value.costs
    assert portfolio is not None and margin is not None and costs is not None
    if case == "collateral":
        value = bound(
            value.model_copy(
                update={"portfolio": portfolio.model_copy(update={"available_collateral": D(1)})}
            )
        )
    elif case == "exhausted":
        value = value.model_copy(
            update={"costs": costs.model_copy(update={"adverse_funding_fraction": D("0.6")})}
        )
    elif case == "tier":
        value = value.model_copy(
            update={"margin": margin.model_copy(update={"maximum_mark_notional": D(10)})}
        )
    elif case == "gap":
        scenarios = tuple(
            s.model_copy(update={"adverse_gap_fraction": D(2)}) if s.kind == StressKind.GAP else s
            for s in value.policy.scenarios
        )
        value = value.model_copy(
            update={"policy": value.policy.model_copy(update={"scenarios": scenarios})}
        )
    elif case == "ruin":
        value = bound(
            value.model_copy(
                update={
                    "portfolio": portfolio.model_copy(
                        update={"equity": D(1), "available_collateral": D(1)}
                    )
                }
            )
        )
    else:
        updates = (
            {"maximum_position_notional": D(50)}
            if case == "notional"
            else {"maximum_collateral_fraction": D("0.001")}
            if case == "allocation"
            else {"minimum_liquidation_buffer_fraction": D("0.5")}
            if case == "buffer"
            else {"reject_collateral_deficit": True}
            if case == "deficit"
            else {
                "elevated_loss_fraction": D("0.001"),
                "high_loss_fraction": D("0.002"),
                "maximum_loss_fraction": D("0.003"),
            }
        )
        value = value.model_copy(update={"policy": value.policy.model_copy(update=updates)})
    report = LeverageResearch(CLOCK).assess(value)
    assert report.status == AssessmentStatus.REJECTED and reason in report.rejection_reasons
    assert report.maximum_modeled_loss is not None and report.stresses
    if case == "gap":
        gap = next(s for s in report.stresses if s.kind == StressKind.GAP)
        assert gap.exit_mark == 0 and gap.liquidated and gap.collateral_deficit > 0
    if case == "ruin":
        assert any(s.ruin_scenario and s.projected_portfolio_equity < 0 for s in report.stresses)


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_context_independence_determinism_and_monetary_precision(side: str) -> None:
    value = request(side)
    service = LeverageResearch(CLOCK)
    baseline = service.assess(value)
    with localcontext(Context(prec=4)):
        assert service.assess(value) == baseline
    assert service.assess(value).content_hash == baseline.content_hash
    later = LeverageResearch(FrozenClock(AT + timedelta(seconds=1))).assess(value)
    assert (
        later.assessment_id == baseline.assessment_id
        and later.content_hash != baseline.content_hash
    )
    with pytest.raises(ValueError, match="future"):
        LeverageResearch(FrozenClock(AT - timedelta(seconds=1))).assess(value)


@pytest.mark.parametrize(
    "status,elevated,high",
    [(AssessmentStatus.ELEVATED, ".004", ".01"), (AssessmentStatus.HIGH_RISK, ".001", ".004")],
)
def test_configured_risk_bands(status: AssessmentStatus, elevated: str, high: str) -> None:
    value = request()
    value = value.model_copy(
        update={
            "policy": value.policy.model_copy(
                update={"elevated_loss_fraction": D(elevated), "high_loss_fraction": D(high)}
            )
        }
    )
    assert LeverageResearch(CLOCK).assess(value).status == status


@pytest.mark.parametrize(
    "case", ["hash", "input", "identity", "time", "status", "live", "authorization", "probability"]
)
def test_immutable_assessment_contract_tampering(case: str) -> None:
    report = LeverageResearch(CLOCK).assess(request())
    data = report.model_dump(mode="json", exclude={"content_hash"})
    if case == "hash":
        data["status"] = "HIGH_RISK"
    elif case == "input":
        data["input_hash"] = "a" * 64
    elif case == "identity":
        data["assessment_id"] = str(uuid4())
    elif case == "time":
        data["generated_at"] = (AT - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    elif case == "status":
        data["status"] = "REJECTED"
    elif case == "probability":
        data["ruin_probability"] = "0.1"
    else:
        data["live_ready" if case == "live" else "execution_authorized"] = True
    with pytest.raises(ValidationError):
        LeverageAssessment.model_validate(
            data | {"content_hash": report.content_hash if case == "hash" else digest(data)}
        )


@pytest.mark.parametrize(
    "case",
    [
        "bands",
        "missing-stress",
        "duplicate",
        "inactive",
        "negative",
        "nan",
        "confidence",
        "portfolio",
        "risk-time",
        "margin-time",
        "mm",
        "vol-time",
    ],
)
def test_input_schemas_fail_closed(case: str) -> None:
    value = request()
    data = value.model_dump(mode="json")
    if case == "bands":
        data["policy"]["high_loss_fraction"] = "0.001"
    elif case == "missing-stress":
        data["policy"]["scenarios"] = data["policy"]["scenarios"][:-1]
    elif case == "duplicate":
        data["policy"]["scenarios"][1]["name"] = data["policy"]["scenarios"][0]["name"]
    elif case == "inactive":
        data["policy"]["scenarios"][0]["adverse_gap_fraction"] = "0"
    elif case in {"negative", "nan"}:
        data["position"]["entry"] = "-1" if case == "negative" else "NaN"
    elif case == "confidence":
        data["position"]["confidence"] = "0.99"
    elif case == "portfolio":
        data["portfolio"]["available_collateral"] = "10001"
    elif case == "risk-time":
        data["prior_risk"]["valid_until"] = data["prior_risk"]["assessed_at"]
    elif case == "margin-time":
        data["margin"]["valid_until"] = data["margin"]["available_at"]
    elif case == "mm":
        data["margin"]["maintenance_margin_rate"] = ".9"
    else:
        data["volatility"]["available_at"] = (AT - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValidationError):
        type(value).model_validate(data)


def test_dated_future_without_funding_and_one_times_long_boundary() -> None:
    value = request()
    assert value.margin is not None and value.volatility is not None and value.costs is not None
    contract = value.position.contract.model_copy(
        update={"kind": ContractKind.FUTURE, "expires_at": AT + timedelta(days=365)}
    )
    position = value.position.model_copy(update={"contract": contract, "proposed_leverage": D(1)})
    value = bound(
        value.model_copy(
            update={
                "position": position,
                "margin": value.margin.model_copy(
                    update={
                        "contract_hash": digest(contract),
                        "maintenance_margin_rate": D(0),
                        "liquidation_fee_rate": D(0),
                    }
                ),
                "volatility": value.volatility.model_copy(
                    update={"contract_hash": digest(contract)}
                ),
                "costs": value.costs.model_copy(
                    update={
                        "contract_hash": digest(contract),
                        "entry_fee_bps": D(0),
                        "exit_fee_bps": D(0),
                        "spread_bps": D(0),
                        "slippage_bps": D(0),
                        "adverse_funding_fraction": D(0),
                    }
                ),
                "policy": value.policy.model_copy(
                    update={
                        "scenarios": tuple(
                            s.model_copy(update={"additional_funding_fraction": D(0)})
                            for s in value.policy.scenarios
                        )
                    }
                ),
            }
        )
    )
    report = LeverageResearch(CLOCK).assess(value)
    assert report.status == AssessmentStatus.ELEVATED and report.liquidation_price == 0
    assert report.liquidation_distance_fraction == 1
    assert all(s.funding_cost == 0 for s in report.stresses)
    assert value.costs is not None
    funded = value.model_copy(
        update={"costs": value.costs.model_copy(update={"adverse_funding_fraction": D("0.01")})}
    )
    assert (
        "FUNDING_UNSUPPORTED_FOR_DATED_FUTURE"
        in LeverageResearch(CLOCK).assess(funded).rejection_reasons
    )


def test_full_family_coverage_requires_all_six_kinds() -> None:
    value = request()
    data = value.model_dump(mode="json")
    data["policy"]["scenarios"][-1]["kind"] = "GAP"
    data["policy"]["scenarios"][-1]["adverse_gap_fraction"] = ".01"
    with pytest.raises(ValidationError, match="six stress"):
        type(value).model_validate(data)


@pytest.mark.parametrize(
    "field", ["confidence", "pocket_score", "opportunity_score", "forecast_probability"]
)
def test_scores_and_probabilities_cannot_supply_leverage(field: str) -> None:
    data = request().position.model_dump()
    data[field] = D("0.99")
    with pytest.raises(ValidationError, match="extra"):
        type(request().position).model_validate(data)


def test_rejected_status_requires_reasons_even_with_valid_hash() -> None:
    report = LeverageResearch(CLOCK).assess(request().model_copy(update={"prior_risk": None}))
    data = report.model_dump(mode="json", exclude={"content_hash"})
    data["status"] = "ACCEPTABLE"
    with pytest.raises(ValidationError, match="status"):
        LeverageAssessment.model_validate(data | {"content_hash": digest(data)})


def test_research_cannot_import_execution_or_strategy_routes() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "pocket_alpha" / "leverage"
    forbidden = {"execution", "brokers", "strategies", "paper_trading", "simulation"}
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not forbidden.intersection(node.module.split("."))
            if isinstance(node, ast.Import):
                assert all(
                    not forbidden.intersection(alias.name.split(".")) for alias in node.names
                )


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_higher_funding_slippage_and_volatility_never_hide_stress_loss(side: str) -> None:
    value = request(side)
    service = LeverageResearch(CLOCK)
    baseline = service.assess(value)
    assert value.costs is not None and value.volatility is not None
    shocked = value.model_copy(
        update={
            "costs": value.costs.model_copy(
                update={"adverse_funding_fraction": D(".02"), "slippage_bps": D(25)}
            ),
            "volatility": value.volatility.model_copy(update={"value": D(".1")}),
        }
    )
    stressed = service.assess(shocked)
    for original, changed in zip(baseline.stresses, stressed.stresses, strict=True):
        assert changed.modeled_position_loss >= original.modeled_position_loss
    assert stressed.maximum_modeled_loss is not None and baseline.maximum_modeled_loss is not None
    assert stressed.maximum_modeled_loss >= baseline.maximum_modeled_loss
