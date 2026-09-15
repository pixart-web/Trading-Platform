from collections import defaultdict
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.domain.market import Identifier
from pocket_alpha.intelligence.provenance import canonical
from pocket_alpha.portfolio.models import PortfolioPosition, PortfolioSnapshot
from pocket_alpha.portfolio.service import PortfolioService, fingerprint
from pocket_alpha.portfolio.storage import PortfolioRepository
from pocket_alpha.portfolio_intelligence.models import (
    AllocationBucket,
    AllocationDimension,
    Concentration,
    Correlation,
    IntelligenceStatus,
    MarketRisk,
    Metric,
    MetricStatus,
    ObservationSeverity,
    PortfolioIntelligencePolicy,
    PortfolioIntelligenceReport,
    PortfolioObservation,
    RiskContribution,
    UnavailableReason,
)
from pocket_alpha.portfolio_intelligence.storage import (
    ClosePoint,
    ConflictingPortfolioIntelligence,
    PortfolioIntelligenceRepository,
)

D = Decimal
Q = D("0.000000000000000001")


def published(value: Decimal) -> Decimal:
    return value.quantize(Q, rounding=ROUND_HALF_EVEN)


def available(value: Decimal, explanation: str) -> Metric:
    return Metric(status=MetricStatus.AVAILABLE, value=published(value), explanation=explanation)


def unavailable(reason: UnavailableReason, explanation: str) -> Metric:
    return Metric(status=MetricStatus.UNAVAILABLE, reason=reason, explanation=explanation)


def mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, D(0)) / D(len(values))


def covariance(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("covariance requires aligned observations")
    left_mean, right_mean = mean(left), mean(right)
    return sum(
        ((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)),
        D(0),
    ) / D(len(left) - 1)


def variance(values: tuple[Decimal, ...]) -> Decimal:
    return covariance(values, values)


def returns(points: tuple[ClosePoint, ...]) -> dict[datetime, Decimal]:
    result: dict[datetime, Decimal] = {}
    for previous, current in zip(points, points[1:], strict=False):
        if previous.close > 0:
            result[current.close_time] = current.close / previous.close - D(1)
    return result


def aligned(
    left: dict[datetime, Decimal], right: dict[datetime, Decimal]
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    keys = tuple(sorted(set(left) & set(right)))
    return tuple(left[key] for key in keys), tuple(right[key] for key in keys)


class PortfolioIntelligenceService:
    def __init__(
        self,
        portfolios: PortfolioRepository,
        reports: PortfolioIntelligenceRepository,
        clock: Clock,
    ) -> None:
        self.portfolios = portfolios
        self.reports = reports
        self.clock = clock

    def create(
        self,
        analysis_id: UUID,
        portfolio_id: UUID,
        as_of: datetime,
        policy: PortfolioIntelligencePolicy,
        benchmark_market_id: Identifier | None = None,
    ) -> PortfolioIntelligenceReport:
        cutoff = utc(as_of)
        existing = self.reports.find(analysis_id)
        if existing is not None:
            if (
                existing.portfolio_id != portfolio_id
                or existing.as_of != cutoff
                or existing.policy != policy
                or existing.benchmark_market_id != benchmark_market_id
            ):
                raise ConflictingPortfolioIntelligence(
                    "portfolio intelligence identity conflicts with requested analysis"
                )
            return existing
        if benchmark_market_id is not None and not self.reports.market_exists(benchmark_market_id):
            raise LookupError("benchmark market not found")

        snapshot = PortfolioService(self.portfolios, self.clock).snapshot(portfolio_id, cutoff)
        open_positions = tuple(position for position in snapshot.positions if position.quantity > 0)
        market_ids = tuple(position.market.market_id for position in open_positions)
        benchmark_ids = (benchmark_market_id,) if benchmark_market_id else ()
        series_ids = tuple(sorted(set(market_ids + benchmark_ids)))
        closes = self.reports.closes(
            series_ids, snapshot.valuation_timeframe, cutoff, policy.lookback_bars + 1
        )
        return_series = {market_id: returns(closes[market_id]) for market_id in series_ids}

        stale = tuple(
            position.market.market_id
            for position in open_positions
            if position.price_available_at is not None
            and cutoff - position.price_available_at
            > snapshot.valuation_timeframe.duration * policy.maximum_price_age_bars
        )
        allocations = self._allocations(snapshot)
        concentrations = self._concentrations(open_positions)
        market_risk = self._market_risk(
            market_ids, return_series, benchmark_market_id, policy.minimum_observations
        )
        correlations = self._correlations(market_ids, return_series, policy.minimum_observations)
        portfolio_volatility, portfolio_beta, contributions = self._portfolio_risk(
            snapshot,
            market_ids,
            return_series,
            benchmark_market_id,
            policy.minimum_observations,
        )

        if stale:
            allocations = ()
            stale_metric = unavailable(
                UnavailableReason.STALE_VALUATION,
                "Current-weight metrics require valuation prices within the policy age limit.",
            )
            concentrations = tuple(
                Concentration(
                    dimension=item.dimension,
                    hhi=stale_metric,
                    largest_weight=stale_metric,
                    effective_count=stale_metric,
                )
                for item in concentrations
            )
            portfolio_volatility = stale_metric
            portfolio_beta = stale_metric
            contributions = ()
        observations = self._observations(snapshot, concentrations, stale, portfolio_volatility)
        sector = unavailable(
            UnavailableReason.SECTOR_DATA_UNAVAILABLE,
            "No versioned sector taxonomy exists for registered assets.",
        )
        drawdown = unavailable(
            UnavailableReason.NAV_HISTORY_UNAVAILABLE,
            "Drawdown requires a causal portfolio NAV history, which is not stored yet.",
        )
        liquidity = unavailable(
            UnavailableReason.LIQUIDITY_DATA_UNAVAILABLE,
            "Stored candles do not provide authoritative executable liquidity or capacity.",
        )
        regime = unavailable(
            UnavailableReason.REGIME_ATTRIBUTION_UNAVAILABLE,
            "Positions do not carry an immutable regime attribution.",
        )
        horizon = unavailable(
            UnavailableReason.HORIZON_ATTRIBUTION_UNAVAILABLE,
            "Manual positions do not carry an immutable forecast-horizon attribution.",
        )
        policy_hash = fingerprint(policy.model_dump())
        payload = {
            "portfolio_snapshot": snapshot.model_dump(),
            "policy": policy.model_dump(),
            "benchmark_market_id": benchmark_market_id,
            "closes": {
                key: [
                    {
                        "close_time": point.close_time,
                        "received_at": point.received_at,
                        "close": point.close,
                    }
                    for point in value
                ]
                for key, value in sorted(closes.items())
            },
        }
        report = PortfolioIntelligenceReport(
            analysis_id=analysis_id,
            portfolio_id=portfolio_id,
            portfolio_revision=snapshot.portfolio_revision,
            ledger_sequence=snapshot.ledger_sequence,
            timeframe=snapshot.valuation_timeframe,
            benchmark_market_id=benchmark_market_id,
            as_of=cutoff,
            generated_at=utc(self.clock.now()),
            status=IntelligenceStatus.PARTIAL,
            policy=policy,
            policy_hash=policy_hash,
            portfolio_input_hash=snapshot.input_hash,
            equity=snapshot.equity,
            allocations=allocations,
            concentrations=concentrations,
            market_risk=market_risk,
            correlations=correlations,
            portfolio_per_bar_volatility=portfolio_volatility,
            portfolio_beta=portfolio_beta,
            risk_contributions=contributions,
            sector_concentration=sector,
            drawdown=drawdown,
            liquidity=liquidity,
            regime_exposure=regime,
            horizon_exposure=horizon,
            observations=observations,
            input_hash=fingerprint(canonical(payload)),
        )
        self.reports.put(report)
        return report

    def _allocations(self, snapshot: PortfolioSnapshot) -> tuple[AllocationBucket, ...]:
        if snapshot.equity is None or snapshot.equity <= 0:
            return ()
        grouped: dict[tuple[AllocationDimension, str], Decimal] = defaultdict(Decimal)
        grouped[(AllocationDimension.CASH, snapshot.base_currency)] += snapshot.cash_balance
        grouped[(AllocationDimension.CURRENCY, snapshot.base_currency)] += snapshot.cash_balance
        for position in snapshot.positions:
            if position.market_value is None or position.quantity <= 0:
                continue
            value = position.market_value
            grouped[(AllocationDimension.MARKET, position.market.market_id)] += value
            grouped[(AllocationDimension.ASSET_CLASS, position.market.asset_type.value)] += value
            grouped[(AllocationDimension.CURRENCY, position.market.quote_currency)] += value
            grouped[(AllocationDimension.VENUE, position.market.venue_id)] += value
            grouped[(AllocationDimension.DIRECTION, "LONG")] += value
        return tuple(
            AllocationBucket(
                dimension=dimension,
                key=key,
                value=published(value),
                portfolio_weight=published(value / snapshot.equity),
            )
            for (dimension, key), value in sorted(
                grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
            )
        )

    def _concentrations(
        self, positions: tuple[PortfolioPosition, ...]
    ) -> tuple[Concentration, ...]:
        values = tuple(position.market_value for position in positions)
        dimensions = (
            AllocationDimension.MARKET,
            AllocationDimension.ASSET_CLASS,
            AllocationDimension.CURRENCY,
            AllocationDimension.VENUE,
        )
        if not positions or any(value is None for value in values):
            reason = (
                UnavailableReason.NO_OPEN_POSITIONS
                if not positions
                else UnavailableReason.PORTFOLIO_VALUATION_INCOMPLETE
            )
            return tuple(
                Concentration(
                    dimension=dimension,
                    hhi=unavailable(reason, "Concentration requires valued open positions."),
                    largest_weight=unavailable(
                        reason, "Concentration requires valued open positions."
                    ),
                    effective_count=unavailable(
                        reason, "Concentration requires valued open positions."
                    ),
                )
                for dimension in dimensions
            )
        groups: dict[AllocationDimension, dict[str, Decimal]] = {
            dimension: defaultdict(Decimal) for dimension in dimensions
        }
        for position in positions:
            assert position.market_value is not None
            groups[AllocationDimension.MARKET][position.market.market_id] += position.market_value
            groups[AllocationDimension.ASSET_CLASS][position.market.asset_type.value] += (
                position.market_value
            )
            groups[AllocationDimension.CURRENCY][position.market.quote_currency] += (
                position.market_value
            )
            groups[AllocationDimension.VENUE][position.market.venue_id] += position.market_value
        result = []
        for dimension, buckets in groups.items():
            total = sum(buckets.values(), D(0))
            weights = tuple(value / total for value in buckets.values())
            hhi = sum((weight * weight for weight in weights), D(0))
            result.append(
                Concentration(
                    dimension=dimension,
                    hhi=available(hhi, "Herfindahl index over the valued invested sleeve."),
                    largest_weight=available(
                        max(weights), "Largest invested-sleeve bucket weight."
                    ),
                    effective_count=available(
                        D(1) / hhi, "Inverse HHI; this is not a raw asset count."
                    ),
                )
            )
        return tuple(result)

    def _market_risk(
        self,
        market_ids: tuple[str, ...],
        series: dict[str, dict[datetime, Decimal]],
        benchmark: str | None,
        minimum: int,
    ) -> tuple[MarketRisk, ...]:
        result = []
        for market_id in market_ids:
            values = tuple(series[market_id].values())
            volatility = self._volatility(values, minimum)
            beta = unavailable(
                UnavailableReason.BENCHMARK_NOT_CONFIGURED,
                "Beta requires an explicit benchmark market.",
            )
            if benchmark is not None:
                left, right = aligned(series[market_id], series[benchmark])
                beta = self._beta(left, right, minimum)
            result.append(
                MarketRisk(
                    market_id=market_id,
                    observations=len(values),
                    per_bar_volatility=volatility,
                    beta=beta,
                )
            )
        return tuple(result)

    def _correlations(
        self,
        market_ids: tuple[str, ...],
        series: dict[str, dict[datetime, Decimal]],
        minimum: int,
    ) -> tuple[Correlation, ...]:
        result = []
        for index, left_id in enumerate(market_ids):
            for right_id in market_ids[index + 1 :]:
                left, right = aligned(series[left_id], series[right_id])
                metric = unavailable(
                    UnavailableReason.INSUFFICIENT_HISTORY,
                    f"Correlation requires at least {minimum} aligned returns.",
                )
                if len(left) >= minimum:
                    left_variance, right_variance = variance(left), variance(right)
                    if left_variance > 0 and right_variance > 0:
                        value = covariance(left, right) / (
                            left_variance.sqrt() * right_variance.sqrt()
                        )
                        metric = available(
                            max(D(-1), min(D(1), value)),
                            "Sample correlation over causal aligned close-to-close returns.",
                        )
                    else:
                        metric = unavailable(
                            UnavailableReason.ZERO_VARIANCE,
                            "Correlation is undefined when either return series has zero variance.",
                        )
                result.append(
                    Correlation(
                        left_market_id=left_id,
                        right_market_id=right_id,
                        observations=len(left),
                        correlation=metric,
                    )
                )
        return tuple(result)

    def _portfolio_risk(
        self,
        snapshot: PortfolioSnapshot,
        market_ids: tuple[str, ...],
        series: dict[str, dict[datetime, Decimal]],
        benchmark: str | None,
        minimum: int,
    ) -> tuple[Metric, Metric, tuple[RiskContribution, ...]]:
        no_benchmark = unavailable(
            UnavailableReason.BENCHMARK_NOT_CONFIGURED,
            "Portfolio beta requires an explicit benchmark market.",
        )
        if snapshot.equity is None or snapshot.equity <= 0 or not market_ids:
            reason = (
                UnavailableReason.PORTFOLIO_VALUATION_INCOMPLETE
                if snapshot.equity is None
                else UnavailableReason.NO_OPEN_POSITIONS
            )
            metric = unavailable(reason, "Portfolio market risk requires valued open positions.")
            return metric, no_benchmark if benchmark is None else metric, ()
        timestamps = set(series[market_ids[0]])
        for market_id in market_ids[1:]:
            timestamps &= set(series[market_id])
        keys = tuple(sorted(timestamps))
        if len(keys) < minimum:
            no_history = unavailable(
                UnavailableReason.INSUFFICIENT_HISTORY,
                f"Portfolio risk requires at least {minimum} aligned returns.",
            )
            return no_history, no_benchmark if benchmark is None else no_history, ()
        values_by_id = {
            market_id: tuple(series[market_id][key] for key in keys) for market_id in market_ids
        }
        weights = {
            position.market.market_id: position.market_value / snapshot.equity
            for position in snapshot.positions
            if position.market.market_id in market_ids and position.market_value is not None
        }
        portfolio_returns = tuple(
            sum(
                (weights[market_id] * values_by_id[market_id][index] for market_id in market_ids),
                D(0),
            )
            for index in range(len(keys))
        )
        portfolio_variance = variance(portfolio_returns)
        if portfolio_variance <= 0:
            zero = unavailable(
                UnavailableReason.ZERO_VARIANCE,
                "Portfolio return variance is zero over the aligned window.",
            )
            return zero, zero if benchmark is not None else no_benchmark, ()
        volatility = available(
            portfolio_variance.sqrt(),
            "Sample per-bar volatility of current portfolio weights over aligned returns.",
        )
        beta = no_benchmark
        if benchmark is not None:
            benchmark_values = tuple(
                series[benchmark][key] for key in keys if key in series[benchmark]
            )
            portfolio_for_beta = tuple(
                portfolio_returns[index]
                for index, key in enumerate(keys)
                if key in series[benchmark]
            )
            beta = self._beta(portfolio_for_beta, benchmark_values, minimum)
        contributions = tuple(
            RiskContribution(
                market_id=market_id,
                contribution_fraction=available(
                    weights[market_id]
                    * covariance(values_by_id[market_id], portfolio_returns)
                    / portfolio_variance,
                    "Euler contribution to current-weight variance; it may be negative.",
                ),
            )
            for market_id in market_ids
        )
        return volatility, beta, contributions

    def _volatility(self, values: tuple[Decimal, ...], minimum: int) -> Metric:
        if len(values) < minimum:
            return unavailable(
                UnavailableReason.INSUFFICIENT_HISTORY,
                f"Volatility requires at least {minimum} causal returns.",
            )
        return available(
            variance(values).sqrt(),
            "Sample per-bar volatility of causal close-to-close returns; not annualized.",
        )

    def _beta(
        self, values: tuple[Decimal, ...], benchmark: tuple[Decimal, ...], minimum: int
    ) -> Metric:
        if len(values) < minimum:
            return unavailable(
                UnavailableReason.INSUFFICIENT_HISTORY,
                f"Beta requires at least {minimum} aligned benchmark returns.",
            )
        benchmark_variance = variance(benchmark)
        if benchmark_variance <= 0:
            return unavailable(
                UnavailableReason.ZERO_VARIANCE,
                "Beta is undefined when benchmark variance is zero.",
            )
        return available(
            covariance(values, benchmark) / benchmark_variance,
            "Sample beta over causal aligned close-to-close returns.",
        )

    def _observations(
        self,
        snapshot: PortfolioSnapshot,
        concentrations: tuple[Concentration, ...],
        stale: tuple[str, ...],
        portfolio_volatility: Metric,
    ) -> tuple[PortfolioObservation, ...]:
        result = [
            PortfolioObservation(
                code="ACCOUNTING_CONTEXT",
                severity=ObservationSeverity.INFO,
                message="Realized and unrealized P&L are accounting context, not a forecast.",
                evidence=(
                    f"realized_pnl={snapshot.realized_pnl}",
                    f"unrealized_pnl={snapshot.unrealized_pnl}",
                ),
            )
        ]
        market = next(
            (item for item in concentrations if item.dimension == AllocationDimension.MARKET), None
        )
        if market is not None and market.hhi.value is not None:
            result.append(
                PortfolioObservation(
                    code="DIVERSIFICATION_CONTEXT",
                    severity=ObservationSeverity.INFO,
                    message="Diversification uses invested-value concentration and inverse HHI.",
                    evidence=(
                        f"hhi={market.hhi.value}",
                        f"effective_count={market.effective_count.value}",
                    ),
                )
            )
        if stale:
            result.append(
                PortfolioObservation(
                    code="STALE_VALUATION",
                    severity=ObservationSeverity.WARNING,
                    message="At least one valuation price exceeds the configured age limit.",
                    evidence=stale,
                )
            )
        if portfolio_volatility.status == MetricStatus.UNAVAILABLE:
            result.append(
                PortfolioObservation(
                    code="RISK_HISTORY_UNAVAILABLE",
                    severity=ObservationSeverity.WARNING,
                    message=(
                        "Portfolio volatility and risk contribution need aligned causal history."
                    ),
                    evidence=(f"reason={portfolio_volatility.reason}",),
                )
            )
        return tuple(result)
