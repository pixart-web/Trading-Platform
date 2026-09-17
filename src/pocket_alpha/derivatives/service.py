from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.derivatives.context import build_context, option_skew, term_structure
from pocket_alpha.derivatives.models import (
    DerivativeContext,
    DerivativeContract,
    DerivativeContractSpec,
    DerivativeObservation,
    DerivativePolicy,
    DerivativeSample,
    OptionSkew,
    TermStructure,
    validate_contract_sample,
)
from pocket_alpha.derivatives.providers import DerivativeProvider, DerivativeProviderError
from pocket_alpha.derivatives.storage import ConflictingDerivative, DerivativeRepository

DEFAULT_POLICY = DerivativePolicy()


class DerivativeService:
    def __init__(self, repository: DerivativeRepository, clock: Clock) -> None:
        self.repository = repository
        self.clock = clock

    def register(self, spec: DerivativeContractSpec) -> DerivativeContract:
        existing = self.repository.get_contract(spec.contract_id)
        if existing is not None:
            if existing.model_dump(exclude={"available_at", "ingested_at"}) != spec.model_dump():
                raise ConflictingDerivative("derivative contract specification cannot be rewritten")
            return existing
        now = utc(self.clock.now())
        contract = DerivativeContract(**spec.model_dump(), available_at=now, ingested_at=now)
        self.repository.register(contract)
        return contract

    def ingest(self, provider: DerivativeProvider, contract_id: str) -> int:
        contract = self.repository.get_contract(contract_id, lock=True)
        if contract is None or contract.available_at > utc(self.clock.now()):
            raise LookupError("derivative contract is unavailable")
        if provider.source != contract.source:
            raise ValueError("derivative provider does not match contract source")
        records: list[DerivativeSample] = []
        cursor = None
        seen: set[str] = set()
        for _ in range(100):
            page = provider.history(contract.external_contract_id, cursor)
            records.extend(page.records)
            if len(records) > 10000:
                raise DerivativeProviderError("derivative import exceeds bounded record limit")
            cursor = page.next_cursor
            if cursor is None:
                break
            if cursor in seen:
                raise DerivativeProviderError("derivative provider repeated pagination cursor")
            seen.add(cursor)
        else:
            raise DerivativeProviderError("derivative import exceeds bounded page limit")
        unique: dict[str, DerivativeSample] = {}
        for sample in records:
            if sample.external_contract_id != contract.external_contract_id:
                raise DerivativeProviderError("provider observation identity differs from contract")
            if sample.source_record_id in unique and unique[sample.source_record_id] != sample:
                raise ConflictingDerivative("provider batch contains conflicting source records")
            unique[sample.source_record_id] = sample
        now = utc(self.clock.now())
        history = {
            (obs.observed_at, obs.revision): obs
            for obs in self.repository.history(contract_id, now)
        }
        pending: list[DerivativeObservation] = []
        for sample in sorted(unique.values(), key=lambda s: (s.observed_at, s.revision)):
            observation_id = uuid5(
                NAMESPACE_URL, f"{provider.source}|{contract_id}|{sample.source_record_id}"
            )
            existing = self.repository.get(observation_id)
            if existing is not None:
                original = existing.model_dump(
                    exclude={
                        "observation_id",
                        "contract_id",
                        "source",
                        "available_at",
                        "ingested_at",
                        "supersedes_observation_id",
                    }
                )
                if original != sample.model_dump():
                    raise ConflictingDerivative("provider changed an immutable source observation")
                continue
            key = (sample.observed_at, sample.revision)
            if key in history:
                raise ConflictingDerivative("provider revision has another source identity")
            parent = history.get((sample.observed_at, sample.revision - 1))
            if sample.revision > 1 and (
                parent is None or parent.published_at > sample.published_at
            ):
                raise ValueError("derivative revision is missing a coherent prior observation")
            observation = DerivativeObservation(
                **sample.model_dump(),
                observation_id=observation_id,
                contract_id=contract_id,
                source=provider.source,
                available_at=now,
                ingested_at=now,
                supersedes_observation_id=parent.observation_id if parent is not None else None,
            )
            # Validate instrument compatibility for the entire batch before persistence.
            validate_contract_sample(contract, sample)
            pending.append(observation)
            history[key] = observation
        for observation in pending:
            self.repository.put(observation)
        return len(pending)

    def cutoff(self, as_of: datetime) -> tuple[datetime, datetime]:
        cutoff, now = utc(as_of), utc(self.clock.now())
        if cutoff > now:
            raise ValueError("derivative cutoff cannot be in the future")
        return cutoff, now

    def context(
        self,
        contract_id: str,
        as_of: datetime,
        policy: DerivativePolicy = DEFAULT_POLICY,
    ) -> DerivativeContext:
        cutoff, now = self.cutoff(as_of)
        contract = self.repository.get_contract(contract_id)
        if contract is None or contract.available_at > cutoff or contract.ingested_at > cutoff:
            raise LookupError("derivative contract is unavailable at cutoff")
        return build_context(
            contract,
            self.repository.latest(contract_id, cutoff),
            cutoff,
            now,
            policy,
        )

    def curve(
        self,
        underlying_asset_id: str,
        venue_id: str,
        as_of: datetime,
        policy: DerivativePolicy = DEFAULT_POLICY,
    ) -> TermStructure:
        cutoff, now = self.cutoff(as_of)
        contexts = tuple(
            self.context(contract.contract_id, cutoff, policy)
            for contract in self.repository.contracts(underlying_asset_id, venue_id, cutoff)
            if contract.kind == "FUTURE"
            and contract.expires_at is not None
            and contract.expires_at > cutoff
        )
        return term_structure(contexts, cutoff, now)

    def skew(
        self,
        call_contract_id: str,
        put_contract_id: str,
        as_of: datetime,
        policy: DerivativePolicy = DEFAULT_POLICY,
    ) -> OptionSkew:
        cutoff, now = self.cutoff(as_of)
        return option_skew(
            self.context(call_contract_id, cutoff, policy),
            self.context(put_contract_id, cutoff, policy),
            cutoff,
            now,
        )
