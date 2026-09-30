"""Public classifiers routes over typed services and repository ports."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from openclass_core.discovery import DiscoveryService
from openclass_core.models import (
    Candidate,
    ClassificationRecord,
    ClassificationResult,
    Classifier,
    Observation,
    OntologyVersion,
    SupervisorReview,
    UnknownEvent,
)
from openclass_core.providers import ProviderError
from openclass_core.repositories import Repository
from openclass_core.service import ClassificationService
from openclass_core.supervisor import SupervisorService

from openclass_server.api.schemas import (
    ClassifyRequest,
    CreateClassifier,
    CreateReview,
    DiscoverRequest,
    RejectCandidateRequest,
)
from openclass_server.provider_config import reject_credentials
from openclass_server.settings import Settings


def classifiers_router(
    config: Settings,
    repository: Repository,
    service: ClassificationService,
    supervisor: SupervisorService,
    discovery: DiscoveryService,
) -> APIRouter:
    router = APIRouter(tags=["classifiers"])

    @router.post("/api/v1/classifiers", response_model=Classifier, status_code=201)
    async def create_classifier(body: CreateClassifier) -> Classifier:
        reject_credentials(body.model_dump(mode="json"), config)
        return await service.create_classifier(
            **body.model_dump(exclude={"classes"}), classes=body.classes, actor="local-user"
        )

    @router.get("/api/v1/classifiers", response_model=list[Classifier])
    async def classifiers() -> list[Classifier]:
        return await repository.list_classifiers()

    @router.get("/api/v1/classifiers/{identifier}", response_model=Classifier)
    async def classifier(identifier: str) -> Classifier:
        return await repository.get_classifier(identifier)

    @router.post("/api/v1/classifiers/{identifier}/classify", response_model=ClassificationResult)
    async def classify(identifier: str, body: ClassifyRequest) -> ClassificationResult:
        reject_credentials(body.model_dump(mode="json"), config)
        return await service.classify(
            identifier, Observation(content=body.observation, metadata=body.metadata)
        )

    @router.get("/api/v1/classifiers/{identifier}/ontology", response_model=OntologyVersion)
    async def ontology(identifier: str) -> OntologyVersion:
        classifier = await repository.get_classifier(identifier)
        return await repository.get_ontology(classifier.active_ontology_version_id)

    @router.get(
        "/api/v1/classifiers/{identifier}/ontology/versions", response_model=list[OntologyVersion]
    )
    async def versions(identifier: str) -> list[OntologyVersion]:
        classifier = await repository.get_classifier(identifier)
        return await repository.versions(classifier.id)

    @router.get("/api/v1/classifiers/{identifier}/unknowns", response_model=list[UnknownEvent])
    async def unknowns(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[UnknownEvent]:
        classifier = await repository.get_classifier(identifier)
        return await repository.unknowns(classifier.id, limit, offset)

    @router.post(
        "/api/v1/classifiers/{identifier}/discoveries", response_model=Candidate, status_code=201
    )
    async def discover(identifier: str, body: DiscoverRequest) -> Candidate:
        reject_credentials(body.model_dump(mode="json"), config)
        return await discovery.discover(
            identifier, tuple(UUID(i) for i in body.unknown_ids), "local-user"
        )

    @router.get("/api/v1/classifiers/{identifier}/candidates", response_model=list[Candidate])
    async def candidates(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Candidate]:
        classifier = await repository.get_classifier(identifier)
        return await repository.candidates(classifier.id, limit, offset)

    @router.post(
        "/api/v1/classifiers/{identifier}/candidates/{candidate_id}/reject",
        response_model=Candidate,
    )
    async def reject_candidate(
        identifier: str, candidate_id: UUID, body: RejectCandidateRequest
    ) -> Candidate:
        reject_credentials(body.model_dump(mode="json"), config)
        return await discovery.reject(identifier, candidate_id, body.reason, "local-user")

    @router.post(
        "/api/v1/classifiers/{identifier}/candidates/{candidate_id}/approve",
        response_model=OntologyVersion,
    )
    async def approve(identifier: str, candidate_id: UUID) -> OntologyVersion:
        return await discovery.approve(identifier, candidate_id, "local-user")

    @router.post(
        "/api/v1/classifiers/{identifier}/candidates/{candidate_id}/evaluate",
        response_model=Candidate,
    )
    async def evaluate(identifier: str, candidate_id: UUID) -> Candidate:
        return await discovery.evaluate(identifier, candidate_id, "local-user")

    @router.get("/api/v1/classifiers/{identifier}/runs", response_model=list[ClassificationRecord])
    async def runs(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ClassificationRecord]:
        classifier = await repository.get_classifier(identifier)
        return await repository.list_classifications(classifier.id, limit, offset)

    @router.get(
        "/api/v1/classifiers/{identifier}/runs/{run_id}", response_model=ClassificationRecord
    )
    async def run(identifier: str, run_id: UUID) -> ClassificationRecord:
        classifier = await repository.get_classifier(identifier)
        return await repository.get_classification(classifier.id, run_id)

    @router.post(
        "/api/v1/classifiers/{identifier}/runs/{run_id}/reviews",
        response_model=SupervisorReview,
        status_code=201,
    )
    async def create_review(
        identifier: str, run_id: UUID, body: CreateReview | None = None
    ) -> SupervisorReview:
        try:
            return await supervisor.review_run(identifier, run_id, actor="local-user")
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail="Supervisor provider failed") from exc

    @router.get("/api/v1/classifiers/{identifier}/reviews", response_model=list[SupervisorReview])
    async def reviews(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[SupervisorReview]:
        classifier = await repository.get_classifier(identifier)
        return await repository.supervisor_reviews(classifier.id, limit, offset)

    @router.get("/api/v1/classifiers/{identifier}/events")
    async def events(
        identifier: str,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        classifier = await repository.get_classifier(identifier)
        return [
            {"sequence": sequence, "event": event.model_dump(mode="json")}
            for sequence, event in await repository.events(classifier.id, after, limit)
        ]

    return router
