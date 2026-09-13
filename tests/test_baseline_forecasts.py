from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import ForecastHorizon, Timeframe
from pocket_alpha.forecasts.baseline import (
    BaselineForecastTrainer,
    apply_temperature,
    fingerprint,
    predict,
    raw_probabilities,
)
from pocket_alpha.forecasts.calibration import TemperatureCalibrator
from pocket_alpha.forecasts.economic import BaselineForecastEvaluator
from pocket_alpha.forecasts.models import (
    CalibrationStatus,
    ForecastDirection,
    ForecastStatus,
    ProbabilityValue,
)
from pocket_alpha.forecasts.research_models import (
    BaselineForecastModel,
    BaselineSpec,
    EconomicCostSpec,
    ForecastObservation,
    ForecastPartition,
    LabeledForecastExample,
    TemperatureCalibration,
)
from pocket_alpha.forecasts.service import canonical_snapshot

D = Decimal
START = datetime(2025, 1, 1, tzinfo=UTC)
CLOCK = FrozenClock(START + timedelta(days=100))
SPEC = BaselineSpec(
    feature_names=("signed-trend", "volatility"),
    direction_threshold=D("0.02"),
    minimum_per_class=2,
)
FIT_VERSIONS = {"code_version": "phase9-code-v1", "environment_version": "python-3.12-test"}


def example(
    index: int,
    actual_return: str,
    partition: ForecastPartition,
    *,
    base_hour: int,
    identity_offset: int,
    **observation_changes: object,
) -> LabeledForecastExample:
    generated_at = START + timedelta(hours=base_hour + index * 2)
    value = D(actual_return)
    signed = (
        D("1")
        if value > SPEC.direction_threshold
        else D("-1")
        if value < -SPEC.direction_threshold
        else D("0")
    )
    snapshot = canonical_snapshot(
        "features",
        "features-v1",
        "a" * 64,
        generated_at,
        {"signed-trend": signed, "volatility": D("0.1")},
    )
    observation: dict[str, object] = {
        "observation_id": UUID(int=identity_offset + index + 1),
        "market_id": "test-market",
        "asset_id": "test-asset",
        "candle_timeframe": Timeframe.H1,
        "horizon": ForecastHorizon.H1,
        "input_start": generated_at - timedelta(hours=1),
        "generated_at": generated_at,
        "expires_at": generated_at + timedelta(hours=1),
        "reference_price": D("100"),
        "feature_version": "features-v1",
        "feature_values": (signed, D("0.1")),
        "evidence": (snapshot,),
    }
    observation.update(observation_changes)
    return LabeledForecastExample(
        observation=ForecastObservation.model_validate(observation),
        actual_return=value,
        outcome_available_at=generated_at + timedelta(hours=2),
        outcome_hash=f"{identity_offset + 1:064x}"[-64:],
        partition=partition,
    )


def sample_set(
    partition: ForecastPartition, base_hour: int, identity_offset: int
) -> tuple[LabeledForecastExample, ...]:
    returns = ("0.10", "0.08", "-0.10", "-0.08", "0", "0.01")
    return tuple(
        example(
            index,
            value,
            partition,
            base_hour=base_hour,
            identity_offset=identity_offset,
        )
        for index, value in enumerate(returns)
    )


def fitted_model() -> BaselineForecastModel:
    return BaselineForecastTrainer(CLOCK).fit(
        sample_set(ForecastPartition.TRAIN, 0, 0),
        fitted_at=START + timedelta(hours=12),
        model_version="baseline-v1",
        spec=SPEC,
        **FIT_VERSIONS,
    )


def calibration(model: BaselineForecastModel) -> TemperatureCalibration:
    return TemperatureCalibrator(CLOCK).fit(
        model,
        sample_set(ForecastPartition.CALIBRATION, 13, 100),
        fitted_at=START + timedelta(hours=25),
        calibration_version="temperature-v1",
        candidates=(D("0.5"), D("1"), D("2")),
        minimum_samples=6,
    )


def test_trainer_is_deterministic_interpretable_and_versioned() -> None:
    examples = sample_set(ForecastPartition.TRAIN, 0, 0)
    trainer = BaselineForecastTrainer(CLOCK)
    model = trainer.fit(
        examples,
        fitted_at=START + timedelta(hours=12),
        model_version="baseline-v1",
        spec=SPEC,
        **FIT_VERSIONS,
    )
    repeated = trainer.fit(
        tuple(reversed(examples)),
        fitted_at=START + timedelta(hours=12),
        model_version="baseline-v1",
        spec=SPEC,
        **FIT_VERSIONS,
    )
    assert model == repeated
    assert model.dataset_hash == fingerprint([item.model_dump() for item in examples])
    assert tuple(item.direction for item in model.classes) == tuple(ForecastDirection)
    assert tuple(item.count for item in model.classes) == (2, 2, 2)
    assert model.classes[0].return_mean == D("0.09")
    assert model.classes[1].return_mean == D("-0.09")
    assert model.classes[2].return_mean == D("0.005")


def test_inference_and_temperature_preserve_exact_probability_contract() -> None:
    model = fitted_model()
    observation = example(
        0,
        "0.10",
        ForecastPartition.VALIDATION,
        base_hour=27,
        identity_offset=200,
    ).observation
    raw = raw_probabilities(observation, model)
    moderate = (
        ProbabilityValue(direction=ForecastDirection.UP, probability=D("0.6")),
        ProbabilityValue(direction=ForecastDirection.DOWN, probability=D("0.3")),
        ProbabilityValue(direction=ForecastDirection.RANGE, probability=D("0.1")),
    )
    adjusted = apply_temperature(moderate, D("2"))
    assert sum((item.probability for item in raw), D(0)) == 1
    assert sum((item.probability for item in adjusted), D(0)) == 1
    assert raw[0].probability == max(item.probability for item in raw)
    assert adjusted[0].probability < moderate[0].probability
    with pytest.raises(ValueError, match="positive"):
        apply_temperature(raw, D(0))


def test_calibration_uses_only_later_outcomes_and_never_worsens_fit() -> None:
    model = fitted_model()
    artifact = calibration(model)
    assert artifact.model_hash == fingerprint(model.model_dump())
    assert artifact.temperature in artifact.candidates
    assert artifact.calibrated_brier <= artifact.raw_brier
    assert artifact.sample_count == 6
    with pytest.raises(ValueError, match="CALIBRATION"):
        TemperatureCalibrator(CLOCK).fit(
            model,
            sample_set(ForecastPartition.VALIDATION, 13, 100),
            fitted_at=START + timedelta(hours=25),
            calibration_version="temperature-v1",
            candidates=(D("0.5"), D("1")),
            minimum_samples=6,
        )
    overlapping = sample_set(ForecastPartition.CALIBRATION, 10, 100)
    with pytest.raises(ValueError, match="overlaps training"):
        TemperatureCalibrator(CLOCK).fit(
            model,
            overlapping,
            fitted_at=START + timedelta(hours=30),
            calibration_version="temperature-v1",
            candidates=(D("0.5"), D("1")),
            minimum_samples=6,
        )


def test_prediction_is_phase_8_forecast_with_causal_calibration() -> None:
    model = fitted_model()
    artifact = calibration(model)
    observation = example(
        0,
        "0.10",
        ForecastPartition.VALIDATION,
        base_hour=27,
        identity_offset=200,
    ).observation
    forecast = predict(UUID(int=999), observation, model, calibration=artifact)
    assert forecast.status == ForecastStatus.AVAILABLE
    assert forecast.direction == ForecastDirection.UP
    assert forecast.probability_calibration == CalibrationStatus.CALIBRATED
    assert forecast.confidence == forecast.probabilities[0].probability
    assert forecast.horizon == ForecastHorizon.H1
    assert forecast.candle_timeframe == Timeframe.H1
    assert forecast.evidence == observation.evidence


def test_economic_evaluation_has_independent_reference_values() -> None:
    model = fitted_model()
    artifact = calibration(model)
    validation = sample_set(ForecastPartition.VALIDATION, 27, 200)[:3]
    costs = EconomicCostSpec(
        version="costs-v1",
        round_trip_fee_bps=D("50"),
        round_trip_spread_bps=D("20"),
        round_trip_slippage_bps=D("20"),
        latency_bps=D("10"),
    )
    report = BaselineForecastEvaluator(CLOCK).evaluate(
        model,
        artifact,
        validation,
        costs=costs,
        evaluated_at=START + timedelta(hours=40),
    )
    assert report.sample_count == 3
    assert report.gross_expectancy == D("0.093333333333333333333333333333")
    assert report.net_expectancy == D("0.083333333333333333333333333333")
    assert report.compounded_net_return == D("0.271267000000000000000000000000")
    assert report.maximum_drawdown == 0
    assert report.total_cost == D("0.03")
    assert report.active_fraction == 1
    assert not report.ruin_observed


def test_higher_costs_reduce_net_expectancy_exactly() -> None:
    model = fitted_model()
    validation = sample_set(ForecastPartition.VALIDATION, 13, 200)[:2]
    zero = EconomicCostSpec(
        version="zero",
        round_trip_fee_bps=D(0),
        round_trip_spread_bps=D(0),
        round_trip_slippage_bps=D(0),
        latency_bps=D(0),
    )
    costly = zero.model_copy(update={"version": "one-percent", "round_trip_fee_bps": D("100")})
    evaluator = BaselineForecastEvaluator(CLOCK)
    gross = evaluator.evaluate(
        model,
        None,
        validation,
        costs=zero,
        evaluated_at=START + timedelta(hours=30),
    )
    net = evaluator.evaluate(
        model,
        None,
        validation,
        costs=costly,
        evaluated_at=START + timedelta(hours=30),
    )
    assert gross.net_expectancy - net.net_expectancy == D("0.01")
    assert net.total_cost == D("0.02")
    assert net.cost_spec == costly
    assert net.turnover == D("2")


def test_training_rejects_leakage_partition_and_feature_mismatch() -> None:
    trainer = BaselineForecastTrainer(CLOCK)
    with pytest.raises(ValueError, match="only TRAIN"):
        trainer.fit(
            sample_set(ForecastPartition.FINAL_HOLDOUT, 0, 0),
            fitted_at=START + timedelta(hours=20),
            model_version="baseline-v1",
            spec=SPEC,
            **FIT_VERSIONS,
        )
    bad = list(sample_set(ForecastPartition.TRAIN, 0, 0))
    bad[0] = example(
        0,
        "0.10",
        ForecastPartition.TRAIN,
        base_hour=0,
        identity_offset=0,
        feature_values=(D("1"),),
    )
    with pytest.raises(ValueError, match="feature specification"):
        trainer.fit(
            tuple(bad),
            fitted_at=START + timedelta(hours=20),
            model_version="baseline-v1",
            spec=SPEC,
            **FIT_VERSIONS,
        )


def test_evaluation_rejects_overlap_and_overlapping_compounding_periods() -> None:
    model = fitted_model()
    evaluator = BaselineForecastEvaluator(CLOCK)
    costs = EconomicCostSpec(
        version="zero",
        round_trip_fee_bps=D(0),
        round_trip_spread_bps=D(0),
        round_trip_slippage_bps=D(0),
        latency_bps=D(0),
    )
    with pytest.raises(ValueError, match="fitted targets"):
        evaluator.evaluate(
            model,
            None,
            sample_set(ForecastPartition.VALIDATION, 10, 200)[:2],
            costs=costs,
            evaluated_at=START + timedelta(hours=30),
        )
    first = example(0, "0.1", ForecastPartition.VALIDATION, base_hour=20, identity_offset=300)
    second = example(
        0,
        "0.1",
        ForecastPartition.VALIDATION,
        base_hour=20,
        identity_offset=400,
    )
    with pytest.raises(ValueError, match="non-overlapping"):
        evaluator.evaluate(
            model,
            None,
            (first, second),
            costs=costs,
            evaluated_at=START + timedelta(hours=30),
        )


def test_research_models_reject_incoherent_time_and_schema() -> None:
    valid = example(
        0,
        "0.1",
        ForecastPartition.TRAIN,
        base_hour=0,
        identity_offset=0,
    )
    with pytest.raises(ValidationError, match="before forecast expiry"):
        LabeledForecastExample.model_validate({**valid.model_dump(), "outcome_available_at": START})
    with pytest.raises(ValidationError, match="unique"):
        BaselineSpec(
            feature_names=("same", "same"), direction_threshold=D("0.02"), minimum_per_class=2
        )


def replace_observation(item: LabeledForecastExample, **changes: object) -> LabeledForecastExample:
    values = item.observation.model_dump()
    values.update(changes)
    observation = ForecastObservation.model_validate(values)
    return LabeledForecastExample.model_validate({**item.model_dump(), "observation": observation})


def test_training_guards_size_time_duplicates_identity_and_class_support() -> None:
    examples = sample_set(ForecastPartition.TRAIN, 0, 0)
    trainer = BaselineForecastTrainer(CLOCK)

    def fit(items: tuple[LabeledForecastExample, ...]) -> BaselineForecastModel:
        return trainer.fit(
            items,
            fitted_at=START + timedelta(hours=20),
            model_version="v",
            spec=SPEC,
            **FIT_VERSIONS,
        )

    with pytest.raises(ValueError, match="training size"):
        fit(examples[:5])
    with pytest.raises(ValueError, match="future"):
        trainer.fit(
            examples,
            fitted_at=CLOCK.now() + timedelta(seconds=1),
            model_version="v",
            spec=SPEC,
            **FIT_VERSIONS,
        )
    with pytest.raises(ValueError, match="duplicate"):
        fit((*examples[:5], examples[0]))
    mixed = list(examples)
    mixed[0] = replace_observation(mixed[0], market_id="different")
    with pytest.raises(ValueError, match="one market"):
        fit(tuple(mixed))
    unavailable = list(examples)
    unavailable[0] = LabeledForecastExample.model_validate(
        {**unavailable[0].model_dump(), "outcome_available_at": START + timedelta(days=2)}
    )
    with pytest.raises(ValueError, match="not yet available"):
        fit(tuple(unavailable))
    only_up = tuple(
        example(i, "0.1", ForecastPartition.TRAIN, base_hour=0, identity_offset=500)
        for i in range(6)
    )
    with pytest.raises(ValueError, match="per direction"):
        fit(only_up)


def test_calibration_guards_candidates_time_duplicates_and_class_coverage() -> None:
    model = fitted_model()
    examples = sample_set(ForecastPartition.CALIBRATION, 13, 100)
    calibrator = TemperatureCalibrator(CLOCK)

    def fit(
        items: tuple[LabeledForecastExample, ...], candidates: tuple[Decimal, ...]
    ) -> TemperatureCalibration:
        return calibrator.fit(
            model,
            items,
            candidates=candidates,
            fitted_at=START + timedelta(hours=25),
            calibration_version="v",
            minimum_samples=6,
        )

    with pytest.raises(ValueError, match="minimum sample"):
        fit(examples[:5], (D("1"), D("2")))
    with pytest.raises(ValueError, match="include one"):
        fit(examples, (D("0.5"), D("2")))
    with pytest.raises(ValueError, match="positive, unique and ordered"):
        fit(examples, (D("1"), D("1")))
    with pytest.raises(ValueError, match="future"):
        calibrator.fit(
            model,
            examples,
            fitted_at=CLOCK.now() + timedelta(seconds=1),
            calibration_version="v",
            candidates=(D("1"), D("2")),
            minimum_samples=6,
        )
    with pytest.raises(ValueError, match="duplicate"):
        fit((*examples[:5], examples[0]), (D("1"), D("2")))
    only_up = tuple(
        example(i, "0.1", ForecastPartition.CALIBRATION, base_hour=13, identity_offset=600)
        for i in range(6)
    )
    with pytest.raises(ValueError, match="every direction"):
        fit(only_up, (D("1"), D("2")))


def test_prediction_rejects_incompatible_or_unavailable_artifacts() -> None:
    model = fitted_model()
    artifact = calibration(model)
    observation = example(
        0, "0.1", ForecastPartition.VALIDATION, base_hour=27, identity_offset=700
    ).observation
    with pytest.raises(ValueError, match="incompatible"):
        raw_probabilities(observation.model_copy(update={"market_id": "different"}), model)
    with pytest.raises(ValueError, match="model was not available"):
        predict(UUID(int=700), observation.model_copy(update={"generated_at": START}), model)
    wrong = TemperatureCalibration.model_validate({**artifact.model_dump(), "model_hash": "f" * 64})
    with pytest.raises(ValueError, match="does not belong"):
        predict(UUID(int=701), observation, model, calibration=wrong)
    early = observation.model_copy(update={"generated_at": START + timedelta(hours=24)})
    with pytest.raises(ValueError, match="calibration was not available"):
        predict(UUID(int=702), early, model, calibration=artifact)


def test_range_forecast_has_no_exposure_or_cost() -> None:
    model = fitted_model()
    item = example(0, "0", ForecastPartition.VALIDATION, base_hour=13, identity_offset=800)
    costs = EconomicCostSpec(
        version="large",
        round_trip_fee_bps=D("100"),
        round_trip_spread_bps=D("100"),
        round_trip_slippage_bps=D("100"),
        latency_bps=D("100"),
    )
    report = BaselineForecastEvaluator(CLOCK).evaluate(
        model,
        None,
        (item,),
        costs=costs,
        evaluated_at=START + timedelta(hours=20),
    )
    assert report.active_fraction == 0
    assert report.total_cost == 0
    assert report.gross_expectancy == report.net_expectancy == 0
    assert report.sharpe is report.sortino is report.profit_factor is None


def test_short_loss_can_record_ruin_without_clamping_the_observation() -> None:
    model = fitted_model()
    item = example(
        0,
        "2",
        ForecastPartition.FINAL_HOLDOUT,
        base_hour=13,
        identity_offset=900,
        feature_values=(D("-1"), D("0.1")),
    )
    costs = EconomicCostSpec(
        version="zero",
        round_trip_fee_bps=D(0),
        round_trip_spread_bps=D(0),
        round_trip_slippage_bps=D(0),
        latency_bps=D(0),
    )
    report = BaselineForecastEvaluator(CLOCK).evaluate(
        model,
        None,
        (item,),
        costs=costs,
        evaluated_at=START + timedelta(hours=20),
    )
    assert report.ruin_observed
    assert report.compounded_net_return == -1
    assert report.maximum_drawdown == 1
    assert report.net_expectancy == -2
    assert report.losing_periods == 1


def test_evaluation_guards_partition_time_duplicates_and_outcome_availability() -> None:
    model = fitted_model()
    evaluator = BaselineForecastEvaluator(CLOCK)
    costs = EconomicCostSpec(
        version="zero",
        round_trip_fee_bps=D(0),
        round_trip_spread_bps=D(0),
        round_trip_slippage_bps=D(0),
        latency_bps=D(0),
    )
    validation = sample_set(ForecastPartition.VALIDATION, 13, 100)
    with pytest.raises(ValueError, match="1..10000"):
        evaluator.evaluate(model, None, (), costs=costs, evaluated_at=START)
    with pytest.raises(ValueError, match="VALIDATION"):
        evaluator.evaluate(
            model,
            None,
            sample_set(ForecastPartition.CALIBRATION, 13, 100),
            costs=costs,
            evaluated_at=START + timedelta(hours=30),
        )
    with pytest.raises(ValueError, match="future"):
        evaluator.evaluate(
            model, None, validation, costs=costs, evaluated_at=CLOCK.now() + timedelta(seconds=1)
        )
    with pytest.raises(ValueError, match="duplicate"):
        evaluator.evaluate(
            model,
            None,
            (validation[0], validation[0]),
            costs=costs,
            evaluated_at=START + timedelta(hours=30),
        )
    unavailable = LabeledForecastExample.model_validate(
        {**validation[0].model_dump(), "outcome_available_at": START + timedelta(hours=40)}
    )
    with pytest.raises(ValueError, match="not yet available"):
        evaluator.evaluate(
            model, None, (unavailable,), costs=costs, evaluated_at=START + timedelta(hours=30)
        )
