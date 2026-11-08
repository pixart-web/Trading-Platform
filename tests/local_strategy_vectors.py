"""Native research decision projections from the existing Python strategy, never market evidence."""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pocket_alpha.backtesting.models import StrategyView, digest
from pocket_alpha.domain.models import ForecastHorizon
from pocket_alpha.forecasts.horizons import expires_at
from pocket_alpha.intelligence.technical.models import FeatureStatus, IndicatorKind, IndicatorSpec
from pocket_alpha.strategies.engine import TrendStrategy
from pocket_alpha.strategies.models import PositionMemory, StrategyDefinition
from tests.strategy_fixtures import definition, evidence, view


def native_definition(value: StrategyDefinition) -> dict[str, Any]:
    p = value.parameters
    return dict(
        version=value.version,
        market=value.market_id,
        asset=value.asset_id,
        source=value.source,
        timeframe=value.timeframe.value,
        horizon=value.horizon.value,
        modelVersion=value.model_version,
        featureVersion=value.feature_version,
        fastPeriod=p.fast_period,
        slowPeriod=p.slow_period,
        minimumTrend=str(p.minimum_trend_fraction),
        minimumReturn=str(p.minimum_expected_return),
        invalidation=str(p.invalidation_fraction),
        maximumAge=value.maximum_data_age_seconds,
    )


def native_input(
    value: StrategyDefinition, current: StrategyView, memory: PositionMemory
) -> dict[str, Any]:
    def values(period: int) -> list[str | None]:
        return [
            next(
                (
                    str(f.value)
                    for f in result.features
                    if f.name == "sma" and f.status == FeatureStatus.READY
                ),
                None,
            )
            for result in current.technical.results
            if result.spec == IndicatorSpec(kind=IndicatorKind.SMA, period=period)
        ]

    t = current.technical
    return dict(
        asOf=current.as_of.isoformat(),
        history=[
            dict(
                market=c.market_id,
                source=c.source,
                timeframe=c.timeframe.value,
                close=str(c.close),
                closedAt=c.close_time.isoformat(),
                receivedAt=c.received_at.isoformat(),
            )
            for c in current.history
        ],
        technical=dict(
            market=t.market_id,
            source=t.source,
            timeframe=t.timeframe.value,
            featureVersion=t.engine_version,
            barClose=t.bar_close.isoformat(),
            availableAt=t.available_at.isoformat(),
            fastValues=values(value.parameters.fast_period),
            slowValues=values(value.parameters.slow_period),
        ),
        forecasts=[
            dict(
                id=str(f.forecast_id),
                market=f.market_id,
                asset=f.asset_id,
                timeframe=f.candle_timeframe.value,
                horizon=f.horizon.value,
                modelVersion=f.model_version,
                featureVersion=f.feature_version,
                status=f.status.value,
                generatedAt=f.generated_at.isoformat(),
                expiresAt=f.expires_at.isoformat(),
                expectedReturn=str(f.expected_return) if f.expected_return is not None else None,
            )
            for f in current.forecasts
        ],
        quantity=str(current.portfolio.quantity),
        memory=dict(
            observedQuantity=str(memory.observed_quantity),
            invalidationPrice=(
                str(memory.invalidation_price) if memory.invalidation_price is not None else None
            ),
            holdingUntil=memory.holding_until.isoformat() if memory.holding_until else None,
        ),
    )


def generate() -> str:
    cases: list[dict[str, Any]] = []
    for name in (
        "long",
        "missing",
        "flat",
        "short",
        "opposing-return",
        "opposing-trend",
        "holding",
        "price-stop",
        "holding-expiry",
        "stop-and-expiry",
        "trend-exit",
        "stale-stop",
        "warmup",
        "wrong-model",
        "wrong-horizon",
        "wrong-feature",
        "wrong-market",
        "ambiguous",
        "newest",
        "compatible-older",
        "stale",
        "fresh-boundary",
        "stale-subsecond",
        "wrong-source",
        "bar-mismatch",
        "rounded-return",
        "empty-history",
    ):
        d = definition()
        v = view()
        m = PositionMemory(definition_hash=digest(d))
        if name == "missing":
            v = view(with_forecast=False)
        elif name == "flat":
            v = view(("100",) * 4)
        elif name in {"short", "opposing-trend", "trend-exit"}:
            v = view(("106", "104", "102", "100"), quantity="2" if name == "trend-exit" else "0")
            if name != "opposing-trend":
                v = v.model_copy(update={"forecasts": (evidence(v.as_of, "-0.02"),)})
        elif name == "opposing-return":
            v = v.model_copy(update={"forecasts": (evidence(v.as_of, "-0.02"),)})
        elif name == "holding":
            v = view(quantity="2")
        elif name in {"price-stop", "holding-expiry", "stop-and-expiry", "stale-stop"}:
            v = view(quantity="2", with_forecast=False)
            m = m.model_copy(
                update={
                    "observed_quantity": Decimal(2),
                    "invalidation_price": Decimal(200 if name != "holding-expiry" else 90),
                    "holding_until": v.as_of
                    if name in {"holding-expiry", "stop-and-expiry"}
                    else None,
                }
            )
            if name == "stale-stop":
                v = v.model_copy(update={"as_of": v.as_of + timedelta(seconds=61)})
        elif name == "warmup":
            v = view(("100",))
        elif name in {"wrong-model", "wrong-feature", "wrong-market", "wrong-horizon"}:
            f = v.forecasts[0]
            field = {
                "wrong-model": "model_version",
                "wrong-feature": "feature_version",
                "wrong-market": "market_id",
            }.get(name)
            if field:
                f = f.model_copy(update={field: "other-identity"})
            else:
                f = f.model_copy(
                    update={
                        "horizon": ForecastHorizon.H1,
                        "expires_at": expires_at(f.generated_at, ForecastHorizon.H1),
                    }
                )
            v = v.model_copy(update={"forecasts": (f,)})
        elif name == "ambiguous":
            v = v.model_copy(
                update={
                    "forecasts": v.forecasts
                    + (v.forecasts[0].model_copy(update={"forecast_id": UUID(int=9999)}),)
                }
            )
        elif name in {"newest", "compatible-older"}:
            older = evidence(v.as_of - timedelta(seconds=1), "-0.02")
            latest = v.forecasts[0]
            if name == "compatible-older":
                latest = latest.model_copy(update={"model_version": "other-model"})
            v = v.model_copy(update={"forecasts": (older, latest)})
        elif name in {"stale", "fresh-boundary", "stale-subsecond"}:
            v = v.model_copy(
                update={
                    "as_of": v.as_of
                    + timedelta(
                        seconds=61 if name == "stale" else 60,
                        microseconds=1 if name == "stale-subsecond" else 0,
                    )
                }
            )
        elif name == "wrong-source":
            v = v.model_copy(
                update={"technical": v.technical.model_copy(update={"source": "other-source"})}
            )
        elif name == "bar-mismatch":
            v = v.model_copy(
                update={
                    "technical": v.technical.model_copy(
                        update={"bar_close": v.history[-2].close_time}
                    )
                }
            )
        elif name == "rounded-return":
            v = v.model_copy(
                update={"forecasts": (evidence(v.as_of, "0.0009999999999999999999995"),)}
            )
        elif name == "empty-history":
            v = v.model_copy(update={"history": ()})
        proposal = TrendStrategy(d).proposal(v, m)
        directional = proposal.directional
        metrics = directional.long_case.results if directional else ()
        # Values are taken from the original engine's retained criterion evidence, not recomputed.
        observed = {c.criterion: c.value for c in metrics}
        cases.append(
            dict(
                name=name,
                definition=native_definition(d),
                input=native_input(d, v, m),
                expected=dict(
                    action=proposal.action,
                    reason=proposal.reason,
                    referencePrice=str(proposal.reference_price)
                    if proposal.reference_price is not None
                    else None,
                    invalidationPrice=str(proposal.invalidation_price)
                    if proposal.invalidation_price is not None
                    else None,
                    expiresAt=proposal.expires_at.isoformat() if proposal.expires_at else None,
                    directional=directional.decision.value if directional else None,
                    trend=str(observed["sma-trend"]) if directional else None,
                    expectedReturn=str(observed["expected-return"]) if directional else None,
                    forecastId=str(proposal.forecast.forecast_id) if proposal.forecast else None,
                ),
            )
        )
    horizons = [
        dict(at=at, horizon=h.value, expected=expires_at(datetime.fromisoformat(at), h).isoformat())
        for at in ("2024-08-31T23:59:59.123456+00:00", "2024-02-29T00:00:00+00:00")
        for h in ForecastHorizon
    ]
    return (
        json.dumps(
            dict(
                schema="native-trend-review-oracle-1",
                origin="SYNTHETIC_ENGINEERING_FIXTURE",
                cases=cases,
                horizons=horizons,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    rendered = generate()
    for path in (
        Path("android/app/src/test/resources/local-strategy-golden.json"),
        Path("android/app/src/androidTest/assets/local-strategy-golden.json"),
    ):
        if "--check" in sys.argv:
            if path.read_text() != rendered:
                raise SystemExit(f"Stale strategy oracle: {path}")
        else:
            path.write_text(rendered)
