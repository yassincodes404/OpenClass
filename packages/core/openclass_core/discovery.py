from uuid import UUID

from openclass_core.models import (
    Candidate,
    DiscoveryProposalType,
    DiscoveryRequest,
    DomainEvent,
    OntologyVersion,
)
from openclass_core.providers import DiscoveryProvider, ProviderError
from openclass_core.repositories import ConflictError, Repository


class DiscoveryService:
    def __init__(self, repository: Repository, provider: DiscoveryProvider) -> None:
        self.repository = repository
        self.provider = provider

    async def discover(
        self, identifier: str, unknown_ids: tuple[UUID, ...], actor: str
    ) -> Candidate:
        if len(set(unknown_ids)) != len(unknown_ids):
            raise ConflictError("Duplicate unknown evidence")
        if len(unknown_ids) < 3:
            raise ConflictError("At least three distinct unknown observations are required")
        classifier = await self.repository.get_classifier(identifier)
        ontology = await self.repository.get_ontology(classifier.active_ontology_version_id)
        unknowns = tuple(await self.repository.unknowns(classifier.id, 200, 0))
        selected = tuple(u for u in unknowns if u.id in set(unknown_ids))
        if len(selected) != len(unknown_ids):
            raise ConflictError("Unknown evidence is not available for this classifier")
        try:
            result = await self.provider.discover(
                DiscoveryRequest(classifier=classifier, ontology=ontology, unknowns=selected)
            )
        except ProviderError:
            raise
        if result.proposal_type == DiscoveryProposalType.NEW_CLASS:
            assert result.canonical_name is not None
            terms = {t.casefold() for c in ontology.classes for t in (c.canonical_name, *c.aliases)}
            if result.canonical_name.casefold() in terms:
                raise ConflictError("Discovery proposal duplicates an existing concept")
        candidate = Candidate(
            classifier_id=classifier.id,
            base_ontology_version_id=ontology.id,
            proposal_type=result.proposal_type,
            canonical_name=result.canonical_name,
            display_name=result.display_name,
            description=result.description,
            confidence=result.confidence,
            rationale=result.rationale,
            discovery_provider=result.provider,
            discovery_model=result.model,
            evidence_ids=unknown_ids,
        )
        event = DomainEvent(
            classifier_id=classifier.id,
            type="candidate.created",
            actor=actor,
            payload={
                "candidate_id": str(candidate.id),
                "base_ontology_version_id": str(ontology.id),
                "evidence_ids": [str(i) for i in unknown_ids],
            },
        )
        await self.repository.save_candidate(candidate, unknown_ids, event)
        return candidate

    async def approve(self, identifier: str, candidate_id: UUID, actor: str) -> OntologyVersion:
        classifier = await self.repository.get_classifier(identifier)
        await self.repository.get_candidate(classifier.id, candidate_id)
        # Legacy evaluation_passed flags only counted evidence. They do not prove
        # a verified baseline/candidate replay, so no candidate can use them.
        raise ConflictError("Verified replay evaluation is required before approval")

    async def evaluate(self, identifier: str, candidate_id: UUID, actor: str) -> Candidate:
        classifier = await self.repository.get_classifier(identifier)
        await self.repository.get_candidate(classifier.id, candidate_id)
        raise ConflictError("Verified replay evaluation is not implemented")

    async def reject(
        self, identifier: str, candidate_id: UUID, reason: str, actor: str
    ) -> Candidate:
        classifier = await self.repository.get_classifier(identifier)
        candidate = await self.repository.get_candidate(classifier.id, candidate_id)
        if candidate.status != "candidate":
            raise ConflictError("Only pending candidates can be rejected")
        event = DomainEvent(
            classifier_id=classifier.id,
            type="candidate.rejected",
            actor=actor,
            payload={"candidate_id": str(candidate.id), "reason": reason},
        )
        return await self.repository.reject_candidate(candidate, reason, event)
