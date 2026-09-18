from uuid import UUID

from pocket_alpha.backtesting.engine import Backtester
from pocket_alpha.backtesting.inputs import ResearchStrategy
from pocket_alpha.backtesting.models import BacktestReport, RunConfig
from pocket_alpha.backtesting.storage import BacktestRepository
from pocket_alpha.common.clock import Clock
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.market_data.datasets import DatasetRepository


class BacktestService:
    def __init__(self, repository: BacktestRepository, clock: Clock) -> None:
        self.repository, self.clock = repository, clock

    def run(
        self,
        dataset_id: UUID,
        config: RunConfig,
        strategy: ResearchStrategy,
        forecasts: tuple[Forecast, ...] = (),
    ) -> BacktestReport:
        dataset = DatasetRepository(self.repository.session).get(dataset_id)
        if dataset is None:
            raise LookupError("backtest dataset not found")
        report = Backtester(self.clock).run(dataset, config, strategy, forecasts)
        return self.repository.put(report)
