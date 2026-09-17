"""Deterministic descriptive financial features, never trade authorization."""

import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from pydantic import Field

from pocket_alpha.domain.market import UTCDateTime
from pocket_alpha.domain.models import AssetId, Currency, DomainModel, Timeframe
from pocket_alpha.fundamentals.models import (
    FundamentalFact,
    FundamentalMetric,
    FundamentalSnapshot,
    Value,
)


class FinancialFeature(DomainModel):
    metric: FundamentalMetric
    value: Value | None = None
    unit: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    input_fact_ids: tuple[UUID, ...] = ()
    unavailable_reason: str | None = None


class FundamentalPrice(DomainModel):
    asset_id: AssetId
    market_id: str
    currency: Currency
    price: Value = Field(gt=0)
    timeframe: Timeframe
    close_time: UTCDateTime
    received_at: UTCDateTime
    source: str


class FundamentalContext(DomainModel):
    feature_version: Literal["fundamental-context-1.0.0"] = "fundamental-context-1.0.0"
    snapshot: FundamentalSnapshot
    price: FundamentalPrice | None = None
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    features: tuple[FinancialFeature, ...]
    unavailable_context: tuple[Literal["GUIDANCE", "EARNINGS_EVENTS"], ...] = (
        "GUIDANCE",
        "EARNINGS_EVENTS",
    )


D = Decimal
DERIVED = (
    FundamentalMetric.REVENUE_GROWTH,
    FundamentalMetric.EARNINGS_GROWTH,
    FundamentalMetric.GROSS_MARGIN,
    FundamentalMetric.OPERATING_MARGIN,
    FundamentalMetric.NET_MARGIN,
    FundamentalMetric.FREE_CASH_FLOW,
    FundamentalMetric.ROE,
    FundamentalMetric.ROIC,
    FundamentalMetric.PRICE_EARNINGS,
    FundamentalMetric.PRICE_SALES,
    FundamentalMetric.ENTERPRISE_VALUE_EBITDA,
)


def _missing(metric: FundamentalMetric, reason: str) -> FinancialFeature:
    return FinancialFeature(metric=metric, unavailable_reason=reason)


def _annual(fact: FundamentalFact) -> bool:
    return (
        fact.period_start is not None
        and 350 <= (fact.period_end - fact.period_start).days <= 380
        and fact.fiscal_period == "FY"
        and fact.form in {"10-K", "10-K/A", "20-F", "20-F/A"}
    )


def _one(snapshot: FundamentalSnapshot, metric: FundamentalMetric) -> FundamentalFact | None:
    candidates = [f for f in snapshot.facts if f.metric == metric and _annual(f)]
    if not candidates:
        return None
    latest_end = max(f.period_end for f in candidates)
    latest = [f for f in candidates if f.period_end == latest_end]
    # Do not guess between taxonomies, currencies or reporting contexts.
    return latest[0] if len(latest) == 1 else None


def _compatible(left: FundamentalFact, right: FundamentalFact) -> bool:
    return (
        left.source == right.source
        and left.currency == right.currency
        and left.unit == right.unit
        and left.period_start == right.period_start
        and left.period_end == right.period_end
    )


def _feature(
    metric: FundamentalMetric,
    value: Decimal,
    unit: str,
    facts: tuple[FundamentalFact, ...],
) -> FinancialFeature:
    with localcontext() as ctx:
        ctx.prec = 80
        rounded = value.quantize(D("0.000000000000000001"))
    return FinancialFeature(
        metric=metric,
        value=rounded,
        unit=unit,
        period_start=facts[0].period_start,
        period_end=facts[0].period_end,
        input_fact_ids=tuple(f.fact_id for f in facts),
    )


def financial_context(
    snapshot: FundamentalSnapshot,
    price: FundamentalPrice | None = None,
) -> FundamentalContext:
    if price is not None and (
        price.asset_id != snapshot.asset_id
        or price.close_time > snapshot.as_of
        or price.received_at > snapshot.as_of
        or price.received_at < price.close_time
    ):
        raise ValueError("valuation price identity or availability is invalid")
    features: dict[FundamentalMetric, FinancialFeature] = {
        m: _missing(m, "REQUIRED_CAUSAL_FINANCIAL_INPUTS_UNAVAILABLE") for m in DERIVED
    }
    with localcontext() as ctx:
        ctx.prec = 80
        revenue = _one(snapshot, FundamentalMetric.REVENUE)
        if revenue is not None and revenue.value > 0:
            for numerator, metric in (
                (FundamentalMetric.GROSS_PROFIT, FundamentalMetric.GROSS_MARGIN),
                (FundamentalMetric.OPERATING_INCOME, FundamentalMetric.OPERATING_MARGIN),
                (FundamentalMetric.NET_INCOME, FundamentalMetric.NET_MARGIN),
            ):
                fact = _one(snapshot, numerator)
                if fact is not None and _compatible(fact, revenue):
                    features[metric] = _feature(
                        metric,
                        fact.value / revenue.value,
                        "ratio",
                        (fact, revenue),
                    )
        cash_flow = _one(snapshot, FundamentalMetric.OPERATING_CASH_FLOW)
        capex = _one(snapshot, FundamentalMetric.CAPITAL_EXPENDITURE)
        if cash_flow is not None and capex is not None and _compatible(cash_flow, capex):
            if capex.value >= 0:
                features[FundamentalMetric.FREE_CASH_FLOW] = _feature(
                    FundamentalMetric.FREE_CASH_FLOW,
                    cash_flow.value - capex.value,
                    cash_flow.unit,
                    (cash_flow, capex),
                )
        for base, metric in (
            (FundamentalMetric.REVENUE, FundamentalMetric.REVENUE_GROWTH),
            (FundamentalMetric.EPS_DILUTED, FundamentalMetric.EARNINGS_GROWTH),
        ):
            latest = _one(snapshot, base)
            if latest is None:
                continue
            prior = [
                f
                for f in snapshot.facts
                if f.metric == base
                and _annual(f)
                and f.source == latest.source
                and f.source_concept == latest.source_concept
                and f.currency == latest.currency
                and f.unit == latest.unit
                and 350 <= (latest.period_end - f.period_end).days <= 380
            ]
            if len(prior) == 1 and prior[0].value > 0:
                features[metric] = _feature(
                    metric,
                    latest.value / prior[0].value - D(1),
                    "ratio",
                    (latest, prior[0]),
                )
            elif prior and any(f.value <= 0 for f in prior):
                features[metric] = _missing(metric, "NONPOSITIVE_GROWTH_BASE")
    for metric, reason in (
        (FundamentalMetric.ROE, "AVERAGE_PERIOD_EQUITY_UNAVAILABLE"),
        (FundamentalMetric.ROIC, "INVESTED_CAPITAL_AND_NOPAT_UNAVAILABLE"),
        (FundamentalMetric.PRICE_EARNINGS, "CAUSAL_PRICE_AND_COMPARABLE_EPS_UNAVAILABLE"),
        (FundamentalMetric.PRICE_SALES, "CAUSAL_MARKET_CAPITALIZATION_UNAVAILABLE"),
        (
            FundamentalMetric.ENTERPRISE_VALUE_EBITDA,
            "CAUSAL_ENTERPRISE_VALUE_AND_EBITDA_UNAVAILABLE",
        ),
    ):
        features[metric] = _missing(metric, reason)
    eps = _one(snapshot, FundamentalMetric.EPS_DILUTED)
    if price is not None and eps is not None:
        if (
            price.currency == eps.currency
            and eps.unit == f"{price.currency}/shares"
            and price.close_time >= eps.available_at
        ):
            if eps.value > 0:
                with localcontext() as ctx:
                    ctx.prec = 80
                    features[FundamentalMetric.PRICE_EARNINGS] = _feature(
                        FundamentalMetric.PRICE_EARNINGS,
                        price.price / eps.value,
                        "ratio",
                        (eps,),
                    )
            else:
                features[FundamentalMetric.PRICE_EARNINGS] = _missing(
                    FundamentalMetric.PRICE_EARNINGS,
                    "NONPOSITIVE_EPS",
                )
    encoded = json.dumps(
        {
            "snapshot": snapshot.model_dump(mode="json", exclude={"generated_at"}),
            "price": price.model_dump(mode="json") if price is not None else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return FundamentalContext(
        snapshot=snapshot,
        price=price,
        input_hash=hashlib.sha256(encoded).hexdigest(),
        features=tuple(features[m] for m in DERIVED),
    )
