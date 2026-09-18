import logging
from decimal import ROUND_HALF_EVEN, Context, localcontext
from uuid import UUID, uuid4

from pocket_alpha.backtesting.inputs import current_code_hash, current_environment_hash
from pocket_alpha.backtesting.models import digest
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.market_data.storage import (
    AssetRecord,
    MarketRecord,
    MarketRepository,
    VenueRecord,
    asset_value,
    market_value,
)
from pocket_alpha.paper_trading.engine import PaperRuntime, PaperStrategy
from pocket_alpha.paper_trading.models import (
    PaperConfig,
    PaperHeader,
    PaperInput,
    PaperJournal,
    PaperState,
    PaperView,
    canonical_state,
)
from pocket_alpha.paper_trading.storage import PaperConflict, PaperRepository
from pocket_alpha.simulation.engine import StrategyError

logger = logging.getLogger(__name__)


class PaperService:
    def __init__(self, repository: PaperRepository, clock: Clock) -> None:
        self.repository, self.clock = repository, clock

    def create(self, config: PaperConfig, strategy: PaperStrategy) -> PaperState:
        config = PaperConfig.model_validate_json(config.model_dump_json())
        self._identity(config)
        if strategy.identity != config.run.strategy:
            raise ValueError("paper strategy identity mismatch")
        session = self.repository.session
        market = session.get(MarketRecord, config.market.market_id)
        asset = session.get(AssetRecord, config.asset.asset_id)
        venue = session.get(VenueRecord, config.venue.venue_id)
        if (
            market is None
            or asset is None
            or venue is None
            or (
                market_value(market) != config.market
                or asset_value(asset) != config.asset
                or venue.name != config.venue.name
                or MarketRepository(session).mapping(config.market.market_id, config.mapping.source)
                != config.mapping
            )
        ):
            raise ValueError("paper requires registered matching market provenance")
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            checkpoint = canonical_state(strategy.checkpoint())
            header = PaperHeader(
                account_id=uuid4(),
                config=config,
                created_at=utc(self.clock.now()),
                initial_checkpoint=checkpoint,
            )
            state = PaperRuntime(header.account_id, config, header.created_at, checkpoint).state()
            with session.begin_nested():
                self.repository.create(header, state)
        logger.info(
            "PAPER account transaction prepared",
            extra={"mode": "PAPER", "account_id": str(state.account_id)},
        )
        return state

    def _identity(self, config: PaperConfig) -> None:
        if (
            config.run.code_tree_hash != current_code_hash()
            or config.run.environment_hash != current_environment_hash()
        ):
            raise ValueError("paper source/runtime identity changed; session is not ready")

    def view(self, account_id: UUID) -> PaperView | None:
        loaded = self.repository.load(account_id)
        if loaded is None:
            return None
        header, runtime, _ = loaded
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            state = runtime.state()
        now = utc(self.clock.now())
        if now < state.at:
            raise ValueError("paper clock is earlier than persisted state")
        reason = state.reason
        ready = state.status == "ACTIVE"
        if state.last_close is None:
            ready, reason = False, reason or "WAITING_DATA"
        elif (
            ready
            and (now - state.last_close).total_seconds()
            > header.config.run.risk.maximum_data_age_seconds
        ):
            ready, reason = False, "STALE_FEED"
        if state.revision >= header.config.maximum_events:
            ready, reason = False, "JOURNAL_BUDGET_EXHAUSTED"
        if (
            header.config.run.code_tree_hash != current_code_hash()
            or header.config.run.environment_hash != current_environment_hash()
        ):
            ready, reason = False, "RUNTIME_IDENTITY_CHANGED"
        return PaperView(
            config=header.config, state=state, observed_at=now, ready=ready, readiness_reason=reason
        )

    def process(
        self, account_id: UUID, event: PaperInput, strategy: PaperStrategy, expected_revision: int
    ) -> PaperState:
        event = PaperInput.model_validate_json(event.model_dump_json())
        request_hash = digest(event)
        with self.repository.session.begin_nested():
            loaded = self.repository.load(account_id)
            if loaded is None:
                raise LookupError("paper account not found")
            header, runtime, entries = loaded
            previous = next((e for e in entries if e.input.event_id == event.event_id), None)
            if previous is not None:
                if previous.request_hash != request_hash:
                    raise PaperConflict("paper event id reused with conflicting input")
                with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                    return runtime.state()
            if runtime.revision != expected_revision:
                raise PaperConflict("paper revision changed; reload before retry")
            self._identity(header.config)
            if runtime.revision >= header.config.maximum_events and event.kind not in {
                "KILL",
                "CLOSE",
            }:
                raise ValueError("paper journal budget exceeded; session is not ready")
            now = utc(self.clock.now())
            if event.at > now or event.at < runtime.at or runtime.status == "CLOSED":
                raise ValueError("paper event timestamp/account state invalid")
            with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                event = event.model_copy(update={"at": now})
                previous_hash = entries[-1].content_hash if entries else runtime.state().state_hash
                try:
                    runtime.market(event)
                except ValueError:
                    # Discard any tentative timers/fills before recording a failed input.
                    loaded = self.repository.load(account_id)
                    assert loaded is not None
                    runtime = loaded[1]
                    event = PaperInput(
                        event_id=event.event_id,
                        at=event.at,
                        kind="DISCONNECT",
                        reason="INVALID_MARKET_DATA",
                    )
                    runtime.market(event)
                intents, checkpoint, failure = runtime.call(strategy)
                try:
                    runtime.decisions(intents, checkpoint, failure)
                except (ValueError, StrategyError):
                    # Replay market fills and discard all new intentions.
                    restored = self.repository.load(account_id)
                    assert restored is not None
                    runtime = restored[1]
                    runtime.market(event)
                    intents, checkpoint, failure = (), runtime.checkpoint, "STRATEGY_FAILED"
                    runtime.decisions(intents, checkpoint, failure)
                state = runtime.state()
                draft = PaperJournal.model_construct(
                    account_id=account_id,
                    revision=state.revision,
                    request_hash=request_hash,
                    input=event,
                    intents=intents,
                    strategy_checkpoint=checkpoint,
                    failure=failure,
                    previous_hash=previous_hash,
                    state_hash=state.state_hash,
                    content_hash="0" * 64,
                )
                entry = PaperJournal.model_validate(
                    draft.model_dump()
                    | dict(
                        content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"}))
                    )
                )
                self.repository.append(entry, state)
        logger.info(
            "PAPER journal transaction prepared",
            extra={
                "mode": "PAPER",
                "account_id": str(account_id),
                "revision": state.revision,
                "paper_status": state.status,
                "paper_reason": state.reason,
            },
        )
        return state
