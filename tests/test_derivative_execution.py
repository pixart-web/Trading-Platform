import sqlite3
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.models import digest
from pocket_alpha.config import Settings
from pocket_alpha.derivative_execution import (
    DerivativeBrokerReport,
    DerivativeCommission,
    DerivativeExecution,
    DerivativeExecutionRequest,
    DerivativeOrderIntent,
    DerivativePositionState,
    ExecutionError,
    SyntheticDerivativeBroker,
    client_id,
)
from pocket_alpha.derivative_execution.models import DerivativeLocalState
from pocket_alpha.derivative_execution.risk import evaluate
from pocket_alpha.derivatives.models import DerivativeContract, MultiplierUnit, Settlement
from pocket_alpha.leverage.engine import LeverageResearch
from tests.derivative_execution_fixtures import (
    ACCOUNT_HASH,
    CLOCK,
    execution_request,
    policy,
    strategy,
)
from tests.leverage_fixtures import AT, bound
from tests.leverage_fixtures import request as leverage_request


@pytest.mark.parametrize(
    ("side", "effect"),
    [("LONG", "OPEN"), ("SHORT", "OPEN"), ("LONG", "CLOSE"), ("SHORT", "CLOSE")],
)
def test_independent_risk_qualifies_supported_synthetic_flows(
    side: Literal["LONG", "SHORT"], effect: Literal["OPEN", "CLOSE"]
) -> None:
    decision = evaluate(
        execution_request(side, effect),
        policy(),
        now=AT,
        broker_origin="SYNTHETIC",
        killed=False,
    )

    assert decision.submission_permitted
    assert decision.reasons == ()
    assert decision.order_notional == D(100)
    assert decision.live_trading_enabled is False
    assert decision.derivative_execution_enabled is False
    assert decision.execution_authorized is False


@pytest.mark.parametrize(
    ("policy_change", "reason"),
    [
        ({"mode": "DISABLED"}, "DERIVATIVE_EXECUTION_DISABLED"),
        ({"global_enable": False}, "GLOBAL_ENABLE_REQUIRED"),
        ({"derivative_enable": False}, "DERIVATIVE_ENABLE_REQUIRED"),
        ({"manual_enable": False}, "MANUAL_ENABLE_REQUIRED"),
        ({"maximum_leverage": D(1)}, "LEVERAGE_LIMIT"),
        ({"maximum_modeled_loss_fraction": D("0.001")}, "MODELED_LOSS_LIMIT"),
    ],
)
def test_policy_gates_fail_closed(policy_change: dict[str, object], reason: str) -> None:
    decision = evaluate(
        execution_request(),
        policy(**policy_change),
        now=AT,
        broker_origin="SYNTHETIC",
        killed=False,
    )

    assert not decision.submission_permitted
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("request_change", "reason"),
    [
        ({"health_ready": False}, "SYSTEM_HEALTH_NOT_READY"),
        ({"independent_qualification": False}, "INDEPENDENT_QUALIFICATION_REQUIRED"),
        ({"loss_context_at": AT - timedelta(minutes=2)}, "LOSS_CONTEXT_STALE"),
        ({"high_water_equity": D(12000)}, "DRAWDOWN_LIMIT"),
    ],
)
def test_request_health_and_loss_context_fail_closed(
    request_change: dict[str, object], reason: str
) -> None:
    decision = evaluate(
        execution_request().model_copy(update=request_change),
        policy(),
        now=AT,
        broker_origin="SYNTHETIC",
        killed=False,
    )

    assert not decision.submission_permitted
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("contract_change", "reason"),
    [
        (
            {"multiplier_unit": MultiplierUnit.QUOTE_CURRENCY_PER_CONTRACT},
            "UNSUPPORTED_MULTIPLIER_UNIT",
        ),
        ({"settlement": Settlement.PHYSICAL}, "UNSUPPORTED_SETTLEMENT"),
        ({"margin_scheme": "CROSS"}, "UNSUPPORTED_MARGIN_SCHEME"),
    ],
)
def test_unsupported_contract_conventions_are_rejected(
    contract_change: dict[str, object], reason: str
) -> None:
    leverage_input = leverage_request()
    contract = DerivativeContract.model_validate(
        leverage_input.position.contract.model_dump() | contract_change
    )
    position = leverage_input.position.model_copy(update={"contract": contract})
    contract_hash = digest(contract)
    changed_input = bound(
        leverage_input.model_copy(
            update={
                "position": position,
                "margin": leverage_input.margin.model_copy(update={"contract_hash": contract_hash})
                if leverage_input.margin
                else None,
                "volatility": leverage_input.volatility.model_copy(
                    update={"contract_hash": contract_hash}
                )
                if leverage_input.volatility
                else None,
                "costs": leverage_input.costs.model_copy(update={"contract_hash": contract_hash})
                if leverage_input.costs
                else None,
            }
        )
    )
    assessment = LeverageResearch(CLOCK).assess(changed_input)
    baseline = execution_request()
    market = baseline.market.model_copy(update={"contract": contract})
    changed = baseline.model_copy(
        update={
            "leverage": assessment,
            "market": market,
            "strategy": strategy(position),
        }
    )

    decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)

    assert not decision.submission_permitted
    assert reason in decision.reasons


def test_native_origin_and_kill_switch_are_rejected() -> None:
    request = execution_request()
    native = evaluate(request, policy(), now=AT, broker_origin="REAL", killed=False)
    killed = evaluate(request, policy(), now=AT, broker_origin="SYNTHETIC", killed=True)

    assert "NATIVE_DERIVATIVE_EXECUTION_UNQUALIFIED" in native.reasons
    assert "KILL_SWITCH_LATCHED" in killed.reasons


def test_market_mark_index_basis_funding_and_staleness_are_checked() -> None:
    request = execution_request()
    market = request.market.model_copy(
        update={
            "mark_price": D(104),
            "funding_rate": D("0.02"),
            "available_at": AT - timedelta(minutes=2),
        }
    )
    changed = request.model_copy(update={"market": market})

    decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)

    assert {
        "MARKET_STATE_STALE",
        "MARK_INDEX_DEVIATION_LIMIT",
        "BASIS_LIMIT",
        "PRICE_DEVIATION_LIMIT",
        "FUNDING_LIMIT",
    }.issubset(decision.reasons)


def test_reconciliation_and_account_permissions_are_mandatory() -> None:
    request = execution_request()
    account = request.account.model_copy(
        update={"trading_permission": False, "open_order_client_ids": ("existing",)}
    )
    local = DerivativeLocalState(
        account_identity_hash=ACCOUNT_HASH,
        revision=2,
        recorded_at=account.completed_at,
        account_state_hash=digest(account),
        independently_reconciled=False,
    )
    changed = request.model_copy(update={"account": account, "local_state": local})

    decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)

    assert {
        "TRADING_PERMISSION_UNAVAILABLE",
        "BROKER_OPEN_ORDERS_UNRESOLVED",
        "ACCOUNT_NOT_RECONCILED",
    }.issubset(decision.reasons)


def test_reduce_only_close_requires_a_matching_position() -> None:
    request = execution_request(effect="CLOSE")
    account = request.account.model_copy(update={"positions": ()})
    changed = request.model_copy(
        update={
            "account": account,
            "local_state": request.local_state.model_copy(
                update={"account_state_hash": digest(account)}
            ),
        }
    )

    decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)

    assert "REDUCE_ONLY_POSITION_MISMATCH" in decision.reasons


def test_one_way_mode_rejects_an_opposite_position() -> None:
    request = execution_request(side="LONG")
    contract = request.market.contract
    opposite = DerivativePositionState(
        contract_id=contract.contract_id,
        contract_hash=digest(contract),
        side="SHORT",
        contracts=D(1),
        entry_price=D(100),
        mark_price=D(100),
        notional=D(100),
        initial_margin=D(10),
        maintenance_margin=D(1),
        unrealized_pnl=D(0),
        liquidation_price=D(150),
    )
    account = request.account.model_copy(update={"positions": (opposite,)})
    changed = request.model_copy(
        update={
            "account": account,
            "local_state": request.local_state.model_copy(
                update={"account_state_hash": digest(account)}
            ),
        }
    )

    decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)

    assert "ONE_WAY_POSITION_CONFLICT" in decision.reasons


def test_reduce_only_close_is_not_blocked_by_entry_risk_limits() -> None:
    request = execution_request(effect="CLOSE").model_copy(
        update={
            "high_water_equity": D(12000),
            "daily_start_equity": D(11000),
        }
    )
    restrictive = policy(
        maximum_leverage=D(1),
        maximum_modeled_loss_fraction=D("0.001"),
        daily_loss_limit=D(100),
        maximum_drawdown=D("0.01"),
    )

    decision = evaluate(request, restrictive, now=AT, broker_origin="SYNTHETIC", killed=False)

    assert decision.submission_permitted
    assert decision.reserved_collateral == D(2)


def test_intent_model_enforces_side_and_reduce_only_semantics() -> None:
    request = execution_request()
    values = request.intent.model_dump()
    values.update(order_side="SELL", reduce_only=True)

    with pytest.raises(ValidationError):
        DerivativeOrderIntent.model_validate(values)


def test_broker_report_rejects_overfill() -> None:
    request = execution_request()
    values = _filled_report(request, "pd" + "a" * 32).model_dump()
    values["executed_contracts"] = D(2)

    with pytest.raises(ValidationError):
        DerivativeBrokerReport.model_validate(values)


def test_fresh_settings_cannot_enable_live_or_derivative_execution() -> None:
    settings = Settings()
    assert settings.live_trading_enabled is False
    assert settings.derivative_execution_enabled is False

    with pytest.raises(ValidationError):
        Settings(live_trading_enabled=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(derivative_execution_enabled=True)  # type: ignore[arg-type]


def test_synthetic_dispatch_is_idempotent_and_reconciles_fill(tmp_path: Path) -> None:
    request = execution_request()
    broker = SyntheticDerivativeBroker(clock=CLOCK)
    execution = DerivativeExecution(
        tmp_path / "derivatives.sqlite", policy(), broker=broker, clock=CLOCK
    )

    first = execution.submit(request)
    repeated = execution.submit(request)
    assert first["status"] == "NEW"
    assert repeated == first
    assert broker.submissions == 1

    report = _filled_report(request, client_id(request), order_id=first["report"]["order_id"])
    broker.publish(report)
    reconciled = execution.reconcile(client_id(request))

    assert reconciled["status"] == "FILLED"
    assert execution.reconcile(client_id(request)) == reconciled
    execution.journal.close()


def test_changed_payload_with_same_intent_is_idempotency_conflict(tmp_path: Path) -> None:
    request = execution_request()
    execution = DerivativeExecution(
        tmp_path / "derivatives.sqlite",
        policy(),
        broker=SyntheticDerivativeBroker(clock=CLOCK),
        clock=CLOCK,
    )
    execution.submit(request)
    changed = request.model_copy(update={"daily_start_equity": D(9999)})

    with pytest.raises(ExecutionError, match="IDEMPOTENCY_CONFLICT"):
        execution.submit(changed)
    execution.journal.close()


def test_ambiguous_submission_becomes_unknown_and_is_reconciled(tmp_path: Path) -> None:
    request = execution_request()

    class AmbiguousBroker(SyntheticDerivativeBroker):
        def submit(
            self, client_id_value: str, request_value: DerivativeExecutionRequest
        ) -> DerivativeBrokerReport:
            super().submit(client_id_value, request_value)
            raise TimeoutError("synthetic transport ambiguity")

    broker = AmbiguousBroker(clock=CLOCK)
    execution = DerivativeExecution(
        tmp_path / "ambiguous.sqlite", policy(), broker=broker, clock=CLOCK
    )

    result = execution.submit(request)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "SUBMISSION_RESULT_UNKNOWN"

    reconciled = execution.reconcile(client_id(request))
    assert reconciled["status"] == "NEW"
    execution.journal.close()


def test_current_known_report_resolves_a_later_unknown(tmp_path: Path) -> None:
    request = execution_request()

    class IntermittentQueryBroker(SyntheticDerivativeBroker):
        queries = 0

        def query(
            self, client_id_value: str, contract_id_value: str
        ) -> DerivativeBrokerReport | None:
            self.queries += 1
            if self.queries == 1:
                raise TimeoutError("synthetic query ambiguity")
            return super().query(client_id_value, contract_id_value)

    broker = IntermittentQueryBroker(clock=CLOCK)
    execution = DerivativeExecution(
        tmp_path / "repeated-report.sqlite", policy(), broker=broker, clock=CLOCK
    )
    assert execution.submit(request)["status"] == "NEW"
    assert execution.reconcile(client_id(request))["status"] == "UNKNOWN"

    resolved = execution.reconcile(client_id(request))
    assert resolved["status"] == "NEW"
    assert resolved["kind"] == "REPORT"
    execution.journal.close()


def test_unresolved_order_blocks_another_submission(tmp_path: Path) -> None:
    first_request = execution_request()
    second_intent = first_request.intent.model_copy(
        update={"intent_id": UUID("00000000-0000-0000-0000-000000000229")}
    )
    second_request = first_request.model_copy(update={"intent": second_intent})
    execution = DerivativeExecution(
        tmp_path / "serialized.sqlite",
        policy(),
        broker=SyntheticDerivativeBroker(clock=CLOCK),
        clock=CLOCK,
    )

    assert execution.submit(first_request)["status"] == "NEW"
    rejected = execution.submit(second_request)

    assert rejected["kind"] == "RISK_REJECTED"
    assert "ACCOUNT_FLOW_UNRESOLVED" in rejected["reasons"]
    execution.journal.close()


def test_kill_is_latched_and_native_default_never_dispatches(tmp_path: Path) -> None:
    execution = DerivativeExecution(tmp_path / "native.sqlite", policy(), clock=CLOCK)
    rejected = execution.submit(execution_request())
    assert rejected["kind"] == "RISK_REJECTED"
    assert "NATIVE_DERIVATIVE_EXECUTION_UNQUALIFIED" in rejected["reasons"]

    execution.kill()
    other = execution_request().model_copy(
        update={
            "intent": execution_request().intent.model_copy(
                update={"intent_id": UUID("00000000-0000-0000-0000-000000000329")}
            )
        }
    )
    killed = execution.submit(other)
    assert "KILL_SWITCH_LATCHED" in killed["reasons"]
    execution.journal.close()


def test_journal_tampering_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "tampered.sqlite"
    execution = DerivativeExecution(
        path,
        policy(),
        broker=SyntheticDerivativeBroker(clock=CLOCK),
        clock=CLOCK,
    )
    execution.submit(execution_request())
    execution.journal.close()

    connection = sqlite3.connect(path)
    connection.execute("UPDATE events SET payload='{}' WHERE sequence=1")
    connection.commit()
    connection.close()

    with pytest.raises(ExecutionError, match="JOURNAL_INTEGRITY_FAILURE"):
        DerivativeExecution(
            path,
            policy(),
            broker=SyntheticDerivativeBroker(clock=CLOCK),
            clock=CLOCK,
        )


def test_commission_currency_and_budget_are_verified(tmp_path: Path) -> None:
    request = execution_request()
    broker = SyntheticDerivativeBroker(clock=CLOCK)
    execution = DerivativeExecution(tmp_path / "fees.sqlite", policy(), broker=broker, clock=CLOCK)
    execution.submit(request)
    invalid = _filled_report(
        request,
        client_id(request),
        order_id=broker.reports[client_id(request)].order_id,
        commissions=(DerivativeCommission(currency="BTC", amount=D("0.1")),),
    )
    broker.publish(invalid)

    result = execution.reconcile(client_id(request))
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "BROKER_REPORT_REQUIRES_RECONCILIATION"
    execution.journal.close()


def _filled_report(
    request: DerivativeExecutionRequest,
    cid: str,
    *,
    order_id: str = "synthetic-order",
    commissions: tuple[DerivativeCommission, ...] = (),
) -> DerivativeBrokerReport:
    return DerivativeBrokerReport(
        client_id=cid,
        contract_id=request.intent.contract_id,
        position_side=request.intent.position_side,
        order_side=request.intent.order_side,
        effect=request.intent.effect,
        reduce_only=request.intent.reduce_only,
        order_id=order_id,
        status="FILLED",
        original_contracts=request.intent.contracts,
        limit_price=request.intent.limit_price,
        executed_contracts=request.intent.contracts,
        cumulative_settlement_value=D(100),
        commissions=commissions,
        realized_pnl=D(0),
        funding_paid=D(0),
        at=AT,
    )


def test_identity_causality_and_reconciliation_mismatches_fail_closed() -> None:
    base = execution_request()
    bad_hash = "f" * 64

    cases = [
        (
            base.model_copy(update={"market": base.market.model_copy(update={"origin": "REAL"})}),
            policy(),
            "SYNTHETIC_ORIGIN_REQUIRED",
        ),
        (base, policy(contract_ids=("derivative:other",)), "CONTRACT_NOT_ALLOWED"),
        (base, policy(strategy_hashes=(bad_hash,)), "STRATEGY_NOT_ALLOWED"),
        (
            base,
            policy(account_identity_hash=bad_hash),
            "ACCOUNT_IDENTITY_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "market": base.market.model_copy(
                        update={"funding_rate": None, "next_funding_at": None}
                    )
                }
            ),
            policy(),
            "FUNDING_UNAVAILABLE",
        ),
        (
            base.model_copy(
                update={
                    "intent": base.intent.model_copy(update={"contract_id": "derivative:other"})
                }
            ),
            policy(),
            "INTENT_CONTRACT_MISMATCH",
        ),
        (
            base.model_copy(
                update={"intent": base.intent.model_copy(update={"position_side": "SHORT"})}
            ),
            policy(),
            "POSITION_SIDE_MISMATCH",
        ),
        (
            base.model_copy(update={"intent": base.intent.model_copy(update={"contracts": D(2)})}),
            policy(),
            "ASSESSED_QUANTITY_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "intent": base.intent.model_copy(update={"strategy_proposal_hash": bad_hash})
                }
            ),
            policy(),
            "STRATEGY_PROPOSAL_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "strategy": base.strategy.model_copy(
                        update={"leverage_position_hash": bad_hash}
                    )
                }
            ),
            policy(),
            "STRATEGY_LEVERAGE_BINDING_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "strategy": base.strategy.model_copy(
                        update={"valid_until": AT - timedelta(seconds=1)}
                    )
                }
            ),
            policy(),
            "STRATEGY_EVIDENCE_EXPIRED",
        ),
        (
            base.model_copy(
                update={
                    "intent": base.intent.model_copy(
                        update={"expires_at": AT - timedelta(seconds=1)}
                    )
                }
            ),
            policy(),
            "INTENT_EXPIRED_OR_PRECAUSAL",
        ),
        (
            base.model_copy(
                update={
                    "local_state": base.local_state.model_copy(
                        update={"account_identity_hash": bad_hash}
                    )
                }
            ),
            policy(),
            "LOCAL_ACCOUNT_IDENTITY_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "local_state": base.local_state.model_copy(
                        update={"account_state_hash": bad_hash}
                    )
                }
            ),
            policy(),
            "LOCAL_BROKER_STATE_MISMATCH",
        ),
        (
            base.model_copy(
                update={
                    "account": base.account.model_copy(
                        update={"completed_at": AT - timedelta(minutes=2)}
                    )
                }
            ),
            policy(),
            "ACCOUNT_STATE_STALE",
        ),
    ]

    for request_value, policy_value, expected in cases:
        decision = evaluate(
            request_value,
            policy_value,
            now=AT,
            broker_origin="SYNTHETIC",
            killed=False,
        )
        assert expected in decision.reasons


def test_venue_collateral_and_portfolio_limits_fail_closed() -> None:
    base = execution_request()
    restrictive = policy(
        order_notional_limit=D(50),
        position_notional_limit=D(50),
        total_gross_notional_limit=D(50),
        total_net_notional_limit=D(50),
        collateral_limit=D(10),
        maximum_collateral_fraction=D("0.001"),
        maximum_initial_margin_rate=D("0.05"),
        maximum_maintenance_margin_rate=D("0.005"),
        maximum_spread_fraction=D("0.001"),
        minimum_liquidation_buffer_fraction=D("0.9"),
    )
    decision = evaluate(
        base,
        restrictive,
        now=AT,
        broker_origin="SYNTHETIC",
        killed=False,
    )
    assert {
        "ORDER_NOTIONAL_LIMIT",
        "POSITION_NOTIONAL_LIMIT",
        "GROSS_NOTIONAL_LIMIT",
        "NET_NOTIONAL_LIMIT",
        "COLLATERAL_LIMIT",
        "COLLATERAL_FRACTION_LIMIT",
        "INITIAL_MARGIN_RATE_LIMIT",
        "MAINTENANCE_MARGIN_RATE_LIMIT",
        "SPREAD_LIMIT",
        "LIQUIDATION_BUFFER_LIMIT",
        "CURRENT_LIQUIDATION_BUFFER_LIMIT",
    }.issubset(decision.reasons)

    stepped_market = base.market.model_copy(
        update={
            "quantity_step": D(2),
            "price_tick": D(3),
            "minimum_contracts": D(2),
            "maximum_notional": D(50),
        }
    )
    stepped = base.model_copy(update={"market": stepped_market})
    stepped_decision = evaluate(stepped, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)
    assert {
        "CONTRACT_QUANTITY_LIMIT",
        "CONTRACT_QUANTITY_STEP",
        "PRICE_TICK",
        "VENUE_NOTIONAL_LIMIT",
    }.issubset(stepped_decision.reasons)


@pytest.mark.parametrize(
    ("factory", "changes"),
    [
        ("policy", {"contract_ids": ("derivative:perp", "derivative:perp")}),
        ("policy", {"total_net_notional_limit": D(6000)}),
        ("policy", {"collateral_limit": D(11000)}),
        ("intent", {"expires_at": AT}),
        ("market", {"ask": D(99)}),
        ("market", {"maintenance_margin_rate": D("0.2")}),
        ("market", {"minimum_contracts": D(101)}),
        ("market", {"minimum_notional": D(20000)}),
        ("market", {"next_funding_at": None}),
        ("account", {"completed_at": AT - timedelta(seconds=1)}),
        ("account", {"available_collateral": D(11000)}),
        ("account", {"open_order_client_ids": ("same", "same")}),
    ],
)
def test_contract_validators_reject_incoherent_state(
    factory: str, changes: dict[str, object]
) -> None:
    request = execution_request()
    source = {
        "policy": policy(),
        "intent": request.intent,
        "market": request.market,
        "account": request.account,
    }[factory]

    with pytest.raises(ValidationError):
        type(source).model_validate(source.model_dump() | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "NEW", "executed_contracts": D(1), "cumulative_settlement_value": D(100)},
        {
            "status": "PARTIALLY_FILLED",
            "executed_contracts": D(0),
            "cumulative_settlement_value": D(0),
        },
        {"status": "FILLED", "executed_contracts": D("0.5"), "cumulative_settlement_value": D(50)},
        {"status": "FILLED", "executed_contracts": D(1), "cumulative_settlement_value": D(0)},
        {
            "commissions": (
                DerivativeCommission(currency="USD", amount=D(1)),
                DerivativeCommission(currency="USD", amount=D(2)),
            )
        },
    ],
)
def test_broker_report_validators_reject_incoherent_cumulative_state(
    changes: dict[str, object],
) -> None:
    request = execution_request()
    report = _filled_report(request, "pd" + "a" * 32)

    with pytest.raises(ValidationError):
        DerivativeBrokerReport.model_validate(report.model_dump() | changes)


def test_remaining_model_invariants_are_explicitly_enforced() -> None:
    request = execution_request()

    invalid_policy = policy().model_dump()
    invalid_policy["order_notional_limit"] = D(3000)
    with pytest.raises(ValidationError):
        type(policy()).model_validate(invalid_policy)

    strategy_values = request.strategy.model_dump()
    strategy_values["valid_until"] = request.strategy.evaluated_at
    with pytest.raises(ValidationError):
        type(request.strategy).model_validate(strategy_values)

    strategy_values = request.strategy.model_dump()
    strategy_values["content_hash"] = "f" * 64
    with pytest.raises(ValidationError):
        type(request.strategy).model_validate(strategy_values)

    intent_values = request.intent.model_dump()
    intent_values["reduce_only"] = True
    with pytest.raises(ValidationError):
        type(request.intent).model_validate(intent_values)

    market_values = request.market.model_dump()
    market_values["available_at"] = request.market.observed_at - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        type(request.market).model_validate(market_values)

    close = execution_request(effect="CLOSE")
    account_values = close.account.model_dump()
    account_values["positions"] = close.account.positions * 2
    with pytest.raises(ValidationError):
        type(close.account).model_validate(account_values)


def test_missing_portfolio_risk_and_margin_inputs_fail_closed() -> None:
    base = execution_request()

    for field, reason in (
        ("portfolio", "PORTFOLIO_COLLATERAL_UNAVAILABLE"),
        ("prior_risk", "PRIOR_RISK_UNAVAILABLE"),
        ("margin", "MARGIN_RULES_UNAVAILABLE"),
    ):
        leverage_request_value = base.leverage.request.model_copy(update={field: None})
        assessment = base.leverage.model_copy(update={"request": leverage_request_value})
        changed = base.model_copy(update={"leverage": assessment})
        decision = evaluate(changed, policy(), now=AT, broker_origin="SYNTHETIC", killed=False)
        assert reason in decision.reasons
