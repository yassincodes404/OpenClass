"""Deterministic lexical demo provider. Scores are fixtures, not calibrated probabilities."""

import re
from typing import Any

from openclass_core.evidence import DiagnosisCategory, DiagnosisResult
from openclass_core.models import (
    ChoiceRequest,
    ChoiceResult,
    DiscoveryProposalType,
    DiscoveryRequest,
    DiscoveryResult,
    ReviewRecommendation,
    ReviewRequest,
    ReviewResult,
    SupervisorFinding,
)
from openclass_core.project_evolution import ChoiceProposal, ProposalKind
from openclass_core.projects import DecisionRun, DecisionService
from openclass_core.supervision import (
    InferenceProvenance,
    OperatingProfile,
    ProvenancedChoiceResult,
)


class MockChoiceTeacher:
    """Explicitly simulated proposal fixture for offline lifecycle tests."""

    async def propose(
        self, service: DecisionService, runs: tuple[DecisionRun, ...]
    ) -> ChoiceProposal:
        text = " ".join(str(run.input_snapshot.get("content", "")) for run in runs).casefold()
        if "pause" in text:
            return ChoiceProposal(
                kind=ProposalKind.NEW_CHOICE,
                key="SUBSCRIPTION_PAUSE",
                label="Subscription pause",
                description="Requests to pause a subscription temporarily.",
                rationale="Simulated fixture recognized recurring pause wording.",
                provider="mock-teacher",
                model="fixture-v1",
                simulated=True,
            )
        return ChoiceProposal(
            kind=ProposalKind.INSUFFICIENT_EVIDENCE,
            rationale="Simulated fixture found no supported recurring pattern.",
            provider="mock-teacher",
            model="fixture-v1",
            simulated=True,
        )


class MockDecisionProvider:
    operating_profile = OperatingProfile(
        calibration_status="simulated",
        allow_simulated_continuation=True,
    )

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
        return ProvenancedChoiceResult(
            inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
            provider="mock",
            model="lexical-demo-v1",
            probabilities=probabilities,
            unknown_probability=unknown,
            provider_metadata={
                "simulated": True,
                "execution_mode": "mock",
                "real_inference": False,
            },
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


class MockDiscoveryProvider:
    """Deterministic discovery fixture for credential-free tests."""

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        return DiscoveryResult(
            provider="mock-discovery",
            model="discovery-demo-v1",
            proposal_type=DiscoveryProposalType.NEW_CLASS,
            canonical_name="tablet",
            display_name="Tablet",
            description=(
                "Portable touchscreen computing devices primarily operated through a touch display."
            ),
            confidence=0.9,
            rationale=(
                "Simulated discovery fixture; selected evidence is treated as tablet evidence."
            ),
            provider_metadata={"simulated": True},
            estimated_cost=0.0,
        )


class MockDiagnosisProvider:
    """Explicitly simulated failure diagnosis for offline tests."""

    async def diagnose(self, context: dict[str, Any]) -> DiagnosisResult:
        obs = str(context.get("observation", "")).lower()
        if "workspace" in obs or "sso" in obs or "feature" in obs:
            return DiagnosisResult(
                diagnosis=DiagnosisCategory.DECISION_SPACE,
                rationale=(
                    "Simulated diagnosis: customer inquiry requests an unrepresented "
                    "feature/capability."
                ),
                confidence=0.95,
                recommended_action="Expand decision service choices to include feature requests.",
                provider="mock-diagnostician",
                model="fixture-v1",
                simulated=True,
            )
        return DiagnosisResult(
            diagnosis=DiagnosisCategory.AMBIGUOUS_OR_INSUFFICIENT,
            rationale="Simulated diagnosis: input lacks sufficient context to determine intent.",
            confidence=0.8,
            recommended_action="Request clarification from customer.",
            provider="mock-diagnostician",
            model="fixture-v1",
            simulated=True,
        )
