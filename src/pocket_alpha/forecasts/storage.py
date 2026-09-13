import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.forecasts.models import Forecast, ForecastOutcome
from pocket_alpha.market_data.storage import Timestamp


class ForecastRecord(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_market_horizon_generated", "market_id", "horizon", "generated_at"),
    )
    forecast_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.market_id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"))
    candle_timeframe: Mapped[str] = mapped_column(String(3))
    horizon: Mapped[str] = mapped_column(String(3))
    generated_at: Mapped[datetime] = mapped_column(Timestamp())
    expires_at: Mapped[datetime] = mapped_column(Timestamp())
    model_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[str] = mapped_column(Text)


class ForecastOutcomeRecord(Base):
    __tablename__ = "forecast_outcomes"
    outcome_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    forecast_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecasts.forecast_id"), unique=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(Timestamp())
    end_price_at: Mapped[datetime] = mapped_column(Timestamp())
    observation_available_at: Mapped[datetime] = mapped_column(Timestamp())
    payload: Mapped[str] = mapped_column(Text)


class ConflictingForecast(Exception):
    """The immutable forecast identity already has different content."""


class ConflictingOutcome(Exception):
    """The forecast already has a different immutable outcome."""


def _payload(value: Forecast | ForecastOutcome) -> str:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class ForecastRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _insert(self, model: type[Base], values: dict[str, Any], key: str) -> bool:
        dialect = self.session.get_bind().dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError("unsupported persistence dialect")
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        return (
            self.session.execute(
                insert(model)
                .values(**values)
                .on_conflict_do_nothing()
                .returning(getattr(model, key))
            ).scalar_one_or_none()
            is not None
        )

    def put_forecast(self, forecast: Forecast) -> bool:
        payload = _payload(forecast)
        values = {
            "forecast_id": forecast.forecast_id,
            "market_id": forecast.market_id,
            "asset_id": forecast.asset_id,
            "candle_timeframe": forecast.candle_timeframe.value,
            "horizon": forecast.horizon.value,
            "generated_at": forecast.generated_at,
            "expires_at": forecast.expires_at,
            "model_version": forecast.model_version,
            "status": forecast.status.value,
            "payload": payload,
        }
        with self.session.begin_nested():
            if self._insert(ForecastRecord, values, "forecast_id"):
                return True
            row = self.session.get(ForecastRecord, forecast.forecast_id, populate_existing=True)
            if row is None or row.payload != payload:
                raise ConflictingForecast("forecast identity conflicts with persisted content")
        return False

    def forecast(self, forecast_id: UUID) -> Forecast:
        row = self.session.get(ForecastRecord, forecast_id)
        if row is None:
            raise LookupError("forecast not found")
        return Forecast.model_validate_json(row.payload)

    def forecasts(
        self, market_id: str, *, horizon: str | None = None, limit: int = 1000
    ) -> tuple[Forecast, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("bounded query required")
        statement = select(ForecastRecord).where(ForecastRecord.market_id == market_id)
        if horizon is not None:
            statement = statement.where(ForecastRecord.horizon == horizon)
        rows = self.session.scalars(statement.order_by(ForecastRecord.generated_at).limit(limit))
        return tuple(Forecast.model_validate_json(row.payload) for row in rows)

    def put_outcome(self, outcome: ForecastOutcome) -> bool:
        payload = _payload(outcome)
        values = {
            "outcome_id": outcome.outcome_id,
            "forecast_id": outcome.forecast_id,
            "recorded_at": outcome.recorded_at,
            "end_price_at": outcome.end_price_at,
            "observation_available_at": outcome.observation_available_at,
            "payload": payload,
        }
        with self.session.begin_nested():
            if self._insert(ForecastOutcomeRecord, values, "outcome_id"):
                return True
            row = self.session.scalar(
                select(ForecastOutcomeRecord).where(
                    ForecastOutcomeRecord.forecast_id == outcome.forecast_id
                )
            )
            if row is None or row.payload != payload:
                raise ConflictingOutcome("forecast already has a different outcome")
        return False

    def outcome(self, forecast_id: UUID) -> ForecastOutcome | None:
        row = self.session.scalar(
            select(ForecastOutcomeRecord).where(ForecastOutcomeRecord.forecast_id == forecast_id)
        )
        return ForecastOutcome.model_validate_json(row.payload) if row is not None else None
