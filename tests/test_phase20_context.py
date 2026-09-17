"""Synthetic test cases only; no public network calls."""

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.contextual.models import (
    ContextEntity,
    ContextKind,
    ContextMapping,
    ContextSample,
    ContextSnapshot,
)
from pocket_alpha.contextual.providers import ContextPage
from pocket_alpha.contextual.service import ContextService
from pocket_alpha.contextual.storage import (
    ConflictingContext,
    ContextObservationRecord,
    ContextRepository,
)
from pocket_alpha.market_data.storage import MarketRepository
from tests.market_fixtures import START


class Provider:
    source = "synthetic-context"

    def __init__(self, *records: ContextSample) -> None:
        self.records = records

    def observations(self, external_entity_id: str, cursor: str | None = None) -> ContextPage:
        return ContextPage(self.records)


def macro(**changes: object) -> ContextSample:
    return ContextSample.model_validate(
        dict(
            external_entity_id="synthetic-series",
            source_record_id="release1",
            event_key="release",
            kind="MACRO",
            event_at=START,
            published_at=START,
            value="4.5",
            unit="percent",
            **changes,
        )
    )


def setup(repository: MarketRepository) -> ContextRepository:
    repo = ContextRepository(repository.session)
    repo.register(
        ContextEntity(entity_id="macro:synthetic", name="Synthetic policy rate", kind="MACRO"),
        ContextMapping(
            source=Provider.source,
            entity_id="macro:synthetic",
            external_entity_id="synthetic-series",
        ),
    )
    return repo


def test_causal_cutoff_revisions_and_idempotence(repository: MarketRepository) -> None:
    repo = setup(repository)
    first = START + timedelta(days=1)
    service = ContextService(repo, FrozenClock(first))
    assert service.ingest("macro:synthetic", Provider(macro())) == 1
    assert service.ingest("macro:synthetic", Provider(macro())) == 0
    assert service.snapshot("macro:synthetic", START).observations == ()
    old = service.snapshot("macro:synthetic", first)
    with pytest.raises(ValidationError, match="hash"):
        ContextSnapshot.model_validate(old.model_dump() | {"input_hash": "0" * 64})
    assert old.observations[0].value == Decimal("4.5")
    assert old.unavailable_kinds == (ContextKind.NEWS, ContextKind.SENTIMENT)
    later = ContextService(repo, FrozenClock(first + timedelta(days=1)))
    revision = macro().model_dump()
    revision.update(source_record_id="release2", revision=2, value="4.25", published_at=first)
    assert later.ingest("macro:synthetic", Provider(ContextSample.model_validate(revision))) == 1
    assert later.snapshot("macro:synthetic", first).input_hash == old.input_hash
    assert later.snapshot("macro:synthetic", first + timedelta(days=1)).observations[
        0
    ].value == Decimal("4.25")
    changed = macro().model_dump()
    changed["value"] = "3"
    with pytest.raises(ConflictingContext):
        later.ingest("macro:synthetic", Provider(ContextSample.model_validate(changed)))


def test_atomic_invalid_revision_and_future_publication(repository: MarketRepository) -> None:
    repo = setup(repository)
    service = ContextService(repo, FrozenClock(START + timedelta(days=1)))
    missing = macro().model_dump()
    missing.update(source_record_id="missing-parent", event_key="z", revision=2)
    with pytest.raises(ValidationError):
        service.ingest("macro:synthetic", Provider(macro(), ContextSample.model_validate(missing)))
    assert repository.session.scalars(select(ContextObservationRecord)).all() == []
    future = macro().model_dump()
    future["published_at"] = START + timedelta(days=2)
    with pytest.raises(ValueError, match="future publication"):
        service.ingest("macro:synthetic", Provider(ContextSample.model_validate(future)))
    with pytest.raises(ValueError, match="future"):
        service.snapshot("macro:synthetic", START + timedelta(days=2))
    with pytest.raises(LookupError):
        service.snapshot("unknown", START)


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "NaN"},
        {"unit": "USD"},
        {"event_at": START + timedelta(days=1)},
        {"period_start": "2025-01-02", "period_end": "2025-01-03"},
    ],
)
def test_numeric_contract_rejects_ambiguous_or_future_values(changes: dict[str, object]) -> None:
    data = macro().model_dump()
    data.update(changes)
    with pytest.raises(ValidationError):
        ContextSample.model_validate(data)


def test_sentiment_is_versioned_score_and_scheduled_news_is_not_observed_macro() -> None:
    data = macro().model_dump()
    data.update(
        kind="SENTIMENT", unit="normalized-score", value="0.6", method_version="synthetic-method-1"
    )
    assert ContextSample.model_validate(data).value == Decimal("0.6")
    for changes in ({"method_version": None}, {"value": "1.1"}, {"currency": "USD"}):
        with pytest.raises(ValidationError):
            ContextSample.model_validate(data | changes)
    news = dict(
        external_entity_id="synthetic-series",
        source_record_id="calendar",
        event_key="calendar",
        kind="NEWS",
        event_at=START + timedelta(days=1),
        published_at=START,
        event_status="SCHEDULED",
        title="Synthetic scheduled release",
        url="https://example.org/release",
    )
    assert ContextSample.model_validate(news).event_status == "SCHEDULED"
    with pytest.raises(ValidationError):
        ContextSample.model_validate(news | {"event_status": "OCCURRED"})


def test_mapping_mismatch_and_revision_unit_changes_reject(repository: MarketRepository) -> None:
    repo = setup(repository)
    service = ContextService(repo, FrozenClock(START + timedelta(days=1)))
    wrong = macro().model_dump()
    wrong["external_entity_id"] = "another"
    with pytest.raises(ValueError):
        service.ingest("macro:synthetic", Provider(ContextSample.model_validate(wrong)))
    service.ingest("macro:synthetic", Provider(macro()))
    changed = macro().model_dump()
    changed.update(source_record_id="release2", revision=2, unit="fraction")
    with pytest.raises(ValueError, match="identity"):
        service.ingest("macro:synthetic", Provider(ContextSample.model_validate(changed)))


class BrokenProvider:
    source = Provider.source

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def observations(self, external_entity_id: str, cursor: str | None = None) -> ContextPage:
        if self.mode == "overflow":
            return ContextPage(tuple(macro() for _ in range(1001)))
        if self.mode == "cycle":
            return ContextPage((), "same")
        return ContextPage((), str(int(cursor or "0") + 1))


@pytest.mark.parametrize("mode", ["overflow", "cycle", "pages"])
def test_provider_budgets_fail_closed_without_partial_writes(
    repository: MarketRepository, mode: str
) -> None:
    from pocket_alpha.contextual.providers import ContextProviderError

    repo = setup(repository)
    service = ContextService(repo, FrozenClock(START + timedelta(days=1)))
    with pytest.raises(ContextProviderError):
        service.ingest("macro:synthetic", BrokenProvider(mode))
    assert repo.history("macro:synthetic", service.clock.now()) == ()
