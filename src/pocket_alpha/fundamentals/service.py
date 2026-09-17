from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.fundamentals.models import FundamentalFact, FundamentalSnapshot
from pocket_alpha.fundamentals.providers import (
    FundamentalProvider,
    FundamentalProviderError,
    ProviderFact,
)
from pocket_alpha.fundamentals.storage import (
    ConflictingFundamental,
    FundamentalRepository,
    series_key,
)


class FundamentalService:
    def __init__(self, repository: FundamentalRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def ingest(self, provider: FundamentalProvider, asset_id: str) -> int:
        now = utc(self.clock.now())
        self.repository.lock_asset(asset_id)
        mapping = self.repository.mapping(provider.source, asset_id)
        if mapping is None or mapping.created_at > now:
            raise LookupError("fundamental provider mapping is unavailable")
        records: list[ProviderFact] = []
        cursor = None
        seen: set[str] = set()
        for _ in range(100):
            page = provider.facts(mapping.instrument_id, cursor)
            records.extend(page.records)
            if len(records) > 10000:
                raise FundamentalProviderError("fundamental import exceeds bounded record limit")
            cursor = page.next_cursor
            if cursor is None:
                break
            if cursor in seen:
                raise FundamentalProviderError("fundamental provider repeated pagination cursor")
            seen.add(cursor)
        else:
            raise FundamentalProviderError("fundamental import exceeds bounded page limit")
        unique: dict[str, ProviderFact] = {}
        for record in records:
            prior = unique.get(record.source_record_id)
            if prior is not None and prior != record:
                raise ConflictingFundamental("provider batch contains conflicting source records")
            unique[record.source_record_id] = record
        records = list(unique.values())
        # Capture availability after provider I/O, never before data actually arrives.
        now = utc(self.clock.now())
        history = list(self.repository.available(asset_id, now))
        pending: list[FundamentalFact] = []
        for record in sorted(records, key=lambda r: (r.published_at, r.source_record_id)):
            fact_id = uuid5(
                NAMESPACE_URL, f"{provider.source}|{asset_id}|{record.source_record_id}"
            )
            existing = self.repository.get(fact_id)
            if existing is not None:
                original = existing.model_dump(
                    exclude={
                        "schema_version",
                        "fact_id",
                        "asset_id",
                        "source",
                        "revision",
                        "supersedes_fact_id",
                        "available_at",
                        "ingested_at",
                    }
                )
                if original != record.model_dump():
                    raise ConflictingFundamental("provider changed an immutable source record")
                continue
            values = record.model_dump()
            provisional = FundamentalFact(
                **values,
                fact_id=fact_id,
                asset_id=asset_id,
                source=provider.source,
                revision=1,
                available_at=now,
                ingested_at=now,
            )
            previous = [
                fact for fact in history + pending if series_key(fact) == series_key(provisional)
            ]
            latest = max(previous, key=lambda f: (f.published_at, f.revision)) if previous else None
            # A late import of an older filing is retained without superseding a newer filing.
            if latest is not None and record.published_at >= latest.published_at:
                provisional = provisional.model_copy(
                    update={
                        "revision": latest.revision + 1,
                        "supersedes_fact_id": latest.fact_id,
                    }
                )
            pending.append(provisional)
        # Validate the entire batch before inserts; the transaction owner commits or rolls back.
        for fact in pending:
            self.repository.put(fact)
        return len(pending)

    def snapshot(self, asset_id: str, as_of: datetime) -> FundamentalSnapshot:
        cutoff = utc(as_of)
        now = utc(self.clock.now())
        if cutoff > now:
            raise ValueError("fundamental cutoff cannot be in the future")
        if not self.repository.asset_exists(asset_id):
            raise LookupError("fundamental asset is not registered")
        selected: dict[tuple[str, ...], FundamentalFact] = {}
        for fact in self.repository.available(asset_id, cutoff):
            key = series_key(fact)
            previous = selected.get(key)
            if previous is None or (fact.published_at, fact.revision) > (
                previous.published_at,
                previous.revision,
            ):
                selected[key] = fact
        facts = tuple(
            sorted(selected.values(), key=lambda f: (f.metric.value, f.period_end, f.revision))
        )
        return FundamentalSnapshot(
            asset_id=asset_id,
            as_of=cutoff,
            generated_at=now,
            facts=facts,
            unavailable_reason=None if facts else "NO_POINT_IN_TIME_FUNDAMENTALS",
        )
