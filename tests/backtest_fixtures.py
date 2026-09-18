"""Explicitly synthetic simulation inputs; never empirical profit evidence."""

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from pocket_alpha.backtesting.inputs import current_code_hash, current_environment_hash
from pocket_alpha.backtesting.models import (
    CostPolicy,
    Intent,
    RiskPolicy,
    RunConfig,
    StrategyIdentity,
    StrategyView,
)
from pocket_alpha.domain.market import Candle, CandleQuery, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.intelligence.technical.models import IndicatorKind, IndicatorSpec
from pocket_alpha.market_data.datasets import DatasetInputs, MarketDataset
from pocket_alpha.market_data.providers import ProviderMapping
from tests.market_fixtures import START

D = Decimal
IDENTITY = StrategyIdentity(
    strategy_version="synthetic-plan-1", model_version="synthetic-model-1", parameters=()
)


def dataset(
    prices: tuple[str, ...] = ("100",) * 10,
    volumes: tuple[str, ...] | None = None,
    delayed: dict[int, int] | None = None,
) -> MarketDataset:
    bars = tuple(
        Candle(
            market_id="simulation:BTC-USD",
            timeframe=Timeframe.H1,
            open_time=START + timedelta(hours=i),
            close_time=START + timedelta(hours=i + 1),
            open=D(price),
            high=D(price) + 10,
            low=max(D("0.01"), D(price) - 10),
            close=D(price),
            volume=D(volumes[i] if volumes else "100"),
            source="synthetic-simulation",
            received_at=START + timedelta(hours=(delayed or {}).get(i, i + 1)),
        )
        for i, price in enumerate(prices)
    )
    inputs = DatasetInputs(
        origin="SYNTHETIC",
        mapping=ProviderMapping(
            source="synthetic-simulation",
            market_id="simulation:BTC-USD",
            instrument_id="synthetic-product",
        ),
        market=Market(
            market_id="simulation:BTC-USD",
            asset_id="synthetic:BTC",
            venue_id="synthetic-venue",
            symbol="BTC-USD",
            quote_currency="USD",
        ),
        asset=Asset(
            asset_id="synthetic:BTC",
            symbol="BTC",
            name="Synthetic Bitcoin",
            asset_type=AssetType.CRYPTO,
        ),
        venue=Venue(venue_id="synthetic-venue", name="Synthetic venue"),
        query=CandleQuery(
            market_id="simulation:BTC-USD",
            timeframe=Timeframe.H1,
            start=START,
            end=START + timedelta(hours=len(bars)),
        ),
        captured_at=max(b.received_at for b in bars),
        candles=bars,
    )
    return MarketDataset(dataset_id=UUID(int=2101), inputs=inputs, content_hash=inputs.digest())


def config(**changes: object) -> RunConfig:
    result = RunConfig(
        strategy=IDENTITY,
        costs=CostPolicy(
            version="synthetic-costs-1",
            fee_bps=D(10),
            spread_bps=D(10),
            slippage_bps=D(5),
            impact_bps_at_capacity=D(5),
            maximum_price_deviation_fraction=D("0.5"),
            participation=D("0.1"),
            latency_seconds=0,
            order_lifetime_seconds=86400,
            quantity_step=D("0.01"),
            minimum_quantity=D("0.01"),
            minimum_notional=D(1),
        ),
        risk=RiskPolicy(
            version="synthetic-risk-1",
            maximum_order_notional=D(10000),
            maximum_exposure_fraction=D(1),
            maximum_drawdown=D("0.8"),
            maximum_daily_loss=D("0.8"),
            maximum_data_age_seconds=60,
            maximum_pending_orders=10,
            maximum_spread_bps=D(100),
        ),
        initial_cash=D(10000),
        code_revision="0" * 40,
        code_tree_hash=current_code_hash(),
        environment_hash=current_environment_hash(),
        environment_identity="synthetic-unit-test-python",
        random_seed=0,
        maximum_intents=100,
        maximum_history_bars=100,
        feature_specs=(IndicatorSpec(kind=IndicatorKind.SMA, period=2),),
        selection_rationale="Explicitly synthetic fixed-market regression only",
        evaluation_split="RESEARCH",
        annualization_seconds=31536000,
        minimum_ratio_returns=3,
        annual_risk_free_rate=D(0),
        tail_fraction=D("0.05"),
    )
    return RunConfig.model_validate(result.model_dump() | changes)


class Plan:
    identity = IDENTITY

    def __init__(self, decisions: Mapping[int, tuple[Intent, ...]]) -> None:
        self.decisions = decisions
        self.views: list[StrategyView] = []

    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        self.views.append(view)
        hour = int((view.as_of - START) / timedelta(hours=1))
        return self.decisions.get(hour, ())
