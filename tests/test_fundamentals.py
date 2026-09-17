import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.fundamentals.context import financial_context
from pocket_alpha.fundamentals.models import (
    FundamentalFact,
    FundamentalMapping,
    FundamentalMetric,
    FundamentalSnapshot,
)
from pocket_alpha.fundamentals.providers import (
    MAX_RESPONSE_BYTES,
    FundamentalProviderError,
    HttpResponse,
    SecCompanyFactsProvider,
)
from pocket_alpha.fundamentals.service import FundamentalService
from pocket_alpha.fundamentals.storage import ConflictingFundamental, FundamentalRepository
from pocket_alpha.market_data.storage import MarketRepository


class Transport:
    def __init__(self, responses: list[HttpResponse | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url: str, headers: object, timeout: float) -> HttpResponse:
        assert url == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000042.json"
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def payload(value: str = "123.123456789012345678") -> bytes:
    return (
        '{"cik":42,"facts":{"us-gaap":{"EarningsPerShareDiluted":{"units":{"USD/shares":['
        '{"val":' + value + ',"start":"2024-01-01","end":"2024-12-31",'
        '"filed":"2025-02-01","form":"10-K","accn":"00042-25-01","fy":2024,"fp":"FY"}'
        "]}}}}}"
    ).encode()


def provider(transport: Transport) -> SecCompanyFactsProvider:
    return SecCompanyFactsProvider(
        "Pocket Alpha test@example.invalid",
        transport=transport,
        sleep=lambda _: None,
        monotonic=lambda: 1.0,
    )


def test_sec_preserves_decimal_and_currency_per_share() -> None:
    result = provider(Transport([HttpResponse(200, payload(), {})])).facts("42")
    assert result.next_cursor is None
    assert result.records[0].value == Decimal("123.123456789012345678")
    assert result.records[0].currency == "USD"
    assert result.records[0].published_at == datetime(2025, 2, 1, tzinfo=UTC)


def test_sec_retries_transport_and_rate_limit_without_fallback() -> None:
    transport = Transport(
        [
            FundamentalProviderError("offline"),
            HttpResponse(429, b"", {"retry-after": "invalid"}),
            HttpResponse(200, payload(), {}),
        ]
    )
    assert len(provider(transport).facts("42").records) == 1
    assert transport.calls == 3


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(403, b"", {}),
        HttpResponse(200, b"broken", {}),
        HttpResponse(200, b"x" * (MAX_RESPONSE_BYTES + 1), {}),
        HttpResponse(429, b"", {"retry-after": "120"}),
        HttpResponse(429, b"", {"retry-after": "-1"}),
    ],
)
def test_sec_failure_is_explicit(response: HttpResponse) -> None:
    with pytest.raises(FundamentalProviderError):
        provider(Transport([response])).facts("42")


def test_sec_rejects_invalid_financial_value() -> None:
    body = json.loads(payload())
    body["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"][0]["val"] = "invalid"
    with pytest.raises(FundamentalProviderError):
        provider(Transport([HttpResponse(200, json.dumps(body).encode(), {})])).facts("42")


def test_sec_exhaustion_and_invalid_identity() -> None:
    transport = Transport([HttpResponse(503, b"", {}) for _ in range(3)])
    with pytest.raises(FundamentalProviderError):
        provider(transport).facts("42")
    assert transport.calls == 3
    with pytest.raises(ValueError):
        provider(Transport([])).facts("../42")
    with pytest.raises(FundamentalProviderError):
        provider(Transport([])).facts("42", cursor="page")


def test_fundamental_rejects_availability_before_publication() -> None:
    from uuid import UUID

    with pytest.raises(ValidationError):
        FundamentalFact(
            fact_id=UUID(int=1),
            asset_id="stock:42",
            metric=FundamentalMetric.REVENUE,
            value=Decimal("1"),
            currency="USD",
            unit="USD",
            period_end=datetime(2024, 12, 31).date(),
            form="10-K",
            source="sec-companyfacts",
            source_concept="revenue",
            source_record_id="record",
            revision=1,
            published_at=datetime(2025, 2, 1, tzinfo=UTC),
            available_at=datetime(2025, 1, 1, tzinfo=UTC),
            ingested_at=datetime(2025, 3, 1, tzinfo=UTC),
        )


def test_restatement_preserves_point_in_time(repository: "MarketRepository") -> None:
    first_time = datetime(2025, 3, 1, tzinfo=UTC)
    second_time = datetime(2025, 4, 1, tzinfo=UTC)
    repo = FundamentalRepository(repository.session)
    mapping = FundamentalMapping(
        source="sec-companyfacts",
        asset_id="test-asset",
        instrument_id="42",
        created_at=first_time,
    )
    assert repo.register(mapping)
    assert not repo.register(mapping)
    first = FundamentalService(repo, FrozenClock(first_time))
    assert (
        first.ingest(provider(Transport([HttpResponse(200, payload("10"), {})])), "test-asset") == 1
    )
    assert (
        first.ingest(provider(Transport([HttpResponse(200, payload("10"), {})])), "test-asset") == 0
    )
    second_body = (
        payload("9").replace(b"2025-02-01", b"2025-03-15").replace(b"00042-25-01", b"00042-25-02")
    )
    second = FundamentalService(repo, FrozenClock(second_time))
    assert (
        second.ingest(provider(Transport([HttpResponse(200, second_body, {})])), "test-asset") == 1
    )
    original = second.snapshot("test-asset", first_time)
    revised = second.snapshot("test-asset", second_time)
    assert original.facts[0].value == Decimal("10")
    assert revised.facts[0].value == Decimal("9")
    assert revised.facts[0].revision == 2
    assert revised.facts[0].supersedes_fact_id == original.facts[0].fact_id
    assert second.snapshot("test-asset", datetime(2025, 2, 28, tzinfo=UTC)).facts == ()
    with pytest.raises(ConflictingFundamental):
        second.ingest(provider(Transport([HttpResponse(200, payload("99"), {})])), "test-asset")
    assert second.snapshot("test-asset", first_time) == original


def test_fundamental_query_is_honest_and_future_rejected(repository: "MarketRepository") -> None:
    service = FundamentalService(
        FundamentalRepository(repository.session), FrozenClock(datetime(2025, 3, 1, tzinfo=UTC))
    )
    result = service.snapshot("test-asset", datetime(2025, 2, 1, tzinfo=UTC))
    assert result.unavailable_reason == "NO_POINT_IN_TIME_FUNDAMENTALS"
    with pytest.raises(ValueError):
        service.snapshot("test-asset", datetime(2025, 4, 1, tzinfo=UTC))
    with pytest.raises(LookupError):
        service.snapshot("unknown", datetime(2025, 2, 1, tzinfo=UTC))
    with pytest.raises(LookupError):
        service.ingest(provider(Transport([])), "test-asset")


def financial_fact(
    metric: FundamentalMetric,
    value: str,
    identity: int,
    year: int = 2024,
) -> FundamentalFact:
    from datetime import date
    from uuid import UUID

    return FundamentalFact(
        fact_id=UUID(int=identity),
        asset_id="test-asset",
        metric=metric,
        value=Decimal(value),
        currency="USD",
        unit="USD",
        source="fixture",
        source_concept=metric.value,
        source_record_id=str(identity),
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        fiscal_year=year,
        fiscal_period="FY",
        form="10-K",
        revision=1,
        published_at=datetime(2025, 2, 1, tzinfo=UTC),
        available_at=datetime(2025, 3, 1, tzinfo=UTC),
        ingested_at=datetime(2025, 3, 1, tzinfo=UTC),
    )


def make_snapshot(facts: tuple[FundamentalFact, ...]) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        asset_id="test-asset",
        as_of=datetime(2025, 3, 1, tzinfo=UTC),
        generated_at=datetime(2025, 3, 1, tzinfo=UTC),
        facts=tuple(sorted(facts, key=lambda f: (f.metric.value, f.period_end, f.revision))),
        unavailable_reason=None if facts else "NO_POINT_IN_TIME_FUNDAMENTALS",
    )


def test_financial_context_coherent_annual_ratios_and_losses() -> None:
    result = financial_context(
        make_snapshot(
            (
                financial_fact(FundamentalMetric.REVENUE, "100", 1),
                financial_fact(FundamentalMetric.REVENUE, "80", 2, 2023),
                financial_fact(FundamentalMetric.GROSS_PROFIT, "30", 3),
                financial_fact(FundamentalMetric.NET_INCOME, "-10", 4),
                financial_fact(FundamentalMetric.OPERATING_CASH_FLOW, "5", 5),
                financial_fact(FundamentalMetric.CAPITAL_EXPENDITURE, "8", 6),
            )
        )
    )
    features = {f.metric: f for f in result.features}
    assert features[FundamentalMetric.REVENUE_GROWTH].value == Decimal("0.25")
    assert features[FundamentalMetric.GROSS_MARGIN].value == Decimal("0.3")
    assert features[FundamentalMetric.NET_MARGIN].value == Decimal("-0.1")
    assert features[FundamentalMetric.FREE_CASH_FLOW].value == Decimal("-3")
    assert len(features[FundamentalMetric.GROSS_MARGIN].input_fact_ids) == 2
    assert features[FundamentalMetric.PRICE_EARNINGS].value is None
    assert len(result.input_hash) == 64


def test_financial_context_rejects_ambiguous_periods_and_nonpositive_base() -> None:
    revenue = financial_fact(FundamentalMetric.REVENUE, "100", 1)
    alternate = financial_fact(FundamentalMetric.REVENUE, "99", 2).model_copy(
        update={"source_concept": "alternate"}
    )
    features = {
        f.metric: f
        for f in financial_context(
            make_snapshot(
                (
                    revenue,
                    alternate,
                    financial_fact(FundamentalMetric.GROSS_PROFIT, "30", 3),
                )
            )
        ).features
    }
    assert features[FundamentalMetric.GROSS_MARGIN].value is None
    features = {
        f.metric: f
        for f in financial_context(
            make_snapshot(
                (
                    revenue,
                    financial_fact(FundamentalMetric.REVENUE, "-10", 2, 2023),
                )
            )
        ).features
    }
    assert (
        features[FundamentalMetric.REVENUE_GROWTH].unavailable_reason == "NONPOSITIVE_GROWTH_BASE"
    )
    quarterly = financial_fact(FundamentalMetric.GROSS_PROFIT, "30", 3).model_copy(
        update={"fiscal_period": "Q4"}
    )
    assert all(
        f.value is None for f in financial_context(make_snapshot((revenue, quarterly))).features
    )


def test_context_hash_excludes_generation_time_and_api_unavailable(
    repository: MarketRepository,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pocket_alpha.fundamentals.api import router
    from pocket_alpha.market_data.api import session_dependency

    snapshot = make_snapshot(())
    changed = snapshot.model_copy(update={"generated_at": datetime(2025, 4, 1, tzinfo=UTC)})
    assert financial_context(snapshot).input_hash == financial_context(changed).input_hash
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/assets/test-asset/fundamental-context",
            params={"as_of": "2025-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["snapshot"]["unavailable_reason"] == "NO_POINT_IN_TIME_FUNDAMENTALS"
        assert all(feature["value"] is None for feature in response.json()["features"])
        assert (
            client.get(
                "/api/v1/assets/test-asset/fundamentals", params={"as_of": "2025-01-01"}
            ).status_code
            == 422
        )


def test_price_earnings_requires_causal_same_currency_positive_eps() -> None:
    from pocket_alpha.domain.models import Timeframe
    from pocket_alpha.fundamentals.context import FundamentalPrice

    eps = financial_fact(FundamentalMetric.EPS_DILUTED, "2", 1).model_copy(
        update={"unit": "USD/shares"}
    )
    quote = FundamentalPrice(
        asset_id="test-asset",
        market_id="test-market",
        currency="USD",
        price=Decimal("10"),
        timeframe=Timeframe.D1,
        source="fixture",
        close_time=datetime(2025, 3, 1, tzinfo=UTC),
        received_at=datetime(2025, 3, 1, tzinfo=UTC),
    )

    def pe(snapshot: FundamentalSnapshot, price: FundamentalPrice) -> Decimal | None:
        return next(
            f.value
            for f in financial_context(snapshot, price).features
            if f.metric == FundamentalMetric.PRICE_EARNINGS
        )

    report = make_snapshot((eps,))
    assert pe(report, quote) == Decimal("5")
    assert pe(report, quote.model_copy(update={"currency": "EUR"})) is None
    assert (
        pe(
            report,
            quote.model_copy(
                update={
                    "close_time": datetime(2025, 2, 28, tzinfo=UTC),
                }
            ),
        )
        is None
    )
    assert pe(make_snapshot((eps.model_copy(update={"value": Decimal("-2")}),)), quote) is None
    with pytest.raises(ValueError):
        pe(report, quote.model_copy(update={"received_at": datetime(2025, 3, 2, tzinfo=UTC)}))
    assert financial_context(report, quote).input_hash != financial_context(report).input_hash


def test_pagination_and_conflicting_batch_do_not_write(repository: MarketRepository) -> None:
    from pocket_alpha.fundamentals.providers import FundamentalPage

    class Paging:
        source = "sec-companyfacts"

        def facts(self, instrument_id: str, cursor: str | None = None) -> FundamentalPage:
            return FundamentalPage(records=(), next_cursor="cycle")

    repo = FundamentalRepository(repository.session)
    now = datetime(2025, 3, 1, tzinfo=UTC)
    repo.register(
        FundamentalMapping(
            source="sec-companyfacts",
            asset_id="test-asset",
            instrument_id="42",
            created_at=now,
        )
    )
    service = FundamentalService(repo, FrozenClock(now))
    with pytest.raises(FundamentalProviderError, match="repeated pagination"):
        service.ingest(Paging(), "test-asset")
    assert repo.available("test-asset", now) == ()


def test_stored_price_rejects_future_receipt_and_wrong_market(repository: MarketRepository) -> None:
    from datetime import timedelta

    from pocket_alpha.domain.models import Timeframe
    from tests.market_fixtures import START, sample

    first = sample(0)
    second = sample(1, received_at=START + timedelta(days=1))
    repository.put((first, second))
    repo = FundamentalRepository(repository.session)
    price = repo.price("test-asset", "test-market", Timeframe.H1, START + timedelta(hours=3))
    assert price is not None and price.close_time == first.close_time
    assert price.currency == "EUR" and price.price == first.close
    assert repo.price("test-asset", "test-market", Timeframe.D1, START + timedelta(hours=3)) is None
    with pytest.raises(LookupError):
        repo.price("different-asset", "test-market", Timeframe.H1, START + timedelta(hours=3))


def test_availability_is_captured_after_provider_response(repository: MarketRepository) -> None:
    from pocket_alpha.fundamentals.providers import FundamentalPage

    before = datetime(2025, 3, 1, tzinfo=UTC)
    after = datetime(2025, 3, 2, tzinfo=UTC)

    class AdvancingClock:
        instant = before

        def now(self) -> datetime:
            return self.instant

    clock = AdvancingClock()
    record = provider(Transport([HttpResponse(200, payload(), {})])).facts("42").records[0]

    class Delayed:
        source = "sec-companyfacts"

        def facts(self, instrument_id: str, cursor: str | None = None) -> FundamentalPage:
            clock.instant = after
            return FundamentalPage(records=(record,))

    repo = FundamentalRepository(repository.session)
    repo.register(
        FundamentalMapping(
            source="sec-companyfacts",
            asset_id="test-asset",
            instrument_id="42",
            created_at=before,
        )
    )
    service = FundamentalService(repo, clock)
    assert service.ingest(Delayed(), "test-asset") == 1
    assert service.snapshot("test-asset", before).facts == ()
    assert service.snapshot("test-asset", after).facts[0].ingested_at == after


def test_operator_cli_transaction_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from pocket_alpha.database import Base
    from pocket_alpha.fundamentals import __main__ as cli
    from tests.market_fixtures import register

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        register(MarketRepository(session))
    dispose = engine.dispose
    transport = Transport([HttpResponse(200, payload(), {}) for _ in range(2)])
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(cli, "build_engine", lambda _: engine)
    monkeypatch.setattr(cli, "SecCompanyFactsProvider", lambda _: provider(transport))
    monkeypatch.setenv("PA_SEC_USER_AGENT", "Fixture test@example.invalid")
    monkeypatch.setattr("sys.argv", ["fundamentals", "--asset-id", "test-asset", "--cik", "42"])
    try:
        cli.main()
        assert "Imported 1 immutable" in capsys.readouterr().out
        cli.main()
        assert "Imported 0 immutable" in capsys.readouterr().out
        monkeypatch.setattr("sys.argv", ["fundamentals", "--asset-id", "test-asset", "--cik", "99"])
        with pytest.raises(ConflictingFundamental):
            cli.main()
    finally:
        dispose()
