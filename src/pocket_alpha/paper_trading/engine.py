from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Protocol
from uuid import UUID

from pocket_alpha.backtesting.inputs import ResearchStrategy
from pocket_alpha.backtesting.models import Intent, StrategyView, digest
from pocket_alpha.backtesting.risk import snapshot
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, CandleQuery, UTCDateTime
from pocket_alpha.forecasts.models import ForecastStatus
from pocket_alpha.intelligence.technical.service import _calculate
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy, inspect_candles
from pocket_alpha.paper_trading.models import (
    PaperConfig,
    PaperInput,
    PaperPending,
    PaperState,
    canonical_state,
)
from pocket_alpha.simulation.engine import SimulatedExecution, StrategyError

D = Decimal


class PaperStrategy(ResearchStrategy, Protocol):
    def checkpoint(self) -> str: ...
    def restore(self, checkpoint: str) -> None: ...


class PaperRuntime:
    def __init__(
        self, account_id: UUID, config: PaperConfig, created_at: UTCDateTime, checkpoint: str
    ) -> None:
        self.account_id, self.config = account_id, config
        self.sim = SimulatedExecution(account_id, config.run)
        self.at = created_at
        self.revision = 0
        self.history: list[Candle] = []
        self.last: Candle | None = None
        self.next_open = config.start
        self.checkpoint = canonical_state(checkpoint)
        self.status = "WAITING_DATA"
        self.reason: str | None = None
        self.day = created_at.date()
        self.current: PaperInput | None = None

    def cancel(self, reason: str) -> None:
        for order in list(self.sim.pending):
            self.sim.terminal(order, self.at, "CANCELLED", reason)

    def suspend(self, reason: str) -> None:
        if self.status not in {"HALTED", "CLOSED"}:
            self.status, self.reason = "SUSPENDED", reason
        self.cancel(reason)

    def market(self, event: PaperInput) -> None:
        if event.at < self.at:
            raise ValueError("paper input must be chronologically ordered")
        if self.status == "CLOSED":
            raise ValueError("paper account is closed")
        self.at, self.current = event.at, event
        if event.kind == "DISCONNECT":
            self.suspend(event.reason or "FEED_DISCONNECTED")
        if event.kind in {"KILL", "CLOSE"}:
            self.status = "HALTED" if event.kind == "KILL" else "CLOSED"
            self.reason = "OPERATOR_KILL_SWITCH" if event.kind == "KILL" else "OPERATOR_CLOSE"
            if event.kind == "KILL":
                self.sim.halted = self.reason
            self.cancel(self.reason)
        self.sim.timers(self.at)
        if self.at.date() != self.day:
            self.sim.book.daily_start_equity = self.sim.book.cash + self.sim.book.quantity * (
                self.last.close if self.last else D(0)
            )
            self.day = self.at.date()
        if event.kind == "CANDLE":
            candle = event.candle
            assert candle is not None
            if (
                candle.market_id != self.config.market.market_id
                or candle.source != self.config.mapping.source
                or candle.timeframe != self.config.timeframe
                or candle.open_time != self.next_open
                or candle.received_at > self.at
            ):
                raise ValueError("paper candle mapping, gap, duplicate or receipt invalid")
            query = CandleQuery(
                market_id=candle.market_id,
                timeframe=candle.timeframe,
                start=candle.open_time,
                end=candle.close_time,
            )
            try:
                _, quality = inspect_candles(
                    [candle.model_dump()],
                    query,
                    candle.source,
                    FreshnessPolicy(),
                    FrozenClock(self.at),
                )
            except DataRejected as error:
                raise ValueError("paper market quality rejected") from error
            if not quality.valid:
                raise ValueError("paper market quality rejected")
            for forecast in event.forecasts:
                if (
                    forecast.market_id != candle.market_id
                    or forecast.asset_id != self.config.asset.asset_id
                    or forecast.model_version != self.config.run.strategy.model_version
                    or forecast.feature_version != self.config.run.feature_version
                    or forecast.generated_at > self.at
                ):
                    raise ValueError("paper forecast identity/version/availability rejected")
            self.history.append(candle)
            self.history = self.history[-self.config.run.maximum_history_bars :]
            self.last = candle
            self.next_open = candle.close_time
            if (
                self.at - candle.close_time
            ).total_seconds() > self.config.run.risk.maximum_data_age_seconds:
                self.suspend("STALE_FEED")
            self.sim.observe_risk(candle.close)
            if self.status in {"WAITING_DATA", "ACTIVE"}:
                # Original receipt remains immutable in the journal; fills observe processing time.
                self.sim.execute(candle.model_copy(update={"received_at": self.at}), candle.close)
                self.status = "ACTIVE"
        if self.last is not None:
            self.sim.observe_risk(self.last.close)
            if self.sim.halted:
                self.status, self.reason = "HALTED", self.sim.halted
                self.cancel(self.reason)
            elif (
                self.at - self.last.close_time
            ).total_seconds() > self.config.run.risk.maximum_data_age_seconds:
                self.suspend("STALE_FEED")
        if event.kind == "RECONCILE":
            expected = self.state().accounting_hash
            if event.reconciliation_hash != expected:
                self.suspend("RECONCILIATION_MISMATCH")
            elif self.status not in {"HALTED", "CLOSED"}:
                if (
                    self.last is not None
                    and (self.at - self.last.close_time).total_seconds()
                    <= self.config.run.risk.maximum_data_age_seconds
                ):
                    self.status, self.reason = "ACTIVE", None
                else:
                    self.suspend("RECONCILIATION_REQUIRES_FRESH_DATA")

    def view(self) -> StrategyView | None:
        if self.current is None or self.current.kind != "CANDLE" or self.status != "ACTIVE":
            return None
        assert self.last is not None and self.history
        candles = tuple(self.history)
        query = CandleQuery(
            market_id=self.last.market_id,
            timeframe=self.last.timeframe,
            start=candles[0].open_time,
            end=self.last.close_time,
        )
        features = _calculate(candles, query, FreshnessPolicy(), self.config.run.feature_specs)[-1]
        return StrategyView(
            as_of=self.at,
            history=candles,
            technical=features,
            forecasts=tuple(
                f
                for f in self.current.forecasts
                if f.status == ForecastStatus.AVAILABLE and f.generated_at <= self.at < f.expires_at
            ),
            portfolio=snapshot(self.sim.book, self.sim.pending, self.last.close),
        )

    def decisions(self, intents: tuple[Intent, ...], checkpoint: str, failure: str | None) -> None:
        view = self.view()
        if intents and view is None:
            raise ValueError("paper decisions require fresh active market input")
        if failure:
            if intents:
                raise ValueError("failed strategy cannot emit intentions")
            self.suspend(failure)
        if view is not None:
            assert self.last is not None
            for intent in intents:
                self.sim.submit(intent, self.at, self.last, view.technical.bar_close)
        self.checkpoint = canonical_state(checkpoint)
        self.revision += 1

    def call(self, strategy: PaperStrategy) -> tuple[tuple[Intent, ...], str, str | None]:
        view = self.view()
        if view is None:
            return (), self.checkpoint, None
        try:
            with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                if strategy.identity != self.config.run.strategy:
                    raise StrategyError("paper strategy identity mismatch")
                strategy.restore(self.checkpoint)
                emitted = strategy.on_event(view)
                if not isinstance(emitted, tuple) or len(emitted) > 10:
                    raise StrategyError("paper strategy must emit a bounded tuple")
                intents = tuple(Intent.model_validate_json(i.model_dump_json()) for i in emitted)
                checkpoint = canonical_state(strategy.checkpoint())
                if strategy.identity != self.config.run.strategy:
                    raise StrategyError("paper strategy identity changed")
            return intents, checkpoint, None
        except Exception:
            return (), self.checkpoint, "STRATEGY_FAILED"

    def state(self) -> PaperState:
        mark = self.last.close if self.last else D(0)
        portfolio = snapshot(self.sim.book, self.sim.pending, mark)
        pending = tuple(
            PaperPending.model_validate(
                dict(
                    client_id=o.intent.client_id,
                    risk_id=o.risk_id,
                    action=o.intent.action,
                    created_at=o.created_at,
                    ready_at=o.ready_at,
                    expires_at=o.expires_at,
                    remaining=o.remaining,
                    reserved_unit_cash=o.reserved_unit_cash,
                    acknowledged=o.acknowledged,
                )
            )
            for o in self.sim.pending
        )
        accounting = dict(
            portfolio=portfolio.model_dump(mode="json"),
            pending=[p.model_dump(mode="json") for p in pending],
            fills=[f.model_dump(mode="json") for f in self.sim.fills],
        )
        draft = PaperState.model_construct(
            account_id=self.account_id,
            revision=self.revision,
            origin=self.config.origin,
            market_id=self.config.market.market_id,
            asset_id=self.config.asset.asset_id,
            quote_currency=self.config.market.quote_currency,
            at=self.at,
            status=self.status,
            reason=self.reason,
            next_open=self.next_open,
            last_price=self.last.close if self.last else None,
            last_close=self.last.close_time if self.last else None,
            portfolio=portfolio,
            initial_cash=self.config.run.initial_cash,
            realized_pnl=sum((f.realized_pnl or D(0) for f in self.sim.fills), D(0)),
            unrealized_pnl=portfolio.quantity * mark - portfolio.cost_basis if self.last else None,
            net_return=portfolio.equity / self.config.run.initial_cash - 1 if self.last else None,
            total_fees=sum((f.fee for f in self.sim.fills), D(0)),
            pending=pending,
            orders=tuple(self.sim.events),
            fills=tuple(self.sim.fills),
            strategy_checkpoint=self.checkpoint,
            accounting_hash=digest(accounting),
            state_hash="0" * 64,
        )
        return PaperState.model_validate(
            draft.model_dump()
            | dict(state_hash=digest(draft.model_dump(mode="json", exclude={"state_hash"})))
        )
