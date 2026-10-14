"""Live contract test for Gemini via Vercel AI Gateway.

Performs live structured failure diagnosis and inactive choice proposals using Google Gemini
when OPENCLASS_VERCEL_GATEWAY_KEY or AI_GATEWAY_API_KEY is configured in the environment.
Never commits or leaks credentials.
"""

import os
from uuid import uuid4

import pytest
from openclass_core.evidence import DiagnosisCategory
from openclass_core.project_evolution import ProposalKind
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceChoice,
    DecisionServiceNode,
)
from openclass_provider_glm import (
    OpenAICompatibleChoiceTeacher,
    OpenAICompatibleDiagnosisProvider,
)
from pydantic import SecretStr

GATEWAY_KEY = (
    os.getenv("OPENCLASS_VERCEL_GATEWAY_KEY", "").strip()
    or os.getenv("AI_GATEWAY_API_KEY", "").strip()
)
RUN_LIVE = os.getenv("OPENCLASS_RUN_LIVE_TESTS") == "1"


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE or not GATEWAY_KEY,
    reason="Set OPENCLASS_RUN_LIVE_TESTS=1 and configure AI_GATEWAY_API_KEY",
)
@pytest.mark.asyncio
async def test_live_gemini_diagnosis() -> None:
    provider = OpenAICompatibleDiagnosisProvider(
        api_key=SecretStr(GATEWAY_KEY),
        base_url="https://ai-gateway.vercel.sh/v1",
        model="google/gemini-2.5-flash",
    )
    result = await provider.diagnose(
        {
            "service": "customer-triage",
            "instructions": (
                "Route customer requests to billing or tech support. "
                "If unknown or missing, return UNKNOWN."
            ),
            "observation": "I want to pause my monthly subscription for the summer",
            "choice_distribution": {"BILLING": 0.2, "TECH_SUPPORT": 0.1, "UNKNOWN": 0.7},
        }
    )
    assert isinstance(result.diagnosis, DiagnosisCategory)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.rationale) > 10
    assert result.provider == "vercel-ai-gateway"
    assert result.model == "google/gemini-2.5-flash"
    assert result.simulated is False


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE or not GATEWAY_KEY,
    reason="Set OPENCLASS_RUN_LIVE_TESTS=1 and configure AI_GATEWAY_API_KEY",
)
@pytest.mark.asyncio
async def test_live_gemini_teacher_proposal() -> None:
    teacher = OpenAICompatibleChoiceTeacher(
        api_key=SecretStr(GATEWAY_KEY),
        base_url="https://ai-gateway.vercel.sh/v1",
        model="google/gemini-2.5-flash",
    )
    service = DecisionService(
        project_id=uuid4(),
        slug="customer-triage",
        name="Customer Triage",
        instructions="Classify support tickets into departments",
        nodes=(
            DecisionServiceNode(
                name="root",
                instructions="Route to appropriate department",
                choices=(
                    DecisionServiceChoice(key="BILLING", label="Billing Inquiry"),
                    DecisionServiceChoice(key="TECH_SUPPORT", label="Technical Support"),
                    DecisionServiceChoice(key="UNKNOWN", label="Unknown Request"),
                ),
            ),
        ),
    )
    run = DecisionRun(
        project_id=service.project_id,
        raw_event_id=uuid4(),
        decision_service_id=service.id,
        decision_node_id=service.nodes[0].id,
        provider="laya",
        model="laya-router",
        execution_mode="in_process",
        real_inference=True,
        selected_choice="UNKNOWN",
        probabilities={"BILLING": 0.1, "TECH_SUPPORT": 0.05, "UNKNOWN": 0.85},
        top_probability=0.85,
        margin=0.75,
        unknown_probability=0.85,
        supervision_outcome="UNKNOWN",
        supervision_reason="Unmatched intent",
        latency_ms=12.5,
        input_snapshot={"content": "Please pause my gym subscription until September"},
        instructions_snapshot=service.nodes[0].instructions,
        choices_snapshot=[c.model_dump(mode="json") for c in service.nodes[0].choices],
    )
    proposal = await teacher.propose(service, (run,))
    assert isinstance(proposal.kind, ProposalKind)
    assert proposal.key is not None
    assert proposal.label is not None
    assert len(proposal.rationale) > 10
    assert proposal.model == "google/gemini-2.5-flash"
    assert proposal.simulated is False
