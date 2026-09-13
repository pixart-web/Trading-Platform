import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.scoring.models import (
    ComponentStatus,
    PocketScore,
    PocketScoreComponentExplanation,
    PocketScoreComponentInput,
    PocketScoreRequest,
    PocketScoreStatus,
)

D = Decimal
RESOLUTION = D("1e-30")


def fingerprint(payload: object) -> str:
    encoded = json.dumps(
        canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return sum(values, D(0))


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return (numerator / denominator).quantize(RESOLUTION)


def _available_value(item: PocketScoreComponentInput) -> Decimal:
    if item.value is None:
        raise ValueError("available Pocket Score input requires a value")
    return item.value


def _weighted(value: Decimal, weight: Decimal, total_weight: Decimal) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return (value * weight / total_weight).quantize(RESOLUTION)


def _weighted_score(
    positions: list[int], request: PocketScoreRequest, available_weight: Decimal
) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        value = sum(
            (
                _available_value(request.inputs[index]) * request.spec.components[index].weight
                for index in positions
                if request.inputs[index].value is not None
            ),
            D(0),
        )
        return (value / available_weight).quantize(RESOLUTION)


class PocketScoreEngine:
    """Combine versioned normalized evidence without treating a score as probability."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def calculate(self, request: PocketScoreRequest, *, generated_at: datetime) -> PocketScore:
        generated_at = utc(generated_at)
        now = utc(self.clock.now())
        if request.as_of > now:
            raise ValueError("Pocket Score as-of time cannot be in the future")
        if generated_at > now:
            raise ValueError("Pocket Score generation cannot be in the future")
        if generated_at < request.as_of:
            raise ValueError("Pocket Score cannot be generated before its as-of time")
        for item in request.inputs:
            if item.available_at is not None and item.available_at > request.as_of:
                raise ValueError("Pocket Score component was unavailable at the as-of time")

        definitions = request.spec.components
        total_weight = _sum(item.weight for item in definitions)
        available_weight = _sum(
            definition.weight
            for definition, item in zip(definitions, request.inputs, strict=True)
            if item.status == ComponentStatus.AVAILABLE
        )
        coverage = _divide(available_weight, total_weight)
        required_missing = any(
            definition.required and item.status == ComponentStatus.UNAVAILABLE
            for definition, item in zip(definitions, request.inputs, strict=True)
        )
        unavailable_reason = None
        if available_weight == 0:
            unavailable_reason = "NO_COMPONENTS_AVAILABLE"
        elif required_missing:
            unavailable_reason = "REQUIRED_COMPONENT_UNAVAILABLE"
        elif coverage < request.spec.minimum_coverage:
            unavailable_reason = "INSUFFICIENT_COMPONENT_COVERAGE"

        effective_weights: dict[str, Decimal] = {}
        if unavailable_reason is None:
            positions = [
                index
                for index, item in enumerate(request.inputs)
                if item.status == ComponentStatus.AVAILABLE
            ]
            values = [_divide(definitions[index].weight, available_weight) for index in positions]
            winner = max(
                range(len(values)),
                key=lambda position: definitions[positions[position]].weight,
            )
            with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
                values[winner] += 1 - sum(values, D(0))
            effective_weights = {
                definitions[index].component: value
                for index, value in zip(positions, values, strict=True)
            }
            contributions = [
                _weighted(
                    _available_value(request.inputs[index]),
                    definitions[index].weight,
                    available_weight,
                )
                for index in positions
                if request.inputs[index].value is not None
            ]
            score = _weighted_score(positions, request, available_weight)
            with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
                contributions[winner] += score - _sum(contributions)
            component_contributions = {
                definitions[index].component: value
                for index, value in zip(positions, contributions, strict=True)
            }
        else:
            score = None
            component_contributions = {}

        explanations = []
        for definition, item in zip(definitions, request.inputs, strict=True):
            effective = effective_weights.get(definition.component)
            if item.status == ComponentStatus.UNAVAILABLE:
                explanations.append(
                    PocketScoreComponentExplanation(
                        component=definition.component,
                        label=definition.label,
                        status=item.status,
                        required=definition.required,
                        configured_weight=definition.weight,
                        normalization_version=item.normalization_version,
                        unavailable_reason=item.unavailable_reason,
                    )
                )
                continue
            assert item.value is not None
            assert item.available_at is not None
            explanations.append(
                PocketScoreComponentExplanation(
                    component=definition.component,
                    label=definition.label,
                    status=item.status,
                    required=definition.required,
                    configured_weight=definition.weight,
                    effective_weight=effective,
                    raw_value=item.value,
                    contribution=component_contributions.get(definition.component),
                    normalization_version=item.normalization_version,
                    available_at=item.available_at,
                    evidence=item.evidence,
                )
            )

        status = (
            PocketScoreStatus.AVAILABLE
            if unavailable_reason is None
            else PocketScoreStatus.UNAVAILABLE
        )
        return PocketScore(
            score_id=request.score_id,
            market_id=request.market_id,
            asset_id=request.asset_id,
            candle_timeframe=request.candle_timeframe,
            as_of=request.as_of,
            generated_at=generated_at,
            status=status,
            score_version=request.spec.score_version,
            config_hash=fingerprint(request.spec.model_dump()),
            input_hash=fingerprint([item.model_dump() for item in request.inputs]),
            coverage=coverage,
            total_weight=total_weight,
            available_weight=available_weight,
            score=score,
            unavailable_reason=unavailable_reason,
            components=tuple(explanations),
        )
