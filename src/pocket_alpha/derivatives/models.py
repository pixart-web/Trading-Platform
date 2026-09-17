from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, Currency, DomainModel

Number = Annotated[Decimal, Field(max_digits=38, decimal_places=18)]
Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=38, decimal_places=18)]
Fraction = Annotated[Decimal, Field(ge=0, le=1, max_digits=38, decimal_places=18)]


class ContractKind(StrEnum):
    PERPETUAL = "PERPETUAL"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class MultiplierUnit(StrEnum):
    BASE_UNITS_PER_CONTRACT = "BASE_UNITS_PER_CONTRACT"
    QUOTE_CURRENCY_PER_CONTRACT = "QUOTE_CURRENCY_PER_CONTRACT"


class Settlement(StrEnum):
    CASH = "CASH"
    PHYSICAL = "PHYSICAL"


class OptionRight(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class OptionStyle(StrEnum):
    EUROPEAN = "EUROPEAN"
    AMERICAN = "AMERICAN"


class GreekName(StrEnum):
    DELTA = "DELTA"
    GAMMA = "GAMMA"
    THETA = "THETA"
    VEGA = "VEGA"
    RHO = "RHO"


class ReportedGreek(DomainModel):
    name: GreekName
    value: Number
    unit: str = Field(min_length=1, max_length=128)
    convention: Identifier
    model_version: str = Field(min_length=1, max_length=128)


class DerivativeContractSpec(DomainModel):
    schema_version: Literal["derivative-contract-1.0.0"] = "derivative-contract-1.0.0"
    contract_id: Identifier
    underlying_asset_id: AssetId
    venue_id: Identifier
    kind: ContractKind
    quote_currency: Currency
    settlement_currency: Currency
    multiplier: Positive
    multiplier_unit: MultiplierUnit
    settlement: Settlement
    reference_index_id: Identifier
    reference_index_currency: Currency
    margin_scheme: str = Field(min_length=1, max_length=128)
    source: Identifier
    external_contract_id: str = Field(min_length=1, max_length=256)
    published_at: UTCDateTime
    expires_at: UTCDateTime | None = None
    strike: Positive | None = None
    option_right: OptionRight | None = None
    option_style: OptionStyle | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not self.contract_id.startswith("derivative:"):
            raise ValueError("derivative contract must use the derivative identity namespace")
        if self.contract_id == self.underlying_asset_id:
            raise ValueError("derivative contract cannot be the underlying asset identity")
        if (self.kind == ContractKind.PERPETUAL) != (self.expires_at is None):
            raise ValueError("only perpetual contracts have no expiration")
        option_fields = (self.strike, self.option_right, self.option_style)
        if self.kind == ContractKind.OPTION:
            if any(value is None for value in option_fields):
                raise ValueError("options require strike, right and exercise style")
        elif any(value is not None for value in option_fields):
            raise ValueError("non-option contracts cannot have option fields")
        return self


class DerivativeContract(DerivativeContractSpec):
    available_at: UTCDateTime
    ingested_at: UTCDateTime

    @model_validator(mode="after")
    def available(self) -> Self:
        if not self.published_at <= self.available_at <= self.ingested_at:
            raise ValueError("contract publication, availability and ingestion must be ordered")
        return self


class DerivativeSample(DomainModel):
    schema_version: Literal["derivative-observation-1.0.0"] = "derivative-observation-1.0.0"
    external_contract_id: str = Field(min_length=1, max_length=256)
    source_record_id: str = Field(min_length=1, max_length=256)
    revision: int = Field(default=1, ge=1, le=2147483647)
    observed_at: UTCDateTime
    published_at: UTCDateTime
    mark_price: Number | None = None
    index_price: Positive | None = None
    open_interest_contracts: Nonnegative | None = None
    funding_rate: Number | None = None
    funding_interval_seconds: int | None = Field(default=None, ge=1, le=604800)
    funding_kind: Literal["REALIZED", "INDICATIVE"] | None = None
    implied_volatility: Nonnegative | None = None
    iv_convention: Literal["ANNUALIZED_FRACTION"] | None = None
    greeks: tuple[ReportedGreek, ...] = Field(default=(), max_length=5)
    initial_margin_rate: Fraction | None = None
    maintenance_margin_rate: Fraction | None = None
    margin_basis: Identifier | None = None
    margin_rules_reference: str | None = Field(default=None, min_length=1, max_length=512)
    settlement_price: Number | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.published_at < self.observed_at:
            raise ValueError("derivative observation cannot be published before observation")
        if self.funding_rate is not None:
            if self.funding_interval_seconds is None or self.funding_kind is None:
                raise ValueError("funding requires explicit interval and realized/indicative kind")
        elif self.funding_interval_seconds is not None or self.funding_kind is not None:
            raise ValueError("funding metadata requires a funding rate")
        if (self.implied_volatility is None) != (self.iv_convention is None):
            raise ValueError("implied volatility requires an explicit normalized convention")
        names = tuple(g.name for g in self.greeks)
        if len(set(names)) != len(names):
            raise ValueError("reported Greeks cannot repeat names")
        if self.initial_margin_rate is not None and self.maintenance_margin_rate is not None:
            if self.maintenance_margin_rate > self.initial_margin_rate:
                raise ValueError("maintenance margin cannot exceed initial margin")
        if self.initial_margin_rate is not None or self.maintenance_margin_rate is not None:
            if self.margin_rules_reference is None or self.margin_basis is None:
                raise ValueError("reported margin requires explicit rules and denominator basis")
        if (
            not any(
                value is not None
                for value in (
                    self.mark_price,
                    self.index_price,
                    self.open_interest_contracts,
                    self.funding_rate,
                    self.implied_volatility,
                    self.initial_margin_rate,
                    self.maintenance_margin_rate,
                    self.settlement_price,
                )
            )
            and not self.greeks
        ):
            raise ValueError("empty derivative observation is unavailable, not a data record")
        return self


class DerivativeObservation(DerivativeSample):
    observation_id: UUID
    contract_id: Identifier
    source: Identifier
    available_at: UTCDateTime
    ingested_at: UTCDateTime
    supersedes_observation_id: UUID | None = None

    @model_validator(mode="after")
    def available(self) -> Self:
        if not self.published_at <= self.available_at <= self.ingested_at:
            raise ValueError("observation publication, availability and ingestion must be ordered")
        if (self.revision == 1) != (self.supersedes_observation_id is None):
            raise ValueError("derivative revision requires coherent supersession")
        return self


class DerivativePolicy(DomainModel):
    policy_version: Literal["derivative-context-policy-1.0.0"] = "derivative-context-policy-1.0.0"
    maximum_age_seconds: int = Field(default=300, ge=1, le=86400)


class DerivativeMetric(DomainModel):
    name: Identifier
    value: Number | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=128)
    input_observation_ids: tuple[UUID, ...] = ()
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.value is None:
            if (
                self.unavailable_reason is None
                or self.unit is not None
                or self.input_observation_ids
            ):
                raise ValueError("unavailable metric requires reason and no fabricated inputs")
        elif (
            self.unit is None
            or not self.input_observation_ids
            or self.unavailable_reason is not None
        ):
            raise ValueError(
                "available metric requires units, provenance and no unavailable reason"
            )
        return self


class DerivativeContext(DomainModel):
    feature_version: Literal["derivative-context-1.0.0"] = "derivative-context-1.0.0"
    contract: DerivativeContract
    as_of: UTCDateTime
    generated_at: UTCDateTime
    policy: DerivativePolicy
    observation: DerivativeObservation | None
    observation_status: Literal["AVAILABLE", "MISSING", "STALE", "EXPIRED"]
    metrics: tuple[DerivativeMetric, ...]
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class TermStructure(DomainModel):
    feature_version: Literal["derivative-term-structure-1.0.0"] = "derivative-term-structure-1.0.0"
    as_of: UTCDateTime
    generated_at: UTCDateTime
    points: tuple[DerivativeContext, ...] = Field(max_length=1000)
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    unavailable_reason: str | None = None
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class OptionSkew(DomainModel):
    feature_version: Literal["derivative-option-skew-1.0.0"] = "derivative-option-skew-1.0.0"
    as_of: UTCDateTime
    generated_at: UTCDateTime
    call: DerivativeContext
    put: DerivativeContext
    delta_target: Fraction
    put_minus_call_iv: DerivativeMetric
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def validate_contract_sample(contract: DerivativeContract, sample: DerivativeSample) -> None:
    if contract.kind != ContractKind.PERPETUAL and sample.funding_rate is not None:
        raise ValueError("only perpetual contracts can report perpetual funding")
    if contract.kind != ContractKind.OPTION and (
        sample.implied_volatility is not None or sample.greeks
    ):
        raise ValueError("only options can report option volatility and Greeks")
    if sample.mark_price is not None:
        if contract.kind == ContractKind.OPTION and sample.mark_price < 0:
            raise ValueError("option price cannot be negative")
        if contract.kind == ContractKind.PERPETUAL and sample.mark_price <= 0:
            raise ValueError("perpetual price must be positive")
