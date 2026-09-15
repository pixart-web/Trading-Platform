from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.portfolio.models import PortfolioEntryType
from pocket_alpha.portfolio.service import PortfolioEntryRequest, PortfolioService
from pocket_alpha.portfolio.storage import PortfolioRepository
from pocket_alpha.portfolio_intelligence.models import (
    AllocationDimension,
    IntelligenceStatus,
    MetricStatus,
    PortfolioIntelligencePolicy,
    UnavailableReason,
)
from pocket_alpha.portfolio_intelligence.service import PortfolioIntelligenceService
from pocket_alpha.portfolio_intelligence.storage import (
    ConflictingPortfolioIntelligence,
    PortfolioIntelligenceRepository,
)

D = Decimal
AS_OF = datetime(2025, 1, 10, 12, tzinfo=UTC)
CLOCK = FrozenClock(AS_OF)
PORTFOLIO_ID = UUID(int=1700)
ANALYSIS_ID = UUID(int=1701)


def register_second_market(repository: MarketRepository) -> None:
    repository.register(
        Asset(
            asset_id="second-asset",
            symbol="SECOND",
            name="Second synthetic asset",
            asset_type=AssetType.ETF,
        ),
        Venue(venue_id="second-venue", name="Second synthetic venue"),
        Market(
            market_id="second-market",
            asset_id="second-asset",
            venue_id="second-venue",
            symbol="SECOND",
            quote_currency="EUR",
        ),
        ProviderMapping(source="fixture", market_id="second-market", instrument_id="SECOND"),
    )


def candles(
    market_id: str,
    closes: tuple[str, ...],
    *,
    received_lag: timedelta = timedelta(0),
) -> tuple[Candle, ...]:
    start = AS_OF - timedelta(hours=len(closes))
    values = tuple(D(value) for value in closes)
    return tuple(
        Candle(
            market_id=market_id,
            timeframe=Timeframe.H1,
            open_time=start + timedelta(hours=index),
            close_time=start + timedelta(hours=index + 1),
            open=value,
            high=value + D("1"),
            low=value - D("1"),
            close=value,
            volume=D("100"),
            source="fixture",
            received_at=start + timedelta(hours=index + 1) + received_lag,
        )
        for index, value in enumerate(values)
    )


def request(
    entry_id: int,
    entry_type: PortfolioEntryType,
    revision: int,
    *,
    cash: str | None = None,
    market_id: str | None = None,
    quantity: str | None = None,
    price: str | None = None,
    occurred_at: datetime,
) -> PortfolioEntryRequest:
    return PortfolioEntryRequest(
        entry_id=UUID(int=entry_id),
        entry_type=entry_type,
        expected_revision=revision,
        occurred_at=occurred_at,
        cash_amount=D(cash) if cash else None,
        market_id=market_id,
        quantity=D(quantity) if quantity else None,
        unit_price=D(price) if price else None,
    )


def funded_portfolio(
    repository: MarketRepository, *, two_markets: bool = True
) -> PortfolioRepository:
    if two_markets:
        register_second_market(repository)
    portfolios = PortfolioRepository(repository.session)
    portfolios.create(PORTFOLIO_ID, "Principal", "EUR", AS_OF - timedelta(days=2))
    accounting = PortfolioService(portfolios, CLOCK)
    accounting.record(
        PORTFOLIO_ID,
        request(
            1710,
            PortfolioEntryType.DEPOSIT,
            1,
            cash="10000",
            occurred_at=AS_OF - timedelta(days=1),
        ),
    )
    accounting.record(
        PORTFOLIO_ID,
        request(
            1711,
            PortfolioEntryType.BUY,
            2,
            market_id="test-market",
            quantity="10",
            price="100",
            occurred_at=AS_OF - timedelta(hours=23),
        ),
    )
    if two_markets:
        accounting.record(
            PORTFOLIO_ID,
            request(
                1712,
                PortfolioEntryType.BUY,
                3,
                market_id="second-market",
                quantity="20",
                price="50",
                occurred_at=AS_OF - timedelta(hours=22),
            ),
        )
    return portfolios


def intelligence(
    repository: MarketRepository, portfolios: PortfolioRepository
) -> PortfolioIntelligenceService:
    return PortfolioIntelligenceService(
        portfolios, PortfolioIntelligenceRepository(repository.session), CLOCK
    )


def client_for(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def test_analysis_computes_explained_allocation_correlation_and_risk(
    repository: MarketRepository,
) -> None:
    portfolios = funded_portfolio(repository)
    repository.put(candles("test-market", tuple(str(100 + index) for index in range(25))))
    repository.put(candles("second-market", tuple(str(50 + index * 2) for index in range(25))))
    report = intelligence(repository, portfolios).create(
        ANALYSIS_ID,
        PORTFOLIO_ID,
        AS_OF,
        PortfolioIntelligencePolicy(lookback_bars=24, minimum_observations=10),
        "test-market",
    )
    assert report.status == IntelligenceStatus.PARTIAL
    assert report.portfolio_per_bar_volatility.status == MetricStatus.AVAILABLE
    assert report.portfolio_beta.status == MetricStatus.AVAILABLE
    assert len(report.correlations) == 1
    assert report.correlations[0].correlation.status == MetricStatus.AVAILABLE
    assert len(report.risk_contributions) == 2
    total_contribution = sum(
        (item.contribution_fraction.value or D(0) for item in report.risk_contributions), D(0)
    )
    assert abs(total_contribution - D(1)) < D("0.000000000000001")
    market_allocations = [
        item for item in report.allocations if item.dimension == AllocationDimension.MARKET
    ]
    assert len(market_allocations) == 2
    assert report.sector_concentration.reason == UnavailableReason.SECTOR_DATA_UNAVAILABLE
    assert report.drawdown.reason == UnavailableReason.NAV_HISTORY_UNAVAILABLE
    assert report.liquidity.reason == UnavailableReason.LIQUIDITY_DATA_UNAVAILABLE
    assert report.policy_hash != report.input_hash
    assert {item.code for item in report.observations} >= {
        "ACCOUNTING_CONTEXT",
        "DIVERSIFICATION_CONTEXT",
    }


def test_analysis_is_idempotent_and_rejects_conflicting_identity(
    repository: MarketRepository,
) -> None:
    portfolios = funded_portfolio(repository, two_markets=False)
    repository.put(candles("test-market", tuple(str(100 + index) for index in range(25))))
    service = intelligence(repository, portfolios)
    policy = PortfolioIntelligencePolicy(lookback_bars=24, minimum_observations=10)
    first = service.create(ANALYSIS_ID, PORTFOLIO_ID, AS_OF, policy)
    assert service.create(ANALYSIS_ID, PORTFOLIO_ID, AS_OF, policy) == first
    with pytest.raises(ConflictingPortfolioIntelligence):
        service.create(
            ANALYSIS_ID,
            PORTFOLIO_ID,
            AS_OF - timedelta(hours=1),
            policy,
        )


def test_late_received_candle_cannot_change_historical_inputs(
    repository: MarketRepository,
) -> None:
    portfolios = funded_portfolio(repository, two_markets=False)
    base = candles("test-market", tuple(str(100 + index) for index in range(24)))[:-1]
    repository.put(base)
    service = intelligence(repository, portfolios)
    policy = PortfolioIntelligencePolicy(lookback_bars=24, minimum_observations=10)
    first = service.create(ANALYSIS_ID, PORTFOLIO_ID, AS_OF, policy)
    repository.put(
        candles(
            "test-market",
            ("999",),
            received_lag=timedelta(hours=2),
        )
    )
    second = service.create(UUID(int=1702), PORTFOLIO_ID, AS_OF, policy)
    assert second.input_hash == first.input_hash
    assert second.portfolio_input_hash == first.portfolio_input_hash


def test_insufficient_history_and_absent_benchmark_are_explicit(
    repository: MarketRepository,
) -> None:
    portfolios = funded_portfolio(repository, two_markets=False)
    repository.put(candles("test-market", ("100", "101", "102")))
    report = intelligence(repository, portfolios).create(
        ANALYSIS_ID,
        PORTFOLIO_ID,
        AS_OF,
        PortfolioIntelligencePolicy(lookback_bars=20, minimum_observations=10),
    )
    assert report.market_risk[0].per_bar_volatility.reason == UnavailableReason.INSUFFICIENT_HISTORY
    assert report.market_risk[0].beta.reason == UnavailableReason.BENCHMARK_NOT_CONFIGURED
    assert report.portfolio_per_bar_volatility.reason == UnavailableReason.INSUFFICIENT_HISTORY
    assert report.risk_contributions == ()


def test_portfolio_intelligence_api_persists_and_lists_reports(
    repository: MarketRepository,
) -> None:
    funded_portfolio(repository, two_markets=False)
    repository.put(candles("test-market", tuple(str(100 + index) for index in range(25))))
    client = client_for(repository)
    response = client.post(
        f"/api/v1/portfolios/{PORTFOLIO_ID}/intelligence",
        json={
            "analysis_id": str(ANALYSIS_ID),
            "as_of": AS_OF.isoformat(),
            "benchmark_market_id": "test-market",
            "policy": {
                "lookback_bars": 24,
                "minimum_observations": 10,
                "maximum_price_age_bars": 3,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["analysis_id"] == str(ANALYSIS_ID)
    listed = client.get(f"/api/v1/portfolios/{PORTFOLIO_ID}/intelligence")
    assert listed.status_code == 200 and len(listed.json()) == 1
    fetched = client.get(f"/api/v1/portfolio-intelligence/{ANALYSIS_ID}")
    assert fetched.status_code == 200 and fetched.json() == response.json()
    assert client.get(f"/api/v1/portfolio-intelligence/{UUID(int=1799)}").status_code == 404


def test_stale_valuation_suppresses_current_weight_metrics(
    repository: MarketRepository,
) -> None:
    portfolios = funded_portfolio(repository, two_markets=False)
    old = candles("test-market", tuple(str(100 + index) for index in range(25)))[:20]
    repository.put(old)
    report = intelligence(repository, portfolios).create(
        ANALYSIS_ID,
        PORTFOLIO_ID,
        AS_OF,
        PortfolioIntelligencePolicy(
            lookback_bars=24,
            minimum_observations=10,
            maximum_price_age_bars=3,
        ),
    )
    assert report.allocations == ()
    assert report.portfolio_per_bar_volatility.reason == UnavailableReason.STALE_VALUATION
    assert report.risk_contributions == ()
    assert "STALE_VALUATION" in {item.code for item in report.observations}
