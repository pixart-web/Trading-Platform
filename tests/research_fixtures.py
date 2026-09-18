"""Synthetic research mechanics only; no empirical return or profitability evidence."""

import json
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pocket_alpha.backtesting.models import Intent, Parameter, StrategyView, digest
from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.models import ForecastHorizon
from pocket_alpha.market_data.datasets import MarketDataset, MarketDatasetRecord
from pocket_alpha.research.models import AnalysisPolicy, Segment, Source, StudyPlan, Variant, Window
from pocket_alpha.research.storage import ResearchRepository
from pocket_alpha.research.temporal import folds
from tests.backtest_fixtures import config, dataset
from tests.market_fixtures import START


def research_data() -> MarketDataset:
    return dataset(("100",) * 64)


def plan(
    data: MarketDataset | None = None, mode: Literal["WALK_FORWARD", "ROLLING"] = "WALK_FORWARD"
) -> StudyPlan:
    data = data or research_data()
    base = config()
    parameter = base.strategy.model_dump() | dict(
        parameters=(Parameter(name="quantity", value="0.5"),)
    )
    candidate = config(strategy=parameter)
    stressed = config(
        costs=base.costs.model_dump() | dict(version="synthetic-stress-1", fee_bps=Decimal(20))
    )
    return StudyPlan(
        version="synthetic-study-1",
        rationale="Synthetic robustness mechanics only",
        mode=mode,
        sources=(Source(dataset_id=data.dataset_id, dataset_hash=data.content_hash),),
        folds=folds(START, 8 * 3600, 8 * 3600, 3600, 2, mode),
        variants=(
            Variant(name="baseline", role="BASELINE", config=base, horizon=ForecastHorizon.H1),
            Variant(
                name="quantity", role="PARAMETER", config=candidate, horizon=ForecastHorizon.H1
            ),
            Variant(name="stress", role="COST_STRESS", config=stressed, horizon=ForecastHorizon.H1),
        ),
        segments=(
            Segment(
                name="declared-regime",
                window=Window(start=START + timedelta(hours=20), end=START + timedelta(hours=24)),
                evidence_hash=digest(dict(synthetic=True)),
                available_at=START + timedelta(hours=19),
                provenance="Synthetic declared label",
            ),
        ),
        final_holdout=Window(start=START + timedelta(hours=45), end=START + timedelta(hours=64)),
        label_horizon_seconds=3600,
        analysis=AnalysisPolicy(
            version="synthetic-analysis-1",
            seed=22,
            simulations=20,
            block_length=2,
            minimum_returns=3,
            lower_quantile=Decimal("0.1"),
            upper_quantile=Decimal("0.9"),
        ),
        maximum_runs=64,
    )


class Callback:
    def __init__(self, variant: Variant) -> None:
        self.identity = variant.config.strategy
        self.counter = 0
        self.quantity = Decimal("0.5") if variant.name == "quantity" else Decimal(1)

    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        self.counter += 1
        if self.counter == 1:
            return (Intent(client_id="research-buy", action="BUY", quantity=self.quantity),)
        if self.counter == 4:
            return (Intent(client_id="research-sell", action="SELL", quantity=self.quantity),)
        return ()


class Factory:
    def __init__(self) -> None:
        self.training: list[MarketDataset] = []
        self.callbacks: list[Callback] = []

    def fit(self, training: MarketDataset, variant: Variant) -> str:
        self.training.append(training)
        return json.dumps(
            dict(
                train_hash=training.content_hash,
                model_version=variant.config.strategy.model_version,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )

    def materialize(self, artifact_json: str, variant: Variant) -> Callback:
        callback = Callback(variant)
        self.callbacks.append(callback)
        return callback


def seed(repository: ResearchRepository) -> MarketDataset:
    data = research_data()
    from pocket_alpha.market_data.storage import MarketRepository

    MarketRepository(repository.session).register(
        data.inputs.asset, data.inputs.venue, data.inputs.market, data.inputs.mapping
    )
    repository.session.add(
        MarketDatasetRecord(dataset_id=data.dataset_id, payload=data.model_dump_json())
    )
    repository.session.flush()
    return data


CLOCK = FrozenClock(START + timedelta(days=10))
