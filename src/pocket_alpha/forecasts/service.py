import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import TYPE_CHECKING

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.forecasts.models import (
    EvidenceSnapshot,
    Forecast,
    ForecastDirection,
    ForecastOutcome,
)
from pocket_alpha.intelligence.provenance import canonical

if TYPE_CHECKING:
    from pocket_alpha.forecasts.storage import ForecastRepository

D = Decimal


def canonical_snapshot(
    kind: str, version: str, input_hash: str, available_at: datetime, payload: object
) -> EvidenceSnapshot:
    encoded = json.dumps(canonical(payload), sort_keys=True, separators=(",", ":"), default=str)
    return EvidenceSnapshot(
        kind=kind,
        version=version,
        input_hash=input_hash,
        available_at=available_at,
        canonical_json=encoded,
        content_hash=hashlib.sha256(encoded.encode()).hexdigest(),
    )


def validate_forecast_time(forecast: Forecast, clock: Clock) -> None:
    if forecast.generated_at > utc(clock.now()):
        raise ValueError("forecast cannot be generated in the future")


def validate_outcome(forecast: Forecast, outcome: ForecastOutcome, clock: Clock) -> None:
    if forecast.status.value != "AVAILABLE":
        raise ValueError("unavailable forecasts cannot have outcomes")
    if outcome.forecast_id != forecast.forecast_id:
        raise ValueError("outcome must reference its forecast")
    if outcome.end_price_at < forecast.expires_at:
        raise ValueError("outcome cannot observe before forecast expiry")
    if outcome.recorded_at > utc(clock.now()):
        raise ValueError("outcome cannot be recorded in the future")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        actual = outcome.end_price / forecast.reference_price - 1
        if outcome.actual_return != actual:
            raise ValueError("actual return must match reference and end prices")
        up = outcome.high_price / forecast.reference_price - 1
        down = 1 - outcome.low_price / forecast.reference_price
        assert forecast.direction is not None
        assert forecast.range_threshold is not None
        if forecast.direction == ForecastDirection.DOWN:
            favorable, adverse = max(D(0), down), max(D(0), up)
        elif forecast.direction == ForecastDirection.RANGE:
            favorable, adverse = None, None
        else:
            favorable, adverse = max(D(0), up), max(D(0), down)
        if (outcome.maximum_favorable_excursion, outcome.maximum_adverse_excursion) != (
            favorable,
            adverse,
        ):
            raise ValueError("excursions must match the stored extrema and direction convention")
        actual_direction = (
            ForecastDirection.UP
            if actual > forecast.range_threshold
            else ForecastDirection.DOWN
            if actual < -forecast.range_threshold
            else ForecastDirection.RANGE
        )
        if forecast.target_return is None or forecast.invalidation_return is None:
            if outcome.target_hit is not None or outcome.invalidation_hit is not None:
                raise ValueError("hit flags require forecast target and invalidation levels")
        else:
            low_return = outcome.low_price / forecast.reference_price - 1
            if forecast.direction == ForecastDirection.UP:
                target_hit = up >= forecast.target_return
                invalidation_hit = low_return <= forecast.invalidation_return
            else:
                target_hit = low_return <= forecast.target_return
                invalidation_hit = up >= forecast.invalidation_return
            if (outcome.target_hit, outcome.invalidation_hit) != (target_hit, invalidation_hit):
                raise ValueError("hit flags must match forecast levels and observed extrema")
        if outcome.directional_correct != (forecast.direction == actual_direction):
            raise ValueError("directional correctness must use the forecast range threshold")


class ForecastLedger:
    """Append-only application boundary for forecasts and their later outcomes."""

    def __init__(self, repository: "ForecastRepository", clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def append_forecast(self, forecast: Forecast) -> bool:
        validate_forecast_time(forecast, self.clock)
        return self.repository.put_forecast(forecast)

    def append_outcome(self, outcome: ForecastOutcome) -> bool:
        forecast = self.repository.forecast(outcome.forecast_id)
        validate_outcome(forecast, outcome, self.clock)
        return self.repository.put_outcome(outcome)
