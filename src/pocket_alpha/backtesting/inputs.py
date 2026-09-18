import hashlib
import platform
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from itertools import groupby
from pathlib import Path
from typing import Protocol

from pocket_alpha.backtesting.models import Intent, RunConfig, StrategyIdentity, StrategyView
from pocket_alpha.domain.market import Candle
from pocket_alpha.domain.models import AssetType
from pocket_alpha.forecasts.models import Forecast
from pocket_alpha.intelligence.technical.models import FeatureSnapshot
from pocket_alpha.intelligence.technical.service import _calculate
from pocket_alpha.market_data.datasets import MarketDataset
from pocket_alpha.market_data.quality import FreshnessPolicy


class ResearchStrategy(Protocol):
    @property
    def identity(self) -> StrategyIdentity: ...
    def on_event(self, view: StrategyView) -> tuple[Intent, ...]: ...


@dataclass(frozen=True)
class PreparedInputs:
    arrivals: tuple[tuple[datetime, tuple[Candle, ...]], ...]
    technical: tuple[FeatureSnapshot, ...]
    forecasts: tuple[Forecast, ...]


def prepare(
    dataset: MarketDataset, config: RunConfig, forecasts: tuple[Forecast, ...]
) -> PreparedInputs:
    # Revalidate boundary models even when a caller has used Pydantic model_copy/construct.
    dataset = MarketDataset.model_validate_json(dataset.model_dump_json())
    if dataset.inputs.asset.asset_type != AssetType.CRYPTO:
        raise ValueError(
            "Phase 21 supports crypto spot only; corporate actions/borrow/derivatives "
            "are unavailable"
        )
    if len(forecasts) > 10000 or len({f.forecast_id for f in forecasts}) != len(forecasts):
        raise ValueError("forecast inputs must be bounded and have unique immutable identities")
    validated_forecasts: list[Forecast] = []
    forecast_bytes = 0
    for forecast in forecasts:
        forecast_bytes += len(forecast.model_dump_json().encode())
        if forecast_bytes > 5_000_000:
            raise ValueError("forecast inputs exceed serialized byte budget")
        forecast = Forecast.model_validate_json(forecast.model_dump_json())
        if forecast.generated_at > dataset.inputs.captured_at:
            raise ValueError("forecast input generated after dataset capture")
        validated_forecasts.append(forecast)
        if (
            forecast.market_id != dataset.inputs.market.market_id
            or forecast.asset_id != dataset.inputs.asset.asset_id
            or forecast.model_version != config.strategy.model_version
            or forecast.feature_version != config.feature_version
        ):
            raise ValueError("forecast identity/version does not match research run")
    ordered = sorted(dataset.inputs.candles, key=lambda c: (c.received_at, c.open_time))
    arrivals = tuple(
        (instant, tuple(values))
        for instant, values in groupby(ordered, key=lambda c: c.received_at)
    )
    technical = _calculate(
        dataset.inputs.candles, dataset.inputs.query, FreshnessPolicy(), config.feature_specs
    )
    return PreparedInputs(
        arrivals, technical, tuple(sorted(validated_forecasts, key=lambda f: str(f.forecast_id)))
    )


def current_code_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(b"pocket-alpha-python-tree-v1")
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def current_environment_hash() -> str:
    from pocket_alpha.backtesting.models import digest

    return digest(
        dict(
            python=platform.python_version(),
            implementation=platform.python_implementation(),
            system=platform.system(),
            machine=platform.machine(),
            dependencies={
                name: version(name)
                for name in (
                    "pocket-alpha",
                    "fastapi",
                    "pydantic",
                    "sqlalchemy",
                    "alembic",
                    "psycopg",
                    "redis",
                )
            },
        )
    )
