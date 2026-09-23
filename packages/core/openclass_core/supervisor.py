"""Advisory review of historical runs. Findings never rewrite the reviewed run."""

from uuid import UUID

from openclass_core.models import DomainEvent, ReviewRequest, SupervisorReview
from openclass_core.providers import SupervisorProvider
from openclass_core.repositories import Repository


class SupervisorService:
    def __init__(self, repository: Repository, provider: SupervisorProvider) -> None:
        self.repository = repository
        self.provider = provider

    async def review_run(
        self, classifier_identifier: str, run_id: UUID, actor: str
    ) -> SupervisorReview:
        classifier = await self.repository.get_classifier(classifier_identifier)
        record = await self.repository.get_classification(classifier.id, run_id)
        # The run's captured ontology, not the classifier's active version, is the
        # context a review must reason over once later versions exist.
        ontology = await self.repository.get_ontology(record.result.ontology_version_id)
        result = await self.provider.review(
            ReviewRequest(
                observation=record.observation, classification=record.result, ontology=ontology
            )
        )
        review = SupervisorReview(
            classifier_id=classifier.id,
            classification_run_id=record.result.id,
            ontology_version_id=record.result.ontology_version_id,
            result=result,
        )
        event = DomainEvent(
            classifier_id=classifier.id,
            type="supervisor.review_completed",
            actor=actor,
            payload={
                "review_id": str(review.id),
                "run_id": str(record.result.id),
                "finding": result.finding.value,
            },
        )
        await self.repository.save_supervisor_review(review, event)
        return review
