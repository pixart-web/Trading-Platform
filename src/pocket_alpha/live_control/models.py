from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from pocket_alpha.database import Base
from pocket_alpha.domain.models import DomainModel

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
Fraction = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=18)]


class TradingMode(StrEnum):
    OFF = "OFF"
    PAPER = "PAPER"
    LIVE_ARMED = "LIVE_ARMED"
    LIVE_ACTIVE = "LIVE_ACTIVE"
    HALTED = "HALTED"
    KILL_SWITCH = "KILL_SWITCH"


class Broker(StrEnum):
    BINANCE = "BINANCE"
    KUCOIN = "KUCOIN"


class MarketKind(StrEnum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"


class LivePolicy(DomainModel):
    schema_version: Literal["live-policy-1.0.0"] = "live-policy-1.0.0"
    version: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z0-9]{2,12}$")
    capital_limit: PositiveMoney
    order_notional_limit: PositiveMoney
    total_exposure_limit: PositiveMoney
    position_notional_limit: PositiveMoney
    strategy_exposure_limit: PositiveMoney
    broker_exposure_limit: PositiveMoney
    asset_exposure_limit: PositiveMoney
    daily_loss_limit: PositiveMoney
    maximum_drawdown: Annotated[Decimal, Field(gt=0, lt=1, max_digits=38, decimal_places=18)]
    maximum_leverage: Annotated[Decimal, Field(ge=1, max_digits=38, decimal_places=18)]
    maximum_positions: int = Field(ge=1, le=1000, strict=True)
    maximum_orders_per_minute: int = Field(ge=1, le=10000, strict=True)
    maximum_orders_per_day: int = Field(ge=1, le=1000000, strict=True)
    maximum_slippage_fraction: Fraction
    maximum_spread_fraction: Fraction
    maximum_price_deviation_fraction: Fraction
    maximum_data_age_seconds: int = Field(ge=1, le=3600, strict=True)
    maximum_account_age_seconds: int = Field(ge=1, le=3600, strict=True)

    @model_validator(mode="after")
    def coherent_limits(self) -> Self:
        if self.order_notional_limit > self.position_notional_limit:
            raise ValueError("order limit exceeds position limit")
        if any(
            value > self.total_exposure_limit
            for value in (
                self.position_notional_limit,
                self.strategy_exposure_limit,
                self.broker_exposure_limit,
                self.asset_exposure_limit,
            )
        ):
            raise ValueError("component exposure exceeds total exposure")
        if self.total_exposure_limit > self.capital_limit * self.maximum_leverage:
            raise ValueError("total exposure exceeds configured leveraged capital")
        return self


class ReadinessEvidence(DomainModel):
    schema_version: Literal["live-readiness-1.0.0"] = "live-readiness-1.0.0"
    source: str = Field(min_length=1, max_length=128)
    verified_at: AwareDatetime
    credential_qualified: bool
    account_qualified: bool
    risk_ready: bool
    strategy_ready: bool
    market_data_healthy: bool
    infrastructure_healthy: bool
    reconciliation_healthy: bool
    execution_healthy: bool
    evidence_hash: Hash


class ConfigureControl(DomainModel):
    expected_revision: int = Field(ge=0, strict=True)
    broker: Broker
    market: MarketKind
    account_identity_hash: Hash
    policy: LivePolicy
    confirmation: Literal["CONFIGURE LIVE CONTROL"]


class ControlAction(StrEnum):
    ENABLE_PAPER = "ENABLE_PAPER"
    ARM_LIVE = "ARM_LIVE"
    ACTIVATE_LIVE = "ACTIVATE_LIVE"
    DISABLE_LIVE = "DISABLE_LIVE"
    HALT_NEW_ORDERS = "HALT_NEW_ORDERS"
    ACTIVATE_KILL_SWITCH = "ACTIVATE_KILL_SWITCH"
    RESET_KILL_SWITCH = "RESET_KILL_SWITCH"


class TransitionControl(DomainModel):
    expected_revision: int = Field(ge=0, strict=True)
    action: ControlAction
    confirmation: str = Field(min_length=1, max_length=64)


class LiveControlSnapshot(DomainModel):
    control_id: UUID
    revision: int
    mode: TradingMode
    broker: Broker | None
    market: MarketKind | None
    account_identity_hash: Hash | None
    policy: LivePolicy | None
    policy_hash: Hash | None
    readiness: ReadinessEvidence | None
    kill_switch_active: bool
    live_deployment_enabled: bool
    derivative_deployment_enabled: bool
    updated_at: AwareDatetime


class LiveControlRecord(Base):
    __tablename__ = "live_control"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_live_control_revision"),
        CheckConstraint(
            "mode IN ('OFF','PAPER','LIVE_ARMED','LIVE_ACTIVE','HALTED','KILL_SWITCH')",
            name="ck_live_control_mode",
        ),
        CheckConstraint(
            "broker IS NULL OR broker IN ('BINANCE','KUCOIN')", name="ck_live_control_broker"
        ),
        CheckConstraint(
            "market IS NULL OR market IN ('SPOT','FUTURES')", name="ck_live_control_market"
        ),
    )

    control_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    control_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(16))
    market: Mapped[str | None] = mapped_column(String(16))
    account_identity_hash: Mapped[str | None] = mapped_column(String(64))
    policy_payload: Mapped[str | None] = mapped_column(Text)
    policy_hash: Mapped[str | None] = mapped_column(String(64))
    readiness_payload: Mapped[str | None] = mapped_column(Text)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveControlEventRecord(Base):
    __tablename__ = "live_control_events"
    __table_args__ = (
        UniqueConstraint("control_id", "revision", name="uq_live_control_event_revision"),
        UniqueConstraint("content_hash", name="uq_live_control_event_hash"),
        Index("ix_live_control_events_occurred_at", "occurred_at"),
        Index("ix_live_control_events_correlation_id", "correlation_id"),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    control_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_control.control_id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
