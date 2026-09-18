"""Synthetic qualification only; no broker network, keys or real orders."""

from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.models import Intent, digest
from pocket_alpha.broker_readonly.models import LocalState
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.config import Settings
from pocket_alpha.domain.models import AssetType
from pocket_alpha.portfolio.models import (
    PortfolioMarket,
    PortfolioPosition,
    PortfolioSnapshot,
    PortfolioSnapshotStatus,
    PositionStatus,
)
from pocket_alpha.spot_execution.engine import (
    DisabledNativeBroker,
    ExecutionError,
    SpotExecution,
    client_id,
)
from pocket_alpha.spot_execution.models import BrokerReport, Commission, SpotPolicy, SpotRequest
from pocket_alpha.spot_execution.risk import evaluate
from pocket_alpha.strategies.engine import TrendStrategy
from pocket_alpha.strategies.models import PositionMemory
from tests.strategy_fixtures import definition, view
from tests.test_broker_readonly import observe


def request() -> SpotRequest:
    strategy = definition()
    proposal = TrendStrategy(strategy).proposal(
        view(), PositionMemory(definition_hash=digest(strategy))
    )
    at = proposal.at
    observed = observe()
    instrument = observed.state.instruments[0].model_copy(
        update={"market_id": strategy.market_id, "asset_id": strategy.asset_id}
    )
    state = observed.state.model_copy(
        update={"instruments": (instrument,), "open_orders": (), "trades": ()}
    )
    observed = observed.model_copy(update={"state": state, "started_at": at, "completed_at": at})
    position = PortfolioPosition(
        market=PortfolioMarket(
            market_id=strategy.market_id,
            asset_id=strategy.asset_id,
            symbol="BTCUSDT",
            name="synthetic spot",
            asset_type=AssetType.CRYPTO,
            venue_id="binance",
            quote_currency="USDT",
        ),
        status=PositionStatus.OPEN,
        quantity=D("0.02"),
        average_cost=D("100"),
        cost_basis=D("2"),
        realized_pnl=D(0),
        last_price=D(106),
        price_time=at,
        price_available_at=at,
        market_value=D("2.12"),
        unrealized_pnl=D("0.12"),
    )
    portfolio = PortfolioSnapshot(
        portfolio_id=uuid4(),
        portfolio_revision=1,
        ledger_sequence=1,
        base_currency="USDT",
        as_of=at,
        generated_at=at,
        status=PortfolioSnapshotStatus.COMPLETE,
        cash_balance=D(1200),
        net_contributions=D(1202),
        total_fees=D(0),
        realized_pnl=D(0),
        positions=(position,),
        total_cost_basis=D(2),
        total_market_value=D("2.12"),
        unrealized_pnl=D("0.12"),
        equity=D("1202.12"),
        input_hash="0" * 64,
    )
    return SpotRequest(
        strategy=strategy,
        proposal=proposal,
        intent=Intent(client_id="synthetic-intent-1", action="BUY", quantity=D("0.01")),
        symbol="BTCUSDT",
        limit_price=D(106),
        bid=D(106),
        ask=D("106.01"),
        quote_at=at,
        portfolio=portfolio,
        observation=observed,
        local_state=LocalState(
            state=state,
            revision=1,
            recorded_at=at - timedelta(seconds=1),
            independently_verified=True,
        ),
        daily_start_equity=D("1202.12"),
        daily_net_flows=D(0),
        high_water_equity=D("1202.12"),
        loss_context_at=at,
        health_ready=True,
        independent_qualification=True,
    )


def policy(value: SpotRequest, **changes: Any) -> SpotPolicy:
    data: dict[str, Any] = dict(
        version="synthetic-spot-limits-1",
        mode="SYNTHETIC_QUALIFICATION",
        global_enable=True,
        manual_enable=True,
        account_identity_hash=value.observation.state.account_identity_hash,
        symbols=(value.symbol,),
        strategy_hashes=(digest(value.strategy),),
        quote_asset="USDT",
        capital_limit=D(100),
        order_notional_limit=D(10),
        total_exposure_limit=D(30),
        position_notional_limit=D(20),
        daily_loss_limit=D(5),
        maximum_drawdown=D("0.1"),
        maximum_positions=1,
        maximum_orders_per_minute=1,
        maximum_orders_per_day=2,
        maximum_data_age_seconds=30,
        maximum_fee_fraction=D("0.01"),
        maximum_spread_fraction=D("0.01"),
        maximum_price_deviation_fraction=D("0.01"),
    )
    data.update(changes)
    return SpotPolicy(**data)


class SyntheticBroker:
    origin: Literal["REAL", "SYNTHETIC"] = "SYNTHETIC"

    def __init__(self) -> None:
        self.submissions = 0
        self.queries = 0
        self.failure = False
        self.latest: BrokerReport | None = None

    def submit(self, cid: str, value: SpotRequest) -> BrokerReport:
        assert value.intent.action != "CANCEL" and value.intent.quantity is not None
        self.submissions += 1
        self.latest = BrokerReport(
            client_id=cid,
            symbol=value.symbol,
            side=value.intent.action,
            order_id="synthetic-order-1",
            status="NEW",
            original_quantity=value.intent.quantity,
            limit_price=value.limit_price,
            executed_quantity=D(0),
            cumulative_quote=D(0),
            commissions=(),
            at=value.proposal.at,
        )
        if self.failure:
            raise TimeoutError("synthetic upstream credential must never escape")
        return self.latest

    def query(self, cid: str, symbol: str) -> BrokerReport | None:
        self.queries += 1
        return self.latest


def engine(tmp_path: Path, value: SpotRequest, broker: SyntheticBroker) -> SpotExecution:
    return SpotExecution(
        tmp_path / "journal.sqlite",
        policy(value),
        broker=broker,
        clock=FrozenClock(value.proposal.at),
    )


def test_shared_pipeline_and_native_default_disabled(tmp_path: Path) -> None:
    value = request()
    assert value.proposal.action == "ENTER_LONG"
    assert evaluate(
        value, policy(value), now=value.proposal.at, broker_origin="SYNTHETIC"
    ).submission_permitted
    native = SpotExecution(
        tmp_path / "native.sqlite", policy(value), clock=FrozenClock(value.proposal.at)
    )
    result = native.submit(value)
    assert result["kind"] == "RISK_REJECTED"
    assert "FOUNDATION_LIVE_DISABLED" in result["reasons"]
    assert not Settings().live_trading_enabled
    assert not result["decision"]["execution_authorized"]
    native.journal.close()


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"global_enable": False}, "MANUAL_OR_GLOBAL_DISABLED"),
        ({"manual_enable": False}, "MANUAL_OR_GLOBAL_DISABLED"),
        ({"mode": "DISABLED"}, "MANUAL_OR_GLOBAL_DISABLED"),
        ({"account_identity_hash": "0" * 64}, "ACCOUNT_NOT_ALLOWED"),
        ({"symbols": ("ETHUSDT",)}, "SYMBOL_NOT_ALLOWED"),
        ({"strategy_hashes": ("0" * 64,)}, "STRATEGY_NOT_ALLOWED"),
        ({"order_notional_limit": D(1)}, "ORDER_NOTIONAL_LIMIT"),
        ({"position_notional_limit": D(3)}, "POSITION_NOTIONAL_LIMIT"),
        ({"total_exposure_limit": D(3), "position_notional_limit": D(3)}, "TOTAL_EXPOSURE_LIMIT"),
        (
            {
                "capital_limit": D(3),
                "order_notional_limit": D(1),
                "total_exposure_limit": D(3),
                "position_notional_limit": D(3),
            },
            "CAPITAL_LIMIT",
        ),
        ({"maximum_spread_fraction": D(0)}, "SPREAD_LIMIT"),
        ({"quote_asset": "USD"}, "CURRENCY_MISMATCH"),
    ],
)
def test_policy_gates(change: dict[str, Any], reason: str) -> None:
    value = request()
    decision = evaluate(
        value, policy(value, **change), now=value.proposal.at, broker_origin="SYNTHETIC"
    )
    assert not decision.submission_permitted and reason in decision.reasons


@pytest.mark.parametrize(
    "case,reason",
    [
        ("health", "DEPENDENCY_NOT_READY"),
        ("qualification", "QUALIFICATION_MISSING"),
        ("quote_future", "STALE_OR_FUTURE_INPUT"),
        ("quote_stale", "STALE_OR_FUTURE_INPUT"),
        ("daily_loss", "DAILY_LOSS_LIMIT"),
        ("drawdown", "DRAWDOWN_LIMIT"),
        ("highwater", "HIGH_WATER_INCONSISTENT"),
        ("inventory", "SPOT_INVENTORY_LIMIT"),
        ("cash", "INSUFFICIENT_CASH"),
        ("crossed", "CROSSED_QUOTE"),
        ("deviation", "PRICE_DEVIATION_LIMIT"),
        ("step", "PRICE_OR_QUANTITY_STEP"),
        ("external", "EXTERNAL_OPEN_ORDERS"),
        ("local", "BALANCES_MISMATCH"),
    ],
)
def test_request_gates(case: str, reason: str) -> None:
    value = request()
    if case == "health":
        value = value.model_copy(update={"health_ready": False})
    elif case == "qualification":
        value = value.model_copy(update={"independent_qualification": False})
    elif case == "quote_future":
        value = value.model_copy(update={"quote_at": value.quote_at + timedelta(seconds=1)})
    elif case == "quote_stale":
        value = value.model_copy(update={"quote_at": value.quote_at - timedelta(seconds=31)})
    elif case == "daily_loss":
        value = value.model_copy(update={"daily_start_equity": D("1207.12")})
    elif case == "drawdown":
        value = value.model_copy(update={"high_water_equity": D(1400)})
    elif case == "highwater":
        value = value.model_copy(update={"high_water_equity": D(1000)})
    elif case == "inventory":
        value = value.model_copy(
            update={"intent": Intent(client_id="sell", action="SELL", quantity=D("0.02"))}
        )
    elif case == "cash":
        value = value.model_copy(
            update={"intent": Intent(client_id="buy", action="BUY", quantity=D(20))}
        )
    elif case == "crossed":
        value = value.model_copy(update={"ask": D(100)})
    elif case == "deviation":
        value = value.model_copy(update={"limit_price": D(110)})
    elif case == "step":
        value = value.model_copy(update={"limit_price": D("106.001")})
    elif case == "external":
        value = value.model_copy(
            update={
                "observation": value.observation.model_copy(
                    update={
                        "state": value.observation.state.model_copy(
                            update={"open_orders": observe().state.open_orders}
                        )
                    }
                )
            }
        )
    else:
        value = value.model_copy(
            update={
                "local_state": value.local_state.model_copy(
                    update={"state": value.local_state.state.model_copy(update={"balances": ()})}
                )
            }
        )
    assert (
        reason
        in evaluate(value, policy(value), now=value.proposal.at, broker_origin="SYNTHETIC").reasons
    )


def test_idempotency_persistence_conflict_and_unknown_no_retry(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    broker.failure = True
    service = engine(tmp_path, value, broker)
    result = service.submit(value)
    assert result["status"] == "UNKNOWN" and broker.submissions == 1
    assert "credential" not in str(result)
    assert service.submit(value) == result and broker.submissions == 1
    service.journal.close()
    service = engine(tmp_path, value, broker)
    assert service.submit(value) == result and broker.submissions == 1
    assert service.reconcile(client_id(value))["status"] == "NEW"
    assert broker.submissions == 1 and broker.queries == 1
    changed = value.model_copy(update={"limit_price": D(105)})
    with pytest.raises(ExecutionError, match="IDEMPOTENCY_CONFLICT"):
        service.submit(changed)
    other = value.model_copy(
        update={"intent": Intent(client_id="second", action="BUY", quantity=D("0.01"))}
    )
    blocked = service.submit(other)
    assert "ACCOUNT_FLOW_UNRESOLVED" in blocked["reasons"]
    assert "MINUTE_RATE_LIMIT" in blocked["reasons"]
    service.journal.close()


def test_partial_duplicate_final_and_ambiguous_reconciliation(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    service.submit(value)
    assert broker.latest is not None
    partial = broker.latest.model_copy(
        update={
            "status": "PARTIALLY_FILLED",
            "executed_quantity": D("0.005"),
            "cumulative_quote": D("0.53"),
            "commissions": (Commission(asset="USDT", amount=D("0.001")),),
        }
    )
    broker.latest = partial
    assert service.reconcile(client_id(value))["status"] == "PARTIALLY_FILLED"
    count = len(service.journal.read())
    assert service.reconcile(client_id(value))["status"] == "PARTIALLY_FILLED"
    assert len(service.journal.read()) == count
    final = partial.model_copy(
        update={"status": "FILLED", "executed_quantity": D("0.01"), "cumulative_quote": D("1.06")}
    )
    broker.latest = final
    assert service.reconcile(client_id(value))["status"] == "FILLED"
    broker.latest = None
    assert service.reconcile(client_id(value))["status"] == "UNKNOWN"
    assert broker.submissions == 1
    service.journal.close()


@pytest.mark.parametrize(
    "change",
    [
        {"client_id": "wrong"},
        {"symbol": "ETHUSDT"},
        {"order_id": "changed"},
        {"executed_quantity": D("0.01"), "status": "FILLED", "cumulative_quote": D(2)},
        {
            "executed_quantity": D("0.005"),
            "status": "PARTIALLY_FILLED",
            "cumulative_quote": D("0.53"),
            "commissions": (Commission(asset="BNB", amount=D("0.001")),),
        },
    ],
)
def test_invalid_broker_report_blocks(change: dict[str, Any], tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    service.submit(value)
    assert broker.latest is not None
    broker.latest = broker.latest.model_copy(update=change)
    assert service.reconcile(client_id(value))["status"] == "UNKNOWN"
    assert broker.submissions == 1
    service.journal.close()


def test_kill_latched_after_restart_and_integrity(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    service.kill()
    service.journal.close()
    service = engine(tmp_path, value, broker)
    assert "KILL_SWITCH" in service.submit(value)["reasons"]
    assert broker.submissions == 0
    service.journal.connection.execute("UPDATE events SET payload='{}' WHERE sequence=1")
    with pytest.raises(ExecutionError, match="INTEGRITY"):
        service.journal.read()
    service.journal.close()


def test_disabled_native_and_policy_invariants() -> None:
    value = request()
    broker = DisabledNativeBroker()
    with pytest.raises(ExecutionError):
        broker.submit(client_id(value), value)
    with pytest.raises(ExecutionError):
        broker.query(client_id(value), value.symbol)
    with pytest.raises(ValidationError):
        policy(value, symbols=(value.symbol, value.symbol))
    with pytest.raises(ValidationError):
        policy(value, capital_limit=D(1))


def test_terminal_evidence_restores_unknown_without_resubmission(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    service.submit(value)
    assert broker.latest is not None
    terminal = broker.latest.model_copy(update={"status": "REJECTED"})
    broker.latest = terminal
    assert service.reconcile(client_id(value))["status"] == "REJECTED"
    broker.latest = None
    assert service.reconcile(client_id(value))["status"] == "UNKNOWN"
    broker.latest = terminal
    assert service.reconcile(client_id(value))["status"] == "REJECTED"
    assert broker.submissions == 1
    service.journal.close()


def test_crash_after_preparation_blocks_resubmit_and_queries(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    with service.journal.transaction():
        service.journal.append(
            service._event(
                "PREPARED",
                client_id(value),
                request_hash=digest(value),
                request=value.model_dump(mode="json"),
            )
        )
    assert service.submit(value)["status"] == "UNKNOWN"
    assert broker.submissions == 0
    assert service.reconcile(client_id(value))["status"] == "UNKNOWN"
    assert broker.queries == 1
    service.journal.close()


def test_stale_duplicate_partial_response_does_not_regress(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    initial = service.submit(value)
    assert broker.latest is not None
    old = broker.latest
    broker.latest = old.model_copy(
        update={
            "status": "PARTIALLY_FILLED",
            "executed_quantity": D("0.005"),
            "cumulative_quote": D("0.53"),
        }
    )
    partial = service.reconcile(client_id(value))
    broker.latest = old
    assert service.reconcile(client_id(value)) == partial
    assert initial["status"] == "NEW"
    service.journal.close()


@pytest.mark.parametrize(
    "change",
    [{"status": "FILLED"}, {"executed_quantity": D("0.02")}, {"status": "PARTIALLY_FILLED"}],
)
def test_broker_schema_rejects_inconsistent_status(change: dict[str, Any]) -> None:
    value, broker = request(), SyntheticBroker()
    report = broker.submit(client_id(value), value).model_dump()
    report.update(change)
    with pytest.raises(ValidationError):
        BrokerReport.model_validate(report)


def test_account_pinning_and_query_error(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = engine(tmp_path, value, broker)
    with pytest.raises(ExecutionError, match="ORDER_NOT_SUBMITTED"):
        service.reconcile("missing")
    service.submit(value)
    service.journal.close()
    with pytest.raises(ExecutionError, match="IDENTITY_MISMATCH"):
        SpotExecution(
            tmp_path / "journal.sqlite",
            policy(value, account_identity_hash="0" * 64),
            broker=broker,
        )


@pytest.mark.parametrize(
    "case,reason",
    [
        ("unknown_asset", "UNVALUED_OR_UNKNOWN_HOLDING"),
        ("cash_binding", "PORTFOLIO_CASH_MISMATCH"),
        ("inventory_binding", "PORTFOLIO_POSITION_MISMATCH"),
        ("stale_mark", "POSITION_MARK_NOT_CURRENT"),
        ("instrument", "INSTRUMENT_MISSING"),
        ("origin", "ORIGIN_MISMATCH"),
        ("cancel", "UNSUPPORTED_INTENT"),
        ("expired", "PROPOSAL_EXPIRED_OR_FUTURE"),
        ("evidence", "INTELLIGENCE_EVIDENCE_MISSING"),
        ("product", "PRODUCT_IDENTITY_MISMATCH"),
    ],
)
def test_financial_binding_and_upstream_gaps(case: str, reason: str) -> None:
    from pocket_alpha.broker_readonly.models import Balance

    value = request()
    state = value.observation.state
    if case == "unknown_asset":
        state = state.model_copy(
            update={"balances": state.balances + (Balance(asset="ETH", free=D(1), locked=D(0)),)}
        )
    elif case == "cash_binding":
        state = state.model_copy(
            update={
                "balances": tuple(
                    x.model_copy(update={"free": D(900)}) if x.asset == "USDT" else x
                    for x in state.balances
                )
            }
        )
    elif case == "inventory_binding":
        state = state.model_copy(
            update={
                "balances": tuple(
                    x.model_copy(update={"free": D("0.02")}) if x.asset == "BTC" else x
                    for x in state.balances
                )
            }
        )
    elif case == "stale_mark":
        value = value.model_copy(
            update={
                "portfolio": value.portfolio.model_copy(
                    update={
                        "positions": (
                            value.portfolio.positions[0].model_copy(
                                update={
                                    "price_available_at": value.quote_at - timedelta(seconds=31)
                                }
                            ),
                        )
                    }
                )
            }
        )
    elif case == "instrument":
        value = value.model_copy(update={"symbol": "ETHUSDT"})
    elif case == "origin":
        state = state.model_copy(update={"origin": "REAL"})
    elif case == "cancel":
        value = value.model_copy(
            update={
                "intent": Intent(client_id="cancel", action="CANCEL", cancel_client_id="target")
            }
        )
    elif case == "expired":
        value = value.model_copy(
            update={"proposal": value.proposal.model_copy(update={"expires_at": value.proposal.at})}
        )
    elif case == "evidence":
        value = value.model_copy(
            update={"proposal": value.proposal.model_copy(update={"forecast": None})}
        )
    else:
        state = state.model_copy(
            update={
                "instruments": (state.instruments[0].model_copy(update={"asset_id": "different"}),)
            }
        )
    value = value.model_copy(
        update={"observation": value.observation.model_copy(update={"state": state})}
    )
    assert (
        reason
        in evaluate(value, policy(value), now=value.proposal.at, broker_origin="SYNTHETIC").reasons
    )


def test_commission_budget_and_durable_daily_rate(tmp_path: Path) -> None:
    value, broker = request(), SyntheticBroker()
    service = SpotExecution(
        tmp_path / "journal.sqlite",
        policy(value, maximum_orders_per_day=1, maximum_data_age_seconds=300),
        broker=broker,
        clock=FrozenClock(value.proposal.at),
    )
    service.submit(value)
    assert broker.latest is not None
    broker.latest = broker.latest.model_copy(
        update={
            "status": "PARTIALLY_FILLED",
            "executed_quantity": D("0.005"),
            "cumulative_quote": D("0.53"),
            "commissions": (Commission(asset="USDT", amount=D("0.02")),),
        }
    )
    assert service.reconcile(client_id(value))["status"] == "UNKNOWN"
    broker.latest = broker.latest.model_copy(update={"status": "CANCELLED", "commissions": ()})
    assert service.reconcile(client_id(value))["status"] == "CANCELLED"
    future = value.proposal.at + timedelta(seconds=61)
    service.clock = FrozenClock(future)
    newer = value.model_copy(
        update={
            "intent": Intent(client_id="next-day-budget", action="BUY", quantity=D("0.01")),
            "observation": value.observation.model_copy(
                update={"started_at": future, "completed_at": future}
            ),
            "quote_at": future,
            "loss_context_at": future,
            "portfolio": value.portfolio.model_copy(
                update={"as_of": future, "generated_at": future}
            ),
        }
    )
    result = service.submit(newer)
    assert "DAILY_RATE_LIMIT" in result["reasons"]
    assert "MINUTE_RATE_LIMIT" not in result["reasons"]
    assert "ACCOUNT_FLOW_UNRESOLVED" not in result["reasons"]
    assert broker.submissions == 1
    service.journal.close()


def test_serialized_admission_prevents_two_dispatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    second = value.model_copy(
        update={"intent": Intent(client_id="parallel-second", action="BUY", quantity=D("0.01"))}
    )
    results: list[dict[str, Any]] = []
    broker = SyntheticBroker()
    service = engine(tmp_path, value, broker)
    sibling = engine(tmp_path, value, SyntheticBroker())
    original = broker.submit

    def interleaved(cid: str, submitted: SpotRequest) -> BrokerReport:
        results.append(sibling.submit(second))
        return original(cid, submitted)

    monkeypatch.setattr(broker, "submit", interleaved)
    assert service.submit(value)["status"] == "NEW"
    assert "ACCOUNT_FLOW_UNRESOLVED" in results[0]["reasons"]
    assert broker.submissions == 1
    service.journal.close()
    sibling.journal.close()
