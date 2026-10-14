"""Project domain: persistent workspaces that own all OpenClass knowledge.

Projects are the top-level isolation boundary. Every future resource (raw
events, decision runs, versions, candidates) will reference a project, so the
schema carries an owner column from day one even before multi-user
authentication exists.
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .evidence import (
    DiagnosisCategory,
    EvidenceCase,
    EvidenceItem,
    EvidenceStatus,
    EvidenceTriggerType,
    EvolutionSummary,
    FeedbackAction,
    RunFeedback,
    evidence_from_run,
    validate_status_transition,
)
from .models import Model
from .repositories import ConflictError


def now() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(Model):
    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    status: ProjectStatus = ProjectStatus.ACTIVE
    owner_id: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class RawEvent(Model):
    """Immutable source observation persisted before semantic processing."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    source_type: Literal["text", "json", "csv", "webhook"] = "text"
    content: str = Field(min_length=1)
    content_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)

    @model_validator(mode="after")
    def compute_content_hash(self) -> "RawEvent":
        # Dedup identity: identical content inside a project commits once.
        if not self.content_hash:
            digest = sha256(self.content.strip().encode()).hexdigest()
            object.__setattr__(self, "content_hash", digest)
        return self


AuditEventType = Literal[
    "project.created",
    "project.updated",
    "evidence.created",
    "evidence.triaged",
    "evidence.resolved",
    "evidence.dismissed",
    "evidence.ready_for_evolution",
    "evidence.grouped",
    "evidence.ungrouped",
    "feedback.submitted",
    "evidence_case.created",
    "evidence_case.updated",
    "choice_candidate.created",
    "choice_candidate.rejected",
    "choice_candidate.promoted",
    "decision_service.created",
    "decision_service.updated",
    "decision_run_paused",
    "decision_run_resumed",
    "decision_run_cancelled",
    "decision_run_failed",
    "decision_run.paused",
    "decision_run.resumed",
    "decision_run.cancelled",
    "decision_run.failed",
    "integration.created",
    "integration.updated",
    "integration.tested",
    "integration.deleted",
    "integration.webhook_ingested",
    "unknown.triaged",
    "unknown.transitioned",
    "cluster.updated",
    "candidate.created",
    "candidate.updated",
    "candidate.rejected",
    "evaluation.dataset_created",
    "evaluation.dataset_sealed",
    "evaluation.completed",
    "quality.alert",
]

DecisionRunStatus = Literal["completed", "paused", "resumed", "cancelled", "failed"]


class ProjectAuditEvent(Model):
    """Append-only record of a human-visible project change."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    event_type: AuditEventType
    actor: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)


class DecisionServiceTransition(Model):
    from_node_key: str = Field(min_length=1, max_length=200)
    choice_key: str = Field(min_length=1, max_length=120)
    to_node_key: str = Field(min_length=1, max_length=200)
    require_approval: bool = False


class DecisionServiceChoice(Model):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,49}$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    aliases: tuple[str, ...] = ()
    target_node_id: UUID | None = None
    target_node_name: str | None = None

    @model_validator(mode="after")
    def clean_aliases(self) -> "DecisionServiceChoice":
        seen: set[str] = {self.key.strip().casefold()}
        cleaned_aliases: list[str] = []
        for raw_alias in self.aliases:
            cleaned = str(raw_alias).strip()
            if not cleaned:
                continue
            folded = cleaned.casefold()
            if folded not in seen:
                seen.add(folded)
                cleaned_aliases.append(cleaned)
        object.__setattr__(self, "aliases", tuple(cleaned_aliases))
        return self


UNKNOWN_CHOICE = DecisionServiceChoice(
    key="UNKNOWN",
    label="Unknown",
    description="Input cannot be reliably classified, is ambiguous, out of domain, or novel.",
)


class DecisionServiceNode(Model):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=2000)
    choices: tuple[DecisionServiceChoice, ...] = Field(min_length=1, max_length=50)
    risk_level: Literal["ordinary", "high"] = "ordinary"
    min_margin: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    max_unknown_probability: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    pause_on_review: bool = False

    @model_validator(mode="before")
    @classmethod
    def ensure_unknown_choice(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_choices = list(data.get("choices") or [])
            has_unknown = any(
                (c.get("key") if isinstance(c, dict) else getattr(c, "key", None)) == "UNKNOWN"
                for c in raw_choices
            )
            if not has_unknown:
                raw_choices.append(UNKNOWN_CHOICE.model_dump(mode="json"))
            data["choices"] = raw_choices
        return data

    @model_validator(mode="after")
    def validate_unique_keys(self) -> "DecisionServiceNode":
        keys = [c.key for c in self.choices]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate choice keys in node")
        return self


class DecisionServiceStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class DecisionService(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,78}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(min_length=1, max_length=4000)
    nodes: tuple[DecisionServiceNode, ...] = Field(min_length=1)
    transitions: tuple[DecisionServiceTransition, ...] = ()
    status: DecisionServiceStatus = DecisionServiceStatus.ACTIVE
    provider_override: str | None = None
    version_number: int = Field(default=1, ge=1)
    active_version_id: UUID | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


def compute_service_hash(service: DecisionService) -> str:
    """Compute a deterministic SHA-256 fingerprint of a DecisionService definition."""
    snapshot = json.dumps(service.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256(snapshot.encode()).hexdigest()


class DecisionServiceUpdate(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=4000)
    status: DecisionServiceStatus | None = None
    provider_override: str | None = None
    nodes: tuple[DecisionServiceNode, ...] | None = None
    transitions: tuple[DecisionServiceTransition, ...] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "DecisionServiceUpdate":
        if (
            self.name is None
            and self.description is None
            and self.instructions is None
            and self.status is None
            and self.provider_override is None
            and self.nodes is None
            and self.transitions is None
        ):
            raise ValueError("update must change at least one field")
        return self


class DecisionRunCheckpoint(Model):
    run_id: UUID
    project_id: UUID
    decision_service_id: UUID
    run_status: DecisionRunStatus = "completed"
    current_node_key: str | None = None
    next_node_key: str | None = None
    selected_choice: str
    supervision_outcome: Literal["TRUSTED", "REVIEW", "UNKNOWN"]
    supervision_reason: str = ""
    completed_steps: list[dict[str, Any]] = Field(default_factory=list)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    pinned_version_id: UUID | None = None
    pinned_version_number: int = 1
    pinned_service_hash: str | None = None
    pending_operation: dict[str, Any] | None = None
    latency_ms: float = 0.0
    resumed_by: str | None = None
    resumed_at: datetime | None = None
    resume_rationale: str | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    failure_reason: str | None = None
    updated_at: datetime = Field(default_factory=now)


class DecisionRun(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    raw_event_id: UUID
    decision_service_id: UUID
    decision_node_id: UUID
    decision_service_version_id: UUID | None = None
    service_hash: str | None = None

    provider: str
    model: str
    execution_mode: Literal["in_process", "daemon", "api", "deterministic_test_fallback", "mock"]
    real_inference: bool

    selected_choice: str

    probabilities: dict[str, float]
    top_probability: float
    second_probability: float | None = None
    margin: float
    unknown_probability: float

    supervision_outcome: Literal["TRUSTED", "REVIEW", "UNKNOWN"]
    supervision_reason: str

    latency_ms: float

    input_snapshot: dict[str, Any]
    instructions_snapshot: str
    choices_snapshot: list[dict[str, Any]]
    steps: list[dict[str, Any]] = Field(default_factory=list)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)

    run_status: DecisionRunStatus = "completed"
    current_node_key: str | None = None
    next_node_key: str | None = None
    completed_steps: list[dict[str, Any]] = Field(default_factory=list)
    pinned_version_id: UUID | None = None
    pinned_version_number: int = 1
    pinned_service_hash: str | None = None
    pending_operation: dict[str, Any] | None = None
    resumed_by: str | None = None
    resumed_at: datetime | None = None
    resume_rationale: str | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    failure_reason: str | None = None

    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)


class ProjectSummary(Model):
    """Server-computed overview counters. Fields whose resources
    do not exist yet are honest zeros/nulls, never sample data."""

    events: int = Field(default=0, ge=0)
    decision_runs: int = Field(default=0, ge=0)
    unknowns: int = Field(default=0, ge=0)
    pending_evidence: int = Field(default=0, ge=0)
    active_policy: str | None = None
    pending_candidates: int = Field(default=0, ge=0)
    audit_events: int = Field(default=0, ge=0)


def slugify(name: str) -> str:
    slug = ""
    for char in name.lower():
        if char.isalnum():
            slug += char
        elif slug and slug[-1] != "-":
            slug += "-"
    return slug.strip("-")[:78] or "project"


class ProjectUpdate(Model):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=0, max_length=2000)
    status: ProjectStatus | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "ProjectUpdate":
        if self.name is None and self.description is None and self.status is None:
            raise ValueError("update must change at least one field")
        return self


class EvidenceRepository(Protocol):
    """Persistence contract for the proposed evidence slice, separate from projects."""

    # ── Evidence ─────────────────────────────────────────────

    async def create_evidence_item(
        self,
        item: EvidenceItem,
        audit_event: ProjectAuditEvent,
    ) -> None: ...

    async def list_evidence_items(
        self,
        project_id: UUID,
        *,
        status: EvidenceStatus | None = None,
        trigger_type: EvidenceTriggerType | None = None,
        decision_service_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceItem]: ...

    async def get_evidence_item(
        self,
        project_id: UUID,
        evidence_id: UUID,
    ) -> EvidenceItem: ...

    async def update_evidence_item(
        self,
        item: EvidenceItem,
        audit_event: ProjectAuditEvent,
    ) -> None: ...

    async def count_evidence_by_status(
        self,
        project_id: UUID,
    ) -> dict[str, int]: ...

    # ── Evidence Cases ───────────────────────────────────────

    async def create_evidence_case(
        self,
        case: EvidenceCase,
        audit_event: ProjectAuditEvent,
    ) -> None: ...

    async def get_evidence_case(
        self,
        project_id: UUID,
        case_id: UUID,
    ) -> EvidenceCase: ...

    async def list_evidence_cases(
        self,
        project_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceCase]: ...

    async def update_evidence_case(
        self,
        case: EvidenceCase,
        audit_event: ProjectAuditEvent,
    ) -> None: ...

    async def list_case_evidence(
        self,
        project_id: UUID,
        case_id: UUID,
    ) -> list[EvidenceItem]: ...

    # ── Run Feedback ─────────────────────────────────────────

    async def create_run_feedback(
        self,
        feedback: RunFeedback,
        audit_event: ProjectAuditEvent,
    ) -> None: ...

    async def list_run_feedback(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> list[RunFeedback]: ...

    # ── Evolution Summary ────────────────────────────────────

    async def evolution_summary(
        self,
        project_id: UUID,
    ) -> EvolutionSummary: ...

    async def get_evidence_for_run(
        self,
        project_id: UUID,
        run_id: UUID,
    ) -> EvidenceItem | None: ...


class ProjectRepository(EvidenceRepository, Protocol):
    """Persistence boundary. Implementations must keep projects isolated by
    identifier and store audit events atomically with the change they record."""

    async def create_project(self, project: Project, audit_event: ProjectAuditEvent) -> None: ...

    async def get_project(self, identifier: str) -> Project: ...

    async def list_projects(self) -> list[Project]: ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def update_project(self, project: Project, audit_event: ProjectAuditEvent) -> None: ...

    async def audit_events(self, project_id: UUID) -> list[ProjectAuditEvent]: ...

    async def create_raw_event(self, event: RawEvent) -> None: ...

    async def create_raw_events(self, events: list[RawEvent]) -> None: ...

    async def list_raw_events(
        self, project_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[RawEvent]: ...

    async def get_raw_event(self, project_id: UUID, event_id: UUID) -> RawEvent: ...

    async def get_raw_event_by_hash(
        self, project_id: UUID, content_hash: str
    ) -> RawEvent | None: ...

    async def count_raw_events(self, project_id: UUID) -> int: ...

    async def provider_usage(
        self, project_id: UUID, date_from: str, date_to: str
    ) -> list[dict[str, Any]]: ...

    async def record_provider_error(
        self, project_id: UUID, provider: str, model: str, latency_ms: float
    ) -> None: ...

    async def create_decision_service(self, service: DecisionService) -> None: ...

    async def get_decision_service(self, project_id: UUID, identifier: str) -> DecisionService: ...

    async def list_decision_services(self, project_id: UUID) -> list[DecisionService]: ...

    async def update_decision_service(self, service: DecisionService) -> None: ...

    async def create_decision_run(self, run: DecisionRun) -> None: ...

    async def list_decision_runs(
        self, project_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[DecisionRun]: ...

    async def get_decision_run(self, project_id: UUID, run_id: UUID) -> DecisionRun: ...

    async def count_decision_runs(self, project_id: UUID) -> int: ...

    async def analytics_runs(self, project_id: UUID) -> list[DecisionRun]: ...

    async def count_unknown_decision_runs(self, project_id: UUID) -> int: ...

    async def count_pending_choice_candidates(self, project_id: UUID) -> int: ...


class ProjectService:
    """Domain rules for creating and evolving projects. Slug collisions are
    resolved with numeric suffixes; every mutation records an audit event."""

    def __init__(
        self,
        repository: ProjectRepository,
        actor: str = "local-user",
        clock: Any = datetime.now,
    ) -> None:
        self.repository = repository
        self.actor = actor
        self.clock = clock

    async def create(self, name: str, description: str = "") -> Project:
        if not name.strip():
            raise ValueError("project name is required")
        timestamp = self.clock()
        base = slugify(name)
        slug = base
        counter = 2
        while await self.repository.slug_exists(slug):
            slug = f"{base}-{counter}"
            counter += 1
        project = Project(
            slug=slug,
            name=name.strip(),
            description=description.strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )
        await self.repository.create_project(
            project,
            ProjectAuditEvent(
                project_id=project.id,
                event_type="project.created",
                actor=self.actor,
                payload={"name": project.name, "slug": project.slug},
                created_at=timestamp,
            ),
        )
        return project

    async def get(self, identifier: str) -> Project:
        return await self.repository.get_project(identifier)

    async def list_projects(self) -> list[Project]:
        return await self.repository.list_projects()

    async def update(self, identifier: str, update: ProjectUpdate) -> Project:
        project = await self.repository.get_project(identifier)
        changed: dict[str, Any] = {}
        updates: dict[str, Any] = {}
        if update.name is not None and update.name.strip() != project.name:
            updates["name"] = update.name.strip()
            changed["name"] = updates["name"]
        if update.description is not None and update.description.strip() != project.description:
            updates["description"] = update.description.strip()
            changed["description"] = updates["description"]
        if update.status is not None and update.status != project.status:
            updates["status"] = update.status
            changed["status"] = update.status.value
        if not updates:
            return project
        updates["updated_at"] = self.clock()
        project = project.model_copy(update=updates)
        await self.repository.update_project(
            project,
            ProjectAuditEvent(
                project_id=project.id,
                event_type="project.updated",
                actor=self.actor,
                payload={"changes": changed},
                created_at=project.updated_at,
            ),
        )
        return project

    async def audit(self, identifier: str) -> list[ProjectAuditEvent]:
        project = await self.repository.get_project(identifier)
        return await self.repository.audit_events(project.id)

    async def summary(self, identifier: str) -> ProjectSummary:
        project = await self.repository.get_project(identifier)
        events = await self.repository.audit_events(project.id)
        raw_count = await self.repository.count_raw_events(project.id)
        runs_count = await self.repository.count_decision_runs(project.id)
        unknown_count = await self.repository.count_unknown_decision_runs(project.id)
        candidate_count = await self.repository.count_pending_choice_candidates(project.id)
        evidence_counts = await self.repository.count_evidence_by_status(project.id)
        return ProjectSummary(
            events=raw_count,
            decision_runs=runs_count,
            unknowns=unknown_count,
            pending_evidence=evidence_counts.get("pending", 0),
            pending_candidates=candidate_count,
            audit_events=len(events),
        )

    async def ingest_event(
        self,
        identifier: str,
        content: str,
        source_type: Literal["text", "json", "csv", "webhook"] = "text",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[RawEvent, bool]:
        """Ingest one observation; returns (event, deduped).

        Identical content inside a project commits once: a repeat delivery
        returns the original event with deduped=True.
        """
        if not content.strip():
            raise ValueError("event content cannot be blank")
        project = await self.repository.get_project(identifier)
        event = RawEvent(
            project_id=project.id,
            source_type=source_type,
            content=content.strip(),
            metadata=metadata or {},
            created_at=self.clock(),
        )
        try:
            await self.repository.create_raw_event(event)
        except ConflictError:
            existing = await self.repository.get_raw_event_by_hash(project.id, event.content_hash)
            if existing is None:
                raise
            return existing, True
        return event, False

    async def ingest_events_batch(
        self,
        identifier: str,
        items: list[dict[str, Any]],
        source_type: Literal["text", "json", "csv", "webhook"] = "text",
    ) -> list[tuple[RawEvent, bool]]:
        project = await self.repository.get_project(identifier)
        results: list[tuple[RawEvent, bool]] = []
        for item in items:
            c = item.get("content", "")
            if not isinstance(c, str) or not c.strip():
                continue
            meta = item.get("metadata", {})
            st = item.get("source_type", source_type)
            event = RawEvent(
                project_id=project.id,
                source_type=st,
                content=c.strip(),
                metadata=meta if isinstance(meta, dict) else {},
                created_at=self.clock(),
            )
            try:
                await self.repository.create_raw_event(event)
                results.append((event, False))
            except ConflictError:
                existing = await self.repository.get_raw_event_by_hash(
                    project.id, event.content_hash
                )
                if existing is None:
                    raise
                results.append((existing, True))
        if not results:
            raise ValueError("no valid events to ingest")
        return results

    async def list_events(
        self, identifier: str, limit: int = 50, offset: int = 0
    ) -> list[RawEvent]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_raw_events(project.id, limit=limit, offset=offset)

    async def get_event(self, identifier: str, event_id: UUID) -> RawEvent:
        project = await self.repository.get_project(identifier)
        return await self.repository.get_raw_event(project.id, event_id)

    @staticmethod
    def _build_choice(c: DecisionServiceChoice | dict[str, Any]) -> DecisionServiceChoice:
        if isinstance(c, DecisionServiceChoice):
            return c
        key = str(c.get("key", "")).strip().upper()
        if not key:
            raise ValueError("choice key is required")
        raw_aliases = c.get("aliases") or ()
        aliases = tuple(
            str(a).strip()
            for a in raw_aliases
            if isinstance(a, (str, int, float)) and str(a).strip()
        )
        raw_target_id = c.get("target_node_id")
        target_node_id = (
            raw_target_id
            if isinstance(raw_target_id, UUID)
            else UUID(str(raw_target_id))
            if raw_target_id
            else None
        )
        raw_target_name = c.get("target_node_name")
        target_node_name = str(raw_target_name).strip() if raw_target_name else None
        return DecisionServiceChoice(
            key=key,
            label=str(c.get("label") or key).strip(),
            description=str(c.get("description") or "").strip(),
            aliases=aliases,
            target_node_id=target_node_id,
            target_node_name=target_node_name,
        )

    @classmethod
    def _build_node(
        cls, n: DecisionServiceNode | dict[str, Any], default_instructions: str
    ) -> DecisionServiceNode:
        if isinstance(n, DecisionServiceNode):
            return n
        raw_choices = n.get("choices") or []
        if not raw_choices:
            raise ValueError("at least one choice must be defined in node")
        choice_objs = [cls._build_choice(c) for c in raw_choices]
        if not any(c.key == "UNKNOWN" for c in choice_objs):
            choice_objs.append(UNKNOWN_CHOICE)
        node_kwargs: dict[str, Any] = {
            "name": str(n.get("name") or "default").strip(),
            "instructions": str(n.get("instructions") or default_instructions).strip(),
            "choices": tuple(choice_objs),
            "risk_level": n.get("risk_level") or "ordinary",
            "min_margin": n.get("min_margin"),
            "max_unknown_probability": n.get("max_unknown_probability"),
            "pause_on_review": bool(n.get("pause_on_review", False)),
        }
        if n.get("id") is not None:
            node_kwargs["id"] = n["id"] if isinstance(n["id"], UUID) else UUID(str(n["id"]))
        return DecisionServiceNode(**node_kwargs)

    @staticmethod
    def _build_transition(
        t: DecisionServiceTransition | dict[str, Any],
    ) -> DecisionServiceTransition:
        if isinstance(t, DecisionServiceTransition):
            return t
        return DecisionServiceTransition(
            from_node_key=str(t.get("from_node_key") or "").strip(),
            choice_key=str(t.get("choice_key") or "").strip().upper(),
            to_node_key=str(t.get("to_node_key") or "").strip(),
            require_approval=bool(t.get("require_approval", False)),
        )

    async def create_decision_service(
        self,
        identifier: str,
        name: str,
        instructions: str,
        choices: list[dict[str, Any]] | None = None,
        description: str = "",
        provider_override: str | None = None,
        *,
        nodes: list[dict[str, Any]] | tuple[DecisionServiceNode, ...] | None = None,
        transitions: list[dict[str, Any]] | tuple[DecisionServiceTransition, ...] = (),
    ) -> DecisionService:
        project = await self.repository.get_project(identifier)
        if not name.strip():
            raise ValueError("decision service name is required")
        if not instructions.strip():
            raise ValueError("decision service instructions are required")

        if nodes:
            node_objs = tuple(self._build_node(n, instructions.strip()) for n in nodes)
        else:
            if not choices:
                raise ValueError("at least one choice must be defined")
            choice_objs = [self._build_choice(c) for c in choices]
            if not any(c.key == "UNKNOWN" for c in choice_objs):
                choice_objs.append(UNKNOWN_CHOICE)
            node_objs = (
                DecisionServiceNode(
                    name="default",
                    instructions=instructions.strip(),
                    choices=tuple(choice_objs),
                ),
            )

        transition_objs = tuple(self._build_transition(t) for t in (transitions or ()))

        slug_candidate = slugify(name)
        service = DecisionService(
            project_id=project.id,
            slug=slug_candidate,
            name=name.strip(),
            description=description.strip(),
            instructions=instructions.strip(),
            nodes=node_objs,
            transitions=transition_objs,
            provider_override=provider_override,
            version_number=1,
            active_version_id=uuid4(),
            created_at=self.clock(),
            updated_at=self.clock(),
        )
        await self.repository.create_decision_service(service)
        return service

    async def get_decision_service(
        self, identifier: str, service_id_or_slug: str
    ) -> DecisionService:
        project = await self.repository.get_project(identifier)
        return await self.repository.get_decision_service(project.id, service_id_or_slug)

    async def list_decision_services(self, identifier: str) -> list[DecisionService]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_decision_services(project.id)

    async def update_decision_service(
        self, identifier: str, service_id_or_slug: str, update: DecisionServiceUpdate
    ) -> DecisionService:
        project = await self.repository.get_project(identifier)
        service = await self.repository.get_decision_service(project.id, service_id_or_slug)
        updates: dict[str, Any] = {"updated_at": self.clock()}
        version_bump = False
        if update.name is not None:
            updates["name"] = update.name
        if update.description is not None:
            updates["description"] = update.description
        if update.instructions is not None:
            if update.instructions != service.instructions:
                version_bump = True
            updates["instructions"] = update.instructions
            if len(service.nodes) == 1 and update.nodes is None:
                updates["nodes"] = (
                    service.nodes[0].model_copy(update={"instructions": update.instructions}),
                )
        if update.nodes is not None:
            updates["nodes"] = update.nodes
            version_bump = True
        if update.transitions is not None:
            updates["transitions"] = update.transitions
            version_bump = True
        if update.status is not None:
            updates["status"] = update.status
        if update.provider_override is not None:
            if update.provider_override != service.provider_override:
                version_bump = True
            updates["provider_override"] = update.provider_override
        if version_bump:
            updates["version_number"] = service.version_number + 1
            updates["active_version_id"] = uuid4()
        service = service.model_copy(update=updates)
        await self.repository.update_decision_service(service)
        return service

    async def record_decision_run(self, run: DecisionRun) -> EvidenceItem | None:
        await self.repository.create_decision_run(run)
        item = evidence_from_run(run)
        if item is not None:
            audit = ProjectAuditEvent(
                project_id=run.project_id,
                event_type="evidence.created",
                actor=self.actor,
                payload={
                    "evidence_id": str(item.id),
                    "decision_run_id": str(run.id),
                    "trigger_type": item.trigger_type.value,
                },
                created_at=self.clock(),
            )
            await self.repository.create_evidence_item(item, audit)
        return item

    async def list_decision_runs(
        self, identifier: str, limit: int = 50, offset: int = 0
    ) -> list[DecisionRun]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_decision_runs(project.id, limit=limit, offset=offset)

    async def get_decision_run(self, identifier: str, run_id: UUID) -> DecisionRun:
        project = await self.repository.get_project(identifier)
        return await self.repository.get_decision_run(project.id, run_id)

    # ── Evidence Domain Methods ──────────────────────────────────────────

    async def submit_run_feedback(
        self,
        identifier: str,
        run_id: UUID,
        action: FeedbackAction,
        *,
        corrected_choice: str | None = None,
        note: str | None = None,
    ) -> RunFeedback:
        project = await self.repository.get_project(identifier)
        run = await self.repository.get_decision_run(project.id, run_id)
        feedback = RunFeedback(
            project_id=project.id,
            decision_run_id=run.id,
            action=action,
            corrected_choice=corrected_choice,
            note=note,
            actor=self.actor,
            created_at=self.clock(),
        )
        feedback_audit = ProjectAuditEvent(
            project_id=project.id,
            event_type="feedback.submitted",
            actor=self.actor,
            payload={
                "feedback_id": str(feedback.id),
                "decision_run_id": str(run.id),
                "action": action.value,
            },
            created_at=self.clock(),
        )
        await self.repository.create_run_feedback(feedback, feedback_audit)

        if action in (FeedbackAction.CORRECT, FeedbackAction.MISSING_CONCEPT):
            existing_evidence = await self.repository.get_evidence_for_run(project.id, run.id)
            if existing_evidence is None:
                trigger = (
                    EvidenceTriggerType.HUMAN_CORRECTION
                    if action == FeedbackAction.CORRECT
                    else EvidenceTriggerType.HUMAN_MARKED_MISSING_CONCEPT
                )
                evidence = EvidenceItem(
                    project_id=project.id,
                    raw_event_id=run.raw_event_id,
                    decision_run_id=run.id,
                    decision_service_id=run.decision_service_id,
                    decision_node_id=run.decision_node_id,
                    trigger_type=trigger,
                    selected_choice=run.selected_choice,
                    probabilities_snapshot=dict(run.probabilities),
                    unknown_probability=run.unknown_probability,
                    margin=run.margin,
                    supervision_outcome=run.supervision_outcome,
                    supervision_reason=run.supervision_reason,
                    provider=run.provider,
                    model=run.model,
                    execution_mode=run.execution_mode,
                    source="human",
                    human_note=note,
                    corrected_choice=corrected_choice,
                    created_at=self.clock(),
                )
                ev_audit = ProjectAuditEvent(
                    project_id=project.id,
                    event_type="evidence.created",
                    actor=self.actor,
                    payload={
                        "evidence_id": str(evidence.id),
                        "decision_run_id": str(run.id),
                        "trigger_type": trigger.value,
                    },
                    created_at=self.clock(),
                )
                await self.repository.create_evidence_item(evidence, ev_audit)

        return feedback

    async def list_run_feedback(self, identifier: str, run_id: UUID) -> list[RunFeedback]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_run_feedback(project.id, run_id)

    async def triage_evidence(
        self,
        identifier: str,
        evidence_id: UUID,
        diagnosis: DiagnosisCategory,
        rationale: str,
    ) -> EvidenceItem:
        project = await self.repository.get_project(identifier)
        item = await self.repository.get_evidence_item(project.id, evidence_id)
        validate_status_transition(item.status, EvidenceStatus.TRIAGED)
        updated = item.model_copy(
            update={
                "status": EvidenceStatus.TRIAGED,
                "diagnosis": diagnosis,
                "diagnosis_rationale": rationale.strip(),
            }
        )
        audit = ProjectAuditEvent(
            project_id=project.id,
            event_type="evidence.triaged",
            actor=self.actor,
            payload={
                "evidence_id": str(evidence_id),
                "diagnosis": diagnosis.value,
            },
            created_at=self.clock(),
        )
        await self.repository.update_evidence_item(updated, audit)
        return updated

    async def transition_evidence(
        self,
        identifier: str,
        evidence_id: UUID,
        target_status: EvidenceStatus,
        rationale: str | None = None,
    ) -> EvidenceItem:
        project = await self.repository.get_project(identifier)
        item = await self.repository.get_evidence_item(project.id, evidence_id)
        validate_status_transition(item.status, target_status)
        updates: dict[str, Any] = {"status": target_status}
        if rationale is not None:
            updates["diagnosis_rationale"] = rationale.strip()
        if target_status in (EvidenceStatus.RESOLVED, EvidenceStatus.DISMISSED):
            updates["resolved_at"] = self.clock()
        updated = item.model_copy(update=updates)
        event_map = {
            EvidenceStatus.RESOLVED: "evidence.resolved",
            EvidenceStatus.DISMISSED: "evidence.dismissed",
            EvidenceStatus.READY_FOR_EVOLUTION: "evidence.ready_for_evolution",
            EvidenceStatus.TRIAGED: "evidence.triaged",
        }
        audit = ProjectAuditEvent(
            project_id=project.id,
            event_type=event_map.get(target_status, "evidence.triaged"),  # type: ignore[arg-type]
            actor=self.actor,
            payload={
                "evidence_id": str(evidence_id),
                "from_status": item.status.value,
                "to_status": target_status.value,
            },
            created_at=self.clock(),
        )
        await self.repository.update_evidence_item(updated, audit)
        return updated

    async def create_evidence_case(
        self,
        identifier: str,
        title: str,
        *,
        decision_service_id: UUID | None = None,
        evidence_ids: list[UUID] | None = None,
    ) -> EvidenceCase:
        project = await self.repository.get_project(identifier)
        if not title.strip():
            raise ValueError("Case title is required")
        case = EvidenceCase(
            project_id=project.id,
            decision_service_id=decision_service_id,
            title=title.strip(),
            created_at=self.clock(),
            updated_at=self.clock(),
        )
        audit = ProjectAuditEvent(
            project_id=project.id,
            event_type="evidence_case.created",
            actor=self.actor,
            payload={"case_id": str(case.id), "title": case.title},
            created_at=self.clock(),
        )
        await self.repository.create_evidence_case(case, audit)

        if evidence_ids:
            for eid in evidence_ids:
                item = await self.repository.get_evidence_item(project.id, eid)
                updated_item = item.model_copy(update={"evidence_case_id": case.id})
                item_audit = ProjectAuditEvent(
                    project_id=project.id,
                    event_type="evidence.grouped",
                    actor=self.actor,
                    payload={"evidence_id": str(eid), "case_id": str(case.id)},
                    created_at=self.clock(),
                )
                await self.repository.update_evidence_item(updated_item, item_audit)

        return case

    async def add_evidence_to_case(
        self, identifier: str, case_id: UUID, evidence_id: UUID
    ) -> EvidenceCase:
        project = await self.repository.get_project(identifier)
        case = await self.repository.get_evidence_case(project.id, case_id)
        item = await self.repository.get_evidence_item(project.id, evidence_id)
        updated_item = item.model_copy(update={"evidence_case_id": case.id})
        audit = ProjectAuditEvent(
            project_id=project.id,
            event_type="evidence.grouped",
            actor=self.actor,
            payload={"evidence_id": str(evidence_id), "case_id": str(case.id)},
            created_at=self.clock(),
        )
        await self.repository.update_evidence_item(updated_item, audit)
        return case

    async def list_evidence(
        self,
        identifier: str,
        *,
        status: EvidenceStatus | None = None,
        trigger_type: EvidenceTriggerType | None = None,
        decision_service_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceItem]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_evidence_items(
            project.id,
            status=status,
            trigger_type=trigger_type,
            decision_service_id=decision_service_id,
            limit=limit,
            offset=offset,
        )

    async def get_evidence(self, identifier: str, evidence_id: UUID) -> EvidenceItem:
        project = await self.repository.get_project(identifier)
        return await self.repository.get_evidence_item(project.id, evidence_id)

    async def list_evidence_cases(
        self, identifier: str, limit: int = 50, offset: int = 0
    ) -> list[EvidenceCase]:
        project = await self.repository.get_project(identifier)
        return await self.repository.list_evidence_cases(project.id, limit=limit, offset=offset)

    async def get_evidence_case(self, identifier: str, case_id: UUID) -> EvidenceCase:
        project = await self.repository.get_project(identifier)
        return await self.repository.get_evidence_case(project.id, case_id)

    async def evolution_summary(self, identifier: str) -> EvolutionSummary:
        project = await self.repository.get_project(identifier)
        return await self.repository.evolution_summary(project.id)
