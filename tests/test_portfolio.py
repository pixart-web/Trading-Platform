from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.domain.market import Candle, Market, Venue
from pocket_alpha.domain.models import Asset, AssetType, Timeframe
from pocket_alpha.main import create_app
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.providers import ProviderMapping
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.portfolio.models import (
    PortfolioEntry,
    PortfolioEntryType,
    PortfolioSnapshotStatus,
)
from pocket_alpha.portfolio.service import PortfolioEntryRequest, PortfolioService
from pocket_alpha.portfolio.storage import (
    ConflictingPortfolio,
    PortfolioRepository,
    StalePortfolioRevision,
)

D = Decimal
AS_OF = datetime(2025, 1, 10, 12, tzinfo=UTC)
CLOCK = FrozenClock(AS_OF + timedelta(days=2))
PORTFOLIO_ID = UUID(int=900)


def repository_for(repository: MarketRepository) -> PortfolioRepository:
    return PortfolioRepository(repository.session)


def create_portfolio(repository: MarketRepository) -> PortfolioRepository:
    portfolios = repository_for(repository)
    portfolios.create(PORTFOLIO_ID, "Principal", "EUR", AS_OF - timedelta(days=1))
    return portfolios


def entry_request(
    entry_id: int,
    entry_type: PortfolioEntryType,
    revision: int,
    *,
    cash_amount: str | None = None,
    market_id: str | None = None,
    quantity: str | None = None,
    unit_price: str | None = None,
    fee: str = "0",
    occurred_at: datetime = AS_OF,
) -> PortfolioEntryRequest:
    return PortfolioEntryRequest(
        entry_id=UUID(int=entry_id),
        entry_type=entry_type,
        expected_revision=revision,
        occurred_at=occurred_at,
        cash_amount=D(cash_amount) if cash_amount else None,
        market_id=market_id,
        quantity=D(quantity) if quantity else None,
        unit_price=D(unit_price) if unit_price else None,
        fee=D(fee),
    )


def deposit(service: PortfolioService, amount: str = "1000") -> PortfolioEntry:
    return service.record(
        PORTFOLIO_ID,
        entry_request(901, PortfolioEntryType.DEPOSIT, 1, cash_amount=amount),
    )


def put_price(repository: MarketRepository, *, received_at: datetime = AS_OF) -> None:
    repository.put(
        (
            Candle(
                market_id="test-market",
                timeframe=Timeframe.H1,
                open_time=AS_OF - timedelta(hours=1),
                close_time=AS_OF,
                open=D("110"),
                high=D("125"),
                low=D("100"),
                close=D("120"),
                volume=D("50"),
                source="fixture",
                received_at=received_at,
            ),
        )
    )


def register_usd_market(repository: MarketRepository) -> None:
    repository.register(
        Asset(
            asset_id="usd-asset",
            symbol="USDTEST",
            name="USD test asset",
            asset_type=AssetType.STOCK,
        ),
        Venue(venue_id="usd-venue", name="USD venue"),
        Market(
            market_id="usd-market",
            asset_id="usd-asset",
            venue_id="usd-venue",
            symbol="USDTEST",
            quote_currency="USD",
        ),
        ProviderMapping(source="fixture", market_id="usd-market", instrument_id="USD-TEST"),
    )


def client_for(repository: MarketRepository) -> TestClient:
    app = create_app()

    def dependency() -> Iterator[Session]:
        yield repository.session

    app.dependency_overrides[session_dependency] = dependency
    return TestClient(app)


def test_portfolio_creation_is_canonical_idempotent_and_conflict_checked(
    repository: MarketRepository,
) -> None:
    subject = repository_for(repository)
    created = subject.create(PORTFOLIO_ID, "  Principal  ", "eur", AS_OF)
    assert created.name == "Principal" and created.base_currency == "EUR"
    assert created.revision == 1 and subject.list() == (created,)
    assert subject.create(PORTFOLIO_ID, "Principal", "EUR", CLOCK.now()) == created
    with pytest.raises(ConflictingPortfolio):
        subject.create(PORTFOLIO_ID, "Outra", "EUR", AS_OF)


def test_deposit_buy_and_causal_valuation_use_exact_decimal_accounting(
    repository: MarketRepository,
) -> None:
    portfolios = create_portfolio(repository)
    service = PortfolioService(portfolios, CLOCK)
    deposit(service)
    buy = service.record(
        PORTFOLIO_ID,
        entry_request(
            902,
            PortfolioEntryType.BUY,
            2,
            market_id="test-market",
            quantity="2",
            unit_price="100",
            fee="10",
            occurred_at=AS_OF + timedelta(minutes=1),
        ),
    )
    assert buy.gross_value == D("200") and buy.cash_effect == D("-210")
    put_price(repository)
    snapshot = service.snapshot(PORTFOLIO_ID, CLOCK.now())
    assert snapshot.status == PortfolioSnapshotStatus.COMPLETE
    assert snapshot.cash_balance == D("790")
    assert snapshot.total_fees == D("10")
    assert snapshot.total_cost_basis == D("210")
    assert snapshot.total_market_value == D("240")
    assert snapshot.unrealized_pnl == D("30")
    assert snapshot.equity == D("1030")
    assert snapshot.positions[0].average_cost == D("105")
    assert snapshot.positions[0].price_time == AS_OF


def test_partial_sale_tracks_realized_and_unrealized_pnl(repository: MarketRepository) -> None:
    portfolios = create_portfolio(repository)
    service = PortfolioService(portfolios, CLOCK)
    deposit(service)
    service.record(
        PORTFOLIO_ID,
        entry_request(
            902,
            PortfolioEntryType.BUY,
            2,
            market_id="test-market",
            quantity="2",
            unit_price="100",
            occurred_at=AS_OF + timedelta(minutes=1),
        ),
    )
    service.record(
        PORTFOLIO_ID,
        entry_request(
            903,
            PortfolioEntryType.SELL,
            3,
            market_id="test-market",
            quantity="1",
            unit_price="130",
            fee="2",
            occurred_at=AS_OF + timedelta(minutes=2),
        ),
    )
    put_price(repository)
    snapshot = service.snapshot(PORTFOLIO_ID, CLOCK.now())
    assert snapshot.cash_balance == D("928") and snapshot.realized_pnl == D("28")
    assert snapshot.positions[0].quantity == D("1")
    assert snapshot.positions[0].unrealized_pnl == D("20")
    assert snapshot.equity == D("1048")


def test_accounting_rejects_unfunded_oversold_and_cross_currency_entries(
    repository: MarketRepository,
) -> None:
    portfolios = create_portfolio(repository)
    service = PortfolioService(portfolios, CLOCK)
    with pytest.raises(ValueError, match="cash"):
        service.record(
            PORTFOLIO_ID,
            entry_request(
                902,
                PortfolioEntryType.BUY,
                1,
                market_id="test-market",
                quantity="1",
                unit_price="100",
            ),
        )
    deposit(service)
    with pytest.raises(ValueError, match="exceeds"):
        service.record(
            PORTFOLIO_ID,
            entry_request(
                902,
                PortfolioEntryType.SELL,
                2,
                market_id="test-market",
                quantity="1",
                unit_price="100",
                occurred_at=AS_OF + timedelta(minutes=1),
            ),
        )
    register_usd_market(repository)
    with pytest.raises(ValueError, match="FX"):
        service.record(
            PORTFOLIO_ID,
            entry_request(
                903,
                PortfolioEntryType.BUY,
                2,
                market_id="usd-market",
                quantity="1",
                unit_price="10",
                occurred_at=AS_OF + timedelta(minutes=1),
            ),
        )
    assert portfolios.get(PORTFOLIO_ID).revision == 2


def test_missing_or_late_price_is_explicitly_partial(repository: MarketRepository) -> None:
    portfolios = create_portfolio(repository)
    service = PortfolioService(portfolios, CLOCK)
    deposit(service)
    service.record(
        PORTFOLIO_ID,
        entry_request(
            902,
            PortfolioEntryType.BUY,
            2,
            market_id="test-market",
            quantity="1",
            unit_price="100",
            occurred_at=AS_OF + timedelta(minutes=1),
        ),
    )
    put_price(repository, received_at=CLOCK.now() + timedelta(hours=1))
    snapshot = service.snapshot(PORTFOLIO_ID, CLOCK.now())
    assert snapshot.status == PortfolioSnapshotStatus.PARTIAL
    assert snapshot.positions[0].last_price is None
    assert snapshot.total_market_value is None
    assert snapshot.unrealized_pnl is None and snapshot.equity is None


def test_entries_are_idempotent_revisioned_and_temporally_ordered(
    repository: MarketRepository,
) -> None:
    portfolios = create_portfolio(repository)
    service = PortfolioService(portfolios, CLOCK)
    request = entry_request(901, PortfolioEntryType.DEPOSIT, 1, cash_amount="1000")
    original = service.record(PORTFOLIO_ID, request)
    assert service.record(PORTFOLIO_ID, request) == original
    assert portfolios.get(PORTFOLIO_ID).revision == 2
    with pytest.raises(ConflictingPortfolio):
        service.record(
            PORTFOLIO_ID,
            entry_request(901, PortfolioEntryType.DEPOSIT, 1, cash_amount="999"),
        )
    with pytest.raises(StalePortfolioRevision):
        service.record(
            PORTFOLIO_ID,
            entry_request(902, PortfolioEntryType.DEPOSIT, 1, cash_amount="1"),
        )
    with pytest.raises(ValueError, match="occurrence order"):
        service.record(
            PORTFOLIO_ID,
            entry_request(
                903,
                PortfolioEntryType.DEPOSIT,
                2,
                cash_amount="1",
                occurred_at=AS_OF - timedelta(seconds=1),
            ),
        )
    assert portfolios.entries(PORTFOLIO_ID) == (original,)


def test_portfolio_models_reject_incoherent_entries() -> None:
    with pytest.raises(ValidationError, match="cash entry"):
        PortfolioEntry(
            entry_id=UUID(int=999),
            portfolio_id=PORTFOLIO_ID,
            sequence=1,
            entry_type=PortfolioEntryType.DEPOSIT,
            currency="EUR",
            cash_amount=D("100"),
            market_id="test-market",
            fee=D(0),
            gross_value=D("100"),
            cash_effect=D("100"),
            occurred_at=AS_OF,
            recorded_at=AS_OF,
        )
    with pytest.raises(ValidationError):
        entry_request(999, PortfolioEntryType.WITHDRAWAL, 1, cash_amount="-1")


def test_portfolio_api_creates_records_and_values_an_empty_portfolio(
    repository: MarketRepository,
) -> None:
    client = client_for(repository)
    created = client.post(
        "/api/v1/portfolios",
        json={"portfolio_id": str(PORTFOLIO_ID), "name": "Principal", "base_currency": "EUR"},
    )
    assert created.status_code == 200 and created.json()["revision"] == 1
    occurred_at = created.json()["created_at"]
    recorded = client.post(
        f"/api/v1/portfolios/{PORTFOLIO_ID}/entries",
        json={
            "entry_id": str(UUID(int=901)),
            "entry_type": "DEPOSIT",
            "expected_revision": 1,
            "occurred_at": occurred_at,
            "cash_amount": "500",
        },
    )
    assert recorded.status_code == 200
    assert recorded.json()["portfolio"]["revision"] == 2
    assert recorded.json()["entry"]["cash_effect"] == "500.000000000000000000"
    entries = client.get(f"/api/v1/portfolios/{PORTFOLIO_ID}/entries")
    assert entries.status_code == 200 and len(entries.json()) == 1
    snapshot = client.get(
        f"/api/v1/portfolios/{PORTFOLIO_ID}/snapshot",
        params={"as_of": recorded.json()["entry"]["recorded_at"]},
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "COMPLETE"
    assert snapshot.json()["cash_balance"] == "500.000000000000000000"
    stale = client.post(
        f"/api/v1/portfolios/{PORTFOLIO_ID}/entries",
        json={
            "entry_id": str(UUID(int=902)),
            "entry_type": "WITHDRAWAL",
            "expected_revision": 1,
            "occurred_at": occurred_at,
            "cash_amount": "1",
        },
    )
    assert stale.status_code == 409
    assert client.get("/api/v1/portfolios").json()[0]["portfolio_id"] == str(PORTFOLIO_ID)
    assert client.get("/api/v1/portfolios/00000000-0000-0000-0000-000000000999").status_code == 404
