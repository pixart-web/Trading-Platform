"""Frozen, explicitly labelled research inputs; historical downloads are available at ingestion."""

import hashlib
from datetime import datetime
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.common.clock import FrozenClock, utc
from pocket_alpha.database import Base
from pocket_alpha.domain.market import Candle, CandleQuery, Market, UTCDateTime, Venue
from pocket_alpha.domain.models import Asset, AssetType, DomainModel
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy, inspect_candles
from pocket_alpha.market_data.replay import ReplayEvent
from pocket_alpha.market_data.storage import (
    AssetRecord,
    MarketRecord,
    MarketRepository,
    VenueRecord,
    asset_value,
    market_value,
)


class DatasetInputs(DomainModel):
    schema_version: Literal["market-dataset-1.0.0"] = "market-dataset-1.0.0"
    origin: Literal["REAL", "SYNTHETIC"]
    mapping: ProviderMapping
    market: Market
    asset: Asset
    venue: Venue
    query: CandleQuery
    captured_at: UTCDateTime
    candles: tuple[Candle, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def quality(self) -> Self:
        if (
            self.mapping.market_id != self.query.market_id
            or self.market.market_id != self.query.market_id
            or self.market.asset_id != self.asset.asset_id
            or self.market.venue_id != self.venue.venue_id
        ):
            raise ValueError("dataset mapping does not match query")
        if self.origin == "REAL" and self.mapping.source != "coinbase-exchange":
            raise ValueError("real dataset requires implemented public market source")
        if self.origin == "REAL" and (
            self.asset.asset_type != AssetType.CRYPTO
            or self.mapping.instrument_id != self.market.symbol
            or self.market.venue_id != "coinbase-exchange"
            or self.mapping.instrument_id != f"{self.asset.symbol}-{self.market.quote_currency}"
        ):
            raise ValueError("real dataset requires verified base/quote/venue product mapping")
        _, result = inspect_candles(
            [c.model_dump() for c in self.candles],
            self.query,
            self.mapping.source,
            FreshnessPolicy(),
            FrozenClock(self.captured_at),
        )
        if not result.valid:
            raise DataRejected(result)
        return self

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class MarketDataset(DomainModel):
    dataset_id: UUID
    inputs: DatasetInputs
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.content_hash != self.inputs.digest():
            raise ValueError("dataset hash does not match immutable inputs")
        return self

    def replay(self) -> tuple[ReplayEvent, ...]:
        return tuple(
            sorted(
                (ReplayEvent(self.inputs.captured_at, c) for c in self.inputs.candles),
                key=lambda e: (e.available_at, e.candle.open_time),
            )
        )


class MarketDatasetRecord(Base):
    __tablename__ = "market_data_datasets"
    dataset_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class DatasetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def freeze(
        self,
        query: CandleQuery,
        source: str,
        origin: Literal["REAL", "SYNTHETIC"],
        captured_at: datetime,
    ) -> MarketDataset:
        repository = MarketRepository(self.session)
        market = self.session.get(MarketRecord, query.market_id)
        if market is None:
            raise LookupError("dataset market not registered")
        asset = self.session.get(AssetRecord, market.asset_id)
        venue = self.session.get(VenueRecord, market.venue_id)
        if asset is None or venue is None:
            raise LookupError("dataset market references not registered")
        inputs = DatasetInputs(
            market=market_value(market),
            asset=asset_value(asset),
            venue=Venue(venue_id=venue.venue_id, name=venue.name),
            origin=origin,
            mapping=repository.mapping(query.market_id, source),
            query=query,
            captured_at=utc(captured_at),
            candles=repository.candles(query, limit=10001),
        )
        dataset = MarketDataset(dataset_id=uuid4(), inputs=inputs, content_hash=inputs.digest())
        self.session.add(
            MarketDatasetRecord(dataset_id=dataset.dataset_id, payload=dataset.model_dump_json())
        )
        self.session.flush()
        return dataset

    def get(self, dataset_id: UUID) -> MarketDataset | None:
        row = self.session.get(MarketDatasetRecord, dataset_id)
        return MarketDataset.model_validate_json(row.payload) if row else None
