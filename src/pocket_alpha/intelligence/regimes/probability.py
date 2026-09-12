import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.intelligence.regimes.models import (
    FitSpec,
    GaussianClass,
    ProbabilityResult,
    RegimeLabel,
    RegimeModel,
    RegimeObservation,
    RegimeProbability,
    SamplePartition,
    TrainingExample,
    Vector,
)

D = Decimal
DEFAULT_FIT_SPEC = FitSpec()


def fingerprint(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            canonical(payload),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


class RegimeTrainer:
    """Explicit supervised fit. Caller supplies labels and a versioned label policy.

    It never labels data using the baseline, invents examples or fits during inference.
    Label quality and temporal out-of-sample economic validation remain research work.
    """

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def fit(
        self,
        examples: tuple[TrainingExample, ...],
        *,
        fitted_at: datetime,
        label_policy: str,
        spec: FitSpec = DEFAULT_FIT_SPEC,
    ) -> RegimeModel:
        if not 8 <= len(examples) <= 10000:
            raise ValueError("training requires 8..10000 labeled observations")
        if any(e.partition != SamplePartition.TRAIN for e in examples):
            raise ValueError("validation and final holdout samples cannot be used for training")
        fitted_at = utc(fitted_at)
        if fitted_at > utc(self.clock.now()):
            raise ValueError("fitted_at cannot be in the future")
        ordered = sorted(examples, key=lambda e: e.observation.technical.bar_close)
        first = ordered[0].observation
        context = first.technical
        identity = (context.market_id, context.timeframe, context.source, first.spec)
        closes = []
        for example in ordered:
            observation, technical = example.observation, example.observation.technical
            if (
                technical.market_id,
                technical.timeframe,
                technical.source,
                observation.spec,
            ) != identity:
                raise ValueError(
                    "training observations require one market, timeframe, source and spec"
                )
            if example.label_available_at > fitted_at:
                raise ValueError("training label or observation is not yet available")
            closes.append(technical.bar_close)
        if len(set(closes)) != len(closes):
            raise ValueError("duplicate training observation")
        classes: list[GaussianClass] = []
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            for label in RegimeLabel:
                vectors = [e.observation.vector for e in ordered if e.label == label]
                if len(vectors) < spec.minimum_per_class:
                    raise ValueError("insufficient observations per class")
                # TrainingExample validation guarantees a complete vector.
                values: list[Vector] = [v for v in vectors if v is not None]
                means = tuple(sum((v[j] for v in values), D(0)) / len(values) for j in range(3))
                variances = tuple(
                    max(
                        spec.variance_floor,
                        sum(((v[j] - means[j]) ** 2 for v in values), D(0)) / len(values),
                    )
                    for j in range(3)
                )
                classes.append(
                    GaussianClass(
                        label=label,
                        count=len(values),
                        mean=(means[0], means[1], means[2]),
                        variance=(variances[0], variances[1], variances[2]),
                    )
                )
        return RegimeModel(
            feature_spec=first.spec,
            fit_spec=spec,
            label_policy=label_policy,
            market_id=context.market_id,
            timeframe=context.timeframe,
            source=context.source,
            trained_through=max(closes),
            training_available_at=max(e.label_available_at for e in ordered),
            fitted_at=fitted_at,
            dataset_hash=fingerprint([e.model_dump() for e in ordered]),
            classes=tuple(classes),
        )


def infer(observation: RegimeObservation, model: RegimeModel | None) -> ProbabilityResult:
    """Posterior of CURRENT externally labeled regime, never a future return probability."""
    if model is None:
        return ProbabilityResult(status="UNAVAILABLE", reason="NO_MODEL")
    technical = observation.technical
    if (model.market_id, model.timeframe, model.source, model.feature_spec) != (
        technical.market_id,
        technical.timeframe,
        technical.source,
        observation.spec,
    ):
        raise ValueError("model is incompatible with observation identity or feature specification")
    model_hash = fingerprint(model.model_dump())
    if technical.available_at < model.fitted_at:
        return ProbabilityResult(
            status="UNAVAILABLE", reason="MODEL_NOT_AVAILABLE", model_hash=model_hash
        )
    if technical.bar_close <= model.trained_through:
        return ProbabilityResult(
            status="UNAVAILABLE", reason="TRAINING_OVERLAP", model_hash=model_hash
        )
    if observation.vector is None:
        return ProbabilityResult(
            status="UNAVAILABLE", reason="FEATURES_UNAVAILABLE", model_hash=model_hash
        )
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        count = sum(c.count for c in model.classes)
        scores = [
            (D(c.count) / count).ln()
            - sum(
                (
                    variance.ln() + (value - mean) ** 2 / variance
                    for value, mean, variance in zip(
                        observation.vector, c.mean, c.variance, strict=True
                    )
                ),
                D(0),
            )
            / 2
            for c in model.classes
        ]
        maximum = max(scores)
        # Terms below exp(-1000) cannot affect probabilities rounded to 30 decimal places.
        weights = [(s - maximum).exp() if s - maximum >= -1000 else D(0) for s in scores]
        total = sum(weights, D(0))
        probabilities = [(w / total).quantize(D("1e-30")) for w in weights]
        winner = scores.index(maximum)  # Canonical class order resolves exact ties.
        probabilities[winner] += 1 - sum(probabilities, D(0))
        return ProbabilityResult(
            status="RESEARCH",
            reason=None,
            model_hash=model_hash,
            probabilities=tuple(
                RegimeProbability(label=c.label, probability=p)
                for c, p in zip(model.classes, probabilities, strict=True)
            ),
        )
