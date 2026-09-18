from datetime import timedelta
from typing import Literal

import pytest

from pocket_alpha.research.models import StudyPlan, Window
from pocket_alpha.research.temporal import folds, subset
from tests.market_fixtures import START
from tests.research_fixtures import plan, research_data


@pytest.mark.parametrize("mode", ["WALK_FORWARD", "ROLLING"])
def test_fold_modes_and_known_data_isolation(mode: Literal["WALK_FORWARD", "ROLLING"]) -> None:
    study = plan(mode=mode)
    assert study.folds[1].train.end > study.folds[0].train.end
    training = subset(research_data(), study.folds[0].train)
    assert max(c.received_at for c in training.inputs.candles) <= study.folds[0].train.end
    assert all(c.close_time < study.folds[0].validation.start for c in training.inputs.candles)
    assert training.dataset_id != research_data().dataset_id
    assert subset(research_data(), study.folds[0].train) == training


@pytest.mark.parametrize(
    "change",
    [
        {"label_horizon_seconds": 3601},
        {"maximum_runs": 1},
        {"final_holdout": {"start": START, "end": START + timedelta(hours=1)}},
        {"sources": ()},
    ],
)
def test_plan_rejects_unsafe_or_unbounded_design(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        StudyPlan.model_validate(plan().model_dump() | change)


def test_split_receipts_alignment_and_empty_data_fail_closed() -> None:
    data = research_data()
    with pytest.raises(ValueError, match="aligned"):
        subset(data, Window(start=START + timedelta(minutes=1), end=START + timedelta(hours=3)))
    with pytest.raises(ValueError, match="aligned"):
        subset(data, Window(start=START + timedelta(days=10), end=START + timedelta(days=11)))
    delayed = data.inputs.model_dump()
    bars = list(data.inputs.candles)
    bars[0] = bars[0].model_copy(update={"received_at": START + timedelta(days=2)})
    from pocket_alpha.market_data.datasets import DatasetInputs, MarketDataset

    inputs = DatasetInputs.model_validate(delayed | dict(candles=tuple(bars)))
    late = MarketDataset(dataset_id=data.dataset_id, inputs=inputs, content_hash=inputs.digest())
    with pytest.raises(ValueError, match="received"):
        subset(late, plan().folds[0].train)
    with pytest.raises(ValueError):
        folds(START, 1, 1, 1, 0, "ROLLING")


def test_stress_and_segment_are_explicit_and_causal() -> None:
    study = plan()
    payload = study.model_dump()
    variants = list(payload["variants"])
    variants[2]["config"]["costs"]["fee_bps"] = 1
    with pytest.raises(ValueError, match="stress"):
        StudyPlan.model_validate(payload | dict(variants=variants))
    segments = list(study.model_dump()["segments"])
    segments[0]["available_at"] = segments[0]["window"]["end"]
    with pytest.raises(ValueError, match="evidence"):
        StudyPlan.model_validate(study.model_dump() | dict(segments=segments))
