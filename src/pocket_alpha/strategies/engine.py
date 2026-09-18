"""Strategies consume shared intelligence; portfolio turns proposals into risk-bound intents."""

import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.backtesting.execution import stepped
from pocket_alpha.backtesting.models import Intent, RunConfig, StrategyView, digest
from pocket_alpha.backtesting.risk import reserve_unit
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.directional.models import (
    ComparisonOperator,
    DirectionalAnalysis,
    DirectionalAnalysisRequest,
    DirectionalCaseInput,
    DirectionalCasePolicy,
    DirectionalCriterionDefinition,
    DirectionalDecision,
    DirectionalMetric,
    DirectionalPolicy,
    DirectionalSide,
    MetricStatus,
)
from pocket_alpha.directional.service import DirectionalAnalysisEngine
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import Forecast, ForecastStatus
from pocket_alpha.forecasts.service import canonical_snapshot
from pocket_alpha.intelligence.technical.models import FeatureStatus, IndicatorKind, IndicatorSpec
from pocket_alpha.paper_trading.models import canonical_state
from pocket_alpha.strategies.models import PositionMemory, StrategyDefinition, StrategyProposal

D = Decimal


class TrendStrategy:
    def __init__(self, definition: StrategyDefinition) -> None:
        self.definition = StrategyDefinition.model_validate_json(definition.model_dump_json())

    def proposal(self, view: StrategyView, memory: PositionMemory) -> StrategyProposal:
        view = StrategyView.model_validate_json(view.model_dump_json())
        if memory.definition_hash != digest(self.definition):
            raise ValueError("strategy position memory belongs to another definition")
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            return self._proposal(view, memory)

    def _proposal(self, view: StrategyView, memory: PositionMemory) -> StrategyProposal:
        definition = self.definition
        feature = view.technical
        action, reason = "NO_TRADE", "MISSING_EVIDENCE"
        forecast: Forecast | None = None
        directional: DirectionalAnalysis | None = None
        price, stop = None, None
        deadline = expires_at(view.as_of, definition.horizon)
        valid = bool(view.history) and (
            feature.market_id,
            feature.timeframe,
            feature.source,
            feature.engine_version,
        ) == (
            definition.market_id,
            definition.timeframe,
            definition.source,
            definition.feature_version,
        )
        if valid:
            last = view.history[-1]
            valid = (
                (last.market_id, last.timeframe, last.source, last.close_time)
                == (
                    definition.market_id,
                    definition.timeframe,
                    definition.source,
                    feature.bar_close,
                )
                and feature.available_at <= view.as_of
                and (view.as_of - last.close_time).total_seconds()
                <= definition.maximum_data_age_seconds
            )
            valid = valid and all(
                c.market_id == definition.market_id
                and c.source == definition.source
                and c.timeframe == definition.timeframe
                and c.received_at <= view.as_of
                and c.close_time <= view.as_of
                for c in view.history
            )
        if valid:
            price = view.history[-1].close
            stop = (
                memory.invalidation_price
                if memory.observed_quantity > 0
                else price * (1 - definition.parameters.invalidation_fraction)
            )
            if view.portfolio.quantity > 0 and memory.observed_quantity > 0:
                if memory.holding_until is not None and view.as_of >= memory.holding_until:
                    action, reason = "EXIT_LONG", "HORIZON_EXPIRED"
                elif stop is not None and price <= stop:
                    action, reason = "EXIT_LONG", "PRICE_INVALIDATION"
            values = []
            for period in (definition.parameters.fast_period, definition.parameters.slow_period):
                matches = [
                    r
                    for r in feature.results
                    if r.spec == IndicatorSpec(kind=IndicatorKind.SMA, period=period)
                ]
                value = (
                    next(
                        (
                            f.value
                            for f in matches[0].features
                            if f.name == "sma" and f.status == FeatureStatus.READY
                        ),
                        None,
                    )
                    if len(matches) == 1
                    else None
                )
                values.append(value)
            candidates = [
                f
                for f in view.forecasts
                if f.market_id == definition.market_id
                and f.asset_id == definition.asset_id
                and f.candle_timeframe == definition.timeframe
                and f.horizon == definition.horizon
                and f.model_version == definition.model_version
                and f.feature_version == definition.feature_version
                and f.status == ForecastStatus.AVAILABLE
                and f.generated_at <= view.as_of < f.expires_at
            ]
            latest = max((f.generated_at for f in candidates), default=None)
            current = [f for f in candidates if f.generated_at == latest]
            if len(current) == 1 and all(v is not None and v > 0 for v in values):
                forecast = current[0]
                fast, slow = values
                assert (
                    fast is not None and slow is not None and forecast.expected_return is not None
                )
                trend = (fast / slow - 1).quantize(D("1e-24"))
                expected = forecast.expected_return.quantize(D("1e-24"))
                directional = self._directional(view, forecast, trend, expected)
                if action == "NO_TRADE":
                    if view.portfolio.quantity > 0:
                        if directional.decision == DirectionalDecision.SHORT:
                            action, reason = "EXIT_LONG", "TREND_INVALIDATION"
                        else:
                            reason = "HOLD_OR_NO_TRADE"
                    elif directional.decision == DirectionalDecision.LONG:
                        action, reason = "ENTER_LONG", "LONG_CASE_ONLY"
                    else:
                        reason = directional.reason.value
        payload = dict(
            definition_hash=digest(definition),
            at=view.as_of,
            market_id=definition.market_id,
            asset_id=definition.asset_id,
            timeframe=definition.timeframe,
            horizon=definition.horizon,
            action=action,
            reason=reason,
            reference_price=price,
            invalidation_price=stop,
            expires_at=deadline,
            technical_input_hash=feature.input_hash if valid else None,
            directional=directional,
            forecast=forecast,
            input_hash=digest(view),
        )
        identifier = uuid5(
            NAMESPACE_URL,
            "pocket-alpha-strategy-proposal:"
            + digest(
                {
                    k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else str(v))
                    for k, v in payload.items()
                }
            ),
        )
        draft = StrategyProposal.model_construct(
            **cast(Any, payload | dict(proposal_id=identifier, content_hash="0" * 64))
        )
        return StrategyProposal.model_validate(
            draft.model_dump()
            | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
        )

    def _directional(
        self, view: StrategyView, forecast: Forecast, trend: Decimal, expected: Decimal
    ) -> DirectionalAnalysis:
        p = self.definition.parameters
        evidence = (
            canonical_snapshot(
                "technical",
                "technical-1.0.0",
                view.technical.input_hash,
                view.technical.available_at,
                view.technical.model_dump(mode="json"),
            ),
            canonical_snapshot(
                "forecast",
                forecast.model_version,
                digest(forecast),
                forecast.generated_at,
                forecast.model_dump(mode="json"),
            ),
        )
        definitions = []
        inputs = []
        for side in (DirectionalSide.LONG, DirectionalSide.SHORT):
            op = (
                ComparisonOperator.GREATER_THAN_OR_EQUAL
                if side == DirectionalSide.LONG
                else ComparisonOperator.LESS_THAN_OR_EQUAL
            )
            sign = D(1) if side == DirectionalSide.LONG else D(-1)
            criteria = tuple(
                DirectionalCriterionDefinition(
                    criterion=name,
                    label=name,
                    operator=op,
                    threshold=sign * threshold,
                    rule_version=self.definition.version,
                )
                for name, threshold in (
                    ("sma-trend", p.minimum_trend_fraction),
                    ("expected-return", p.minimum_expected_return),
                )
            )
            definitions.append(DirectionalCasePolicy(side=side, criteria=criteria))
            inputs.append(
                DirectionalCaseInput(
                    side=side,
                    metrics=tuple(
                        DirectionalMetric(
                            criterion=name,
                            status=MetricStatus.AVAILABLE,
                            value=value,
                            source_version=self.definition.version,
                            available_at=max(e.available_at for e in evidence),
                            evidence=evidence,
                        )
                        for name, value in (("sma-trend", trend), ("expected-return", expected))
                    ),
                )
            )
        request = DirectionalAnalysisRequest(
            analysis_id=uuid5(NAMESPACE_URL, digest(view)),
            market_id=self.definition.market_id,
            asset_id=self.definition.asset_id,
            candle_timeframe=self.definition.timeframe,
            horizon=self.definition.horizon,
            as_of=view.as_of,
            policy=DirectionalPolicy(
                policy_version=self.definition.version,
                long_case=definitions[0],
                short_case=definitions[1],
            ),
            long_case=inputs[0],
            short_case=inputs[1],
        )
        return DirectionalAnalysisEngine(FrozenClock(view.as_of)).analyze(
            request, generated_at=view.as_of
        )


class StrategyAdapter:
    """Research/PAPER callback. No broker port; every emitted intent still requires risk."""

    def __init__(self, definition: StrategyDefinition, run: RunConfig) -> None:
        self.strategy = TrendStrategy(definition)
        self.definition = self.strategy.definition
        self.identity = self.definition.identity()
        self.run = RunConfig.model_validate_json(run.model_dump_json())
        required = tuple(
            IndicatorSpec(kind=IndicatorKind.SMA, period=p)
            for p in (definition.parameters.fast_period, definition.parameters.slow_period)
        )
        if (
            run.strategy != self.identity
            or run.feature_version != definition.feature_version
            or not all(s in run.feature_specs for s in required)
            or run.maximum_history_bars < definition.parameters.slow_period
        ):
            raise ValueError("strategy/run identity or required indicators mismatch")
        self.memory = PositionMemory(definition_hash=digest(self.definition))

    def checkpoint(self) -> str:
        return json.dumps(
            self.memory.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def restore(self, checkpoint: str) -> None:
        memory = PositionMemory.model_validate_json(canonical_state(checkpoint))
        if memory.definition_hash != digest(self.definition):
            raise ValueError("strategy checkpoint definition mismatch")
        self.memory = memory

    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            if view.portfolio.quantity == 0 and view.portfolio.reserved_cash == 0:
                memory = PositionMemory(definition_hash=digest(self.definition))
            elif self.memory.observed_quantity == 0 and view.portfolio.quantity > 0:
                # Position ownership is observed from actual fills, never presumed from a proposal.
                price = view.portfolio.cost_basis / view.portfolio.quantity
                memory = PositionMemory(
                    definition_hash=digest(self.definition),
                    observed_quantity=view.portfolio.quantity,
                    invalidation_price=price
                    * (1 - self.definition.parameters.invalidation_fraction),
                    holding_until=expires_at(view.as_of, self.definition.horizon),
                    entry_client_id=self.memory.entry_client_id,
                )
            else:
                memory = self.memory.model_copy(
                    update={"observed_quantity": view.portfolio.quantity}
                )
            proposal = self.strategy.proposal(view, memory)
            self.memory = memory.model_copy(update={"proposal": proposal})
            intents = self.allocate(proposal, view)
            if intents and proposal.action == "ENTER_LONG":
                self.memory = self.memory.model_copy(
                    update={"entry_client_id": intents[0].client_id}
                )
            return intents

    def allocate(self, proposal: StrategyProposal, view: StrategyView) -> tuple[Intent, ...]:
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            return self._allocate(proposal, view)

    def _allocate(self, proposal: StrategyProposal, view: StrategyView) -> tuple[Intent, ...]:
        proposal = StrategyProposal.model_validate_json(proposal.model_dump_json())
        if (
            proposal.definition_hash != digest(self.definition)
            or proposal.at != view.as_of
            or proposal.input_hash != digest(view)
        ):
            raise ValueError("portfolio requires a matching causal strategy proposal")
        price = proposal.reference_price
        if proposal.action == "NO_TRADE" or price is None:
            return ()
        state = view.portfolio
        cancellations: tuple[Intent, ...] = ()
        if proposal.action == "EXIT_LONG":
            if state.reserved_cash > 0 and self.memory.entry_client_id is not None:
                cancellations = (
                    Intent(
                        client_id="strategy-cancel:" + str(proposal.proposal_id),
                        action="CANCEL",
                        cancel_client_id=self.memory.entry_client_id,
                    ),
                )
            quantity = stepped(
                state.quantity - state.reserved_quantity, self.run.costs.quantity_step
            )
        else:
            # Do not pyramid or replace an already reserved entry.
            if state.quantity > 0 or state.reserved_cash > 0:
                return ()
            if proposal.forecast is None or proposal.forecast.expected_return is None:
                return ()
            costs = self.run.costs
            modeled_round_trip = (
                2
                * (
                    costs.fee_bps
                    + costs.spread_bps / 2
                    + costs.slippage_bps
                    + costs.impact_bps_at_capacity
                )
                / 10000
            )
            if (
                proposal.forecast.expected_return
                <= modeled_round_trip + self.definition.parameters.minimum_expected_return
            ):
                return ()
            policy = self.definition.allocation
            cash = max(
                D(0), state.cash - state.reserved_cash - state.equity * policy.cash_buffer_fraction
            )
            budget = min(
                cash,
                state.equity * policy.target_exposure_fraction,
                policy.maximum_proposal_notional,
            )
            quantity = stepped(budget / reserve_unit(price, self.run), self.run.costs.quantity_step)
        if (
            quantity < self.run.costs.minimum_quantity
            or quantity * price < self.run.costs.minimum_notional
        ):
            return cancellations
        return cancellations + (
            Intent(
                client_id="strategy:" + str(proposal.proposal_id),
                action="BUY" if proposal.action == "ENTER_LONG" else "SELL",
                quantity=quantity,
            ),
        )
