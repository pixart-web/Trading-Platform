from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.intelligence.regimes.models import (
    ClassSupport,
    RegimeEvaluation,
    RegimeLabel,
    RegimeModel,
    SamplePartition,
    TrainingExample,
)
from pocket_alpha.intelligence.regimes.probability import fingerprint, infer

D = Decimal


class RegimeEvaluator:
    """Temporal held-out diagnostics. Never calibrates, fits or promotes a model."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def evaluate(
        self,
        model: RegimeModel,
        examples: tuple[TrainingExample, ...],
        *,
        evaluated_at: datetime,
        label_policy: str,
    ) -> RegimeEvaluation:
        evaluated_at = utc(evaluated_at)
        if evaluated_at > utc(self.clock.now()):
            raise ValueError("evaluation cannot be in the future")
        if not 1 <= len(examples) <= 10000:
            raise ValueError("evaluation requires 1..10000 examples")
        partition = examples[0].partition
        if partition == SamplePartition.TRAIN or any(e.partition != partition for e in examples):
            raise ValueError("evaluation requires one validation or final holdout partition")
        if label_policy != model.label_policy:
            raise ValueError("evaluation label policy must match the trained model")
        ordered = sorted(examples, key=lambda e: e.observation.technical.bar_close)
        if len({e.observation.technical.bar_close for e in ordered}) != len(ordered):
            raise ValueError("duplicate evaluation observation")
        errors = D(0)
        correct = 0
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            for example in ordered:
                if example.label_available_at > evaluated_at:
                    raise ValueError("evaluation label is not yet available")
                # Evaluation windows must be wholly after training; embargo/warm-up
                # overlap is rejected instead of claiming an independent holdout.
                if example.observation.technical.input_start < model.trained_through:
                    raise ValueError("evaluation input window overlaps training history")
                result = infer(example.observation, model)
                if result.status != "RESEARCH":
                    raise ValueError("model was not usable at evaluation observation availability")
                predicted = max(result.probabilities, key=lambda p: p.probability).label
                correct += predicted == example.label
                errors += sum(
                    (
                        (p.probability - int(p.label == example.label)) ** 2
                        for p in result.probabilities
                    ),
                    D(0),
                )
            return RegimeEvaluation(
                model_hash=fingerprint(model.model_dump()),
                dataset_hash=fingerprint([e.model_dump() for e in ordered]),
                partition=partition,
                evaluated_at=evaluated_at,
                sample_count=len(ordered),
                class_support=tuple(
                    ClassSupport(label=label, count=sum(e.label == label for e in ordered))
                    for label in RegimeLabel
                ),
                accuracy=D(correct) / len(ordered),
                multiclass_brier=errors / len(ordered),
            )
