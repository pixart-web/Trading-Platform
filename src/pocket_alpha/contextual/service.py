import json
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.contextual.models import (
    ContextKind,
    ContextObservation,
    ContextSample,
    ContextSnapshot,
    context_digest,
)
from pocket_alpha.contextual.providers import ContextProvider, ContextProviderError
from pocket_alpha.contextual.storage import ConflictingContext, ContextRepository


class ContextService:
    def __init__(self, repository: ContextRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def ingest(self, entity_id: str, provider: ContextProvider) -> int:
        if self.repository.entity(entity_id, lock=True) is None:
            raise LookupError("context entity not registered")
        mapping = self.repository.mapping(provider.source, entity_id)
        if mapping is None:
            raise LookupError("explicit context provider mapping required")
        samples: list[ContextSample] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(100):
            page = provider.observations(mapping.external_entity_id, cursor)
            samples.extend(page.records)
            if len(samples) > 1000:
                raise ContextProviderError("context batch exceeds bounded limit")
            cursor = page.next_cursor
            if cursor is None:
                break
            if cursor in seen:
                raise ContextProviderError("context cursor cycle")
            seen.add(cursor)
        else:
            raise ContextProviderError("context page budget exceeded")
        instant = utc(self.clock.now())
        if any(
            s.external_entity_id != mapping.external_entity_id or s.published_at > instant
            for s in samples
        ):
            raise ValueError("context batch contains incompatible or future publication")
        inserted = 0
        # A savepoint keeps invalid late revisions from leaving partially imported batches.
        with self.repository.session.begin_nested():
            for sample in sorted(samples, key=lambda s: (s.event_key, s.revision)):
                identity = uuid5(
                    NAMESPACE_URL, json.dumps([provider.source, entity_id, sample.source_record_id])
                )
                previous = self.repository.get(identity)
                if previous is not None:
                    if (
                        ContextSample.model_validate(
                            previous.model_dump(include=set(ContextSample.model_fields))
                        )
                        != sample
                    ):
                        raise ConflictingContext("source record changed without explicit revision")
                    continue
                parents = self.repository.history(entity_id, instant) if sample.revision > 1 else ()
                parent = next(
                    (
                        o
                        for o in parents
                        if o.source == provider.source
                        and o.event_key == sample.event_key
                        and o.revision == sample.revision - 1
                    ),
                    None,
                )
                observation = ContextObservation(
                    **sample.model_dump(),
                    observation_id=identity,
                    entity_id=entity_id,
                    source=provider.source,
                    available_at=instant,
                    ingested_at=instant,
                    supersedes_observation_id=parent.observation_id if parent else None,
                )
                inserted += self.repository.put(observation)
        return inserted

    def snapshot(self, entity_id: str, as_of: datetime) -> ContextSnapshot:
        cutoff, now = utc(as_of), utc(self.clock.now())
        if cutoff > now:
            raise ValueError("context cutoff cannot be in the future")
        entity = self.repository.entity(entity_id)
        if entity is None:
            raise LookupError("context entity not registered")
        latest: dict[tuple[str, str], ContextObservation] = {}
        for observation in self.repository.history(entity_id, cutoff):
            key = (observation.source, observation.event_key)
            if key not in latest or observation.revision > latest[key].revision:
                latest[key] = observation
        observations = tuple(
            sorted(latest.values(), key=lambda o: (o.published_at, o.source, o.event_key))
        )
        return ContextSnapshot(
            entity=entity,
            as_of=cutoff,
            generated_at=now,
            observations=observations,
            unavailable_kinds=tuple(
                k for k in ContextKind if k not in {o.kind for o in observations}
            ),
            input_hash=context_digest(entity, cutoff, observations),
        )
