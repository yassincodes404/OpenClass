"""Public evidence routes over typed services and repository ports."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from openclass_core.evidence import (
    DiagnosisCategory,
    DiagnosisProvider,
    DiagnosisResult,
    EvidenceCase,
    EvidenceItem,
    EvidenceStatus,
    EvidenceTriggerType,
    EvolutionSummary,
    FeedbackAction,
    RunFeedback,
)
from openclass_core.project_evolution import (
    ChoiceCandidateRepository,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import ProviderError
from openclass_core.repositories import NotFoundError

from openclass_server.api.schemas import (
    AddEvidenceToCaseRequest,
    CreateEvidenceCaseRequest,
    SubmitRunFeedbackRequest,
    TransitionEvidenceRequest,
    TriageEvidenceRequest,
)
from openclass_server.provider_config import reject_credentials
from openclass_server.settings import Settings


def evidence_router(
    config: Settings,
    projects: ProjectDomainService,
    project_repository: ChoiceCandidateRepository,
    diagnostician: DiagnosisProvider,
) -> APIRouter:
    router = APIRouter(tags=["evidence"])

    # ── Evidence Endpoints ───────────────────────────────────

    @router.get(
        "/api/v1/projects/{identifier}/evidence",
        response_model=list[EvidenceItem],
    )
    async def list_project_evidence(
        identifier: str,
        status: str | None = None,
        trigger_type: str | None = None,
        decision_service_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[EvidenceItem]:
        st = EvidenceStatus(status) if status else None
        tr = EvidenceTriggerType(trigger_type) if trigger_type else None
        return await projects.list_evidence(
            identifier=identifier,
            status=st,
            trigger_type=tr,
            decision_service_id=decision_service_id,
            limit=limit,
            offset=offset,
        )

    @router.get(
        "/api/v1/projects/{identifier}/evidence/{evidence_id}",
        response_model=EvidenceItem,
    )
    async def get_project_evidence(identifier: str, evidence_id: UUID) -> EvidenceItem:
        return await projects.get_evidence(identifier, evidence_id)

    @router.patch(
        "/api/v1/projects/{identifier}/evidence/{evidence_id}/triage",
        response_model=EvidenceItem,
    )
    async def triage_project_evidence(
        identifier: str, evidence_id: UUID, body: TriageEvidenceRequest
    ) -> EvidenceItem:
        reject_credentials(body.model_dump(mode="json"), config)
        try:
            diag = DiagnosisCategory(body.diagnosis)
        except ValueError as err:
            raise HTTPException(
                status_code=422, detail=f"Invalid diagnosis category: {body.diagnosis}"
            ) from err
        return await projects.triage_evidence(
            identifier=identifier,
            evidence_id=evidence_id,
            diagnosis=diag,
            rationale=body.rationale,
        )

    @router.post(
        "/api/v1/projects/{identifier}/evidence/{evidence_id}/transition",
        response_model=EvidenceItem,
    )
    async def transition_project_evidence(
        identifier: str, evidence_id: UUID, body: TransitionEvidenceRequest
    ) -> EvidenceItem:
        reject_credentials(body.model_dump(mode="json"), config)
        assert body.target_status is not None
        try:
            target = EvidenceStatus(body.target_status)
        except ValueError as err:
            raise HTTPException(
                status_code=422, detail=f"Invalid target status: {body.target_status}"
            ) from err
        return await projects.transition_evidence(
            identifier=identifier,
            evidence_id=evidence_id,
            target_status=target,
            rationale=body.rationale,
        )

    @router.post(
        "/api/v1/projects/{identifier}/evidence/{evidence_id}/ai-diagnose",
        response_model=DiagnosisResult,
    )
    async def ai_diagnose_project_evidence(identifier: str, evidence_id: UUID) -> DiagnosisResult:
        evidence = await projects.get_evidence(identifier, evidence_id)
        service = None
        if evidence.decision_service_id:
            try:
                service = await projects.get_decision_service(
                    identifier, str(evidence.decision_service_id)
                )
            except NotFoundError:
                pass
        raw_event = None
        if evidence.raw_event_id:
            try:
                raw_event = await projects.get_event(identifier, evidence.raw_event_id)
            except NotFoundError:
                pass

        choices = [c.key for c in service.nodes[0].choices] if service and service.nodes else []
        instructions = service.instructions if service else ""
        observation = raw_event.content if raw_event else ""
        context = {
            "service": service.name if service else "Unknown Service",
            "instructions": instructions,
            "choices": choices,
            "observation": observation,
            "selected_choice": evidence.selected_choice,
            "probabilities": evidence.probabilities_snapshot,
            "unknown_probability": evidence.unknown_probability,
            "margin": evidence.margin,
            "supervision_outcome": evidence.supervision_outcome,
            "supervision_reason": evidence.supervision_reason,
            "trigger_type": evidence.trigger_type.value,
        }
        reject_credentials(context, config)
        try:
            return await diagnostician.diagnose(context)
        except ProviderError as err:
            raise HTTPException(status_code=502, detail="Diagnosis provider failed") from err

    # ── Feedback Endpoints ───────────────────────────────────

    @router.post(
        "/api/v1/projects/{identifier}/runs/{run_id}/feedback",
        response_model=RunFeedback,
        status_code=201,
    )
    async def submit_run_feedback(
        identifier: str, run_id: UUID, body: SubmitRunFeedbackRequest
    ) -> RunFeedback:
        reject_credentials(body.model_dump(mode="json"), config)
        try:
            act = FeedbackAction(body.action)
        except ValueError as err:
            raise HTTPException(
                status_code=422, detail=f"Invalid feedback action: {body.action}"
            ) from err
        return await projects.submit_run_feedback(
            identifier=identifier,
            run_id=run_id,
            action=act,
            corrected_choice=body.corrected_choice,
            note=body.note,
        )

    @router.get(
        "/api/v1/projects/{identifier}/runs/{run_id}/feedback",
        response_model=list[RunFeedback],
    )
    async def list_run_feedback(identifier: str, run_id: UUID) -> list[RunFeedback]:
        return await projects.list_run_feedback(identifier, run_id)

    # ── Evidence Cases Endpoints ─────────────────────────────

    @router.post(
        "/api/v1/projects/{identifier}/evidence-cases",
        response_model=EvidenceCase,
        status_code=201,
    )
    async def create_evidence_case(
        identifier: str, body: CreateEvidenceCaseRequest
    ) -> EvidenceCase:
        reject_credentials(body.model_dump(mode="json"), config)
        ev_ids = [UUID(eid) for eid in body.evidence_ids] if body.evidence_ids else None
        svc_id = UUID(body.decision_service_id) if body.decision_service_id else None
        return await projects.create_evidence_case(
            identifier=identifier,
            title=body.title,
            decision_service_id=svc_id,
            evidence_ids=ev_ids,
        )

    @router.get(
        "/api/v1/projects/{identifier}/evidence-cases",
        response_model=list[EvidenceCase],
    )
    async def list_evidence_cases(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[EvidenceCase]:
        return await projects.list_evidence_cases(identifier, limit=limit, offset=offset)

    @router.get(
        "/api/v1/projects/{identifier}/evidence-cases/{case_id}",
        response_model=EvidenceCase,
    )
    async def get_evidence_case(identifier: str, case_id: UUID) -> EvidenceCase:
        return await projects.get_evidence_case(identifier, case_id)

    @router.get(
        "/api/v1/projects/{identifier}/evidence-cases/{case_id}/evidence",
        response_model=list[EvidenceItem],
    )
    async def list_case_evidence(identifier: str, case_id: UUID) -> list[EvidenceItem]:
        project = await projects.get(identifier)
        return await project_repository.list_case_evidence(project.id, case_id)

    @router.post(
        "/api/v1/projects/{identifier}/evidence-cases/{case_id}/evidence",
        response_model=EvidenceCase,
    )
    async def add_case_evidence(
        identifier: str, case_id: UUID, body: AddEvidenceToCaseRequest
    ) -> EvidenceCase:
        reject_credentials(body.model_dump(mode="json"), config)
        ids: list[UUID] = []
        if body.evidence_id is not None:
            ids.append(body.evidence_id)
        for eid in body.evidence_ids:
            if eid not in ids:
                ids.append(eid)
        return await projects.add_evidence_items_to_case(identifier, case_id, ids)

    @router.get(
        "/api/v1/projects/{identifier}/evolution/summary",
        response_model=EvolutionSummary,
    )
    async def evolution_summary(identifier: str) -> EvolutionSummary:
        return await projects.evolution_summary(identifier)

    return router
