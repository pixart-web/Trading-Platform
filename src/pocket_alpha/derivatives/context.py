import hashlib
import json
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from pocket_alpha.common.clock import utc
from pocket_alpha.derivatives.models import (
    ContractKind,
    DerivativeContext,
    DerivativeContract,
    DerivativeMetric,
    DerivativeObservation,
    DerivativePolicy,
    GreekName,
    MultiplierUnit,
    OptionRight,
    OptionSkew,
    TermStructure,
    validate_contract_sample,
)

D = Decimal
METRICS = (
    "funding_rate",
    "open_interest_contracts",
    "implied_volatility",
    "initial_margin_rate",
    "maintenance_margin_rate",
    "derivative_minus_index",
    "derivative_minus_index_fraction",
    "simple_annualized_basis_act365f",
    "open_interest_quote_notional",
)


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def seconds(value: timedelta) -> Decimal:
    microseconds = (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds
    return D(f"{microseconds}e-6")


def missing(name: str, reason: str) -> DerivativeMetric:
    return DerivativeMetric(name=name, unavailable_reason=reason)


def metric(
    name: str,
    value: Decimal,
    unit: str,
    observations: tuple[DerivativeObservation, ...],
) -> DerivativeMetric:
    with localcontext() as ctx:
        ctx.prec = 80
        ctx.rounding = ROUND_HALF_EVEN
        value = value.quantize(D("0.000000000000000001"))
    return DerivativeMetric(
        name=name,
        value=value,
        unit=unit,
        input_observation_ids=tuple(o.observation_id for o in observations),
    )


def build_context(
    contract: DerivativeContract,
    observation: DerivativeObservation | None,
    as_of: datetime,
    generated_at: datetime,
    policy: DerivativePolicy,
) -> DerivativeContext:
    as_of, generated_at = utc(as_of), utc(generated_at)
    if generated_at < as_of or contract.ingested_at > as_of or contract.available_at > as_of:
        raise ValueError("derivative context precedes its cutoff or contract availability")
    if observation is not None and (
        observation.contract_id != contract.contract_id
        or observation.source != contract.source
        or observation.external_contract_id != contract.external_contract_id
        or observation.available_at < contract.available_at
        or observation.ingested_at < contract.ingested_at
        or max(
            observation.observed_at,
            observation.published_at,
            observation.available_at,
            observation.ingested_at,
        )
        > as_of
    ):
        raise ValueError("derivative context contains an incompatible or future observation")
    if observation is not None:
        validate_contract_sample(contract, observation)
    status: Literal["AVAILABLE", "MISSING", "STALE", "EXPIRED"] = "AVAILABLE"
    if contract.expires_at is not None and contract.expires_at <= as_of:
        status = "EXPIRED"
    elif observation is None:
        status = "MISSING"
    elif seconds(as_of - observation.observed_at) > D(policy.maximum_age_seconds):
        status = "STALE"
    features = {
        name: missing(name, status if status != "AVAILABLE" else "INPUT_UNAVAILABLE")
        for name in METRICS
    }
    if status == "AVAILABLE" and observation is not None:
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.rounding = ROUND_HALF_EVEN
            for name, value, unit in (
                ("funding_rate", observation.funding_rate, "fraction-per-funding-interval"),
                ("open_interest_contracts", observation.open_interest_contracts, "contracts"),
                ("implied_volatility", observation.implied_volatility, "annualized-fraction"),
                (
                    "initial_margin_rate",
                    observation.initial_margin_rate,
                    f"fraction-of-{observation.margin_basis}",
                ),
                (
                    "maintenance_margin_rate",
                    observation.maintenance_margin_rate,
                    f"fraction-of-{observation.margin_basis}",
                ),
            ):
                if value is not None:
                    features[name] = metric(name, value, unit, (observation,))
            if contract.kind != ContractKind.OPTION:
                mark, index = observation.mark_price, observation.index_price
                same_currency = contract.quote_currency == contract.reference_index_currency
                if mark is not None and index is not None and same_currency:
                    spread = mark - index
                    ratio = spread / index
                    features["derivative_minus_index"] = metric(
                        "derivative_minus_index",
                        spread,
                        contract.quote_currency,
                        (observation,),
                    )
                    features["derivative_minus_index_fraction"] = metric(
                        "derivative_minus_index_fraction",
                        ratio,
                        "fraction",
                        (observation,),
                    )
                    if contract.kind == ContractKind.FUTURE and contract.expires_at is not None:
                        duration = seconds(contract.expires_at - observation.observed_at)
                        if duration > 0:
                            features["simple_annualized_basis_act365f"] = metric(
                                "simple_annualized_basis_act365f",
                                ratio * D(365 * 86400) / duration,
                                "fraction-per-year-simple",
                                (observation,),
                            )
                oi = observation.open_interest_contracts
                if oi is not None:
                    if contract.multiplier_unit == MultiplierUnit.QUOTE_CURRENCY_PER_CONTRACT:
                        notional = oi * contract.multiplier
                    elif index is not None and same_currency:
                        notional = oi * contract.multiplier * index
                    else:
                        notional = None
                    if notional is not None:
                        features["open_interest_quote_notional"] = metric(
                            "open_interest_quote_notional",
                            notional,
                            contract.quote_currency,
                            (observation,),
                        )
                if not same_currency:
                    for name in (
                        "derivative_minus_index",
                        "derivative_minus_index_fraction",
                        "simple_annualized_basis_act365f",
                    ):
                        features[name] = missing(name, "INDEX_CURRENCY_MISMATCH")
                    if contract.multiplier_unit == MultiplierUnit.BASE_UNITS_PER_CONTRACT:
                        features["open_interest_quote_notional"] = missing(
                            "open_interest_quote_notional",
                            "INDEX_CURRENCY_MISMATCH",
                        )
            else:
                for name in (
                    "derivative_minus_index",
                    "derivative_minus_index_fraction",
                    "simple_annualized_basis_act365f",
                    "open_interest_quote_notional",
                ):
                    features[name] = missing(name, "NOT_APPLICABLE_TO_OPTION")
            if contract.kind != ContractKind.PERPETUAL:
                features["funding_rate"] = missing("funding_rate", "NOT_A_PERPETUAL")
            if contract.kind != ContractKind.OPTION:
                features["implied_volatility"] = missing("implied_volatility", "NOT_AN_OPTION")
            if contract.kind == ContractKind.PERPETUAL:
                features["simple_annualized_basis_act365f"] = missing(
                    "simple_annualized_basis_act365f",
                    "PERPETUAL_HAS_NO_EXPIRATION",
                )
    inputs = {
        "contract": contract.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json") if observation else None,
        "as_of": as_of.isoformat(),
        "policy": policy.model_dump(mode="json"),
        "feature_version": "derivative-context-1.0.0",
    }
    return DerivativeContext(
        contract=contract,
        observation=observation,
        as_of=as_of,
        generated_at=generated_at,
        policy=policy,
        observation_status=status,
        metrics=tuple(features[n] for n in METRICS),
        input_hash=fingerprint(inputs),
    )


def comparison_key(contract: DerivativeContract) -> tuple[str, ...]:
    return (
        contract.underlying_asset_id,
        contract.venue_id,
        contract.source,
        contract.quote_currency,
        contract.settlement_currency,
        contract.reference_index_id,
        contract.reference_index_currency,
        contract.settlement.value,
        str(contract.multiplier),
        contract.multiplier_unit.value,
    )


def term_structure(
    contexts: tuple[DerivativeContext, ...],
    as_of: datetime,
    generated_at: datetime,
) -> TermStructure:
    as_of, generated_at = utc(as_of), utc(generated_at)
    if generated_at < as_of or any(
        c.as_of != as_of
        or c.contract.kind != ContractKind.FUTURE
        or c.contract.expires_at is None
        or c.contract.expires_at <= as_of
        for c in contexts
    ):
        raise ValueError("term structure requires unexpired futures at one cutoff")
    points = tuple(sorted(contexts, key=lambda c: (c.contract.expires_at, c.contract.contract_id)))
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"] = "COMPLETE"
    reason: str | None = None
    if len(points) < 2:
        status, reason = "UNAVAILABLE", "AT_LEAST_TWO_UNEXPIRED_FUTURES_REQUIRED"
    elif len({comparison_key(p.contract) for p in points}) != 1:
        status, reason = "UNAVAILABLE", "INCOMPATIBLE_FUTURES"
    elif any(
        p.observation_status != "AVAILABLE"
        or p.observation is None
        or p.observation.mark_price is None
        for p in points
    ):
        status, reason = "PARTIAL", "INCOMPLETE_FUTURES_QUOTES"
    elif len({p.observation.observed_at for p in points if p.observation is not None}) != 1:
        status, reason = "UNAVAILABLE", "UNALIGNED_FUTURES_QUOTES"
    return TermStructure(
        as_of=as_of,
        generated_at=generated_at,
        points=points,
        status=status,
        unavailable_reason=reason,
        input_hash=fingerprint(
            {
                "point_hashes": [p.input_hash for p in points],
                "as_of": as_of.isoformat(),
                "feature_version": "derivative-term-structure-1.0.0",
            }
        ),
    )


def option_skew(
    call: DerivativeContext,
    put: DerivativeContext,
    as_of: datetime,
    generated_at: datetime,
) -> OptionSkew:
    as_of, generated_at = utc(as_of), utc(generated_at)
    if (
        generated_at < as_of
        or call.as_of != as_of
        or put.as_of != as_of
        or call.contract.kind != ContractKind.OPTION
        or put.contract.kind != ContractKind.OPTION
        or call.contract.option_right != OptionRight.CALL
        or put.contract.option_right != OptionRight.PUT
    ):
        raise ValueError("option skew requires explicit call/put contracts at the same cutoff")
    feature = missing("put_minus_call_iv_25delta", "INCOMPATIBLE_OPTIONS")
    if (
        comparison_key(call.contract) == comparison_key(put.contract)
        and call.contract.expires_at == put.contract.expires_at
        and call.contract.option_style == put.contract.option_style
    ):
        left, right = call.observation, put.observation
        if (
            call.observation_status != "AVAILABLE"
            or put.observation_status != "AVAILABLE"
            or left is None
            or right is None
        ):
            feature = missing("put_minus_call_iv_25delta", "OPTION_QUOTES_UNAVAILABLE")
        elif left.observed_at != right.observed_at:
            feature = missing("put_minus_call_iv_25delta", "UNALIGNED_OPTION_QUOTES")
        elif left.implied_volatility is None or right.implied_volatility is None:
            feature = missing("put_minus_call_iv_25delta", "IMPLIED_VOLATILITY_UNAVAILABLE")
        else:
            ldelta = next((g for g in left.greeks if g.name == GreekName.DELTA), None)
            rdelta = next((g for g in right.greeks if g.name == GreekName.DELTA), None)
            if (
                ldelta is None
                or rdelta is None
                or ldelta.unit != "price-ratio"
                or rdelta.unit != "price-ratio"
                or ldelta.convention != "spot-unadjusted"
                or rdelta.convention != "spot-unadjusted"
                or ldelta.model_version != rdelta.model_version
                or ldelta.value != D("0.25")
                or rdelta.value != D("-0.25")
            ):
                feature = missing(
                    "put_minus_call_iv_25delta", "MATCHED_AUTHORITATIVE_DELTAS_UNAVAILABLE"
                )
            else:
                with localcontext() as ctx:
                    ctx.prec = 80
                    ctx.rounding = ROUND_HALF_EVEN
                    feature = metric(
                        "put_minus_call_iv_25delta",
                        right.implied_volatility - left.implied_volatility,
                        "annualized-fraction",
                        (right, left),
                    )
    return OptionSkew(
        as_of=as_of,
        generated_at=generated_at,
        call=call,
        put=put,
        delta_target=D("0.25"),
        put_minus_call_iv=feature,
        input_hash=fingerprint(
            {
                "call_hash": call.input_hash,
                "put_hash": put.input_hash,
                "as_of": as_of.isoformat(),
                "delta_target": "0.25",
                "feature_version": "derivative-option-skew-1.0.0",
            }
        ),
    )
