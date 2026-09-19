"""Fail-closed Autopilot contracts. Orchestration never grants native execution."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from pocket_alpha.backtesting.models import Hash
from pocket_alpha.domain.market import Identifier, UTCDateTime
from pocket_alpha.domain.models import AssetId, DomainModel
from pocket_alpha.research.registry import RegistryEvent
from pocket_alpha.scanner.models import ScanReport
from pocket_alpha.spot_execution.models import SpotRequest
from pocket_alpha.strategies.registry import StrategyEvent

Positive = Annotated[Decimal, Field(gt=0, max_digits=38, decimal_places=18)]


class AutopilotPolicy(DomainModel):
    schema_version: Literal["autopilot-policy-1.0.0"] = "autopilot-policy-1.0.0"
    version: Identifier
    mode: Literal["DISABLED", "SYNTHETIC_QUALIFICATION"] = "DISABLED"
    enabled: bool = False
    asset_ids: tuple[AssetId, ...] = Field(min_length=1, max_length=100)
    strategy_hashes: tuple[Hash, ...] = Field(min_length=1, max_length=20)
    maximum_capital: Positive
    maximum_exposure: Positive
    maximum_daily_loss: Positive
    maximum_drawdown: Decimal = Field(gt=0, lt=1, max_digits=38, decimal_places=18)
    maximum_simultaneous_positions: int = Field(ge=1, le=10, strict=True)
    cooldown_seconds: int = Field(ge=1, le=86400, strict=True)
    stale_data_seconds: int = Field(ge=1, le=300, strict=True)
    maximum_candidates_per_cycle: int = Field(default=20, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def canonical(self) -> Self:
        if tuple(sorted(set(self.asset_ids))) != self.asset_ids:
            raise ValueError("autopilot assets must be unique and sorted")
        if tuple(sorted(set(self.strategy_hashes))) != self.strategy_hashes:
            raise ValueError("autopilot strategies must be unique and sorted")
        if self.maximum_exposure > self.maximum_capital:
            raise ValueError("autopilot exposure cannot exceed capital")
        return self


class AutopilotHealth(DomainModel):
    checked_at: UTCDateTime
    provider_ready: bool
    risk_ready: bool
    portfolio_ready: bool
    reconciliation_resolved: bool
    execution_ready: bool


class AutopilotCandidate(DomainModel):
    request: SpotRequest
    model_event: RegistryEvent
    strategy_event: StrategyEvent
    scan_policy_hash: Hash | None = None
    scan_rank: int | None = Field(default=None, ge=1, le=250, strict=True)

    @model_validator(mode="after")
    def evidence_shape(self) -> Self:
        is_buy = self.request.intent.action == "BUY"
        if is_buy != (self.scan_policy_hash is not None and self.scan_rank is not None):
            raise ValueError("BUY candidates require scan identity; SELL candidates must omit it")
        expected_strategy = uuid5(
            NAMESPACE_URL, "pocket-alpha-strategy:" + self.request.proposal.definition_hash
        )
        if (
            self.strategy_event.strategy_id != expected_strategy
            or self.strategy_event.model_artifact_id != self.model_event.artifact_id
            or self.strategy_event.model_event_hash != self.model_event.content_hash
            or self.strategy_event.at < self.model_event.at
        ):
            raise ValueError("autopilot lifecycle evidence identity mismatch")
        return self


class AutopilotCycle(DomainModel):
    schema_version: Literal["autopilot-cycle-1.0.0"] = "autopilot-cycle-1.0.0"
    cycle_id: UUID
    requested_at: UTCDateTime
    health: AutopilotHealth
    scan: ScanReport | None = None
    candidates: tuple[AutopilotCandidate, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_candidates(self) -> Self:
        identities = tuple(item.request.intent.client_id for item in self.candidates)
        if len(set(identities)) != len(identities):
            raise ValueError("autopilot candidate intentions must be unique")
        return self


class CandidateAssessment(DomainModel):
    client_id: Identifier
    eligible: bool
    reasons: tuple[str, ...]


class AutopilotDecision(DomainModel):
    schema_version: Literal["autopilot-decision-1.0.0"] = "autopilot-decision-1.0.0"
    cycle_id: UUID
    cycle_hash: Hash
    policy_hash: Hash
    assessed_at: UTCDateTime
    outcome: Literal["HALTED", "NO_ACTION", "SUBMIT"]
    selected_client_id: Identifier | None = None
    reasons: tuple[str, ...]
    candidates: tuple[CandidateAssessment, ...]
    submission_permitted: bool
    live_trading_enabled: Literal[False] = False
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        selected = self.selected_client_id is not None
        if (
            selected != self.submission_permitted
            or selected != (self.outcome == "SUBMIT")
            or (selected and self.reasons)
        ):
            raise ValueError("autopilot decision outcome is inconsistent")
        return self
