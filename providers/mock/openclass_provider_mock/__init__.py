"""Deterministic lexical demo provider. Scores are fixtures, not calibrated probabilities."""

import re

from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    ReviewRecommendation,
    ReviewRequest,
    ReviewResult,
    SupervisorFinding,
)


class MockDecisionProvider:
    async def choice(self, request: ChoiceRequest) -> ChoiceResult:
        content = request.observation.content.casefold()
        hits: list[str] = []
        for concept in request.ontology.classes:
            terms = (
                concept.canonical_name.replace("_", " "),
                *concept.aliases,
                *concept.positive_examples,
            )
            if any(
                re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", content)
                for term in terms
                if term.strip()
            ):
                hits.append(concept.canonical_name)
        unknown = 0.05 if hits else 0.95
        count = len(hits) if hits else len(request.ontology.classes)
        probabilities = {
            c.canonical_name: (
                (1 - unknown) / count if not hits or c.canonical_name in hits else 0.0
            )
            for c in request.ontology.classes
        }
        return ChoiceResult(
            provider="mock",
            model="lexical-demo-v1",
            probabilities=probabilities,
            unknown_probability=unknown,
            provider_metadata={"simulated": True},
            estimated_cost=0.0,
        )


class MockSupervisorProvider:
    """Advisory infrastructure fixture. It reports run shape, not semantic judgment."""

    async def review(self, request: ReviewRequest) -> ReviewResult:
        if request.classification.selected_class is None:
            finding, recommendation = (
                SupervisorFinding.POSSIBLE_MISSING_CLASS,
                ReviewRecommendation.COLLECT_MORE_EVIDENCE,
            )
            rationale = (
                "Simulated advisory review: the run selected no class, so the observation "
                "may belong outside the current ontology. This mock does not judge meaning."
            )
        else:
            finding, recommendation = SupervisorFinding.NO_ISSUE, ReviewRecommendation.NONE
            rationale = (
                "Simulated advisory review: the run selected a known class. This mock does "
                "not evaluate whether that selection is semantically correct."
            )
        return ReviewResult(
            provider="mock-supervisor",
            model="advisory-demo-v1",
            finding=finding,
            confidence=0.5,
            recommendation=recommendation,
            rationale=rationale,
            provider_metadata={"simulated": True},
            estimated_cost=0.0,
        )
