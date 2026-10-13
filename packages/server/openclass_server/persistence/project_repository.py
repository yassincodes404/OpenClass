"""SQL persistence for projects and their audit trail.

Lookup accepts identifier or slug; every stored mutation writes its audit event
in the same transaction so the audit trail cannot drift from project state.
"""

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any
from uuid import UUID

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
    DecisionRun,
    DecisionService,
    Project,
    ProjectAuditEvent,
    RawEvent,
)
from openclass_core.repositories import ConflictError, NotFoundError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.mappers import audit_event_row, raw_event_row
from openclass_server.persistence.tables import (
    AuditEventRow,
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

    async def create_project(self, project: Project, audit_event: ProjectAuditEvent) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    ProjectRow(
                        id=str(project.id),
                        slug=project.slug,
                        owner_id=project.owner_id,
                        status=project.status.value,
                        name=project.name,
                        description=project.description,
                        created_at=project.created_at,
                        updated_at=project.updated_at,
                        payload=project.model_dump(mode="json"),
                    )
                )
                await session.flush()
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Project slug or identifier already exists") from exc

    async def get_project(self, identifier: str) -> Project:
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
                raise NotFoundError("Project not found")
            return Project.model_validate(row.payload)

    async def list_projects(self) -> list[Project]:
        async with self.sessions() as session:
            rows = await session.scalars(select(ProjectRow).order_by(ProjectRow.created_at.desc()))
            return [Project.model_validate(row.payload) for row in rows]

    async def slug_exists(self, slug: str) -> bool:
        async with self.sessions() as session:
            return (
                await session.scalar(select(ProjectRow.id).where(ProjectRow.slug == slug))
                is not None
            )

    async def update_project(self, project: Project, audit_event: ProjectAuditEvent) -> None:
        try:
            async with self.sessions.begin() as session:
                row = await session.scalar(
                    select(ProjectRow).where(ProjectRow.id == str(project.id))
                )
                if row is None:
                    raise NotFoundError("Project not found")
                row.name = project.name
                row.description = project.description
                row.status = project.status.value
                row.updated_at = project.updated_at
                row.payload = project.model_dump(mode="json")
                session.add(self._event(audit_event))
        except IntegrityError as exc:
            raise ConflictError("Project update conflicts with existing state") from exc

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
                await self._roll_up_usage(session, run, error=False)
        except IntegrityError as exc:
            msg = "Decision run already exists or referenced entities missing"
            raise ConflictError(msg) from exc

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
            return [DecisionRun.model_validate(row.payload) for row in rows]

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
            return DecisionRun.model_validate(row.payload)

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
            return [DecisionRun.model_validate(row.payload) for row in rows]

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
            return [DecisionRun.model_validate(row.payload) for row in rows]

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
    async with sessions() as session:
        row = await session.scalar(
            select(ProjectRow).where(
                or_(
                    ProjectRow.id == identifier,
                    ProjectRow.slug == identifier,
                )
            )
        )
        return row is not None
