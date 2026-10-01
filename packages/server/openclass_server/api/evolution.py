"""Public evolution routes over typed services and repository ports."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from openclass_core.project_evolution import (
    CandidateEvaluationResult,
    ChoiceCandidate,
    ChoiceCandidateRepository,
    ProjectEvolutionService,
)
from openclass_core.projects import ProjectService as ProjectDomainService

from openclass_server.api.schemas import (
    PromoteCandidateRequest,
    PromoteCandidateResponse,
    ProposeFromEvidenceRequest,
    ProposeProjectChoiceRequest,
    RejectCandidateRequest,
)
from openclass_server.provider_config import reject_credentials
from openclass_server.settings import Settings


def evolution_router(
    config: Settings,
    projects: ProjectDomainService,
    project_repository: ChoiceCandidateRepository,
    evolution: ProjectEvolutionService,
) -> APIRouter:
    router = APIRouter(tags=["evolution"])

    @router.get("/api/v1/projects/{identifier}/candidates", response_model=list[ChoiceCandidate])
    async def project_candidates(identifier: str) -> list[ChoiceCandidate]:
        project = await projects.get(identifier)
        return await project_repository.list_choice_candidates(project.id)

    @router.get(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}", response_model=ChoiceCandidate
    )
    async def project_candidate(identifier: str, candidate_id: UUID) -> ChoiceCandidate:
        project = await projects.get(identifier)
        return await project_repository.get_choice_candidate(project.id, candidate_id)

    @router.post(
        "/api/v1/projects/{identifier}/decision-services/{service_id}/candidates",
        response_model=ChoiceCandidate,
        status_code=201,
    )
    async def propose_project_choice(
        identifier: str, service_id: str, body: ProposeProjectChoiceRequest
    ) -> ChoiceCandidate:
        project = await projects.get(identifier)
        return await evolution.propose(
            project.id, service_id, tuple(UUID(run_id) for run_id in body.run_ids), "local-user"
        )

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/reject",
        response_model=ChoiceCandidate,
    )
    async def reject_project_choice(
        identifier: str, candidate_id: UUID, body: RejectCandidateRequest
    ) -> ChoiceCandidate:
        reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        return await evolution.reject(project.id, candidate_id, body.reason, "local-user")

    @router.post(
        "/api/v1/projects/{identifier}/evolution/propose",
        response_model=ChoiceCandidate,
        status_code=201,
    )
    async def propose_from_evidence(
        identifier: str, body: ProposeFromEvidenceRequest
    ) -> ChoiceCandidate:
        reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        if body.evidence_case_id is not None:
            return await evolution.propose_from_case(
                project.id, body.evidence_case_id, "local-user"
            )
        assert body.evidence_ids is not None and body.service_id is not None
        return await evolution.propose_from_evidence(
            project.id, body.service_id, tuple(body.evidence_ids), "local-user"
        )

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/evaluate",
        response_model=CandidateEvaluationResult,
    )
    async def evaluate_project_candidate(
        identifier: str, candidate_id: UUID
    ) -> CandidateEvaluationResult:
        project = await projects.get(identifier)
        return await evolution.evaluate(project.id, candidate_id)

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/promote",
        response_model=PromoteCandidateResponse,
    )
    async def promote_project_candidate(
        identifier: str, candidate_id: UUID, body: PromoteCandidateRequest | None = None
    ) -> PromoteCandidateResponse:
        if body is not None:
            reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        cand, serv = await evolution.promote(project.id, candidate_id, "local-user")
        return PromoteCandidateResponse(candidate=cand, decision_service=serv)

    return router
