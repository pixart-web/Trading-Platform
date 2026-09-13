from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.forecasts.evaluation import evaluate_forecasts
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    Forecast,
    ForecastDirection,
    ForecastOutcome,
    ForecastStatus,
    ModelStage,
    ProbabilityValue,
)
from pocket_alpha.forecasts.service import ForecastLedger, canonical_snapshot, validate_outcome
from pocket_alpha.forecasts.storage import (
    ConflictingForecast,
    ConflictingOutcome,
    ForecastRepository,
)
from pocket_alpha.market_data.storage import MarketRepository

D = Decimal
START = datetime(2025, 1, 1, tzinfo=UTC)
CLOCK = FrozenClock(START + timedelta(days=2))
HASH = "a" * 64


def forecast(**changes: object) -> Forecast:
    snapshot = canonical_snapshot("intelligence", "v1", HASH, START, {"close": D("100")})
    values: dict[str, object] = {
        "forecast_id": UUID("00000000-0000-0000-0000-000000000001"),
        "market_id": "test-market",
        "asset_id": "test-asset",
        "candle_timeframe": Timeframe.H1,
        "horizon": ForecastHorizon.H1,
        "generated_at": START,
        "expires_at": START + timedelta(hours=1),
        "reference_price": D("100"),
        "status": ForecastStatus.AVAILABLE,
        "direction": ForecastDirection.UP,
        "probabilities": (
            ProbabilityValue(direction=ForecastDirection.UP, probability=D("0.7")),
            ProbabilityValue(direction=ForecastDirection.DOWN, probability=D("0.2")),
            ProbabilityValue(direction=ForecastDirection.RANGE, probability=D("0.1")),
        ),
        "expected_return": D("0.04"),
        "expected_move": D("0.06"),
        "range_threshold": D("0.02"),
        "expected_low_return": D("-0.03"),
        "expected_high_return": D("0.09"),
        "confidence": D("0.7"),
        "probability_calibration": CalibrationStatus.CALIBRATED,
        "regime": "trend-up",
        "model_version": "model-v1",
        "model_stage": ModelStage.SHADOW,
        "feature_version": "features-v1",
        "dataset_hash": HASH,
        "evidence": (snapshot,),
    }
    values.update(changes)
    return Forecast.model_validate(values)


def unavailable_forecast(**changes: object) -> Forecast:
    values: dict[str, object] = {
        "status": "UNAVAILABLE",
        "unavailable_reason": "INSUFFICIENT_HISTORY",
        "direction": None,
        "probabilities": (),
        "expected_return": None,
        "expected_move": None,
        "range_threshold": None,
        "expected_low_return": None,
        "expected_high_return": None,
        "confidence": None,
        "probability_calibration": None,
        "regime": None,
    }
    values.update(changes)
    return forecast(**values)


def outcome(**changes: object) -> ForecastOutcome:
    values: dict[str, object] = {
        "outcome_id": UUID("00000000-0000-0000-0000-000000000002"),
        "forecast_id": UUID("00000000-0000-0000-0000-000000000001"),
        "recorded_at": START + timedelta(hours=3),
        "end_price_at": START + timedelta(hours=1),
        "observation_available_at": START + timedelta(hours=2),
        "end_price": D("105"),
        "high_price": D("110"),
        "low_price": D("90"),
        "actual_return": D("0.05"),
        "maximum_favorable_excursion": D("0.1"),
        "maximum_adverse_excursion": D("0.1"),
        "realized_volatility": None,
        "directional_correct": True,
        "outcome_source": "fixture",
        "observation_hash": "b" * 64,
    }
    values.update(changes)
    return ForecastOutcome.model_validate(values)


def invalid(base: Forecast, **changes: object) -> dict[str, object]:
    values = base.model_dump()
    values.update(changes)
    return values


def test_every_horizon_has_deterministic_utc_expiry() -> None:
    expected_hours = {
        ForecastHorizon.H1: 1,
        ForecastHorizon.H4: 4,
        ForecastHorizon.H8: 8,
        ForecastHorizon.H12: 12,
        ForecastHorizon.H24: 24,
        ForecastHorizon.D2: 48,
        ForecastHorizon.D3: 72,
        ForecastHorizon.D7: 168,
        ForecastHorizon.D14: 336,
        ForecastHorizon.D30: 720,
        ForecastHorizon.D90: 2160,
    }
    for horizon, hours in expected_hours.items():
        assert expires_at(START, horizon) == START + timedelta(hours=hours)
    shifted = datetime(2025, 1, 31, 12, tzinfo=UTC)
    assert expires_at(shifted, ForecastHorizon.M6) == datetime(2025, 7, 31, 12, tzinfo=UTC)
    assert expires_at(shifted, ForecastHorizon.M12) == datetime(2026, 1, 31, 12, tzinfo=UTC)
    leap = datetime(2024, 8, 31, tzinfo=UTC)
    assert expires_at(leap, ForecastHorizon.M6) == datetime(2025, 2, 28, tzinfo=UTC)


def test_snapshot_is_canonical_hashed_and_causally_available() -> None:
    first = canonical_snapshot("features", "v1", HASH, START, {"b": 2, "a": D("1.20")})
    second = canonical_snapshot("features", "v1", HASH, START, {"a": D("1.2"), "b": 2})
    assert first == second
    assert first.canonical_json == '{"a":"1.2","b":2}'
    with pytest.raises(ValidationError, match="canonical formatting"):
        first.__class__.model_validate(
            {**first.model_dump(), "canonical_json": '{"b":2,"a":"1.2"}'}
        )
    with pytest.raises(ValidationError, match="content hash mismatch"):
        first.__class__.model_validate({**first.model_dump(), "content_hash": "c" * 64})
    with pytest.raises(ValidationError, match="after generation"):
        Forecast.model_validate(
            invalid(
                forecast(),
                evidence=(first.model_copy(update={"available_at": START + timedelta(seconds=1)}),),
            )
        )


def test_forecast_requires_complete_honest_distribution() -> None:
    base = forecast()
    with pytest.raises(ValidationError, match="sum exactly"):
        Forecast.model_validate(
            invalid(
                base,
                probabilities=(
                    {"direction": "UP", "probability": "0.8"},
                    {"direction": "DOWN", "probability": "0.2"},
                    {"direction": "RANGE", "probability": "0.1"},
                ),
            )
        )
    with pytest.raises(ValidationError, match="highest probability"):
        Forecast.model_validate(invalid(base, direction="DOWN"))
    with pytest.raises(ValidationError, match="horizon convention"):
        Forecast.model_validate(invalid(base, expires_at=START + timedelta(hours=2)))
    unavailable = unavailable_forecast()

    assert unavailable.status == ForecastStatus.UNAVAILABLE
    with pytest.raises(ValidationError, match="only an explicit reason"):
        Forecast.model_validate(invalid(unavailable, expected_return=D("0")))


def test_forecast_rejects_ambiguous_or_incoherent_claims() -> None:
    base = forecast()
    cases = (
        (
            {
                "probabilities": (
                    {"direction": "DOWN", "probability": "0.2"},
                    {"direction": "UP", "probability": "0.7"},
                    {"direction": "RANGE", "probability": "0.1"},
                )
            },
            "canonical order",
        ),
        (
            {
                "probabilities": (
                    {"direction": "UP", "probability": "0.4"},
                    {"direction": "DOWN", "probability": "0.4"},
                    {"direction": "RANGE", "probability": "0.2"},
                ),
                "confidence": D("0.4"),
            },
            "unique highest",
        ),
        ({"confidence": D("0.6")}, "confidence must match"),
        ({"expected_return": D("0.2")}, "expected range"),
        ({"target_return": D("0.08")}, "provided together"),
        (
            {
                "direction": "RANGE",
                "probabilities": (
                    {"direction": "UP", "probability": "0.2"},
                    {"direction": "DOWN", "probability": "0.2"},
                    {"direction": "RANGE", "probability": "0.6"},
                ),
                "confidence": D("0.6"),
                "target_return": D("0.08"),
                "invalidation_return": D("-0.05"),
            },
            "range forecasts cannot",
        ),
        (
            {"target_return": D("-0.08"), "invalidation_return": D("0.05")},
            "up forecast levels",
        ),
    )
    for changes, message in cases:
        with pytest.raises(ValidationError, match=message):
            Forecast.model_validate(invalid(base, **changes))


def test_malformed_evidence_and_incomplete_forecasts_fail_closed() -> None:
    snapshot = canonical_snapshot("features", "v1", HASH, START, {"close": "100"})
    with pytest.raises(ValidationError, match="valid JSON"):
        snapshot.__class__.model_validate(
            {**snapshot.model_dump(), "canonical_json": "{{", "content_hash": "c" * 64}
        )
    with pytest.raises(ValidationError, match="complete estimates"):
        Forecast.model_validate(invalid(forecast(), expected_move=None))
    with pytest.raises(ValidationError, match="down forecast levels"):
        Forecast.model_validate(
            invalid(
                forecast(),
                direction="DOWN",
                probabilities=(
                    {"direction": "UP", "probability": "0.2"},
                    {"direction": "DOWN", "probability": "0.7"},
                    {"direction": "RANGE", "probability": "0.1"},
                ),
                expected_return=D("-0.04"),
                expected_low_return=D("-0.1"),
                confidence=D("0.7"),
                target_return=D("0.08"),
                invalidation_return=D("-0.05"),
            )
        )


def test_outcome_shape_and_availability_are_validated() -> None:
    with pytest.raises(ValidationError, match="extrema"):
        outcome(high_price=D("104"))
    with pytest.raises(ValidationError, match="timestamps"):
        outcome(observation_available_at=START + timedelta(minutes=30))


def test_outcome_is_post_expiry_and_derived_from_observations() -> None:
    base, result = forecast(), outcome()
    validate_outcome(base, result, CLOCK)
    with pytest.raises(ValueError, match="before forecast expiry"):
        validate_outcome(base, outcome(end_price_at=START + timedelta(minutes=59)), CLOCK)
    with pytest.raises(ValueError, match="actual return"):
        validate_outcome(base, outcome(actual_return=D("0.04")), CLOCK)
    with pytest.raises(ValueError, match="excursions"):
        validate_outcome(base, outcome(maximum_favorable_excursion=D("0.09")), CLOCK)
    with pytest.raises(ValueError, match="directional correctness"):
        validate_outcome(base, outcome(directional_correct=False), CLOCK)


def test_outcome_rejects_wrong_lifecycle_identity_and_time() -> None:
    with pytest.raises(ValueError, match="unavailable forecasts"):
        validate_outcome(unavailable_forecast(), outcome(), CLOCK)
    with pytest.raises(ValueError, match="reference its forecast"):
        validate_outcome(
            forecast(),
            outcome(forecast_id=UUID("00000000-0000-0000-0000-000000000099")),
            CLOCK,
        )
    with pytest.raises(ValueError, match="recorded in the future"):
        validate_outcome(forecast(), outcome(), FrozenClock(START + timedelta(hours=2)))


def test_down_outcome_and_levels_use_downside_convention() -> None:
    base = forecast(
        direction="DOWN",
        probabilities=(
            {"direction": "UP", "probability": "0.2"},
            {"direction": "DOWN", "probability": "0.7"},
            {"direction": "RANGE", "probability": "0.1"},
        ),
        expected_return=D("-0.04"),
        expected_low_return=D("-0.1"),
        confidence=D("0.7"),
        target_return=D("-0.08"),
        invalidation_return=D("0.05"),
    )
    result = outcome(
        end_price=D("95"),
        actual_return=D("-0.05"),
        target_hit=True,
        invalidation_hit=True,
    )
    validate_outcome(base, result, CLOCK)


def test_range_outcome_does_not_fabricate_directional_excursions() -> None:
    base = forecast(
        direction="RANGE",
        probabilities=(
            {"direction": "UP", "probability": "0.2"},
            {"direction": "DOWN", "probability": "0.2"},
            {"direction": "RANGE", "probability": "0.6"},
        ),
        confidence=D("0.6"),
    )
    result = outcome(
        maximum_favorable_excursion=None,
        maximum_adverse_excursion=None,
        directional_correct=False,
    )
    validate_outcome(base, result, CLOCK)


def test_target_hits_require_explicit_levels_and_observed_extrema() -> None:
    with pytest.raises(ValueError, match="require forecast target"):
        validate_outcome(forecast(), outcome(target_hit=True), CLOCK)
    base = forecast(target_return=D("0.08"), invalidation_return=D("-0.05"))
    validate_outcome(base, outcome(target_hit=True, invalidation_hit=True), CLOCK)
    with pytest.raises(ValueError, match="hit flags must match"):
        validate_outcome(base, outcome(target_hit=False, invalidation_hit=True), CLOCK)


def test_append_only_ledger_round_trip_and_conflicts(repository: MarketRepository) -> None:
    repo = ForecastRepository(repository.session)
    ledger = ForecastLedger(repo, CLOCK)
    base, result = forecast(), outcome()
    assert ledger.append_forecast(base)
    assert not ledger.append_forecast(base)
    assert repo.forecast(base.forecast_id) == base
    assert repo.forecasts("test-market", horizon="1H") == (base,)
    with pytest.raises(ConflictingForecast):
        ledger.append_forecast(forecast(model_version="model-v2"))
    assert ledger.append_outcome(result)
    assert not ledger.append_outcome(result)
    assert repo.outcome(base.forecast_id) == result
    assert repo.outcome(UUID("00000000-0000-0000-0000-000000000099")) is None
    with pytest.raises(LookupError, match="not found"):
        repo.forecast(UUID("00000000-0000-0000-0000-000000000099"))
    with pytest.raises(ConflictingOutcome):
        ledger.append_outcome(outcome(outcome_source="changed"))
    with pytest.raises(ValueError, match="bounded query"):
        repo.forecasts("test-market", limit=0)


def test_ledger_rejects_future_forecast(repository: MarketRepository) -> None:
    ledger = ForecastLedger(ForecastRepository(repository.session), FrozenClock(START))
    future = START + timedelta(seconds=1)
    with pytest.raises(ValueError, match="future"):
        ledger.append_forecast(
            forecast(generated_at=future, expires_at=future + timedelta(hours=1))
        )


def test_evaluation_rejects_empty_and_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="1..10000"):
        evaluate_forecasts((), CLOCK)
    with pytest.raises(ValueError, match="matching available"):
        evaluate_forecasts(((unavailable_forecast(), outcome()),), CLOCK)


def test_reference_evaluation_is_versioned_by_model_and_horizon() -> None:
    report = evaluate_forecasts(((forecast(), outcome()),), CLOCK)[0]
    assert report.model_version == "model-v1"
    assert report.horizon == ForecastHorizon.H1
    assert report.sample_count == 1
    assert report.brier_score == D("0.14")
    assert report.return_mae == D("0.01")
    assert report.return_rmse == D("0.01")
    assert report.directional_accuracy == 1
    assert report.calibration_status == CalibrationStatus.CALIBRATED
