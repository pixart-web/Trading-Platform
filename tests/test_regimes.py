"""Synthetic causal paths and externally supplied test labels, never production data."""

from datetime import timedelta
from decimal import Decimal, localcontext
from math import exp, log

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, CandleQuery
from pocket_alpha.domain.models import Timeframe
from pocket_alpha.intelligence.regimes.evaluation import RegimeEvaluator
from pocket_alpha.intelligence.regimes.models import (
    FitSpec,
    GaussianClass,
    ProbabilityResult,
    RegimeLabel,
    RegimeModel,
    RegimeObservation,
    RegimeProbability,
    RegimeSnapshot,
    RegimeSpec,
    SamplePartition,
    TrainingExample,
    TrendReason,
    VolatilityRegime,
)
from pocket_alpha.intelligence.regimes.probability import RegimeTrainer, fingerprint, infer
from pocket_alpha.intelligence.regimes.service import RegimeEngine, _calculate
from pocket_alpha.intelligence.technical.models import FeatureStatus, IndicatorKind, IndicatorSpec
from pocket_alpha.intelligence.technical.service import TechnicalIntelligence
from pocket_alpha.market_data.quality import DataRejected, FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import START, sample

D = Decimal
SPEC = RegimeSpec(period=2, baseline_period=2)
CLOCK = FrozenClock(START + timedelta(days=90))
PATH = (100, 105, 103, 110, 107, 115, 111, 120, 115, 125, 119, 130, 122, 135, 128, 140)


def bars(values: tuple[int, ...] = PATH) -> tuple[Candle, ...]:
    return tuple(
        sample(i, open=str(p), close=str(p), high=str(p + 1), low=str(p - 1))
        for i, p in enumerate(values)
    )


def query(count: int) -> CandleQuery:
    return CandleQuery(
        market_id="test-market",
        timeframe=Timeframe.H1,
        start=START,
        end=START + timedelta(hours=count),
    )


def snapshots(values: tuple[int, ...] = PATH) -> tuple[TrainingExample, ...]:
    observations = _calculate(bars(values), query(len(values)), FreshnessPolicy(), SPEC)
    return tuple(
        TrainingExample(
            observation=o,
            label=tuple(RegimeLabel)[i % 4],
            label_available_at=o.technical.available_at,
        )
        for i, o in enumerate(observations[2:10])
    )


def fit(examples: tuple[TrainingExample, ...] | None = None) -> RegimeModel:
    return RegimeTrainer(CLOCK).fit(
        examples if examples is not None else snapshots(),
        fitted_at=START + timedelta(hours=10),
        label_policy="synthetic-manual-labels-v1",
        spec=FitSpec(minimum_per_class=2),
    )


@pytest.mark.parametrize(
    "prices,label,reason,efficiency",
    [
        ((10, 12, 14), RegimeLabel.TREND_UP, TrendReason.EFFICIENT_MOVE, D(1)),
        ((14, 12, 10), RegimeLabel.TREND_DOWN, TrendReason.EFFICIENT_MOVE, D(-1)),
        ((10, 14, 10), RegimeLabel.RANGE, TrendReason.LOW_EFFICIENCY, D(0)),
        ((10, 10, 10), RegimeLabel.RANGE, TrendReason.FLAT_CLOSES, None),
        ((10, 14, 12), RegimeLabel.TRANSITION, TrendReason.MIXED_PATH, D(1) / 3),
    ],
)
def test_reference_trend_paths(
    prices: tuple[int, ...], label: RegimeLabel, reason: TrendReason, efficiency: Decimal | None
) -> None:
    result = _calculate(bars(prices), query(3), FreshnessPolicy(), SPEC)
    assert all(o.trend is None and o.trend_reason == TrendReason.WARMUP for o in result[:2])
    last = result[-1]
    assert last.trend == label and last.trend_reason == reason
    if efficiency is None:
        assert last.signed_efficiency.value is None
        assert last.signed_efficiency.status == FeatureStatus.UNDEFINED
    else:
        assert last.signed_efficiency.value is not None
        assert float(last.signed_efficiency.value) == pytest.approx(float(efficiency))


@pytest.mark.parametrize(
    "threshold,expected", [(D("0.5"), RegimeLabel.TREND_UP), (D("0.6"), RegimeLabel.TRANSITION)]
)
def test_exact_trend_boundary(threshold: Decimal, expected: RegimeLabel) -> None:
    spec = RegimeSpec(period=2, trend_efficiency=threshold, range_efficiency=D("0.3"))
    result = _calculate(bars((10, 16, 14)), query(3), FreshnessPolicy(), spec)[-1]
    assert result.signed_efficiency.value == D("0.5") and result.trend == expected


def test_exact_range_boundary() -> None:
    spec = RegimeSpec(period=2, range_efficiency=D("0.5"), trend_efficiency=D("0.6"))
    assert (
        _calculate(bars((10, 16, 14)), query(3), FreshnessPolicy(), spec)[-1].trend
        == RegimeLabel.RANGE
    )


@pytest.mark.parametrize(
    "path,expected",
    [
        ((10, 20, 40, 80, 160), VolatilityRegime.NORMAL),
        ((10, 11, 12, 100, 200), VolatilityRegime.HIGH),
        ((10, 100, 10, 11, 12), VolatilityRegime.LOW),
    ],
)
def test_volatility_uses_previous_baseline(
    path: tuple[int, ...], expected: VolatilityRegime
) -> None:
    result = _calculate(bars(path), query(5), FreshnessPolicy(), SPEC)
    assert all(o.volatility is None for o in result[:4])
    assert result[-1].volatility == expected
    current = result[4].technical.results[0].features[0].value
    previous = [o.technical.results[0].features[0].value for o in result[2:4]]
    assert current is not None and all(v is not None for v in previous)
    with localcontext() as context:
        context.prec = 50
        baseline = sum((v for v in previous if v is not None), D(0)) / 2
        assert result[-1].volatility_ratio.value == current / baseline


def test_flat_and_zero_volume_never_fabricate_model_features() -> None:
    data = tuple(Candle.model_validate({**c.model_dump(), "volume": "0"}) for c in bars((10,) * 8))
    last = _calculate(data, query(8), FreshnessPolicy(), SPEC)[-1]
    assert last.trend == RegimeLabel.RANGE and last.volatility is None and last.vector is None
    assert last.volatility_ratio.status == FeatureStatus.UNDEFINED
    assert last.volatility_ratio.reason == "ZERO_DENOMINATOR"


def test_every_prefix_future_perturbation_and_decimal_context() -> None:
    data = bars()
    full = _calculate(data, query(len(data)), FreshnessPolicy(), SPEC)
    for length in range(1, len(data) + 1):
        assert _calculate(data[:length], query(length), FreshnessPolicy(), SPEC) == full[:length]
    changed = (*data[:8], *bars((*PATH[:8], 999, 3, 777, 4, 888, 5, 500, 6))[8:])
    with localcontext() as context:
        context.prec = 3
        assert _calculate(changed, query(len(data)), FreshnessPolicy(), SPEC)[:8] == full[:8]
        assert _calculate(data, query(len(data)), FreshnessPolicy(), SPEC) == full


def test_service_replay_parity_and_absent_model(repository: MarketRepository) -> None:
    repository.put(bars())
    replay = MarketReplay(repository, CLOCK)
    result = RegimeEngine(replay).analyze(query(len(PATH)), FreshnessPolicy(), SPEC)
    technical = TechnicalIntelligence(replay).analyze(
        query(len(PATH)),
        FreshnessPolicy(),
        (
            IndicatorSpec(kind=IndicatorKind.REALIZED_VOLATILITY, period=2),
            IndicatorSpec(kind=IndicatorKind.VOLUME, period=2),
        ),
    )
    assert tuple(s.observation.technical for s in result) == technical
    assert all(
        s.probability.status == "UNAVAILABLE" and s.probability.reason == "NO_MODEL" for s in result
    )
    assert all(not s.probability.probabilities for s in result)
    assert RegimeSnapshot.model_validate_json(result[-1].model_dump_json()) == result[-1]
    with pytest.raises(ValidationError):
        result[-1].observation.trend = RegimeLabel.RANGE


def test_late_receipt_delays_all_dependent_observations(repository: MarketRepository) -> None:
    data = list(bars())
    data[0] = Candle.model_validate(
        {**data[0].model_dump(), "received_at": START + timedelta(hours=30)}
    )
    repository.put(tuple(data))
    result = RegimeEngine(MarketReplay(repository, CLOCK)).analyze(
        query(len(data)), FreshnessPolicy(), SPEC
    )
    assert all(s.observation.technical.available_at == START + timedelta(hours=30) for s in result)


def test_missing_stale_future_and_explicit_empty_sessions(repository: MarketRepository) -> None:
    engine = RegimeEngine(MarketReplay(repository, CLOCK))
    with pytest.raises(DataRejected):
        engine.analyze(query(3), FreshnessPolicy(), SPEC)
    repository.put(bars()[:3])
    with pytest.raises(DataRejected):
        engine.analyze(query(3), FreshnessPolicy(max_age=timedelta(hours=1)), SPEC)
    with pytest.raises(DataRejected):
        RegimeEngine(MarketReplay(repository, FrozenClock(START))).analyze(
            query(3), FreshnessPolicy(), SPEC
        )
    closed = CandleQuery.model_validate({**query(3).model_dump(), "expected_opens": ()})
    # Use an empty interval distinct from the stored data.
    closed = CandleQuery.model_validate(
        {
            **closed.model_dump(),
            "start": START + timedelta(days=1),
            "end": START + timedelta(days=2),
        }
    )
    assert engine.analyze(closed, FreshnessPolicy(), SPEC) == ()


def test_training_fit_provenance_and_class_moments() -> None:
    examples = snapshots()
    model = fit(examples)
    assert model == fit(tuple(reversed(examples)))
    assert model.stage == "RESEARCH" and model.calibration == "UNCALIBRATED"
    assert model.trained_through == model.training_available_at == model.fitted_at
    assert model.trained_through == START + timedelta(hours=10)
    for c in model.classes:
        vectors = [e.observation.vector for e in examples if e.label == c.label]
        assert c.count == 2
        with localcontext() as context:
            context.prec = 50
            for j in range(3):
                values = [v[j] for v in vectors if v is not None]
                mean = sum(values, D(0)) / 2
                assert c.mean[j] == mean
                assert c.variance[j] == max(
                    model.fit_spec.variance_floor, sum(((v - mean) ** 2 for v in values), D(0)) / 2
                )
    assert RegimeModel.model_validate_json(model.model_dump_json()) == model
    with pytest.raises(ValidationError):
        model.fitted_at = CLOCK.now()
    changed = tuple(
        TrainingExample(
            observation=e.observation,
            label=e.label,
            label_available_at=e.label_available_at + timedelta(seconds=1),
        )
        for e in examples
    )
    newer = RegimeTrainer(CLOCK).fit(
        changed,
        fitted_at=START + timedelta(hours=11),
        label_policy="synthetic-manual-labels-v1",
        spec=FitSpec(minimum_per_class=2),
    )
    assert newer.dataset_hash != model.dataset_hash
    assert fingerprint(newer.model_dump()) != fingerprint(model.model_dump())


def test_model_availability_and_training_overlap() -> None:
    observations = _calculate(bars(), query(len(PATH)), FreshnessPolicy(), SPEC)
    model = fit()
    assert infer(observations[8], model).reason == "MODEL_NOT_AVAILABLE"
    assert infer(observations[9], model).reason == "TRAINING_OVERLAP"
    result = infer(observations[10], model)
    assert result.status == "RESEARCH" and result.reason is None
    assert result.calibration == "UNCALIBRATED"
    assert sum(p.probability for p in result.probabilities) == 1
    assert all(D(0) <= p.probability <= 1 for p in result.probabilities)


def test_model_posteriors_match_independent_float_gaussian_reference() -> None:
    observation = _calculate(bars(), query(len(PATH)), FreshnessPolicy(), SPEC)[-1]
    model = fit()
    assert observation.vector is not None
    logs = [
        log(c.count / sum(k.count for k in model.classes))
        - sum(
            log(float(v)) + (float(x) - float(m)) ** 2 / float(v)
            for x, m, v in zip(observation.vector, c.mean, c.variance, strict=True)
        )
        / 2
        for c in model.classes
    ]
    weights = [exp(score - max(logs)) for score in logs]
    expected = [w / sum(weights) for w in weights]
    actual = infer(observation, model)
    assert [float(p.probability) for p in actual.probabilities] == pytest.approx(
        expected, abs=1e-12
    )
    with localcontext() as context:
        context.prec = 3
        assert infer(observation, model) == actual
        assert fit() == model


def test_service_with_model_is_prefix_invariant(repository: MarketRepository) -> None:
    repository.put(bars())
    service = RegimeEngine(MarketReplay(repository, CLOCK))
    model = fit()
    full = service.analyze(query(len(PATH)), FreshnessPolicy(), SPEC, model)
    assert service.analyze(query(12), FreshnessPolicy(), SPEC, model) == full[:12]
    assert full[-1].probability.status == "RESEARCH"
    assert RegimeSnapshot.model_validate_json(full[-1].model_dump_json()) == full[-1]


@pytest.mark.parametrize(
    "changes",
    [
        {"period": 1},
        {"period": True},
        {"baseline_period": 501},
        {"version": "2.0.0"},
        {"range_efficiency": "0.7", "trend_efficiency": "0.6"},
        {"low_volatility_ratio": "1"},
        {"high_volatility_ratio": "1"},
        {"trend_efficiency": "NaN"},
        {"extra": 1},
    ],
)
def test_bad_spec(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RegimeSpec.model_validate(changes)


def test_training_rejections() -> None:
    examples = snapshots()
    trainer = RegimeTrainer(CLOCK)
    with pytest.raises(ValueError, match="8..10000"):
        fit(())
    with pytest.raises(ValueError, match="duplicate"):
        fit((*examples[:-1], examples[0]))
    with pytest.raises(ValueError, match="per class"):
        trainer.fit(examples, fitted_at=START + timedelta(hours=10), label_policy="synthetic-v1")
    with pytest.raises(ValueError, match="future"):
        trainer.fit(
            examples, fitted_at=CLOCK.now() + timedelta(seconds=1), label_policy="synthetic-v1"
        )
    with pytest.raises(ValueError, match="not yet available"):
        trainer.fit(examples, fitted_at=START + timedelta(hours=9), label_policy="synthetic-v1")
    with pytest.raises(ValueError, match="timezone"):
        trainer.fit(examples, fitted_at=START.replace(tzinfo=None), label_policy="synthetic-v1")
    with pytest.raises(ValidationError, match="predate"):
        TrainingExample(
            observation=examples[0].observation, label=RegimeLabel.RANGE, label_available_at=START
        )
    warmup = _calculate(bars(), query(len(PATH)), FreshnessPolicy(), SPEC)[0]
    with pytest.raises(ValidationError, match="all model features"):
        TrainingExample(observation=warmup, label=RegimeLabel.RANGE, label_available_at=CLOCK.now())


def test_bad_probability_contracts() -> None:
    with pytest.raises(ValidationError):
        ProbabilityResult(status="UNAVAILABLE", reason=None)
    with pytest.raises(ValidationError):
        ProbabilityResult(status="RESEARCH", reason=None)
    with pytest.raises(ValidationError):
        ProbabilityResult(status="RESEARCH", reason=None, model_hash="a" * 64)
    with pytest.raises(ValidationError, match="sum to one"):
        ProbabilityResult(
            status="RESEARCH",
            reason=None,
            model_hash="a" * 64,
            probabilities=tuple(
                RegimeProbability(label=label, probability=D("0.2")) for label in RegimeLabel
            ),
        )
    with pytest.raises(ValidationError):
        RegimeProbability(label=RegimeLabel.RANGE, probability=D("NaN"))


def heldout() -> tuple[TrainingExample, ...]:
    offset = timedelta(days=1)
    data = tuple(
        Candle.model_validate(
            {
                **c.model_dump(),
                "open_time": c.open_time + offset,
                "close_time": c.close_time + offset,
                "received_at": c.received_at + offset,
            }
        )
        for c in bars()
    )
    q = CandleQuery.model_validate(
        {
            **query(len(data)).model_dump(),
            "start": START + offset,
            "end": START + offset + timedelta(hours=len(data)),
        }
    )
    observations = _calculate(data, q, FreshnessPolicy(), SPEC)
    return tuple(
        TrainingExample(
            observation=o,
            label=tuple(RegimeLabel)[i % 4],
            label_available_at=o.technical.available_at,
            partition=SamplePartition.VALIDATION,
        )
        for i, o in enumerate(observations[2:10])
    )


def test_evaluation_independent_brier_and_no_final_holdout_training() -> None:
    model = fit()
    examples = heldout()
    evaluator = RegimeEvaluator(CLOCK)
    report = evaluator.evaluate(
        model, examples, evaluated_at=CLOCK.now(), label_policy=model.label_policy
    )
    expected = [infer(e.observation, model) for e in examples]
    with localcontext() as context:
        context.prec = 50
        brier = sum(
            (
                sum(((p.probability - int(p.label == e.label)) ** 2 for p in r.probabilities), D(0))
                for e, r in zip(examples, expected, strict=True)
            ),
            D(0),
        ) / len(examples)
        accuracy = D(
            sum(
                max(r.probabilities, key=lambda p: p.probability).label == e.label
                for e, r in zip(examples, expected, strict=True)
            )
        ) / len(examples)
        assert report.multiclass_brier == brier and report.accuracy == accuracy
    assert report.calibration == "NOT_ESTABLISHED" and report.sample_count == 8
    assert all(c.count == 2 for c in report.class_support)
    assert report == evaluator.evaluate(
        model, tuple(reversed(examples)), evaluated_at=CLOCK.now(), label_policy=model.label_policy
    )
    final = tuple(
        TrainingExample.model_validate({**e.model_dump(), "partition": "FINAL_HOLDOUT"})
        for e in examples
    )
    final_report = evaluator.evaluate(
        model, final, evaluated_at=CLOCK.now(), label_policy=model.label_policy
    )
    assert final_report.partition == SamplePartition.FINAL_HOLDOUT
    with pytest.raises(ValueError, match="cannot be used for training"):
        RegimeTrainer(CLOCK).fit(final, fitted_at=CLOCK.now(), label_policy=model.label_policy)
    with localcontext() as context:
        context.prec = 3
        assert (
            evaluator.evaluate(
                model, examples, evaluated_at=CLOCK.now(), label_policy=model.label_policy
            )
            == report
        )


def test_evaluation_fail_closed() -> None:
    model, examples = fit(), heldout()
    evaluator = RegimeEvaluator(CLOCK)
    with pytest.raises(ValueError, match="1..10000"):
        evaluator.evaluate(model, (), evaluated_at=CLOCK.now(), label_policy=model.label_policy)
    with pytest.raises(ValueError, match="partition"):
        evaluator.evaluate(
            model, snapshots(), evaluated_at=CLOCK.now(), label_policy=model.label_policy
        )
    with pytest.raises(ValueError, match="duplicate"):
        evaluator.evaluate(
            model,
            (*examples, examples[0]),
            evaluated_at=CLOCK.now(),
            label_policy=model.label_policy,
        )
    with pytest.raises(ValueError, match="label policy"):
        evaluator.evaluate(model, examples, evaluated_at=CLOCK.now(), label_policy="other-v1")
    with pytest.raises(ValueError, match="future"):
        evaluator.evaluate(
            model,
            examples,
            evaluated_at=CLOCK.now() + timedelta(seconds=1),
            label_policy=model.label_policy,
        )
    with pytest.raises(ValueError, match="not yet available"):
        evaluator.evaluate(
            model,
            examples,
            evaluated_at=START + timedelta(hours=10),
            label_policy=model.label_policy,
        )
    overlap = tuple(
        TrainingExample.model_validate({**e.model_dump(), "partition": "VALIDATION"})
        for e in snapshots()
    )
    with pytest.raises(ValueError, match="overlaps training"):
        evaluator.evaluate(
            model, overlap, evaluated_at=CLOCK.now(), label_policy=model.label_policy
        )
    delayed_model = RegimeModel.model_validate({**model.model_dump(), "fitted_at": CLOCK.now()})
    with pytest.raises(ValueError, match="not usable"):
        evaluator.evaluate(
            delayed_model, examples, evaluated_at=CLOCK.now(), label_policy=model.label_policy
        )


@pytest.mark.parametrize(
    "change",
    [
        {"market_id": "other"},
        {"source": "other"},
        {"timeframe": "4h"},
        {"feature_spec": RegimeSpec(period=3)},
    ],
)
def test_incompatible_model_and_training_identity(change: dict[str, object]) -> None:
    model = RegimeModel.model_validate({**fit().model_dump(), **change})
    with pytest.raises(ValueError, match="incompatible"):
        infer(heldout()[0].observation, model)
    examples = snapshots()
    observation = examples[0].observation
    if "feature_spec" in change:
        bad = RegimeObservation.model_validate(
            {**observation.model_dump(), "spec": change["feature_spec"]}
        )
    else:
        bad = RegimeObservation.model_validate(
            {
                **observation.model_dump(),
                "technical": {
                    **observation.technical.model_dump(),
                    **change,
                },
            }
        )
    changed = (
        TrainingExample(
            observation=bad,
            label=examples[0].label,
            label_available_at=examples[0].label_available_at,
        ),
        *examples[1:],
    )
    with pytest.raises(ValueError, match="one market"):
        fit(changed)


def test_missing_features_model_result() -> None:
    observation = heldout()[0].observation
    missing = RegimeObservation.model_validate({**observation.model_dump(), "vector": None})
    result = infer(missing, fit())
    assert result.reason == "FEATURES_UNAVAILABLE" and result.probabilities == ()


def test_equal_likelihood_priors_and_tiny_likelihoods() -> None:
    observation = heldout()[0].observation
    assert observation.vector is not None
    model = fit()
    classes = tuple(
        GaussianClass(
            label=label, count=2 * (i + 1), mean=observation.vector, variance=(D(1), D(1), D(1))
        )
        for i, label in enumerate(RegimeLabel)
    )
    equal = RegimeModel.model_validate({**model.model_dump(), "classes": classes})
    assert [p.probability for p in infer(observation, equal).probabilities] == [
        D("0.1"),
        D("0.2"),
        D("0.3"),
        D("0.4"),
    ]
    extreme = tuple(
        GaussianClass(
            label=label,
            count=2,
            mean=observation.vector if i == 0 else (D(-1), D(99), D(99)),
            variance=(D("1e-12"),) * 3,
        )
        for i, label in enumerate(RegimeLabel)
    )
    sharp = RegimeModel.model_validate({**model.model_dump(), "classes": extreme})
    assert [p.probability for p in infer(observation, sharp).probabilities] == [
        D(1),
        D(0),
        D(0),
        D(0),
    ]


def test_invalid_fitted_model_artifacts() -> None:
    model = fit()
    for change in (
        {"classes": tuple(reversed(model.classes))},
        {"fitted_at": START},
        {"stage": "PRODUCTION"},
        {"calibration": "CALIBRATED"},
        {"fit_spec": FitSpec(minimum_per_class=3)},
        {"fit_spec": FitSpec(minimum_per_class=2, variance_floor=D(1))},
        {
            "classes": tuple(
                GaussianClass.model_validate({**c.model_dump(), "count": 3000})
                for c in model.classes
            )
        },
    ):
        with pytest.raises(ValidationError):
            RegimeModel.model_validate({**model.model_dump(), **change})
    with pytest.raises(ValidationError):
        GaussianClass(
            label=RegimeLabel.RANGE, count=2, mean=(D(0), D(0), D(0)), variance=(D(0),) * 3
        )


def test_single_replay_and_dependency_failure(
    repository: MarketRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pocket_alpha.market_data.replay import ReplayEvent

    repository.put(bars())
    replay = MarketReplay(repository, CLOCK)
    original = replay.replay
    calls = []

    def counted(q: CandleQuery, policy: FreshnessPolicy) -> tuple[ReplayEvent, ...]:
        calls.append(q)
        return original(q, policy)

    monkeypatch.setattr(replay, "replay", counted)
    RegimeEngine(replay).analyze(query(len(PATH)), FreshnessPolicy(), SPEC)
    assert len(calls) == 1

    def failed(q: CandleQuery, policy: FreshnessPolicy) -> tuple[ReplayEvent, ...]:
        raise RuntimeError("unavailable")

    monkeypatch.setattr(replay, "replay", failed)
    with pytest.raises(RuntimeError, match="unavailable"):
        RegimeEngine(replay).analyze(query(3), FreshnessPolicy(), SPEC)


def test_explicit_session_schedule_and_all_timeframes(repository: MarketRepository) -> None:
    for tf in Timeframe:
        data = tuple(
            Candle.model_validate(
                {
                    **c.model_dump(),
                    "timeframe": tf,
                    "open_time": START + i * tf.duration * 2,
                    "close_time": START + (i * 2 + 1) * tf.duration,
                    "received_at": START + (i * 2 + 1) * tf.duration,
                }
            )
            for i, c in enumerate(bars()[:5])
        )
        repository.put(data)
        q = CandleQuery(
            market_id="test-market",
            timeframe=tf,
            start=START,
            end=data[-1].close_time,
            expected_opens=tuple(c.open_time for c in data),
        )
        result = RegimeEngine(MarketReplay(repository, CLOCK)).analyze(q, FreshnessPolicy(), SPEC)
        assert len(result) == 5 and result[-1].observation.technical.input_count == 5
        assert result[-1].observation.trend is not None
