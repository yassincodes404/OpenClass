from typing import Protocol
from uuid import UUID

from openclass_core.models import (
    Candidate,
    ClassificationRecord,
    ClassificationResult,
    Classifier,
    DomainEvent,
    Observation,
    OntologyVersion,
    SupervisorReview,
    UnknownEvent,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class Repository(Protocol):
    """Each write is atomic, including its audit events. Versions are append-only."""

    async def versions(self, classifier_id: UUID) -> list[OntologyVersion]: ...

    async def events(
        self, classifier_id: UUID, after: int, limit: int
    ) -> list[tuple[int, DomainEvent]]: ...

    async def create_classifier(
        self, classifier: Classifier, ontology: OntologyVersion, event: DomainEvent
    ) -> None: ...
    async def record_provider_failure(
        self, classifier_id: UUID, ontology_version_id: UUID
    ) -> None: ...
    async def get_classifier(self, identifier: str) -> Classifier: ...
    async def list_classifiers(self) -> list[Classifier]: ...
    async def get_ontology(self, version_id: UUID) -> OntologyVersion: ...
    async def save_classification(
        self,
        observation: Observation,
        result: ClassificationResult,
        unknown: UnknownEvent | None,
        events: tuple[DomainEvent, ...],
    ) -> None: ...
    async def unknowns(
        self, classifier_id: UUID, limit: int, offset: int
    ) -> list[UnknownEvent]: ...
    async def get_classification(
        self, classifier_id: UUID, run_id: UUID
    ) -> ClassificationRecord: ...
    async def list_classifications(
        self, classifier_id: UUID, limit: int, offset: int
    ) -> list[ClassificationRecord]: ...
    async def save_supervisor_review(
        self, review: SupervisorReview, event: DomainEvent
    ) -> None: ...
    async def supervisor_reviews(
        self, classifier_id: UUID, limit: int, offset: int
    ) -> list[SupervisorReview]: ...
    async def save_candidate(
        self, candidate: Candidate, evidence: tuple[UUID, ...], event: DomainEvent
    ) -> None: ...
    async def candidates(self, classifier_id: UUID, limit: int, offset: int) -> list[Candidate]: ...
    async def get_candidate(self, classifier_id: UUID, candidate_id: UUID) -> Candidate: ...
    async def reject_candidate(
        self, candidate: Candidate, reason: str, event: DomainEvent
    ) -> Candidate: ...
    async def mark_candidate_evaluated(
        self, candidate: Candidate, event: DomainEvent
    ) -> Candidate: ...
    async def approve_candidate(
        self,
        candidate: Candidate,
        ontology: OntologyVersion,
        classifier: Classifier,
        events: tuple[DomainEvent, ...],
    ) -> None: ...
