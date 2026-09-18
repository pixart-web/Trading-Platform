"""Explicit one-shot public polling; no startup worker, credentials or broker routing."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pocket_alpha.common.clock import utc
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.market_data.coinbase import CoinbaseHistoricalProvider
from pocket_alpha.market_data.providers import HistoricalMarketDataProvider, ProviderError
from pocket_alpha.paper_trading.engine import PaperStrategy
from pocket_alpha.paper_trading.models import PaperInput, PaperState
from pocket_alpha.paper_trading.service import PaperService


class PublicPaperPoller:
    def __init__(
        self, service: PaperService, provider: HistoricalMarketDataProvider | None = None
    ) -> None:
        self.service = service
        self.provider = provider or CoinbaseHistoricalProvider()

    def poll(self, account_id: UUID, strategy: PaperStrategy) -> PaperState:
        if not isinstance(account_id, UUID):
            raise ValueError("PAPER account id must be a UUID")
        view = self.service.view(account_id)
        if view is None:
            raise LookupError("PAPER account not found")
        config, state = view.config, view.state
        if config.origin != "REAL" or self.provider.source != config.mapping.source:
            raise ValueError("public PAPER polling requires the native REAL mapping")
        if state.status in {"HALTED", "CLOSED"}:
            raise ValueError("PAPER account is terminal")
        now = utc(self.service.clock.now())
        seconds = int(config.timeframe.duration.total_seconds())
        end = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, UTC)

        def process(event: PaperInput) -> PaperState:
            nonlocal state
            state = self.service.process(account_id, event, strategy, state.revision)
            return state

        if end <= state.next_open:
            return process(PaperInput(event_id=uuid4(), at=now, kind="HEARTBEAT"))
        end = min(end, state.next_open + 299 * config.timeframe.duration)
        query = CandleQuery(
            market_id=config.market.market_id,
            timeframe=config.timeframe,
            start=state.next_open,
            end=end,
        )
        try:
            page = self.provider.candles(query, config.mapping, None)
            bars = tuple(Candle.model_validate(row) for row in page.records)
            expected = int((end - query.start) / config.timeframe.duration)
            if (
                page.next_cursor is not None
                or len(bars) != expected
                or tuple(b.open_time for b in bars)
                != tuple(query.start + i * config.timeframe.duration for i in range(expected))
            ):
                raise ProviderError("public PAPER candle grid incomplete")
        except (ProviderError, ValueError):
            return process(
                PaperInput(
                    event_id=uuid4(),
                    at=utc(self.service.clock.now()),
                    kind="DISCONNECT",
                    reason="FEED_UNAVAILABLE",
                )
            )
        for bar in bars:
            process(
                PaperInput(
                    event_id=uuid4(), at=utc(self.service.clock.now()), kind="CANDLE", candle=bar
                )
            )
            if state.next_open <= bar.open_time or state.status == "HALTED":
                break
        return state
