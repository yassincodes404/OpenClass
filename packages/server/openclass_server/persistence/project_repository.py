"""SQL persistence for projects and their audit trail.

Lookup accepts identifier or slug; every stored mutation writes its audit event
in the same transaction so the audit trail cannot drift from project state.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from openclass_core.evidence import (
    EvidenceCase,
    EvidenceItem,
    EvidenceStatus,
    EvidenceTriggerType,
    EvolutionSummary,
    RunFeedback,
)
from openclass_core.project_evolution import ChoiceCandidate, service_hash
from openclass_core.projects import (
    UNKNOWN_CHOICE,
    DecisionRun,
    DecisionService,
    DecisionServiceChoice,
    Project,
    ProjectAuditEvent,
    RawEvent,
    get_current_workspace_id,
)
from openclass_core.repositories import ConflictError, NotFoundError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.mappers import (
    _project_from_row,
    audit_event_row,
    raw_event_row,
)
from openclass_server.persistence.tables import (
    AuditEventRow,
    DecisionRunCheckpointRow,
    DecisionRunRow,
    DecisionServiceRow,
    EvidenceCaseRow,
    EvidenceItemRow,
    ProjectChoiceCandidateRow,
    ProjectRow,
    RawEventRow,
    RunFeedbackRow,
)


class SQLProjectRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self._session_factory = sessions
        self._claim_lock = asyncio.Lock()

    def _effective_workspace_id(self, explicit_workspace_id: str | None = None) -> str | None:
        cleaned = (explicit_workspace_id or "").strip()
        if cleaned:
            return cleaned
        return get_current_workspace_id()

    @staticmethod
    def _row_workspace_id(row: ProjectRow) -> str | None:
        if row.workspace_id is not None:
            return row.workspace_id
        if isinstance(row.payload, dict):
            val = row.payload.get("workspace_id")
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    async def create_project(self, project: Project, audit_event: ProjectAuditEvent) -> None:
        workspace_id = project.workspace_id or self._effective_workspace_id()
        payload = project.model_dump(mode="json")
        payload["workspace_id"] = workspace_id
        try:
            async with self.sessions.begin() as session:
                session.add(
                    ProjectRow(
                        id=str(project.id),
                        slug=project.slug,
                        owner_id=project.owner_id,
                        workspace_id=workspace_id,
                        status=project.status.value,
                        name=project.name,
                        description=project.description,
                        created_at=project.created_at,
                        updated_at=project.updated_at,
                        payload=payload,
                    )
                )
                await session.flush()
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Project slug or identifier already exists") from exc

    async def get_project(self, identifier: str) -> Project:
        ws_id = self._effective_workspace_id()
        async with self.sessions() as session:
            row = await session.scalar(
                select(ProjectRow).where(
                    or_(
                        ProjectRow.id == identifier,
                        ProjectRow.slug == identifier,
                    )
                )
            )
            if row is None:
                raise NotFoundError(f"Project '{identifier}' was not found")
            row_ws = self._row_workspace_id(row)
            if ws_id is not None:
                if row_ws != ws_id:
                    raise NotFoundError(f"Project '{identifier}' was not found")
            else:
                if row_ws is not None:
                    raise NotFoundError(f"Project '{identifier}' was not found")
            return _project_from_row(row)

    async def list_projects(self, *, include_unassigned: bool = False) -> list[Project]:
        ws_id = self._effective_workspace_id()
        async with self.sessions() as session:
            stmt = select(ProjectRow)
            if ws_id is not None:
                if include_unassigned:
                    stmt = stmt.where(
                        or_(
                            ProjectRow.workspace_id == ws_id,
                            ProjectRow.workspace_id.is_(None),
                        )
                    )
                else:
                    stmt = stmt.where(ProjectRow.workspace_id == ws_id)
            else:
                stmt = stmt.where(ProjectRow.workspace_id.is_(None))
            stmt = stmt.order_by(ProjectRow.created_at.desc())
            rows = await session.scalars(stmt)
            return [_project_from_row(row) for row in rows]

    async def slug_exists(self, slug: str) -> bool:
        async with self.sessions() as session:
            return (
                await session.scalar(select(ProjectRow.id).where(ProjectRow.slug == slug))
                is not None
            )

    async def update_project(self, project: Project, audit_event: ProjectAuditEvent) -> None:
        ws_id = self._effective_workspace_id()
        try:
            async with self.sessions.begin() as session:
                row = await session.scalar(
                    select(ProjectRow).where(ProjectRow.id == str(project.id))
                )
                if row is None:
                    raise NotFoundError(f"Project '{project.id}' was not found")
                row_ws = self._row_workspace_id(row)
                if ws_id is not None:
                    if row_ws != ws_id:
                        raise NotFoundError(f"Project '{project.id}' was not found")
                else:
                    if row_ws is not None:
                        raise NotFoundError(f"Project '{project.id}' was not found")
                effective_ws = project.workspace_id if project.workspace_id is not None else row_ws
                payload = project.model_dump(mode="json")
                payload["workspace_id"] = effective_ws
                row.name = project.name
                row.description = project.description
                row.status = project.status.value
                row.workspace_id = effective_ws
                row.updated_at = project.updated_at
                row.payload = payload
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Project update conflicts with existing state") from exc

    async def claim_unassigned_project(
        self,
        identifier: str,
        workspace_id: str | None = None,
        *,
        actor: str = "operator",
        timestamp: datetime | None = None,
    ) -> Project:
        target_ws = self._effective_workspace_id(workspace_id)
        if not target_ws:
            raise ValueError("workspace_id is required to claim an unassigned project")
        now_ts = timestamp or datetime.now(UTC)
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(ProjectRow).where(
                    or_(
                        ProjectRow.id == identifier,
                        ProjectRow.slug == identifier,
                    )
                )
            )
            if row is None:
                raise NotFoundError(f"Project '{identifier}' was not found")
            row_ws = self._row_workspace_id(row)
            if row_ws is not None and row_ws != target_ws:
                raise ConflictError(
                    f"Project '{identifier}' is already assigned to another workspace"
                )
            if row_ws == target_ws:
                return _project_from_row(row)
            updated_project = _project_from_row(row).model_copy(
                update={"workspace_id": target_ws, "updated_at": now_ts}
            )
            payload = updated_project.model_dump(mode="json")
            payload["workspace_id"] = target_ws
            stmt = (
                sa.update(ProjectRow)
                .where(
                    ProjectRow.id == row.id,
                    or_(
                        ProjectRow.workspace_id.is_(None),
                        ProjectRow.workspace_id == target_ws,
                    ),
                )
                .values(
                    workspace_id=target_ws,
                    updated_at=now_ts,
                    payload=payload,
                )
            )
            result = await session.execute(stmt)
            if int(getattr(result, "rowcount", 0) or 0) != 1:
                raise ConflictError(
                    f"Project '{identifier}' is already assigned to another workspace"
                )
            audit_event = ProjectAuditEvent(
                project_id=updated_project.id,
                event_type="project_updated",
                actor=actor,
                payload={"claimed_workspace_id": target_ws, "actor": actor},
                created_at=now_ts,
            )
            session.add(self._event(audit_event))
            return updated_project

    async def audit_events(self, project_id: UUID) -> list[ProjectAuditEvent]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.project_id == str(project_id))
                .order_by(AuditEventRow.created_at.asc(), AuditEventRow.id.asc())
            )
            events: list[ProjectAuditEvent] = []
            for row in rows:
                raw_payload = row.payload if isinstance(row.payload, dict) else {}
                if (
                    "id" in raw_payload
                    and "project_id" in raw_payload
                    and "event_type" in raw_payload
                ):
                    events.append(ProjectAuditEvent.model_validate(raw_payload))
                else:
                    events.append(
                        ProjectAuditEvent.model_validate(
                            {
                                "id": row.id,
                                "project_id": row.project_id,
                                "event_type": row.event_type,
                                "actor": row.actor,
                                "payload": raw_payload,
                                "created_at": row.created_at,
                            }
                        )
                    )
            return events

    async def create_raw_event(self, event: RawEvent) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(self._raw_event(event))
        except IntegrityError as exc:
            raise ConflictError("Raw event already exists") from exc

    async def create_raw_events(self, events: list[RawEvent]) -> None:
        if not events:
            return
        try:
            async with self.sessions.begin() as session:
                session.add_all([self._raw_event(event) for event in events])
        except IntegrityError as exc:
            raise ConflictError("One or more raw events conflict with existing state") from exc

    async def list_raw_events(
        self, project_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[RawEvent]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(RawEventRow)
                .where(RawEventRow.project_id == str(project_id))
                .order_by(RawEventRow.created_at.desc(), RawEventRow.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return [RawEvent.model_validate(row.payload) for row in rows]

    async def get_raw_event(self, project_id: UUID, event_id: UUID) -> RawEvent:
        async with self.sessions() as session:
            row = await session.scalar(
                select(RawEventRow).where(
                    RawEventRow.project_id == str(project_id),
                    RawEventRow.id == str(event_id),
                )
            )
            if row is None:
                raise NotFoundError("Raw event not found")
            return RawEvent.model_validate(row.payload)

    async def get_raw_event_by_hash(self, project_id: UUID, content_hash: str) -> RawEvent | None:
        async with self.sessions() as session:
            row = await session.scalar(
                select(RawEventRow).where(
                    RawEventRow.project_id == str(project_id),
                    RawEventRow.content_hash == content_hash,
                )
            )
            return RawEvent.model_validate(row.payload) if row else None

    async def count_raw_events(self, project_id: UUID) -> int:
        async with self.sessions() as session:
            return (
                await session.scalar(
                    select(func.count(RawEventRow.id)).where(
                        RawEventRow.project_id == str(project_id)
                    )
                )
                or 0
            )

    async def create_decision_service(self, service: DecisionService) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    DecisionServiceRow(
                        id=str(service.id),
                        project_id=str(service.project_id),
                        slug=service.slug,
                        name=service.name,
                        status=service.status.value,
                        created_at=service.created_at,
                        updated_at=service.updated_at,
                        payload=service.model_dump(mode="json"),
                    )
                )
                await session.flush()
                initial_choices = [
                    {
                        "key": c.key,
                        "label": c.label,
                        "description": c.description,
                        "aliases": list(c.aliases),
                    }
                    for c in service.nodes[0].choices
                    if c.key != "UNKNOWN"
                ]
                await session.execute(
                    sa.text(
                        "INSERT INTO service_versions"
                        " (id, service_id, version_number, choices, origin,"
                        "  rationale, actor, created_at)"
                        " VALUES (:id, :sid, :number, :choices, 'initial',"
                        " 'genesis snapshot', 'system', :created)"
                    ),
                    {
                        "id": str(service.active_version_id or uuid4()),
                        "sid": str(service.id),
                        "number": service.version_number,
                        "choices": json.dumps(initial_choices),
                        "created": service.created_at,
                    },
                )
        except IntegrityError as exc:
            msg = "Decision service with this slug already exists in project"
            raise ConflictError(msg) from exc

    async def get_decision_service(self, project_id: UUID, identifier: str) -> DecisionService:
        async with self.sessions() as session:
            row = await session.scalar(
                select(DecisionServiceRow).where(
                    DecisionServiceRow.project_id == str(project_id),
                    or_(
                        DecisionServiceRow.id == identifier,
                        DecisionServiceRow.slug == identifier,
                    ),
                )
            )
            if row is None:
                raise NotFoundError("Decision service not found")
            return DecisionService.model_validate(row.payload)

    async def list_decision_services(self, project_id: UUID) -> list[DecisionService]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DecisionServiceRow)
                .where(DecisionServiceRow.project_id == str(project_id))
                .order_by(DecisionServiceRow.created_at.asc(), DecisionServiceRow.name.asc())
            )
            return [DecisionService.model_validate(row.payload) for row in rows]

    async def update_decision_service(self, service: DecisionService) -> None:
        try:
            async with self.sessions.begin() as session:
                row = await session.scalar(
                    select(DecisionServiceRow).where(
                        DecisionServiceRow.project_id == str(service.project_id),
                        DecisionServiceRow.id == str(service.id),
                    )
                )
                if row is None:
                    raise NotFoundError("Decision service not found")
                row.name = service.name
                row.status = service.status.value
                row.updated_at = service.updated_at
                row.payload = service.model_dump(mode="json")
                latest = await session.execute(
                    sa.text(
                        "SELECT id, version_number FROM service_versions"
                        " WHERE service_id = :sid ORDER BY version_number DESC LIMIT 1"
                    ),
                    {"sid": str(service.id)},
                )
                latest_row = latest.first()
                latest_num = int(latest_row.version_number) if latest_row else 0
                if service.version_number > latest_num:
                    current_choices = [
                        {
                            "key": c.key,
                            "label": c.label,
                            "description": c.description,
                            "aliases": list(c.aliases),
                        }
                        for c in service.nodes[0].choices
                        if c.key != "UNKNOWN"
                    ]
                    await session.execute(
                        sa.text(
                            "INSERT INTO service_versions"
                            " (id, service_id, version_number, parent_version_id, choices,"
                            "  origin, rationale, actor, created_at)"
                            " VALUES (:id, :sid, :number, :parent, :choices,"
                            " 'update', 'service definition updated', 'system', :created)"
                        ),
                        {
                            "id": str(service.active_version_id or uuid4()),
                            "sid": str(service.id),
                            "number": service.version_number,
                            "parent": latest_row.id if latest_row else None,
                            "choices": json.dumps(current_choices),
                            "created": service.updated_at,
                        },
                    )
        except IntegrityError as exc:
            raise ConflictError("Decision service update conflicts with existing state") from exc

    async def create_decision_run(self, run: DecisionRun) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    DecisionRunRow(
                        id=str(run.id),
                        project_id=str(run.project_id),
                        raw_event_id=str(run.raw_event_id),
                        decision_service_id=str(run.decision_service_id),
                        decision_node_id=str(run.decision_node_id),
                        decision_service_version_id=(
                            str(run.decision_service_version_id)
                            if run.decision_service_version_id is not None
                            else None
                        ),
                        service_hash=run.service_hash,
                        provider=run.provider,
                        model=run.model,
                        execution_mode=run.execution_mode,
                        real_inference=run.real_inference,
                        selected_choice=run.selected_choice,
                        supervision_outcome=run.supervision_outcome,
                        top_probability=run.top_probability,
                        margin=run.margin,
                        unknown_probability=run.unknown_probability,
                        latency_ms=run.latency_ms,
                        created_at=run.created_at,
                        payload=run.model_dump(mode="json"),
                    )
                )
                await session.flush()
                pinned_vid = run.pinned_version_id or run.decision_service_version_id
                session.add(
                    DecisionRunCheckpointRow(
                        run_id=str(run.id),
                        project_id=str(run.project_id),
                        decision_service_id=str(run.decision_service_id),
                        run_status=run.run_status,
                        current_node_key=run.current_node_key,
                        next_node_key=run.next_node_key,
                        selected_choice=run.selected_choice,
                        supervision_outcome=run.supervision_outcome,
                        supervision_reason=run.supervision_reason,
                        completed_steps=list(run.completed_steps or run.steps),
                        state_snapshot=dict(run.state_snapshot),
                        pinned_version_id=str(pinned_vid) if pinned_vid is not None else None,
                        pinned_version_number=run.pinned_version_number,
                        pinned_service_hash=run.pinned_service_hash or run.service_hash,
                        pending_operation=run.pending_operation,
                        latency_ms=run.latency_ms,
                        claim_token=run.claim_token,
                        claimed_by=run.claimed_by,
                        claimed_at=run.claimed_at,
                        resumed_by=run.resumed_by,
                        resumed_at=run.resumed_at,
                        resume_rationale=run.resume_rationale,
                        cancelled_by=run.cancelled_by,
                        cancelled_at=run.cancelled_at,
                        cancel_reason=run.cancel_reason,
                        failure_reason=run.failure_reason,
                        updated_at=run.created_at,
                    )
                )
                if run.run_status == "paused":
                    paused_audit = ProjectAuditEvent(
                        project_id=run.project_id,
                        event_type="decision_run_paused",
                        actor="system",
                        payload={
                            "run_id": str(run.id),
                            "decision_service_id": str(run.decision_service_id),
                            "current_node_key": run.current_node_key,
                            "next_node_key": run.next_node_key,
                            "selected_choice": run.selected_choice,
                            "supervision_outcome": run.supervision_outcome,
                            "pinned_version_number": run.pinned_version_number,
                            "pinned_service_hash": run.pinned_service_hash or run.service_hash,
                        },
                        created_at=run.created_at,
                    )
                    session.add(self._event(paused_audit))
                await self._roll_up_usage(session, run, error=False)
        except IntegrityError as exc:
            msg = "Decision run already exists or referenced entities missing"
            raise ConflictError(msg) from exc

    @staticmethod
    def _apply_checkpoint(run: DecisionRun, cp: DecisionRunCheckpointRow | None) -> DecisionRun:
        if cp is None:
            return run
        completed_steps = list(cp.completed_steps or run.steps)
        last_step = completed_steps[-1] if completed_steps else {}
        node_id = run.decision_node_id
        if last_step.get("node_id"):
            try:
                node_id = UUID(str(last_step["node_id"]))
            except ValueError:
                node_id = run.decision_node_id
        probs = (
            dict(last_step["probabilities"])
            if isinstance(last_step.get("probabilities"), dict)
            else run.probabilities
        )
        top_p = (
            float(last_step["top_probability"])
            if last_step.get("top_probability") is not None
            else run.top_probability
        )
        second_p = (
            float(last_step["second_probability"])
            if last_step.get("second_probability") is not None
            else run.second_probability
        )
        margin_val = (
            float(last_step["margin"]) if last_step.get("margin") is not None else run.margin
        )
        unk_p = (
            float(last_step["unknown_probability"])
            if last_step.get("unknown_probability") is not None
            else run.unknown_probability
        )
        pinned_vid = UUID(cp.pinned_version_id) if cp.pinned_version_id else run.pinned_version_id
        return run.model_copy(
            update={
                "decision_node_id": node_id,
                "selected_choice": cp.selected_choice,
                "probabilities": probs,
                "top_probability": top_p,
                "second_probability": second_p,
                "margin": margin_val,
                "unknown_probability": unk_p,
                "supervision_outcome": cp.supervision_outcome,
                "supervision_reason": cp.supervision_reason,
                "latency_ms": float(cp.latency_ms),
                "steps": completed_steps,
                "completed_steps": completed_steps,
                "state_snapshot": dict(cp.state_snapshot or {}),
                "run_status": cp.run_status,
                "current_node_key": cp.current_node_key,
                "next_node_key": cp.next_node_key,
                "pinned_version_id": pinned_vid,
                "pinned_version_number": int(cp.pinned_version_number),
                "pinned_service_hash": cp.pinned_service_hash,
                "pending_operation": cp.pending_operation,
                "claim_token": cp.claim_token,
                "claimed_by": cp.claimed_by,
                "claimed_at": cp.claimed_at,
                "resumed_by": cp.resumed_by,
                "resumed_at": cp.resumed_at,
                "resume_rationale": cp.resume_rationale,
                "cancelled_by": cp.cancelled_by,
                "cancelled_at": cp.cancelled_at,
                "cancel_reason": cp.cancel_reason,
                "failure_reason": cp.failure_reason,
            }
        )

    async def _overlay_checkpoints(
        self, session: AsyncSession, runs: list[DecisionRun]
    ) -> list[DecisionRun]:
        if not runs:
            return []
        run_ids = [str(r.id) for r in runs]
        cp_rows = await session.scalars(
            select(DecisionRunCheckpointRow).where(DecisionRunCheckpointRow.run_id.in_(run_ids))
        )
        by_id = {cp.run_id: cp for cp in cp_rows}
        return [self._apply_checkpoint(r, by_id.get(str(r.id))) for r in runs]

    async def reconstruct_service_from_version(
        self,
        service: DecisionService,
        version_id: UUID | str | None,
        version_number: int | None,
        pending_operation: dict[str, Any] | None = None,
    ) -> DecisionService | None:
        if isinstance(pending_operation, dict) and isinstance(
            pending_operation.get("service_snapshot"), dict
        ):
            try:
                return DecisionService.model_validate(pending_operation["service_snapshot"])
            except Exception:
                pass
        async with self.sessions() as session:
            row = None
            if version_id is not None:
                res = await session.execute(
                    sa.text(
                        "SELECT id, version_number, choices FROM service_versions WHERE id = :vid"
                    ),
                    {"vid": str(version_id)},
                )
                row = res.first()
            if row is None and version_number is not None:
                res = await session.execute(
                    sa.text(
                        "SELECT id, version_number, choices FROM service_versions"
                        " WHERE service_id = :sid AND version_number = :vnum"
                    ),
                    {"sid": str(service.id), "vnum": int(version_number)},
                )
                row = res.first()
            if row is None:
                return None
            raw_choices = json.loads(row.choices) if isinstance(row.choices, str) else row.choices
            if not isinstance(raw_choices, list) or not raw_choices:
                return None
            choice_objs: list[DecisionServiceChoice] = []
            for c in raw_choices:
                if isinstance(c, dict) and c.get("key"):
                    choice_objs.append(
                        DecisionServiceChoice(
                            key=str(c["key"]).upper(),
                            label=str(c.get("label") or c["key"]),
                            description=str(c.get("description") or ""),
                            aliases=tuple(str(a) for a in (c.get("aliases") or [])),
                        )
                    )
            if not any(c.key == "UNKNOWN" for c in choice_objs):
                choice_objs.append(UNKNOWN_CHOICE)
            updated_first_node = service.nodes[0].model_copy(update={"choices": tuple(choice_objs)})
            updated_nodes = (updated_first_node, *service.nodes[1:])
            return service.model_copy(
                update={
                    "nodes": updated_nodes,
                    "version_number": int(row.version_number),
                    "active_version_id": UUID(str(row.id)),
                }
            )

    async def claim_decision_run_for_resume(
        self,
        project_id: UUID | str,
        run_id: UUID | str,
        *,
        operator: str,
        claim_token: str,
        stale_claim_timeout_seconds: float = 300.0,
        force_recover_stale_claim: bool = False,
    ) -> None:
        pid = str(project_id)
        rid = str(run_id)
        async with self._claim_lock:
            async with self._session_factory() as session:
                now_ts = datetime.now(UTC)
                stale_cutoff = (
                    now_ts
                    if force_recover_stale_claim
                    else (now_ts - timedelta(seconds=stale_claim_timeout_seconds))
                )
                resuming_cond = (
                    DecisionRunCheckpointRow.run_status == "resuming"
                    if force_recover_stale_claim
                    else sa.and_(
                        DecisionRunCheckpointRow.run_status == "resuming",
                        DecisionRunCheckpointRow.claimed_at.is_not(None),
                        DecisionRunCheckpointRow.claimed_at <= stale_cutoff,
                    )
                )
                stmt = (
                    sa.update(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == rid,
                        DecisionRunCheckpointRow.project_id == pid,
                        or_(
                            DecisionRunCheckpointRow.run_status == "paused",
                            resuming_cond,
                        ),
                    )
                    .values(
                        run_status="resuming",
                        claim_token=claim_token,
                        claimed_by=operator,
                        claimed_at=now_ts,
                        updated_at=now_ts,
                    )
                )
                result = await session.execute(stmt)
                if int(getattr(result, "rowcount", 0) or 0) != 1:
                    cp = await session.scalar(
                        select(DecisionRunCheckpointRow).where(
                            DecisionRunCheckpointRow.run_id == rid,
                            DecisionRunCheckpointRow.project_id == pid,
                        )
                    )
                    if cp is None:
                        raise NotFoundError("Decision run checkpoint not found")
                    if cp.run_status == "cancelled":
                        raise ConflictError("Decision run is already cancelled")
                    if cp.run_status == "resuming":
                        raise ConflictError("Decision run is already being resumed")
                    if cp.run_status == "completed":
                        if cp.resumed_at is not None:
                            raise ConflictError("Decision run has already been resumed")
                        raise ConflictError(
                            f"Decision run cannot be resumed from supervision outcome "
                            f"'{cp.supervision_outcome}'"
                        )
                    raise ConflictError(
                        f"Decision run cannot be resumed (status is '{cp.run_status}')"
                    )
                await session.commit()

    async def release_decision_run_claim(
        self,
        project_id: UUID | str,
        run_id: UUID | str,
        *,
        claim_token: str,
    ) -> None:
        pid = str(project_id)
        rid = str(run_id)
        now_ts = datetime.now(UTC)
        async with self._claim_lock:
            async with self._session_factory() as session:
                stmt = (
                    sa.update(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == rid,
                        DecisionRunCheckpointRow.project_id == pid,
                        DecisionRunCheckpointRow.run_status == "resuming",
                        DecisionRunCheckpointRow.claim_token == claim_token,
                    )
                    .values(
                        run_status="paused",
                        claim_token=None,
                        claimed_by=None,
                        claimed_at=None,
                        updated_at=now_ts,
                    )
                )
                await session.execute(stmt)
                await session.commit()

    async def recover_stale_decision_run_checkpoint(
        self,
        project_id: UUID | str,
        run_id: UUID | str,
        *,
        operator: str = "operator",
        rationale: str = "",
        stale_after_seconds: float = 0.0,
    ) -> DecisionRun:
        pid = str(project_id)
        rid = str(run_id)
        now_ts = datetime.now(UTC)
        stale_cutoff = now_ts - timedelta(seconds=max(0.0, stale_after_seconds))
        async with self._claim_lock:
            async with self.sessions.begin() as session:
                run_row = await session.scalar(
                    select(DecisionRunRow).where(
                        DecisionRunRow.project_id == pid,
                        DecisionRunRow.id == rid,
                    )
                )
                if run_row is None:
                    raise NotFoundError("Decision run not found")
                cp = await session.scalar(
                    select(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == rid,
                        DecisionRunCheckpointRow.project_id == pid,
                    )
                    .with_for_update()
                )
                if cp is None:
                    raise NotFoundError("Decision run checkpoint not found")
                if cp.run_status != "resuming":
                    raise ConflictError(
                        f"Decision run cannot be recovered from status '{cp.run_status}'"
                    )
                if stale_after_seconds > 0 and cp.claimed_at is not None:
                    claimed_utc = (
                        cp.claimed_at.replace(tzinfo=UTC)
                        if cp.claimed_at.tzinfo is None
                        else cp.claimed_at.astimezone(UTC)
                    )
                    if claimed_utc > stale_cutoff:
                        raise ConflictError("Decision run resume claim is not yet stale")
                cp.run_status = "paused"
                cp.claim_token = None
                cp.claimed_by = None
                cp.claimed_at = None
                cp.updated_at = now_ts
                recovered_audit = ProjectAuditEvent(
                    project_id=UUID(pid),
                    event_type="decision_run_paused",
                    actor=operator,
                    payload={
                        "run_id": rid,
                        "decision_service_id": cp.decision_service_id,
                        "current_node_key": cp.current_node_key,
                        "next_node_key": cp.next_node_key,
                        "recovered_from_resuming": True,
                        "operator": operator,
                        "rationale": rationale,
                    },
                    created_at=now_ts,
                )
                session.add(self._event(recovered_audit))
                base_run = DecisionRun.model_validate(run_row.payload)
                return self._apply_checkpoint(base_run, cp)

    async def save_resumed_decision_run(
        self,
        run: DecisionRun,
        *,
        operator: str,
        rationale: str | None = None,
        claim_token: str | None = None,
    ) -> DecisionRun:
        now_ts = run.resumed_at or datetime.now(UTC)
        async with self._claim_lock:
            async with self.sessions.begin() as session:
                cp = await session.scalar(
                    select(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == str(run.id),
                        DecisionRunCheckpointRow.project_id == str(run.project_id),
                    )
                    .with_for_update()
                )
                if cp is not None:
                    if cp.run_status == "cancelled":
                        raise ConflictError("Decision run is already cancelled")
                    if claim_token is not None:
                        if cp.run_status != "resuming" or cp.claim_token != claim_token:
                            raise ConflictError("Decision run resume claim is no longer valid")
                    elif cp.resumed_at is not None and cp.run_status == "completed":
                        raise ConflictError("Decision run has already been resumed")
                    cp.run_status = run.run_status
                    cp.current_node_key = run.current_node_key
                    cp.next_node_key = run.next_node_key
                    cp.selected_choice = run.selected_choice
                    cp.supervision_outcome = run.supervision_outcome
                    cp.supervision_reason = run.supervision_reason
                    cp.completed_steps = list(run.completed_steps or run.steps)
                    cp.state_snapshot = dict(run.state_snapshot)
                    cp.pending_operation = run.pending_operation
                    cp.latency_ms = float(run.latency_ms)
                    cp.claim_token = None
                    cp.claimed_by = None
                    cp.claimed_at = None
                    cp.resumed_by = operator
                    cp.resumed_at = now_ts
                    cp.resume_rationale = rationale
                    cp.updated_at = now_ts
                else:
                    pinned_vid = run.pinned_version_id or run.decision_service_version_id
                    session.add(
                        DecisionRunCheckpointRow(
                            run_id=str(run.id),
                            project_id=str(run.project_id),
                            decision_service_id=str(run.decision_service_id),
                            run_status=run.run_status,
                            current_node_key=run.current_node_key,
                            next_node_key=run.next_node_key,
                            selected_choice=run.selected_choice,
                            supervision_outcome=run.supervision_outcome,
                            supervision_reason=run.supervision_reason,
                            completed_steps=list(run.completed_steps or run.steps),
                            state_snapshot=dict(run.state_snapshot),
                            pinned_version_id=str(pinned_vid) if pinned_vid is not None else None,
                            pinned_version_number=run.pinned_version_number,
                            pinned_service_hash=run.pinned_service_hash or run.service_hash,
                            pending_operation=run.pending_operation,
                            latency_ms=float(run.latency_ms),
                            claim_token=None,
                            claimed_by=None,
                            claimed_at=None,
                            resumed_by=operator,
                            resumed_at=now_ts,
                            resume_rationale=rationale,
                            updated_at=now_ts,
                        )
                    )

                resumed_audit = ProjectAuditEvent(
                    project_id=run.project_id,
                    event_type="decision_run_resumed",
                    actor=operator,
                    payload={
                        "run_id": str(run.id),
                        "decision_service_id": str(run.decision_service_id),
                        "selected_choice": run.selected_choice,
                        "supervision_outcome": run.supervision_outcome,
                        "run_status": run.run_status,
                        "current_node_key": run.current_node_key,
                        "next_node_key": run.next_node_key,
                        "steps_count": len(run.steps),
                        "rationale": rationale,
                    },
                    created_at=now_ts,
                )
                session.add(self._event(resumed_audit))

                if run.run_status == "paused":
                    paused_audit = ProjectAuditEvent(
                        project_id=run.project_id,
                        event_type="decision_run_paused",
                        actor="system",
                        payload={
                            "run_id": str(run.id),
                            "decision_service_id": str(run.decision_service_id),
                            "current_node_key": run.current_node_key,
                            "next_node_key": run.next_node_key,
                            "selected_choice": run.selected_choice,
                            "supervision_outcome": run.supervision_outcome,
                        },
                        created_at=now_ts,
                    )
                    session.add(self._event(paused_audit))

        return run.model_copy(
            update={
                "claim_token": None,
                "claimed_by": None,
                "claimed_at": None,
            }
        )

    async def mark_decision_run_failed(
        self,
        project_id: UUID,
        run_id: UUID,
        *,
        operator: str,
        failure_reason: str,
    ) -> None:
        now_ts = datetime.now(UTC)
        async with self._claim_lock:
            async with self.sessions.begin() as session:
                cp = await session.scalar(
                    select(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == str(run_id),
                        DecisionRunCheckpointRow.project_id == str(project_id),
                    )
                    .with_for_update()
                )
                if cp is not None:
                    cp.run_status = "failed"
                    cp.claim_token = None
                    cp.claimed_by = None
                    cp.claimed_at = None
                    cp.failure_reason = failure_reason
                    cp.updated_at = now_ts
                failed_audit = ProjectAuditEvent(
                    project_id=project_id,
                    event_type="decision_run_failed",
                    actor=operator,
                    payload={
                        "run_id": str(run_id),
                        "failure_reason": failure_reason,
                    },
                    created_at=now_ts,
                )
                session.add(self._event(failed_audit))

    async def cancel_decision_run_checkpoint(
        self,
        project_id: UUID,
        run_id: UUID,
        *,
        operator: str,
        reason: str,
    ) -> DecisionRun:
        now_ts = datetime.now(UTC)
        async with self._claim_lock:
            async with self.sessions.begin() as session:
                run_row = await session.scalar(
                    select(DecisionRunRow).where(
                        DecisionRunRow.project_id == str(project_id),
                        DecisionRunRow.id == str(run_id),
                    )
                )
                if run_row is None:
                    raise NotFoundError("Decision run not found")
                cp = await session.scalar(
                    select(DecisionRunCheckpointRow)
                    .where(
                        DecisionRunCheckpointRow.run_id == str(run_id),
                        DecisionRunCheckpointRow.project_id == str(project_id),
                    )
                    .with_for_update()
                )
                if cp is not None:
                    if cp.run_status == "cancelled":
                        raise ConflictError("Decision run is already cancelled")
                    if cp.run_status == "completed":
                        raise ConflictError("Cannot cancel a completed decision run")
                    if cp.run_status == "resuming":
                        raise ConflictError("Cannot cancel a decision run while it is resuming")
                    if cp.run_status != "paused":
                        raise ConflictError(
                            f"Cannot cancel a decision run with status '{cp.run_status}'"
                        )
                    cp.run_status = "cancelled"
                    cp.claim_token = None
                    cp.claimed_by = None
                    cp.claimed_at = None
                    cp.cancelled_by = operator
                    cp.cancelled_at = now_ts
                    cp.cancel_reason = reason
                    cp.pending_operation = None
                    cp.next_node_key = None
                    cp.state_snapshot = {**dict(cp.state_snapshot or {}), "status": "cancelled"}
                    cp.updated_at = now_ts

                cancelled_audit = ProjectAuditEvent(
                    project_id=project_id,
                    event_type="decision_run_cancelled",
                    actor=operator,
                    payload={
                        "run_id": str(run_id),
                        "cancelled_by": operator,
                        "reason": reason,
                    },
                    created_at=now_ts,
                )
                session.add(self._event(cancelled_audit))
                base_run = DecisionRun.model_validate(run_row.payload)
                return self._apply_checkpoint(base_run, cp)

    async def _roll_up_usage(self, session: AsyncSession, run: DecisionRun, *, error: bool) -> None:
        usage_date = (
            run.created_at.date()
            if run.created_at.tzinfo is None
            else run.created_at.astimezone().date()
        )
        statement = sa.text(
            "INSERT INTO provider_usage"
            " (project_id, provider, model, usage_date, calls, errors, input_tokens,"
            "  output_tokens, estimated_cost, latency_ms_total)"
            " VALUES (:project_id, :provider, :model, :usage_date, :calls, :errors,"
            "         :input_tokens, :output_tokens, :estimated_cost, :latency)"
            " ON CONFLICT (project_id, provider, usage_date) DO UPDATE SET"
            " calls = provider_usage.calls + excluded.calls,"
            " errors = provider_usage.errors + excluded.errors,"
            " input_tokens = provider_usage.input_tokens + excluded.input_tokens,"
            " output_tokens = provider_usage.output_tokens + excluded.output_tokens,"
            " estimated_cost = provider_usage.estimated_cost + excluded.estimated_cost,"
            " latency_ms_total = provider_usage.latency_ms_total + excluded.latency_ms_total"
        )
        await session.execute(
            statement,
            {
                "project_id": str(run.project_id),
                "provider": run.provider,
                "model": run.model or "",
                "usage_date": usage_date,
                "calls": 0 if error else 1,
                "errors": 1 if error else 0,
                "input_tokens": run.provider_metadata.get("input_tokens") or 0,
                "output_tokens": run.provider_metadata.get("output_tokens") or 0,
                "estimated_cost": run.provider_metadata.get("estimated_cost") or 0.0,
                "latency": run.latency_ms or 0.0,
            },
        )

    async def record_provider_error(
        self, project_id: UUID, provider: str, model: str, latency_ms: float
    ) -> None:
        """Count a provider failure in the usage rollup without persisting a run."""

        class _UsageOnly:  # minimal carrier for _roll_up_usage
            def __init__(self) -> None:
                self.project_id = project_id
                self.provider = provider
                self.model = model
                self.latency_ms = latency_ms
                self.created_at = datetime.now(UTC)
                self.provider_metadata: dict[str, Any] = {}

        async with self.sessions.begin() as session:
            await self._roll_up_usage(session, _UsageOnly(), error=True)  # type: ignore[arg-type]

    async def provider_usage(
        self, project_id: UUID, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT provider, model, usage_date, calls, errors, input_tokens,"
                    " output_tokens, estimated_cost, latency_ms_total"
                    " FROM provider_usage WHERE project_id = :project_id"
                    " AND usage_date BETWEEN :date_from AND :date_to"
                    " ORDER BY usage_date DESC, provider"
                ),
                {
                    "project_id": str(project_id),
                    "date_from": date_type.fromisoformat(date_from),
                    "date_to": date_type.fromisoformat(date_to),
                },
            )
            return [
                {
                    "provider": row.provider,
                    "model": row.model,
                    "date": str(row.usage_date),
                    "calls": row.calls,
                    "errors": row.errors,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "estimated_cost": row.estimated_cost,
                    "avg_latency_ms": round(row.latency_ms_total / row.calls, 2)
                    if row.calls
                    else 0.0,
                }
                for row in rows
            ]

    async def list_decision_runs(
        self, project_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[DecisionRun]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DecisionRunRow)
                .where(DecisionRunRow.project_id == str(project_id))
                .order_by(DecisionRunRow.created_at.desc(), DecisionRunRow.id.desc())
                .limit(limit)
                .offset(offset)
            )
            runs = [DecisionRun.model_validate(row.payload) for row in rows]
            return await self._overlay_checkpoints(session, runs)

    async def get_decision_run(self, project_id: UUID, run_id: UUID) -> DecisionRun:
        async with self.sessions() as session:
            row = await session.scalar(
                select(DecisionRunRow).where(
                    DecisionRunRow.project_id == str(project_id),
                    DecisionRunRow.id == str(run_id),
                )
            )
            if row is None:
                raise NotFoundError("Decision run not found")
            run = DecisionRun.model_validate(row.payload)
            overlaid = await self._overlay_checkpoints(session, [run])
            return overlaid[0]

    async def list_runs_for_service(
        self, project_id: UUID, service_id: UUID, limit: int = 50
    ) -> list[DecisionRun]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DecisionRunRow)
                .where(
                    DecisionRunRow.project_id == str(project_id),
                    DecisionRunRow.decision_service_id == str(service_id),
                )
                .order_by(DecisionRunRow.created_at.desc(), DecisionRunRow.id.desc())
                .limit(limit)
            )
            runs = [DecisionRun.model_validate(row.payload) for row in rows]
            return await self._overlay_checkpoints(session, runs)

    async def count_decision_runs(self, project_id: UUID) -> int:
        async with self.sessions() as session:
            return (
                await session.scalar(
                    select(func.count(DecisionRunRow.id)).where(
                        DecisionRunRow.project_id == str(project_id)
                    )
                )
                or 0
            )

    async def analytics_runs(self, project_id: UUID) -> list[DecisionRun]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DecisionRunRow).where(DecisionRunRow.project_id == str(project_id))
            )
            runs = [DecisionRun.model_validate(row.payload) for row in rows]
            return await self._overlay_checkpoints(session, runs)

    async def save_choice_candidate(
        self, candidate: ChoiceCandidate, event: ProjectAuditEvent
    ) -> None:
        async with self.sessions.begin() as session:
            service_row = await session.get(DecisionServiceRow, str(candidate.decision_service_id))
            if service_row is None or service_row.project_id != str(candidate.project_id):
                raise NotFoundError("Decision service not found")
            if (
                service_hash(DecisionService.model_validate(service_row.payload))
                != candidate.base_service_hash
            ):
                raise ConflictError("Decision service changed during proposal")
            for run_id in candidate.evidence_run_ids:
                run_row = await session.get(DecisionRunRow, str(run_id))
                if (
                    run_row is None
                    or run_row.project_id != str(candidate.project_id)
                    or run_row.decision_service_id != str(candidate.decision_service_id)
                    or run_row.selected_choice != "UNKNOWN"
                ):
                    raise ConflictError("Proposal evidence is no longer valid")
            session.add(
                ProjectChoiceCandidateRow(
                    id=str(candidate.id),
                    project_id=str(candidate.project_id),
                    decision_service_id=str(candidate.decision_service_id),
                    status=candidate.status,
                    created_at=candidate.created_at,
                    payload=candidate.model_dump(mode="json"),
                )
            )
            session.add(self._event(event))

    async def list_choice_candidates(self, project_id: UUID) -> list[ChoiceCandidate]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(ProjectChoiceCandidateRow)
                .where(ProjectChoiceCandidateRow.project_id == str(project_id))
                .order_by(ProjectChoiceCandidateRow.created_at.desc())
            )
            return [ChoiceCandidate.model_validate(row.payload) for row in rows]

    async def get_choice_candidate(self, project_id: UUID, candidate_id: UUID) -> ChoiceCandidate:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ProjectChoiceCandidateRow).where(
                    ProjectChoiceCandidateRow.project_id == str(project_id),
                    ProjectChoiceCandidateRow.id == str(candidate_id),
                )
            )
            if row is None:
                raise NotFoundError("Choice candidate not found")
            return ChoiceCandidate.model_validate(row.payload)

    async def reject_choice_candidate(
        self, candidate: ChoiceCandidate, reason: str, event: ProjectAuditEvent
    ) -> ChoiceCandidate:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(ProjectChoiceCandidateRow)
                .where(
                    ProjectChoiceCandidateRow.project_id == str(candidate.project_id),
                    ProjectChoiceCandidateRow.id == str(candidate.id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Choice candidate not found")
            stored = ChoiceCandidate.model_validate(row.payload)
            if stored.status != "candidate":
                raise ConflictError("Only pending candidates can be rejected")
            updated = stored.model_copy(update={"status": "rejected", "rejection_reason": reason})
            row.status = "rejected"
            row.payload = updated.model_dump(mode="json")
            session.add(self._event(event))
            return updated

    async def count_unknown_decision_runs(self, project_id: UUID) -> int:
        async with self.sessions() as session:
            return (
                await session.scalar(
                    select(func.count(DecisionRunRow.id)).where(
                        DecisionRunRow.project_id == str(project_id),
                        DecisionRunRow.selected_choice == "UNKNOWN",
                    )
                )
                or 0
            )

    async def count_pending_choice_candidates(self, project_id: UUID) -> int:
        async with self.sessions() as session:
            return (
                await session.scalar(
                    select(func.count(ProjectChoiceCandidateRow.id)).where(
                        ProjectChoiceCandidateRow.project_id == str(project_id),
                        ProjectChoiceCandidateRow.status == "candidate",
                    )
                )
                or 0
            )

    # ── Evidence Items ───────────────────────────────────────

    async def create_evidence_item(
        self, item: EvidenceItem, audit_event: ProjectAuditEvent
    ) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    EvidenceItemRow(
                        id=str(item.id),
                        project_id=str(item.project_id),
                        raw_event_id=str(item.raw_event_id) if item.raw_event_id else None,
                        decision_run_id=str(item.decision_run_id) if item.decision_run_id else None,
                        decision_service_id=str(item.decision_service_id)
                        if item.decision_service_id
                        else None,
                        evidence_case_id=str(item.evidence_case_id)
                        if item.evidence_case_id
                        else None,
                        trigger_type=item.trigger_type.value,
                        status=item.status.value,
                        diagnosis=item.diagnosis.value if item.diagnosis else None,
                        diagnosis_rationale=item.diagnosis_rationale,
                        selected_choice=item.selected_choice,
                        supervision_outcome=item.supervision_outcome,
                        source=item.source,
                        created_at=item.created_at,
                        resolved_at=item.resolved_at,
                        payload=item.model_dump(mode="json"),
                    )
                )
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Evidence item already exists") from exc

    async def get_evidence_item(self, project_id: UUID, evidence_id: UUID) -> EvidenceItem:
        async with self.sessions() as session:
            row = await session.scalar(
                select(EvidenceItemRow).where(
                    EvidenceItemRow.project_id == str(project_id),
                    EvidenceItemRow.id == str(evidence_id),
                )
            )
            if row is None:
                raise NotFoundError("Evidence item not found")
            return EvidenceItem.model_validate(row.payload)

    async def list_evidence_items(
        self,
        project_id: UUID,
        *,
        status: EvidenceStatus | None = None,
        trigger_type: EvidenceTriggerType | None = None,
        decision_service_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceItem]:
        async with self.sessions() as session:
            stmt = (
                select(EvidenceItemRow)
                .where(EvidenceItemRow.project_id == str(project_id))
                .order_by(EvidenceItemRow.created_at.desc())
            )
            if status is not None:
                stmt = stmt.where(EvidenceItemRow.status == status.value)
            if trigger_type is not None:
                stmt = stmt.where(EvidenceItemRow.trigger_type == trigger_type.value)
            if decision_service_id is not None:
                stmt = stmt.where(EvidenceItemRow.decision_service_id == str(decision_service_id))
            stmt = stmt.offset(offset).limit(limit)
            rows = await session.scalars(stmt)
            return [EvidenceItem.model_validate(r.payload) for r in rows]

    async def update_evidence_item(
        self, item: EvidenceItem, audit_event: ProjectAuditEvent
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(EvidenceItemRow)
                .where(
                    EvidenceItemRow.project_id == str(item.project_id),
                    EvidenceItemRow.id == str(item.id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Evidence item not found")
            row.status = item.status.value
            row.diagnosis = item.diagnosis.value if item.diagnosis else None
            row.diagnosis_rationale = item.diagnosis_rationale
            row.evidence_case_id = str(item.evidence_case_id) if item.evidence_case_id else None
            row.resolved_at = item.resolved_at
            row.payload = item.model_dump(mode="json")
            session.add(self._event(audit_event))

    async def count_evidence_by_status(self, project_id: UUID) -> dict[str, int]:
        async with self.sessions() as session:
            stmt = (
                select(EvidenceItemRow.status, func.count(EvidenceItemRow.id))
                .where(EvidenceItemRow.project_id == str(project_id))
                .group_by(EvidenceItemRow.status)
            )
            rows = await session.execute(stmt)
            return {status: count for status, count in rows}

    # ── Evidence Cases ───────────────────────────────────────

    async def create_evidence_case(
        self, case: EvidenceCase, audit_event: ProjectAuditEvent
    ) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    EvidenceCaseRow(
                        id=str(case.id),
                        project_id=str(case.project_id),
                        decision_service_id=str(case.decision_service_id)
                        if case.decision_service_id
                        else None,
                        status=case.status.value,
                        diagnosis=case.diagnosis.value if case.diagnosis else None,
                        diagnosis_rationale=case.diagnosis_rationale,
                        title=case.title,
                        created_at=case.created_at,
                        updated_at=case.updated_at,
                        payload=case.model_dump(mode="json"),
                    )
                )
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Evidence case already exists") from exc

    async def get_evidence_case(self, project_id: UUID, case_id: UUID) -> EvidenceCase:
        async with self.sessions() as session:
            row = await session.scalar(
                select(EvidenceCaseRow).where(
                    EvidenceCaseRow.project_id == str(project_id),
                    EvidenceCaseRow.id == str(case_id),
                )
            )
            if row is None:
                raise NotFoundError("Evidence case not found")
            return EvidenceCase.model_validate(row.payload)

    async def list_evidence_cases(
        self, project_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[EvidenceCase]:
        async with self.sessions() as session:
            stmt = (
                select(EvidenceCaseRow)
                .where(EvidenceCaseRow.project_id == str(project_id))
                .order_by(EvidenceCaseRow.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            rows = await session.scalars(stmt)
            return [EvidenceCase.model_validate(r.payload) for r in rows]

    async def update_evidence_case(
        self, case: EvidenceCase, audit_event: ProjectAuditEvent
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(EvidenceCaseRow)
                .where(
                    EvidenceCaseRow.project_id == str(case.project_id),
                    EvidenceCaseRow.id == str(case.id),
                )
                .with_for_update()
            )
            if row is None:
                raise NotFoundError("Evidence case not found")
            row.status = case.status.value
            row.diagnosis = case.diagnosis.value if case.diagnosis else None
            row.diagnosis_rationale = case.diagnosis_rationale
            row.title = case.title
            row.updated_at = case.updated_at
            row.payload = case.model_dump(mode="json")
            session.add(self._event(audit_event))

    async def list_case_evidence(self, project_id: UUID, case_id: UUID) -> list[EvidenceItem]:
        async with self.sessions() as session:
            stmt = (
                select(EvidenceItemRow)
                .where(
                    EvidenceItemRow.project_id == str(project_id),
                    EvidenceItemRow.evidence_case_id == str(case_id),
                )
                .order_by(EvidenceItemRow.created_at.desc())
            )
            rows = await session.scalars(stmt)
            return [EvidenceItem.model_validate(r.payload) for r in rows]

    # ── Run Feedback ─────────────────────────────────────────

    async def create_run_feedback(
        self, feedback: RunFeedback, audit_event: ProjectAuditEvent
    ) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    RunFeedbackRow(
                        id=str(feedback.id),
                        project_id=str(feedback.project_id),
                        decision_run_id=str(feedback.decision_run_id),
                        action=feedback.action.value,
                        corrected_choice=feedback.corrected_choice,
                        note=feedback.note,
                        actor=feedback.actor,
                        created_at=feedback.created_at,
                        payload=feedback.model_dump(mode="json"),
                    )
                )
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Run feedback creation failed") from exc

    async def list_run_feedback(self, project_id: UUID, run_id: UUID) -> list[RunFeedback]:
        async with self.sessions() as session:
            stmt = (
                select(RunFeedbackRow)
                .where(
                    RunFeedbackRow.project_id == str(project_id),
                    RunFeedbackRow.decision_run_id == str(run_id),
                )
                .order_by(RunFeedbackRow.created_at.desc())
            )
            rows = await session.scalars(stmt)
            return [RunFeedback.model_validate(r.payload) for r in rows]

    # ── Evolution Summary & Helpers ──────────────────────────

    async def evolution_summary(self, project_id: UUID) -> EvolutionSummary:
        counts = await self.count_evidence_by_status(project_id)
        async with self.sessions() as session:
            open_cases = (
                await session.scalar(
                    select(func.count(EvidenceCaseRow.id)).where(
                        EvidenceCaseRow.project_id == str(project_id),
                        EvidenceCaseRow.status.notin_(["resolved", "dismissed"]),
                    )
                )
                or 0
            )
        total = sum(counts.values())
        return EvolutionSummary(
            pending_evidence=counts.get("pending", 0),
            triaged_evidence=counts.get("triaged", 0),
            ready_for_evolution=counts.get("ready_for_evolution", 0),
            resolved_evidence=counts.get("resolved", 0),
            dismissed_evidence=counts.get("dismissed", 0),
            total_evidence=total,
            open_cases=open_cases,
        )

    async def get_evidence_for_run(self, project_id: UUID, run_id: UUID) -> EvidenceItem | None:
        async with self.sessions() as session:
            row = await session.scalar(
                select(EvidenceItemRow).where(
                    EvidenceItemRow.project_id == str(project_id),
                    EvidenceItemRow.decision_run_id == str(run_id),
                )
            )
            if row is None:
                return None
            return EvidenceItem.model_validate(row.payload)

    _raw_event = staticmethod(raw_event_row)
    _event = staticmethod(audit_event_row)


async def project_exists(sessions: async_sessionmaker[AsyncSession], identifier: str) -> bool:
    ws_id = get_current_workspace_id()
    async with sessions() as session:
        stmt = select(ProjectRow).where(
            or_(
                ProjectRow.id == identifier,
                ProjectRow.slug == identifier,
            )
        )
        if ws_id is not None:
            stmt = stmt.where(ProjectRow.workspace_id == ws_id)
        else:
            stmt = stmt.where(ProjectRow.workspace_id.is_(None))
        row = await session.scalar(stmt)
        return row is not None
