from uuid import uuid4

from openclass_core.models import (
    ChoiceRequest,
    ClassificationResult,
    Classifier,
    DomainEvent,
    Observation,
    OntologyClass,
    OntologyVersion,
    UnknownEvent,
)
from openclass_core.novelty import NoveltyPolicy, assess, signals_from
from openclass_core.providers import DecisionProvider, ProviderError
from openclass_core.repositories import Repository


class ClassificationService:
    def __init__(
        self,
        repository: Repository,
        provider: DecisionProvider,
        policy: NoveltyPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.policy = policy or NoveltyPolicy()

    async def create_classifier(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        classes: tuple[OntologyClass, ...],
        actor: str,
    ) -> Classifier:
        classifier_id, version_id = uuid4(), uuid4()
        ontology = OntologyVersion(
            id=version_id,
            classifier_id=classifier_id,
            version_number=1,
            classes=classes,
            created_by=actor,
        )
        classifier = Classifier(
            id=classifier_id,
            slug=slug,
            name=name,
            description=description,
            active_ontology_version_id=version_id,
        )
        event = DomainEvent(
            classifier_id=classifier_id,
            type="ontology.version_created",
            actor=actor,
            payload={"to_version": 1, "version_id": str(version_id)},
        )
        await self.repository.create_classifier(classifier, ontology, event)
        return classifier

    async def classify(self, identifier: str, observation: Observation) -> ClassificationResult:
        classifier = await self.repository.get_classifier(identifier)
        ontology = await self.repository.get_ontology(classifier.active_ontology_version_id)
        decision = await self.provider.choice(
            ChoiceRequest(observation=observation, ontology=ontology)
        )
        expected = {c.canonical_name for c in ontology.classes}
        if set(decision.probabilities) != expected:
            raise ProviderError("Provider returned a distribution that does not match the ontology")
        signals = signals_from(decision)
        novelty = assess(signals, self.policy)
        selected = None
        if novelty.state == "known":
            best = max(decision.probabilities, key=lambda key: decision.probabilities[key])
            selected = next(c for c in ontology.classes if c.canonical_name == best)
        result = ClassificationResult(
            classifier_id=classifier.id,
            observation_id=observation.id,
            ontology_version_id=ontology.id,
            selected_class_id=selected.stable_class_id if selected else None,
            selected_class=selected.canonical_name if selected else None,
            decision=decision,
            signals=signals,
            novelty=novelty,
        )
        unknown = (
            UnknownEvent(
                classifier_id=classifier.id, observation=observation, classification=result
            )
            if selected is None
            else None
        )
        events = [
            DomainEvent(
                classifier_id=classifier.id,
                type="classification.completed",
                actor="system",
                payload={"run_id": str(result.id), "state": novelty.state},
            )
        ]
        if unknown:
            events.append(
                DomainEvent(
                    classifier_id=classifier.id,
                    type="unknown.detected",
                    actor="system",
                    payload={"unknown_id": str(unknown.id), "run_id": str(result.id)},
                )
            )
        await self.repository.save_classification(observation, result, unknown, tuple(events))
        return result
