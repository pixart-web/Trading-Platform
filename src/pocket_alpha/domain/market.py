from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from pocket_alpha.common.clock import utc
from pocket_alpha.domain.models import AssetId, Currency, DomainModel, Symbol, Timeframe

UTCDateTime = Annotated[AwareDatetime, AfterValidator(utc)]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Price = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]


class MarketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class BookSide(StrEnum):
    BID = "BID"
    ASK = "ASK"


class Venue(DomainModel):
    venue_id: Identifier
    name: str = Field(min_length=1, max_length=256)


class Market(DomainModel):
    market_id: Identifier
    asset_id: AssetId
    venue_id: Identifier
    symbol: Symbol
    quote_currency: Currency


class TradingSession(DomainModel):
    market_id: Identifier
    opens_at: UTCDateTime
    closes_at: UTCDateTime
    status: MarketStatus

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.closes_at <= self.opens_at:
            raise ValueError("session must have positive duration")
        return self


class Candle(DomainModel):
    market_id: Identifier
    timeframe: Timeframe
    open_time: UTCDateTime
    close_time: UTCDateTime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    source: Identifier
    received_at: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("INVALID_OHLC")
        if self.close_time != self.open_time + self.timeframe.duration:
            raise ValueError("INVALID_TIMESTAMP")
        if self.received_at < self.close_time:
            raise ValueError("INVALID_TIMESTAMP")
        return self


class Trade(DomainModel):
    market_id: Identifier
    provider_trade_id: str | None = Field(default=None, min_length=1, max_length=256)
    timestamp: UTCDateTime
    price: Price
    quantity: Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
    aggressor_side: Side = Side.UNKNOWN
    source: Identifier


class Quote(DomainModel):
    market_id: Identifier
    timestamp: UTCDateTime
    bid: Price
    ask: Price
    bid_size: Quantity | None = None
    ask_size: Quantity | None = None
    source: Identifier

    @model_validator(mode="after")
    def uncrossed(self) -> Self:
        if self.bid > self.ask:
            raise ValueError("crossed quote")
        return self


class OrderBookLevel(DomainModel):
    side: BookSide
    price: Price
    quantity: Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]


class OrderBook(DomainModel):
    market_id: Identifier
    timestamp: UTCDateTime
    source: Identifier
    sequence: int | None = Field(default=None, ge=0)
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        for levels, side, descending in (
            (self.bids, BookSide.BID, True),
            (self.asks, BookSide.ASK, False),
        ):
            prices = [level.price for level in levels]
            if any(level.side != side for level in levels):
                raise ValueError("wrong book side")
            if len(set(prices)) != len(prices) or prices != sorted(prices, reverse=descending):
                raise ValueError("unordered or duplicate levels")
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise ValueError("crossed book")
        return self


class CandleQuery(DomainModel):
    market_id: Identifier
    timeframe: Timeframe
    start: UTCDateTime
    end: UTCDateTime
    # Explicit session-aware schedule; None declares a continuous series anchored at start.
    expected_opens: tuple[UTCDateTime, ...] | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must follow start")
        if self.expected_opens is None:
            slots = (self.end - self.start) / self.timeframe.duration
            if slots > 10000 or not slots.is_integer():
                raise ValueError("range must contain 1..10000 whole timeframe slots")
        elif tuple(sorted(set(self.expected_opens))) != self.expected_opens or any(
            not self.start <= t < self.end for t in self.expected_opens
        ):
            raise ValueError("expected opens must be unique, ascending and within range")
        return self

    def schedule(self) -> tuple[datetime, ...]:
        if self.expected_opens is not None:
            return self.expected_opens
        count = int((self.end - self.start) / self.timeframe.duration)
        return tuple(self.start + i * self.timeframe.duration for i in range(count))
