from typing import Protocol
from uuid import UUID

from openclass_core.models import (
    ClassificationResult,
    Classifier,
    DomainEvent,
    Observation,
    OntologyVersion,
    UnknownEvent,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class Repository(Protocol):
    """Each write is atomic, including its audit events. Versions are append-only."""

    async def create_classifier(
        self, classifier: Classifier, ontology: OntologyVersion, event: DomainEvent
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
