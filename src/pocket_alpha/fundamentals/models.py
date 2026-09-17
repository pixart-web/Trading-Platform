from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, Currency, DomainModel

Value = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]


class FundamentalMetric(StrEnum):
    GROSS_PROFIT = "GROSS_PROFIT"
    OPERATING_INCOME = "OPERATING_INCOME"
    NET_INCOME = "NET_INCOME"
    OPERATING_CASH_FLOW = "OPERATING_CASH_FLOW"
    CAPITAL_EXPENDITURE = "CAPITAL_EXPENDITURE"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    REVENUE_GROWTH = "REVENUE_GROWTH"
    EPS_DILUTED = "EPS_DILUTED"
    EARNINGS_GROWTH = "EARNINGS_GROWTH"
    GROSS_MARGIN = "GROSS_MARGIN"
    OPERATING_MARGIN = "OPERATING_MARGIN"
    NET_MARGIN = "NET_MARGIN"
    FREE_CASH_FLOW = "FREE_CASH_FLOW"
    LONG_TERM_DEBT = "LONG_TERM_DEBT"
    DEBT = "DEBT"
    CASH = "CASH"
    ROE = "ROE"
    ROIC = "ROIC"
    PRICE_EARNINGS = "PRICE_EARNINGS"
    PRICE_SALES = "PRICE_SALES"
    ENTERPRISE_VALUE_EBITDA = "ENTERPRISE_VALUE_EBITDA"


class FundamentalMapping(DomainModel):
    schema_version: Literal["fundamental-mapping-1.0.0"] = "fundamental-mapping-1.0.0"
    source: Identifier
    asset_id: AssetId
    instrument_id: str = Field(min_length=1, max_length=128)
    created_at: UTCDateTime


class FundamentalFact(DomainModel):
    schema_version: Literal["fundamental-fact-1.0.0"] = "fundamental-fact-1.0.0"
    fact_id: UUID
    asset_id: AssetId
    metric: FundamentalMetric
    value: Value
    currency: Currency | None = None
    unit: str = Field(min_length=1, max_length=64)
    period_start: date | None = None
    period_end: date
    fiscal_year: int | None = Field(default=None, ge=1800, le=9999)
    fiscal_period: str | None = Field(default=None, max_length=16)
    form: str = Field(min_length=1, max_length=32)
    source: Identifier
    source_concept: str = Field(min_length=1, max_length=128)
    source_record_id: str = Field(min_length=1, max_length=256)
    accession_number: str | None = Field(default=None, max_length=32)
    revision: int = Field(ge=1)
    supersedes_fact_id: UUID | None = None
    published_at: UTCDateTime
    available_at: UTCDateTime
    ingested_at: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.revision == 1) != (self.supersedes_fact_id is None):
            raise ValueError("fundamental revisions require coherent supersession linkage")
        if self.period_start is not None and self.period_start > self.period_end:
            raise ValueError("fundamental period start cannot follow its end")
        if not self.published_at <= self.available_at <= self.ingested_at:
            raise ValueError("fundamental publication, availability and ingestion must be ordered")
        if self.period_end > self.published_at.date():
            raise ValueError("fundamental period cannot end after publication")
        if self.currency is None and self.unit.upper() in {"USD", "EUR", "GBP", "JPY", "CAD"}:
            raise ValueError("monetary fundamental fact requires explicit currency")
        if self.currency is not None and self.unit.split("/")[0] != self.currency:
            raise ValueError("monetary fundamental unit must match currency")
        return self


class FundamentalSnapshot(DomainModel):
    schema_version: Literal["fundamental-snapshot-1.0.0"] = "fundamental-snapshot-1.0.0"
    asset_id: AssetId
    as_of: UTCDateTime
    generated_at: UTCDateTime
    facts: tuple[FundamentalFact, ...] = Field(max_length=1000)
    unavailable_reason: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.generated_at < self.as_of:
            raise ValueError("fundamental snapshot cannot precede its as-of time")
        keys = tuple((fact.metric.value, fact.period_end, fact.revision) for fact in self.facts)
        if keys != tuple(sorted(keys)):
            raise ValueError("fundamental facts must use canonical order")
        if any(
            fact.asset_id != self.asset_id
            or fact.available_at > self.as_of
            or fact.ingested_at > self.as_of
            for fact in self.facts
        ):
            raise ValueError("fundamental snapshot contains unavailable facts")
        if self.facts and self.unavailable_reason is not None:
            raise ValueError("available fundamental snapshot cannot have unavailable reason")
        if not self.facts and self.unavailable_reason is None:
            raise ValueError("empty fundamental snapshot requires an unavailable reason")
        return self
