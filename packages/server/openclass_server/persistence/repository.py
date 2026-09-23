from uuid import UUID

from openclass_core.models import (
    ClassificationRecord,
    ClassificationResult,
    Classifier,
    DomainEvent,
    Observation,
    OntologyVersion,
    SupervisorReview,
    UnknownEvent,
)
from openclass_core.repositories import ConflictError, NotFoundError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.tables import (
    ClassifierRow,
    EventRow,
    ObservationRow,
    OntologyRow,
    ReviewRow,
    RunRow,
    UnknownRow,
)


class SQLRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create_classifier(
        self, classifier: Classifier, ontology: OntologyVersion, event: DomainEvent
    ) -> None:
        try:
            async with self.sessions.begin() as session:
                session.add(
                    ClassifierRow(
                        id=str(classifier.id),
                        slug=classifier.slug,
                        payload=classifier.model_dump(mode="json"),
                    )
                )
                await session.flush()
                session.add(
                    OntologyRow(
                        id=str(ontology.id),
                        classifier_id=str(classifier.id),
                        version_number=ontology.version_number,
                        parent_version_id=None,
                        payload=ontology.model_dump(mode="json"),
                    )
                )
                session.add(self._event(event))
        except IntegrityError as exc:
            raise ConflictError("Classifier slug or identifier already exists") from exc

    async def get_classifier(self, identifier: str) -> Classifier:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ClassifierRow).where(
                    or_(ClassifierRow.id == identifier, ClassifierRow.slug == identifier)
                )
            )
            if row is None:
                raise NotFoundError("Classifier not found")
            return Classifier.model_validate(row.payload)

    async def list_classifiers(self) -> list[Classifier]:
        async with self.sessions() as session:
            rows = await session.scalars(select(ClassifierRow).order_by(ClassifierRow.slug))
            return [Classifier.model_validate(row.payload) for row in rows]

    async def get_ontology(self, version_id: UUID) -> OntologyVersion:
        async with self.sessions() as session:
            row = await session.get(OntologyRow, str(version_id))
            if row is None:
                raise NotFoundError("Ontology version not found")
            return OntologyVersion.model_validate(row.payload)

    async def versions(self, classifier_id: UUID) -> list[OntologyVersion]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(OntologyRow)
                .where(OntologyRow.classifier_id == str(classifier_id))
                .order_by(OntologyRow.version_number)
            )
            return [OntologyVersion.model_validate(row.payload) for row in rows]

    async def save_classification(
        self,
        observation: Observation,
        result: ClassificationResult,
        unknown: UnknownEvent | None,
        events: tuple[DomainEvent, ...],
    ) -> None:
        async with self.sessions.begin() as session:
            session.add(
                ObservationRow(id=str(observation.id), payload=observation.model_dump(mode="json"))
            )
            await session.flush()
            session.add(
                RunRow(
                    id=str(result.id),
                    observation_id=str(observation.id),
                    classifier_id=str(result.classifier_id),
                    ontology_version_id=str(result.ontology_version_id),
                    payload=result.model_dump(mode="json"),
                )
            )
            await session.flush()
            if unknown:
                session.add(
                    UnknownRow(
                        id=str(unknown.id),
                        classifier_id=str(result.classifier_id),
                        run_id=str(result.id),
                        payload=unknown.model_dump(mode="json"),
                    )
                )
            session.add_all(self._event(event) for event in events)

    async def unknowns(self, classifier_id: UUID, limit: int, offset: int) -> list[UnknownEvent]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(UnknownRow)
                .where(UnknownRow.classifier_id == str(classifier_id))
                .order_by(UnknownRow.id)
                .offset(offset)
                .limit(limit)
            )
            return [UnknownEvent.model_validate(row.payload) for row in rows]

    async def get_classification(self, classifier_id: UUID, run_id: UUID) -> ClassificationRecord:
        async with self.sessions() as session:
            row = await session.scalar(
                select(RunRow).where(
                    RunRow.id == str(run_id), RunRow.classifier_id == str(classifier_id)
                )
            )
            if row is None:
                raise NotFoundError("Classification run not found")
            observation_row = await session.get(ObservationRow, row.observation_id)
            if observation_row is None:
                raise NotFoundError("Observation not found")
            return ClassificationRecord(
                observation=Observation.model_validate(observation_row.payload),
                result=ClassificationResult.model_validate(row.payload),
            )

    async def list_classifications(
        self, classifier_id: UUID, limit: int, offset: int
    ) -> list[ClassificationRecord]:
        async with self.sessions() as session:
            run_rows = await session.scalars(
                select(RunRow)
                .where(RunRow.classifier_id == str(classifier_id))
                .order_by(RunRow.id)
                .offset(offset)
                .limit(limit)
            )
            records: list[ClassificationRecord] = []
            for run_row in run_rows:
                observation_row = await session.get(ObservationRow, run_row.observation_id)
                if observation_row is None:
                    raise NotFoundError("Observation not found")
                records.append(
                    ClassificationRecord(
                        observation=Observation.model_validate(observation_row.payload),
                        result=ClassificationResult.model_validate(run_row.payload),
                    )
                )
            return records

    async def save_supervisor_review(self, review: SupervisorReview, event: DomainEvent) -> None:
        async with self.sessions.begin() as session:
            run = await session.get(RunRow, str(review.classification_run_id))
            if run is None:
                raise NotFoundError("Classification run not found")
            if run.classifier_id != str(review.classifier_id) or run.ontology_version_id != str(
                review.ontology_version_id
            ):
                raise ConflictError("Review context does not match the classification run")
            session.add(
                ReviewRow(
                    id=str(review.id),
                    classifier_id=str(review.classifier_id),
                    run_id=str(review.classification_run_id),
                    ontology_version_id=str(review.ontology_version_id),
                    payload=review.model_dump(mode="json"),
                )
            )
            await session.flush()
            session.add(self._event(event))

    async def supervisor_reviews(
        self, classifier_id: UUID, limit: int, offset: int
    ) -> list[SupervisorReview]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(ReviewRow)
                .where(ReviewRow.classifier_id == str(classifier_id))
                .order_by(ReviewRow.id)
                .offset(offset)
                .limit(limit)
            )
            return [SupervisorReview.model_validate(row.payload) for row in rows]

    async def events(
        self, classifier_id: UUID, after: int, limit: int
    ) -> list[tuple[int, DomainEvent]]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(EventRow)
                .where(EventRow.classifier_id == str(classifier_id), EventRow.sequence > after)
                .order_by(EventRow.sequence)
                .limit(limit)
            )
            return [(row.sequence, DomainEvent.model_validate(row.payload)) for row in rows]

    @staticmethod
    def _event(event: DomainEvent) -> EventRow:
        return EventRow(
            id=str(event.id),
            classifier_id=str(event.classifier_id),
            payload=event.model_dump(mode="json"),
        )
