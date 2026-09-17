"""All observations/contracts here are explicitly synthetic, never startup seed data."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.derivatives.api import router
from pocket_alpha.derivatives.models import (
    ContractKind,
    DerivativeContext,
    DerivativeContractSpec,
    DerivativePolicy,
    DerivativeSample,
    GreekName,
    MultiplierUnit,
    ReportedGreek,
)
from pocket_alpha.derivatives.providers import DerivativePage, DerivativeProviderError
from pocket_alpha.derivatives.service import DerivativeService
from pocket_alpha.derivatives.storage import ConflictingDerivative, DerivativeRepository
from pocket_alpha.market_data.api import session_dependency
from pocket_alpha.market_data.storage import MarketRepository

T0 = datetime(2025, 1, 1, tzinfo=UTC)
D = Decimal


def spec(
    suffix: str = "perp",
    kind: ContractKind = ContractKind.PERPETUAL,
    **changes: object,
) -> DerivativeContractSpec:
    values: dict[str, object] = {
        "contract_id": f"derivative:{suffix}",
        "underlying_asset_id": "test-asset",
        "venue_id": "test-venue",
        "kind": kind,
        "quote_currency": "USD",
        "settlement_currency": "USD",
        "multiplier": "10",
        "multiplier_unit": "BASE_UNITS_PER_CONTRACT",
        "settlement": "CASH",
        "reference_index_id": "fixture:index",
        "reference_index_currency": "USD",
        "margin_scheme": "UNKNOWN",
        "source": "fixture",
        "external_contract_id": suffix.upper(),
        "published_at": T0,
    }
    if kind != ContractKind.PERPETUAL:
        values["expires_at"] = T0 + timedelta(days=365)
    if kind == ContractKind.OPTION:
        values.update(strike="100", option_right="CALL", option_style="EUROPEAN")
    return DerivativeContractSpec.model_validate(values | changes)


def sample(external: str = "PERP", /, **changes: object) -> DerivativeSample:
    values: dict[str, object] = {
        "external_contract_id": external,
        "source_record_id": "synthetic:1",
        "observed_at": T0,
        "published_at": T0,
        "mark_price": "101",
        "index_price": "100",
        "open_interest_contracts": "2",
    }
    return DerivativeSample.model_validate(values | changes)


class FixtureProvider:
    source = "fixture"

    def __init__(self, records: tuple[DerivativeSample, ...]) -> None:
        self.records = records
        self.calls = 0

    def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage:
        self.calls += 1
        assert cursor is None
        return DerivativePage(self.records)


def service(repository: MarketRepository, now: datetime = T0) -> DerivativeService:
    return DerivativeService(DerivativeRepository(repository.session), FrozenClock(now))


def values(context: "DerivativeContext") -> dict[str, Decimal | None]:
    return {metric.name: metric.value for metric in context.metrics}


@pytest.mark.parametrize(
    "kind,changes",
    [
        (ContractKind.PERPETUAL, {"expires_at": T0}),
        (ContractKind.PERPETUAL, {"strike": "100"}),
        (ContractKind.FUTURE, {"expires_at": None}),
        (ContractKind.OPTION, {"strike": None}),
        (ContractKind.OPTION, {"option_style": None}),
        (ContractKind.OPTION, {"option_right": None}),
        (ContractKind.FUTURE, {"multiplier": "0"}),
        (ContractKind.FUTURE, {"contract_id": "test-asset"}),
        (ContractKind.FUTURE, {"published_at": datetime(2025, 1, 1)}),
    ],
)
def test_precise_contract_metadata_rejects_invalid_inputs(
    kind: ContractKind,
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        spec("perp", kind, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"funding_rate": "0.01"},
        {"funding_interval_seconds": 28800},
        {"implied_volatility": "0.5"},
        {"implied_volatility": "-0.1", "iv_convention": "ANNUALIZED_FRACTION"},
        {"open_interest_contracts": "-1"},
        {"initial_margin_rate": "0.1"},
        {
            "initial_margin_rate": "0.1",
            "maintenance_margin_rate": "0.2",
            "margin_rules_reference": "v1",
        },
        {"published_at": T0 - timedelta(seconds=1)},
        {"mark_price": "NaN"},
    ],
)
def test_observations_reject_unknown_units_or_incoherent_data(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        sample(**changes)


def test_contract_registration_preserves_identity_and_known_time(
    repository: MarketRepository,
) -> None:
    app = service(repository)
    contract = app.register(spec())
    assert service(repository, T0 + timedelta(days=1)).register(spec()) == contract
    with pytest.raises(ConflictingDerivative):
        app.register(spec(multiplier="20"))
    with pytest.raises(LookupError):
        app.context(contract.contract_id, T0 - timedelta(seconds=1))
    with pytest.raises(ValueError):
        app.context(contract.contract_id, T0 + timedelta(seconds=1))
    assert app.context(contract.contract_id, T0).observation_status == "MISSING"
    assert app.repository.get_contract(contract.contract_id) == contract


def test_revision_is_immutable_and_point_in_time(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec())
    first = sample()
    assert app.ingest(FixtureProvider((first,)), "derivative:perp") == 1
    assert app.ingest(FixtureProvider((first,)), "derivative:perp") == 0
    old = app.context("derivative:perp", T0)
    later = service(repository, T0 + timedelta(seconds=30))
    revised = sample(
        source_record_id="synthetic:2",
        revision=2,
        mark_price="99",
        published_at=T0 + timedelta(seconds=10),
    )
    assert later.ingest(FixtureProvider((revised,)), "derivative:perp") == 1
    current = later.context("derivative:perp", T0 + timedelta(seconds=30))
    assert current.observation is not None and old.observation is not None
    assert current.observation.revision == 2
    assert current.observation.supersedes_observation_id == old.observation.observation_id
    historical = later.context("derivative:perp", T0)
    assert historical.observation == old.observation
    assert historical.input_hash == old.input_hash
    with pytest.raises(ConflictingDerivative):
        later.ingest(FixtureProvider((sample(mark_price="123"),)), "derivative:perp")
    assert later.repository.get(old.observation.observation_id) == old.observation


def test_old_revision_does_not_replace_newer_market_observation(
    repository: MarketRepository,
) -> None:
    app = service(repository)
    app.register(spec())
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    later = service(repository, T0 + timedelta(seconds=30))
    newer = sample(
        source_record_id="new-event",
        observed_at=T0 + timedelta(seconds=20),
        published_at=T0 + timedelta(seconds=20),
        mark_price="105",
    )
    correction = sample(
        source_record_id="old-correction",
        revision=2,
        published_at=T0 + timedelta(seconds=30),
        mark_price="99",
    )
    later.ingest(FixtureProvider((newer, correction)), "derivative:perp")
    result = later.context("derivative:perp", T0 + timedelta(seconds=30))
    assert result.observation is not None and result.observation.source_record_id == "new-event"


def test_future_basis_notional_and_signed_prices(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec("future", ContractKind.FUTURE))
    app.ingest(FixtureProvider((sample("FUTURE"),)), "derivative:future")
    result = app.context("derivative:future", T0)
    computed = values(result)
    assert computed["derivative_minus_index"] == D("1")
    assert computed["derivative_minus_index_fraction"] == D("0.01")
    assert computed["simple_annualized_basis_act365f"] == D("0.01")
    assert computed["open_interest_quote_notional"] == D("2000")
    assert computed["funding_rate"] is None
    with pytest.raises(ValidationError):
        result.metrics[0].value = D("1")
    app.register(spec("negative", ContractKind.FUTURE))
    app.ingest(
        FixtureProvider((sample("NEGATIVE", mark_price="-20", index_price="10"),)),
        "derivative:negative",
    )
    assert values(app.context("derivative:negative", T0))["derivative_minus_index_fraction"] == D(
        "-3"
    )


def test_inverse_notional_and_funding_interval_are_preserved(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(
        spec(
            multiplier="100",
            multiplier_unit=MultiplierUnit.QUOTE_CURRENCY_PER_CONTRACT,
            settlement_currency="BTC",
        )
    )
    observation = sample(
        index_price=None,
        funding_rate="-0.000123456789012345",
        funding_interval_seconds=28800,
        funding_kind="REALIZED",
        initial_margin_rate="0.1",
        maintenance_margin_rate="0.05",
        margin_rules_reference="synthetic:margin-v1",
        margin_basis="quote-notional",
    )
    app.ingest(FixtureProvider((observation,)), "derivative:perp")
    repository.session.expire_all()
    result = app.context("derivative:perp", T0)
    assert values(result)["open_interest_quote_notional"] == D("200")
    assert values(result)["funding_rate"] == D("-0.000123456789012345")
    assert result.observation is not None and result.observation.funding_interval_seconds == 28800
    assert values(result)["simple_annualized_basis_act365f"] is None


def test_stale_and_expired_data_never_produce_fresh_features(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec())
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    later = service(repository, T0 + timedelta(seconds=301))
    assert (
        later.context("derivative:perp", T0 + timedelta(seconds=300)).observation_status
        == "AVAILABLE"
    )
    stale = later.context("derivative:perp", T0 + timedelta(seconds=301))
    assert stale.observation_status == "STALE" and all(v is None for v in values(stale).values())
    assert (
        later.context(
            "derivative:perp",
            T0 + timedelta(seconds=301),
            DerivativePolicy(maximum_age_seconds=302),
        ).observation_status
        == "AVAILABLE"
    )
    app.register(spec("expiring", ContractKind.FUTURE, expires_at=T0 + timedelta(seconds=60)))
    app.ingest(FixtureProvider((sample("EXPIRING"),)), "derivative:expiring")
    expired = later.context("derivative:expiring", T0 + timedelta(seconds=61))
    assert expired.observation_status == "EXPIRED" and all(
        v is None for v in values(expired).values()
    )


@pytest.mark.parametrize(
    "bad", ["identity", "missing-parent", "conflicting-record", "future-funding"]
)
def test_invalid_batches_are_rejected_before_writes(repository: MarketRepository, bad: str) -> None:
    app = service(repository)
    kind = ContractKind.FUTURE if bad == "future-funding" else ContractKind.PERPETUAL
    app.register(spec("perp", kind))
    first = sample()
    second = sample(
        source_record_id="second",
        observed_at=T0 + timedelta(seconds=1),
        published_at=T0 + timedelta(seconds=1),
    )
    if bad == "identity":
        second = sample("WRONG")
    elif bad == "missing-parent":
        second = sample(source_record_id="second", revision=3)
    elif bad == "conflicting-record":
        second = sample(mark_price="99")
    else:
        second = sample(
            funding_rate="0.01", funding_interval_seconds=28800, funding_kind="INDICATIVE"
        )
    later = service(repository, T0 + timedelta(seconds=10))
    with pytest.raises((ValueError, ConflictingDerivative, DerivativeProviderError)):
        later.ingest(FixtureProvider((first, second)), "derivative:perp")
    assert later.repository.history("derivative:perp", T0 + timedelta(seconds=10)) == ()


def test_pagination_cycle_and_provider_failure_are_not_data(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec())

    class Cyclic:
        source = "fixture"

        def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage:
            return DerivativePage((sample(),), "cycle")

    class Offline:
        source = "fixture"

        def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage:
            raise DerivativeProviderError("synthetic failure")

    for provider in (Cyclic(), Offline()):
        with pytest.raises(DerivativeProviderError):
            app.ingest(provider, "derivative:perp")
    assert app.repository.history("derivative:perp", T0) == ()


def test_availability_is_captured_after_provider_io(repository: MarketRepository) -> None:
    class Clock:
        instant = T0

        def now(self) -> datetime:
            return self.instant

    clock = Clock()
    app = DerivativeService(DerivativeRepository(repository.session), clock)
    app.register(spec())

    class Delayed:
        source = "fixture"

        def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage:
            clock.instant = T0 + timedelta(seconds=20)
            return DerivativePage((sample(),))

    app.ingest(Delayed(), "derivative:perp")
    assert app.context("derivative:perp", T0).observation is None
    assert app.context("derivative:perp", clock.instant).observation is not None


def greek(value: str, **changes: object) -> ReportedGreek:
    return ReportedGreek.model_validate(
        {
            "name": GreekName.DELTA,
            "value": value,
            "unit": "price-ratio",
            "convention": "spot-unadjusted",
            "model_version": "synthetic:greeks-v1",
        }
        | changes
    )


def option_pair(app: DerivativeService, **put_changes: object) -> None:
    app.register(spec("call", ContractKind.OPTION, strike="110"))
    app.register(spec("put", ContractKind.OPTION, option_right="PUT", strike="90"))
    app.ingest(
        FixtureProvider(
            (
                sample(
                    "CALL",
                    implied_volatility="0.5",
                    iv_convention="ANNUALIZED_FRACTION",
                    greeks=(greek("0.25"),),
                ),
            )
        ),
        "derivative:call",
    )
    defaults: dict[str, object] = {
        "implied_volatility": "0.6",
        "iv_convention": "ANNUALIZED_FRACTION",
        "greeks": (greek("-0.25"),),
    }
    app.ingest(FixtureProvider((sample("PUT", **(defaults | put_changes)),)), "derivative:put")


def test_skew_uses_reported_matching_conventions_and_exposes_provenance(
    repository: MarketRepository,
) -> None:
    app = service(repository)
    option_pair(app)
    result = app.skew("derivative:call", "derivative:put", T0)
    assert result.put_minus_call_iv.value == D("0.1")
    assert len(result.put_minus_call_iv.input_observation_ids) == 2
    assert all(values(result.call)[n] is None for n in ("derivative_minus_index", "funding_rate"))
    with pytest.raises(ValueError):
        app.skew("derivative:put", "derivative:call", T0)


def test_skew_does_not_estimate_missing_authoritative_delta(repository: MarketRepository) -> None:
    app = service(repository)
    option_pair(app, greeks=())
    result = app.skew("derivative:call", "derivative:put", T0)
    assert result.put_minus_call_iv.value is None
    assert result.put_minus_call_iv.unavailable_reason == "MATCHED_AUTHORITATIVE_DELTAS_UNAVAILABLE"


def test_term_structure_alignment_and_missing_quotes(repository: MarketRepository) -> None:
    app = service(repository)
    for name, days in (("far", 60), ("near", 30)):
        app.register(spec(name, ContractKind.FUTURE, expires_at=T0 + timedelta(days=days)))
        app.ingest(FixtureProvider((sample(name.upper()),)), f"derivative:{name}")
    curve = app.curve("test-asset", "test-venue", T0)
    assert curve.status == "COMPLETE"
    assert tuple(p.contract.contract_id for p in curve.points) == (
        "derivative:near",
        "derivative:far",
    )
    app.register(spec("unpriced", ContractKind.FUTURE, expires_at=T0 + timedelta(days=90)))
    partial = app.curve("test-asset", "test-venue", T0)
    assert partial.status == "PARTIAL" and len(partial.points) == 3
    assert partial.unavailable_reason == "INCOMPLETE_FUTURES_QUOTES"


def test_term_structure_rejects_incompatible_contracts(repository: MarketRepository) -> None:
    app = service(repository)
    for name, currency in (("a", "USD"), ("b", "EUR")):
        app.register(spec(name, ContractKind.FUTURE, quote_currency=currency))
        app.ingest(FixtureProvider((sample(name.upper()),)), f"derivative:{name}")
    assert app.curve("test-asset", "test-venue", T0).unavailable_reason == "INCOMPATIBLE_FUTURES"


def test_api_read_only_and_honest_missing_state(repository: MarketRepository) -> None:
    service(repository).register(spec())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    client = TestClient(app)
    url = "/api/v1/derivatives/derivative:perp/context"
    response = client.get(url, params={"as_of": T0.isoformat()})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["observation_status"] == "MISSING"
    assert all(m["value"] is None for m in response.json()["metrics"])
    assert client.post(url, json={}).status_code == 405
    assert client.get(url, params={"as_of": "2025-01-01"}).status_code == 422
    assert (
        client.get(url, params={"as_of": T0.isoformat(), "maximum_age_seconds": 0}).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/derivatives/missing/context", params={"as_of": T0.isoformat()}
        ).status_code
        == 404
    )
    listed = client.get(
        "/api/v1/derivatives/contracts",
        params={
            "underlying_asset_id": "test-asset",
            "venue_id": "test-venue",
            "as_of": T0.isoformat(),
        },
    )
    assert listed.status_code == 200 and len(listed.json()) == 1
    curve = client.get(
        "/api/v1/derivatives/term-structure",
        params={
            "underlying_asset_id": "test-asset",
            "venue_id": "test-venue",
            "as_of": T0.isoformat(),
        },
    )
    assert curve.status_code == 200 and curve.json()["status"] == "UNAVAILABLE"


def test_unaligned_futures_cannot_form_complete_curve(repository: MarketRepository) -> None:
    app = service(repository)
    for name in ("near", "far"):
        app.register(spec(name, ContractKind.FUTURE))
    later = service(repository, T0 + timedelta(seconds=1))
    later.ingest(FixtureProvider((sample("NEAR"),)), "derivative:near")
    later.ingest(
        FixtureProvider(
            (
                sample(
                    "FAR",
                    observed_at=T0 + timedelta(seconds=1),
                    published_at=T0 + timedelta(seconds=1),
                ),
            )
        ),
        "derivative:far",
    )
    curve = later.curve("test-asset", "test-venue", T0 + timedelta(seconds=1))
    assert curve.status == "UNAVAILABLE" and curve.unavailable_reason == "UNALIGNED_FUTURES_QUOTES"


@pytest.mark.parametrize(
    "case", ["unit", "convention", "model", "target", "missing-iv", "time", "stale"]
)
def test_option_skew_rejects_uncomparable_evidence(repository: MarketRepository, case: str) -> None:
    app = service(repository)
    option_pair(app)
    now = T0 + timedelta(seconds=2)
    updates: dict[str, object] = {
        "source_record_id": "synthetic:revision2",
        "revision": 2,
        "published_at": T0 + timedelta(seconds=1),
        "implied_volatility": "0.6",
        "iv_convention": "ANNUALIZED_FRACTION",
        "greeks": (greek("-0.25"),),
    }
    if case == "unit":
        updates["greeks"] = (greek("-0.25", unit="unknown-unit"),)
    elif case == "convention":
        updates["greeks"] = (greek("-0.25", convention="premium-adjusted"),)
    elif case == "model":
        updates["greeks"] = (greek("-0.25", model_version="other-model"),)
    elif case == "target":
        updates["greeks"] = (greek("-0.2"),)
    elif case == "missing-iv":
        updates.update(implied_volatility=None, iv_convention=None)
    elif case == "time":
        updates.update(observed_at=T0 + timedelta(seconds=1), revision=1)
    elif case == "stale":
        now = T0 + timedelta(seconds=301)
    later = service(repository, now)
    later.ingest(FixtureProvider((sample("PUT", **updates),)), "derivative:put")
    assert later.skew("derivative:call", "derivative:put", now).put_minus_call_iv.value is None


def test_skew_different_expirations_are_not_compared(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec("call", ContractKind.OPTION))
    app.register(
        spec(
            "put",
            ContractKind.OPTION,
            option_right="PUT",
            expires_at=T0 + timedelta(days=30),
        )
    )
    result = app.skew("derivative:call", "derivative:put", T0)
    assert result.put_minus_call_iv.unavailable_reason == "INCOMPATIBLE_OPTIONS"


def test_import_limits_provider_mapping_and_revision_identity(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec())

    class Infinite:
        source = "fixture"
        calls = 0

        def history(self, external_contract_id: str, cursor: str | None = None) -> DerivativePage:
            self.calls += 1
            return DerivativePage((), str(self.calls))

    endless = Infinite()
    with pytest.raises(DerivativeProviderError, match="page limit"):
        app.ingest(endless, "derivative:perp")
    assert endless.calls == 100
    with pytest.raises(DerivativeProviderError, match="record limit"):
        app.ingest(FixtureProvider((sample(),) * 10001), "derivative:perp")
    wrong = FixtureProvider(())
    wrong.source = "other-source"
    with pytest.raises(ValueError, match="source"):
        app.ingest(wrong, "derivative:perp")
    with pytest.raises(LookupError):
        app.ingest(FixtureProvider(()), "derivative:unknown")
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    with pytest.raises(ConflictingDerivative, match="another source identity"):
        app.ingest(FixtureProvider((sample(source_record_id="other-id"),)), "derivative:perp")


def test_registration_requires_actual_underlying_and_venue(repository: MarketRepository) -> None:
    app = service(repository)
    with pytest.raises(LookupError):
        app.register(spec(underlying_asset_id="unknown"))
    with pytest.raises(LookupError):
        app.register(spec(venue_id="unknown"))


def test_repository_rejects_immutable_edits_and_cross_contract_revision(
    repository: MarketRepository,
) -> None:
    from uuid import UUID

    app = service(repository)
    app.register(spec())
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    original = app.repository.latest("derivative:perp", T0)
    assert original is not None
    assert not app.repository.put(original)
    with pytest.raises(ConflictingDerivative):
        app.repository.put(original.model_copy(update={"mark_price": D("999")}))
    contract = app.repository.get_contract("derivative:perp")
    assert contract is not None and not app.repository.register(contract)
    with pytest.raises(ConflictingDerivative):
        app.repository.register(contract.model_copy(update={"multiplier": D("999")}))
    app.register(spec("other"))
    invalid = original.model_copy(
        update={
            "observation_id": UUID(int=1901),
            "contract_id": "derivative:other",
            "external_contract_id": "OTHER",
            "revision": 2,
            "supersedes_observation_id": original.observation_id,
            "source_record_id": "cross-contract",
        }
    )
    with pytest.raises(ValueError, match="coherent observation"):
        app.repository.put(invalid)
    with pytest.raises(ValueError, match="provenance"):
        app.repository.put(
            original.model_copy(
                update={
                    "observation_id": UUID(int=1902),
                    "source": "wrong",
                }
            )
        )


def test_context_rejects_future_evidence_and_generation_before_cutoff(
    repository: MarketRepository,
) -> None:
    from pocket_alpha.derivatives.context import build_context

    app = service(repository)
    contract = app.register(spec())
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    original = app.repository.latest("derivative:perp", T0)
    assert original is not None
    with pytest.raises(ValueError):
        build_context(contract, original, T0, T0 - timedelta(seconds=1), DerivativePolicy())
    future = original.model_copy(
        update={
            "available_at": T0 + timedelta(seconds=1),
            "ingested_at": T0 + timedelta(seconds=1),
        }
    )
    with pytest.raises(ValueError):
        build_context(contract, future, T0, T0, DerivativePolicy())


def test_option_quotes_and_greeks_never_inferred_for_future(repository: MarketRepository) -> None:
    app = service(repository)
    app.register(spec("future", ContractKind.FUTURE))
    with pytest.raises(ValueError):
        app.ingest(
            FixtureProvider(
                (
                    sample(
                        "FUTURE",
                        implied_volatility="0.5",
                        iv_convention="ANNUALIZED_FRACTION",
                    ),
                )
            ),
            "derivative:future",
        )
    app.register(spec("call", ContractKind.OPTION))
    with pytest.raises(ValueError):
        app.ingest(FixtureProvider((sample("CALL", mark_price="-1"),)), "derivative:call")
    app.register(spec())
    with pytest.raises(ValueError):
        app.ingest(FixtureProvider((sample(mark_price="0"),)), "derivative:perp")
    with pytest.raises(ValidationError):
        sample(greeks=(greek("0.25"), greek("0.3")))


def test_api_skew_errors_and_storage_failure_are_safe(
    repository: MarketRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    app_service = service(repository)
    option_pair(app_service)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_dependency] = lambda: repository.session
    client = TestClient(app)
    params = {
        "call_contract_id": "derivative:call",
        "put_contract_id": "derivative:put",
        "as_of": T0.isoformat(),
    }
    response = client.get("/api/v1/derivatives/option-skew", params=params)
    assert (
        response.status_code == 200
        and response.json()["put_minus_call_iv"]["value"] == "0.100000000000000000"
    )
    response = client.get(
        "/api/v1/derivatives/option-skew",
        params=params
        | {
            "call_contract_id": "derivative:put",
        },
    )
    assert response.status_code == 422
    unknown = client.get(
        "/api/v1/derivatives/contracts",
        params={
            "underlying_asset_id": "unknown",
            "venue_id": "test-venue",
            "as_of": T0.isoformat(),
        },
    )
    assert unknown.status_code == 404

    def unavailable(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("synthetic-private-connection-detail")

    monkeypatch.setattr(DerivativeRepository, "latest", unavailable)
    failure = client.get(
        "/api/v1/derivatives/derivative:call/context", params={"as_of": T0.isoformat()}
    )
    assert failure.status_code == 503 and "synthetic-private" not in failure.text


def test_phase19_registers_only_read_only_routes() -> None:
    from pocket_alpha.main import create_app

    paths = create_app().openapi()["paths"]
    derivative_paths = {path: methods for path, methods in paths.items() if "/derivatives/" in path}
    assert len(derivative_paths) == 4
    assert all(set(methods) == {"get"} for methods in derivative_paths.values())


def test_index_currency_mismatch_does_not_create_false_basis_or_notional(
    repository: MarketRepository,
) -> None:
    app = service(repository)
    app.register(spec(quote_currency="EUR", reference_index_currency="USD"))
    app.ingest(FixtureProvider((sample(),)), "derivative:perp")
    context = app.context("derivative:perp", T0)
    for name in (
        "derivative_minus_index",
        "derivative_minus_index_fraction",
        "open_interest_quote_notional",
    ):
        feature = next(m for m in context.metrics if m.name == name)
        assert feature.value is None and feature.unavailable_reason == "INDEX_CURRENCY_MISMATCH"


def test_financial_context_is_independent_of_callers_decimal_precision(
    repository: MarketRepository,
) -> None:
    from decimal import ROUND_UP, localcontext

    app = service(repository)
    app.register(spec("future", ContractKind.FUTURE))
    app.ingest(
        FixtureProvider((sample("FUTURE", mark_price="4", index_price="3"),)), "derivative:future"
    )
    option_pair(app)
    normal = app.context("derivative:future", T0)
    normal_skew = app.skew("derivative:call", "derivative:put", T0)
    with localcontext() as ctx:
        ctx.prec = 4
        ctx.rounding = ROUND_UP
        low_precision = app.context("derivative:future", T0)
        low_skew = app.skew("derivative:call", "derivative:put", T0)
    assert low_precision.metrics == normal.metrics
    assert low_precision.input_hash == normal.input_hash
    assert low_skew.put_minus_call_iv == normal_skew.put_minus_call_iv
    assert low_skew.input_hash == normal_skew.input_hash
