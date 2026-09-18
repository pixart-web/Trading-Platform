from datetime import timedelta
from decimal import Context, Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import DirectionalDecision
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.strategies.engine import StrategyAdapter, TrendStrategy
from pocket_alpha.strategies.models import PositionMemory, StrategyProposal
from tests.backtest_fixtures import dataset
from tests.strategy_fixtures import definition, evidence, run_config, view

D = Decimal


def test_proposal_upstream_directional_provenance_and_portfolio_before_risk() -> None:
    value = definition()
    callback = StrategyAdapter(value, run_config())
    current = view()
    intents = callback.on_event(current)
    proposal = callback.memory.proposal
    assert proposal is not None and proposal.action == "ENTER_LONG"
    assert (
        proposal.directional is not None
        and proposal.directional.decision == DirectionalDecision.LONG
    )
    assert (
        proposal.forecast == current.forecasts[0]
        and proposal.technical_input_hash == current.technical.input_hash
    )
    assert (
        proposal.timeframe.value == "1h"
        and proposal.horizon.value == "4H"
        and proposal.invalidation_price == D("95.4")
    )
    assert len(intents) == 1 and intents[0].action == "BUY" and intents[0].quantity is not None
    assert intents[0].quantity * current.history[-1].close <= 1000
    assert not proposal.live_ready and proposal.mode == "RESEARCH_PROPOSAL"
    fresh = StrategyAdapter(value, run_config())
    fresh.restore(callback.checkpoint())
    assert fresh.memory == callback.memory
    assert fresh.on_event(current) == intents


@pytest.mark.parametrize(
    "case",
    ["missing", "flat", "short", "wrong-model", "wrong-horizon", "ambiguous", "stale", "warmup"],
)
def test_missing_opposing_incompatible_or_stale_evidence_has_no_entry(case: str) -> None:
    current = view()
    if case == "missing":
        current = current.model_copy(update={"forecasts": ()})
    elif case == "flat":
        current = view(("100",) * 4)
    elif case == "short":
        current = view(("106", "104", "102", "100"))
        current = current.model_copy(update={"forecasts": (evidence(current.as_of, "-0.02"),)})
    elif case in {"wrong-model", "wrong-horizon"}:
        forecast = current.forecasts[0]
        if case == "wrong-model":
            forecast = forecast.model_copy(update={"model_version": "other-model"})
        else:
            from pocket_alpha.domain.models import ForecastHorizon

            forecast = forecast.model_copy(
                update={
                    "horizon": ForecastHorizon.H1,
                    "expires_at": expires_at(forecast.generated_at, ForecastHorizon.H1),
                }
            )
        current = current.model_copy(update={"forecasts": (forecast,)})
    elif case == "ambiguous":
        current = current.model_copy(
            update={
                "forecasts": current.forecasts
                + (current.forecasts[0].model_copy(update={"forecast_id": uuid4()}),)
            }
        )
    elif case == "stale":
        current = current.model_copy(update={"as_of": current.as_of + timedelta(seconds=61)})
    else:
        current = view(("100",))
    callback = StrategyAdapter(definition(), run_config())
    assert callback.on_event(current) == ()
    assert callback.memory.proposal is not None and callback.memory.proposal.action == "NO_TRADE"


@pytest.mark.parametrize("case", ["invalidation", "horizon", "trend"])
def test_exit_only_owned_inventory_and_explicit_invalidation(case: str) -> None:
    callback = StrategyAdapter(definition(), run_config())
    current = view(quantity="2")
    callback.on_event(current)
    memory = callback.memory
    if case == "invalidation":
        callback.memory = memory.model_copy(update={"invalidation_price": D(200)})
    elif case == "horizon":
        callback.memory = memory.model_copy(update={"holding_until": current.as_of})
    else:
        current = view(("106", "104", "102", "100"), quantity="2")
        current = current.model_copy(update={"forecasts": (evidence(current.as_of, "-0.02"),)})
    result = callback.on_event(current)
    assert len(result) == 1 and result[0].action == "SELL" and result[0].quantity == 2
    proposal = callback.memory.proposal
    assert proposal is not None and proposal.action == "EXIT_LONG"
    assert (
        proposal.reason
        == {
            "invalidation": "PRICE_INVALIDATION",
            "horizon": "HORIZON_EXPIRED",
            "trend": "TREND_INVALIDATION",
        }[case]
    )


@pytest.mark.parametrize("case", ["reserved", "quantity", "minimum", "cash-buffer", "costs"])
def test_portfolio_limits_block_entry_without_risk_authorization(case: str) -> None:
    current = view()
    callback = StrategyAdapter(definition(), run_config())
    if case == "reserved":
        current = view(reserved="100")
    elif case == "quantity":
        current = view(quantity="1")
    elif case == "minimum":
        current = view(cash="0.1")
    elif case == "cash-buffer":
        callback.definition = callback.definition.model_copy(
            update={
                "allocation": callback.definition.allocation.model_copy(
                    update={"cash_buffer_fraction": D("0.999999")}
                )
            }
        )
        callback.strategy = TrendStrategy(callback.definition)
    else:
        current = current.model_copy(update={"forecasts": (evidence(current.as_of, "0.002"),)})
    assert callback.on_event(current) == ()


def test_causal_validation_identity_and_checkpoint_tampering() -> None:
    callback = StrategyAdapter(definition(), run_config())
    current = view()
    with pytest.raises(ValidationError, match="unavailable"):
        callback.on_event(
            current.model_copy(update={"as_of": current.as_of - timedelta(seconds=1)})
        )
    callback.on_event(current)
    proposal = callback.memory.proposal
    assert proposal is not None
    with pytest.raises(ValidationError, match="hash"):
        StrategyProposal.model_validate(proposal.model_dump() | {"reason": "TAMPERED"})
    with pytest.raises(ValueError):
        callback.restore(callback.checkpoint().replace(digest(definition()), "0" * 64, 1))
    with pytest.raises(ValueError):
        StrategyAdapter(definition(), run_config().model_copy(update={"feature_specs": ()}))
    with pytest.raises(ValueError):
        TrendStrategy(definition()).proposal(current, PositionMemory(definition_hash="0" * 64))
    with pytest.raises(ValueError):
        callback.allocate(
            proposal, current.model_copy(update={"as_of": current.as_of + timedelta(seconds=1)})
        )


def test_private_decimal_context_and_shared_backtesting_risk_fills() -> None:
    data = dataset(("100", "102", "104", "106", "108", "110", "112", "114", "116", "118"))
    forecasts = tuple(evidence(bar.close_time) for bar in data.inputs.candles)
    callback = StrategyAdapter(definition(), run_config())
    with localcontext(Context(prec=5)):
        report = Backtester(FrozenClock(data.inputs.captured_at)).run(
            data, run_config(), callback, forecasts
        )
    assert report.fills and report.final_portfolio.cash < report.config.initial_cash
    assert all(
        any(
            e.risk_id == fill.risk_id and e.state == "APPROVED" and e.at < fill.bar_open
            for e in report.orders
        )
        for fill in report.fills
    )
    assert not report.live_ready and not report.profitability_claim


def test_partial_entry_invalidation_cancels_remainder_before_exit() -> None:
    callback = StrategyAdapter(definition(), run_config())
    entry = callback.on_event(view())[0]
    current = view(quantity="1", reserved="500")
    callback.on_event(current)
    callback.memory = callback.memory.model_copy(update={"invalidation_price": D(200)})
    intents = callback.on_event(current)
    assert [i.action for i in intents] == ["CANCEL", "SELL"]
    assert intents[0].cancel_client_id == entry.client_id
    assert intents[1].quantity == 1


@pytest.mark.parametrize("case", ["periods", "requirements", "invalidation", "expiry", "identity"])
def test_schema_rejects_missing_or_inconsistent_contracts(case: str) -> None:
    from pocket_alpha.strategies.models import StrategyDefinition, TrendParameters

    if case == "periods":
        with pytest.raises(ValidationError):
            TrendParameters.model_validate(
                definition().parameters.model_dump() | {"fast_period": 3}
            )
        return
    if case == "requirements":
        with pytest.raises(ValidationError):
            StrategyDefinition.model_validate(definition().model_dump() | {"required_data": ()})
        return
    callback = StrategyAdapter(definition(), run_config())
    callback.on_event(view())
    proposal = callback.memory.proposal
    assert proposal is not None
    data = proposal.model_dump(mode="json", exclude={"content_hash"})
    if case == "invalidation":
        data["invalidation_price"] = None
    elif case == "expiry":
        data["expires_at"] = data["at"]
    else:
        data["market_id"] = "other-market"
    with pytest.raises(ValidationError):
        StrategyProposal.model_validate(data | {"content_hash": digest(data)})
