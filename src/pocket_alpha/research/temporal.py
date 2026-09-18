from datetime import datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.domain.market import CandleQuery
from pocket_alpha.market_data.datasets import DatasetInputs, MarketDataset
from pocket_alpha.research.models import Fold, Window


def folds(
    start: datetime,
    training_seconds: int,
    evaluation_seconds: int,
    embargo_seconds: int,
    count: int,
    mode: Literal["WALK_FORWARD", "ROLLING"],
) -> tuple[Fold, ...]:
    if not 1 <= count <= 16 or min(training_seconds, evaluation_seconds, embargo_seconds) <= 0:
        raise ValueError("fold dimensions must be positive and bounded")
    if mode not in {"WALK_FORWARD", "ROLLING"}:
        raise ValueError("unsupported fold mode")
    result = []
    for i in range(count):
        advance = timedelta(seconds=i * (2 * evaluation_seconds + 2 * embargo_seconds))
        train_end = start + timedelta(seconds=training_seconds) + advance
        validation_start = train_end + timedelta(seconds=embargo_seconds)
        test_start = validation_start + timedelta(seconds=evaluation_seconds + embargo_seconds)
        result.append(
            Fold(
                name=f"fold-{i + 1}",
                train=Window(
                    start=start if mode == "WALK_FORWARD" else start + advance, end=train_end
                ),
                validation=Window(
                    start=validation_start,
                    end=validation_start + timedelta(seconds=evaluation_seconds),
                ),
                test=Window(
                    start=test_start, end=test_start + timedelta(seconds=evaluation_seconds)
                ),
                embargo_seconds=embargo_seconds,
            )
        )
    return tuple(result)


def subset(dataset: MarketDataset, window: Window) -> MarketDataset:
    dataset = MarketDataset.model_validate_json(dataset.model_dump_json())
    window = Window.model_validate_json(window.model_dump_json())
    candles = tuple(
        c
        for c in dataset.inputs.candles
        if window.start <= c.open_time and c.close_time <= window.end
    )
    if not candles or candles[0].open_time != window.start or candles[-1].close_time != window.end:
        raise ValueError("research windows require complete aligned candle coverage")
    if any(c.received_at > window.end for c in candles):
        raise ValueError("research window contains data received after its cutoff")
    query = CandleQuery(
        market_id=dataset.inputs.query.market_id,
        timeframe=dataset.inputs.query.timeframe,
        start=window.start,
        end=window.end,
    )
    inputs = DatasetInputs.model_validate(
        dataset.inputs.model_dump() | dict(query=query, candles=candles)
    )
    content_hash = inputs.digest()
    return MarketDataset(
        dataset_id=uuid5(
            NAMESPACE_URL,
            "pocket-alpha-research-subset:" + str(dataset.dataset_id) + ":" + content_hash,
        ),
        inputs=inputs,
        content_hash=content_hash,
    )


def economic_key(dataset: MarketDataset) -> str:
    # All venues/dataset UUIDs of the same native crypto symbol share one conservative final lock.
    return dataset.inputs.asset.asset_type.value + ":" + dataset.inputs.asset.symbol.upper()
