"""Evidence-linked strategy lifecycle. Qualification never enables live execution."""

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal, Self, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator
from sqlalchemy import (
    CheckConstraint,
    CursorResult,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from pocket_alpha.backtesting.models import Hash, digest
from pocket_alpha.common.clock import Clock, utc
from pocket_alpha.database import Base
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import DomainModel
from pocket_alpha.forecasts.models import ModelStage
from pocket_alpha.market_data.storage import MarketRecord, MarketRepository
from pocket_alpha.paper_trading.models import PaperConfig
from pocket_alpha.paper_trading.service import PaperService
from pocket_alpha.paper_trading.storage import PaperRepository
from pocket_alpha.research.registry import ModelRegistry, PromotionPolicy
from pocket_alpha.research.storage import ResearchRepository
from pocket_alpha.strategies.engine import StrategyAdapter
from pocket_alpha.strategies.models import StrategyDefinition, StrategyStage


class StrategyArtifact(DomainModel):
    strategy_id: UUID
    definition: StrategyDefinition
    definition_hash: Hash
    registered_at: UTCDateTime
    live_ready: Literal[False] = False

    @model_validator(mode="after")
    def intact(self) -> Self:
        if (
            self.live_ready
            or self.definition_hash != digest(self.definition)
            or self.strategy_id
            != uuid5(NAMESPACE_URL, "pocket-alpha-strategy:" + self.definition_hash)
        ):
            raise ValueError("strategy artifact identity invalid or live unavailable")
        return self


class StrategyEvent(DomainModel):
    strategy_id: UUID
    revision: int = Field(ge=0)
    from_stage: StrategyStage | None
    to_stage: StrategyStage
    at: UTCDateTime
    reason: Identifier
    model_artifact_id: UUID | None = None
    model_event_hash: Hash | None = None
    paper_account_id: UUID | None = None
    paper_state_hash: Hash | None = None
    policy: PromotionPolicy | None = None
    previous_hash: Hash | None = None
    content_hash: Hash

    @model_validator(mode="after")
    def intact(self) -> Self:
        if self.content_hash != digest(
            self.model_dump(mode="json", exclude={"content_hash"})
        ) or self.to_stage in {StrategyStage.LIVE, StrategyStage.LIVE_SMALL}:
            raise ValueError("strategy event corrupted or live unavailable")
        return self


class StrategyRecord(Base):
    __tablename__ = "strategy_registry"
    __table_args__ = (
        UniqueConstraint("version", "market_id", name="uq_strategy_market_version"),
        CheckConstraint(
            "stage IN ('RESEARCH','CANDIDATE','PAPER','SHADOW','DEGRADED','SUSPENDED','RETIRED')",
            name="ck_strategy_no_live",
        ),
    )
    strategy_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[str] = mapped_column(String(128))
    market_id: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column()
    stage: Mapped[str] = mapped_column(String(16))
    definition_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class StrategyEventRecord(Base):
    __tablename__ = "strategy_events"
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_registry.strategy_id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class StrategyConflict(Exception):
    pass


ALLOWED: dict[StrategyStage, set[StrategyStage]] = {
    StrategyStage.RESEARCH: {
        StrategyStage.CANDIDATE,
        StrategyStage.SUSPENDED,
        StrategyStage.RETIRED,
    },
    StrategyStage.CANDIDATE: {
        StrategyStage.PAPER,
        StrategyStage.DEGRADED,
        StrategyStage.SUSPENDED,
        StrategyStage.RETIRED,
    },
    StrategyStage.PAPER: {
        StrategyStage.SHADOW,
        StrategyStage.DEGRADED,
        StrategyStage.SUSPENDED,
        StrategyStage.RETIRED,
    },
    StrategyStage.SHADOW: {StrategyStage.DEGRADED, StrategyStage.SUSPENDED, StrategyStage.RETIRED},
    StrategyStage.DEGRADED: {StrategyStage.RETIRED},
    StrategyStage.SUSPENDED: {StrategyStage.RETIRED},
    StrategyStage.RETIRED: set(),
}


class StrategyRegistry:
    def __init__(self, session: Session, clock: Clock) -> None:
        self.session, self.clock = session, clock

    def ids(self) -> tuple[UUID, ...]:
        return tuple(
            self.session.scalars(
                select(StrategyRecord.strategy_id).order_by(StrategyRecord.strategy_id).limit(100)
            )
        )

    def get(self, key: UUID) -> tuple[StrategyArtifact, tuple[StrategyEvent, ...]] | None:
        head = self.session.get(StrategyRecord, key)
        if head is None:
            return None
        artifact = StrategyArtifact.model_validate_json(head.payload)
        rows = self.session.scalars(
            select(StrategyEventRecord)
            .where(StrategyEventRecord.strategy_id == key)
            .order_by(StrategyEventRecord.revision)
        ).all()
        events = tuple(StrategyEvent.model_validate_json(row.payload) for row in rows)
        if (
            artifact.strategy_id != key
            or artifact.definition_hash != head.definition_hash
            or artifact.definition.version != head.version
            or artifact.definition.market_id != head.market_id
            or len(events) != head.revision + 1
            or not events
            or events[-1].to_stage.value != head.stage
        ):
            raise ValueError("strategy registry index/history corrupted")
        for i, (row, event) in enumerate(zip(rows, events, strict=True)):
            prior = events[i - 1] if i else None
            if (
                event.strategy_id != key
                or event.revision != i
                or row.revision != i
                or row.content_hash != event.content_hash
                or event.previous_hash != (prior.content_hash if prior else None)
                or event.from_stage != (prior.to_stage if prior else None)
                or event.at < artifact.registered_at
                or (prior is not None and event.at < prior.at)
            ):
                raise ValueError("strategy registry audit chain corrupted")
            if prior is None:
                if event.to_stage != StrategyStage.RESEARCH:
                    raise ValueError("strategy must begin in research")
            elif event.to_stage not in ALLOWED.get(prior.to_stage, set()):
                raise ValueError("strategy lifecycle transition unavailable")
            if prior is not None and event.to_stage in {StrategyStage.PAPER, StrategyStage.SHADOW}:
                if (
                    event.model_artifact_id != prior.model_artifact_id
                    or event.policy != prior.policy
                ):
                    raise ValueError("strategy history changed frozen model/policy")
                if (
                    event.to_stage == StrategyStage.SHADOW
                    and event.paper_account_id != prior.paper_account_id
                ):
                    raise ValueError("strategy history changed frozen PAPER account")
            if event.to_stage in {
                StrategyStage.CANDIDATE,
                StrategyStage.PAPER,
                StrategyStage.SHADOW,
            }:
                self._evidence(artifact, event, historical=True)
        return artifact, events

    def register(self, definition: StrategyDefinition) -> StrategyArtifact:
        definition = StrategyDefinition.model_validate_json(definition.model_dump_json())
        market = self.session.get(MarketRecord, definition.market_id)
        if (
            market is None
            or market.asset_id != definition.asset_id
            or MarketRepository(self.session).mapping(definition.market_id, definition.source)
            is None
        ):
            raise ValueError("strategy requires registered market and source provenance")
        artifact = StrategyArtifact(
            strategy_id=uuid5(NAMESPACE_URL, "pocket-alpha-strategy:" + digest(definition)),
            definition=definition,
            definition_hash=digest(definition),
            registered_at=utc(self.clock.now()),
        )
        existing = self.get(artifact.strategy_id)
        if existing is not None:
            return existing[0]
        conflict = self.session.scalar(
            select(StrategyRecord).where(
                StrategyRecord.version == definition.version,
                StrategyRecord.market_id == definition.market_id,
            )
        )
        if conflict is not None:
            raise StrategyConflict("strategy version already binds different parameters")
        with self.session.begin_nested():
            self.session.add(
                StrategyRecord(
                    strategy_id=artifact.strategy_id,
                    version=definition.version,
                    market_id=definition.market_id,
                    revision=0,
                    stage="RESEARCH",
                    definition_hash=artifact.definition_hash,
                    payload=artifact.model_dump_json(),
                )
            )
            self.session.flush()
            self._append(artifact, None, StrategyStage.RESEARCH, "REGISTERED", None, None, None)
        return artifact

    def transition(
        self,
        key: UUID,
        expected_revision: int,
        target: StrategyStage,
        reason: str,
        model_artifact_id: UUID | None = None,
        paper_account_id: UUID | None = None,
        policy: PromotionPolicy | None = None,
    ) -> StrategyEvent:
        with self.session.begin_nested():
            loaded = self.get(key)
            if loaded is None:
                raise LookupError("strategy not found")
            artifact, events = loaded
            prior = events[-1]
            if prior.revision != expected_revision:
                raise StrategyConflict("strategy revision changed")
            if target not in ALLOWED.get(prior.to_stage, set()):
                raise ValueError("strategy transition unavailable; live remains disabled")
            return self._append(
                artifact, prior, target, reason, model_artifact_id, paper_account_id, policy
            )

    def _append(
        self,
        artifact: StrategyArtifact,
        prior: StrategyEvent | None,
        target: StrategyStage,
        reason: str,
        model_id: UUID | None,
        paper_id: UUID | None,
        policy: PromotionPolicy | None,
    ) -> StrategyEvent:
        now = utc(self.clock.now())
        if prior is not None and now < prior.at:
            raise ValueError("strategy clock moved backwards")
        if prior is not None and target in {StrategyStage.PAPER, StrategyStage.SHADOW}:
            if model_id != prior.model_artifact_id or policy != prior.policy:
                raise ValueError("strategy promotions must preserve frozen model and policy")
            if target == StrategyStage.SHADOW and paper_id != prior.paper_account_id:
                raise ValueError("strategy SHADOW must preserve its PAPER account")
        model_hash, paper_hash = None, None
        if target in {StrategyStage.CANDIDATE, StrategyStage.PAPER, StrategyStage.SHADOW}:
            if model_id is None or policy is None:
                raise ValueError(
                    "strategy promotion requires sealed model evidence and explicit policy"
                )
            model = ModelRegistry(ResearchRepository(self.session), self.clock).get(model_id)
            if model is None:
                raise LookupError("strategy model artifact missing")
            model_hash = model[1][-1].content_hash
            if target in {StrategyStage.PAPER, StrategyStage.SHADOW}:
                if paper_id is None:
                    raise ValueError("strategy PAPER/SHADOW requires a bound PAPER account")
                paper = PaperService(PaperRepository(self.session), self.clock).view(paper_id)
                if paper is None:
                    raise LookupError("strategy PAPER account missing")
                paper_hash = paper.state.state_hash
        draft = StrategyEvent.model_construct(
            strategy_id=artifact.strategy_id,
            revision=prior.revision + 1 if prior else 0,
            from_stage=prior.to_stage if prior else None,
            to_stage=target,
            at=now,
            reason=reason,
            model_artifact_id=model_id,
            model_event_hash=model_hash,
            paper_account_id=paper_id,
            paper_state_hash=paper_hash,
            policy=policy,
            previous_hash=prior.content_hash if prior else None,
            content_hash="0" * 64,
        )
        event = StrategyEvent.model_validate(
            draft.model_dump()
            | dict(content_hash=digest(draft.model_dump(mode="json", exclude={"content_hash"})))
        )
        if target in {StrategyStage.CANDIDATE, StrategyStage.PAPER, StrategyStage.SHADOW}:
            self._evidence(artifact, event, historical=False)
        if prior is not None:
            result = self.session.execute(
                update(StrategyRecord)
                .where(
                    StrategyRecord.strategy_id == artifact.strategy_id,
                    StrategyRecord.revision == prior.revision,
                )
                .values(revision=event.revision, stage=target.value)
            )
            if cast(CursorResult[object], result).rowcount != 1:
                raise StrategyConflict("strategy concurrent revision changed")
        self.session.add(
            StrategyEventRecord(
                strategy_id=artifact.strategy_id,
                revision=event.revision,
                content_hash=event.content_hash,
                payload=event.model_dump_json(),
            )
        )
        self.session.flush()
        return event

    def _evidence(
        self, artifact: StrategyArtifact, event: StrategyEvent, *, historical: bool
    ) -> None:
        if event.model_artifact_id is None or event.policy is None:
            raise ValueError("strategy promotion evidence incomplete")
        registry = ModelRegistry(ResearchRepository(self.session), self.clock)
        loaded = registry.get(event.model_artifact_id)
        if loaded is None:
            raise ValueError("strategy model evidence missing")
        model, events = loaded
        sealed = next((e for e in events if e.content_hash == event.model_event_hash), None)
        if (
            sealed is None
            or sealed.at > event.at
            or sealed.to_stage not in {ModelStage.CHALLENGER, ModelStage.SHADOW}
            or (not historical and events[-1] != sealed)
        ):
            raise ValueError("strategy requires current qualified OOS model evidence")
        report = registry.repository.get(model.experiment_id)
        if report is None or report.origin != "REAL":
            raise ValueError("strategy promotion requires real OOS evidence")
        plan = registry.repository.plan(report.study_id)
        assert plan is not None
        variant = next(v for v in plan.variants if v.name == model.selected_variant)
        definition = artifact.definition
        if (
            variant.config.strategy != definition.identity()
            or variant.horizon != definition.horizon
        ):
            raise ValueError("strategy identity/horizon differs from sealed experiments")
        StrategyAdapter(definition, variant.config)
        # Re-evaluate economic gates with the strategy's explicitly selected policy.
        registry._gate(model, report, event.policy, ModelStage.CHALLENGER)
        if event.to_stage == StrategyStage.CANDIDATE:
            return
        if event.paper_account_id is None:
            raise ValueError("strategy PAPER account evidence missing")
        paper_loaded = PaperRepository(self.session).load(event.paper_account_id)
        if paper_loaded is None:
            raise ValueError("strategy PAPER account missing")
        header, runtime, journal = paper_loaded
        cfg = header.config
        if (
            cfg.origin != "REAL"
            or cfg.market.market_id != definition.market_id
            or cfg.asset.asset_id != definition.asset_id
            or cfg.mapping.source != definition.source
            or cfg.timeframe != definition.timeframe
            or cfg.run.strategy != definition.identity()
            or cfg.run != variant.config
            or header.created_at > event.at
        ):
            raise ValueError("strategy PAPER provenance/config differs from qualified evidence")
        hashes = {e.state_hash: e.revision for e in journal}
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            genesis = type(runtime)(
                header.account_id, cfg, header.created_at, header.initial_checkpoint
            )
            hashes[genesis.state().state_hash] = 0
            if event.paper_state_hash not in hashes:
                raise ValueError("strategy PAPER checkpoint evidence missing")
            for entry in journal[: hashes[event.paper_state_hash]]:
                genesis.market(entry.input)
                genesis.decisions(entry.intents, entry.strategy_checkpoint, entry.failure)
            state = genesis.state()
            if state.at > event.at or (
                not historical and state.state_hash != runtime.state().state_hash
            ):
                raise ValueError("strategy PAPER checkpoint is not current or causal")
            if event.to_stage == StrategyStage.SHADOW:
                if (
                    sealed.to_stage != ModelStage.SHADOW
                    or state.status not in {"ACTIVE", "CLOSED"}
                    or not genesis.sim.trades
                ):
                    raise ValueError(
                        "strategy SHADOW requires final holdout and completed PAPER trades"
                    )
                if sealed.evidence_id is None:
                    raise ValueError("strategy SHADOW final evidence missing")
                registry._gate(
                    model,
                    registry.repository.get(sealed.evidence_id),
                    event.policy,
                    ModelStage.SHADOW,
                )
                policy = event.policy
                expectancy = sum((t.net_pnl for t in genesis.sim.trades), Decimal(0)) / len(
                    genesis.sim.trades
                )
                audit = type(runtime)(
                    header.account_id, cfg, header.created_at, header.initial_checkpoint
                )
                dd = Decimal(0)
                for entry in journal[: hashes[event.paper_state_hash]]:
                    audit.market(entry.input)
                    audit.decisions(entry.intents, entry.strategy_checkpoint, entry.failure)
                    equity = audit.state().portfolio.equity
                    dd = max(dd, (audit.sim.book.high_water - equity) / audit.sim.book.high_water)
                if (
                    len(genesis.sim.trades) < policy.minimum_completed_trades
                    or state.net_return is None
                    or state.net_return < policy.minimum_net_return
                    or expectancy < policy.minimum_net_expectancy
                    or dd > policy.maximum_drawdown
                ):
                    raise ValueError("strategy PAPER economics fail SHADOW policy")

    def operational(self, key: UUID, account_id: UUID, config: PaperConfig) -> bool:
        loaded = self.get(key)
        if loaded is None:
            return False
        artifact, events = loaded
        latest = events[-1]
        if (
            latest.at > utc(self.clock.now())
            or latest.to_stage not in {StrategyStage.PAPER, StrategyStage.SHADOW}
            or latest.paper_account_id != account_id
            or config.run.strategy != artifact.definition.identity()
        ):
            return False
        assert latest.model_artifact_id is not None
        model = ModelRegistry(ResearchRepository(self.session), self.clock).get(
            latest.model_artifact_id
        )
        return (
            model is not None
            and model[1][-1].at <= utc(self.clock.now())
            and model[1][-1].to_stage in {ModelStage.CHALLENGER, ModelStage.SHADOW}
        )


class RegisteredStrategyAdapter(StrategyAdapter):
    def __init__(self, registry: StrategyRegistry, strategy_id: UUID, config: PaperConfig) -> None:
        loaded = registry.get(strategy_id)
        if loaded is None:
            raise LookupError("registered strategy missing")
        self.registry, self.strategy_id = registry, strategy_id
        self.bound_config = PaperConfig.model_validate_json(config.model_dump_json())
        super().__init__(loaded[0].definition, config.run)

    def preflight(self, account_id: UUID, config: PaperConfig) -> bool:
        return config == self.bound_config and self.registry.operational(
            self.strategy_id, account_id, config
        )
