"""Unit tests for DecisionExecutor compilation, provider dispatch, and supervision."""

from uuid import uuid4

import pytest
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.projects import (
    DecisionService,
    DecisionServiceChoice,
    DecisionServiceNode,
    RawEvent,
)
from openclass_provider_laya import LayaDecisionProvider
from openclass_provider_mock import MockDecisionProvider


@pytest.fixture
def sample_service() -> DecisionService:
    node = DecisionServiceNode(
        name="default",
        instructions="Classify sentiment of user comment",
        choices=(
            DecisionServiceChoice(key="POSITIVE", label="Positive", description="Happy customer"),
            DecisionServiceChoice(key="NEGATIVE", label="Negative", description="Unhappy customer"),
            DecisionServiceChoice(key="UNKNOWN", label="Unknown", description="Permanent fallback"),
        ),
    )
    return DecisionService(
        project_id=uuid4(),
        slug="sentiment-classifier",
        name="Sentiment Classifier",
        instructions="Classify sentiment of user comment",
        nodes=(node,),
    )


async def test_decision_executor_with_laya_conservative_supervision(
    sample_service: DecisionService,
) -> None:
    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="Positive feedback: I love this product, it is absolutely amazing!",
    )

    provider = LayaDecisionProvider(allow_fallback=True)
    executor = DecisionExecutor(provider)

    run = await executor.execute(event, sample_service)

    assert run.project_id == sample_service.project_id
    assert run.raw_event_id == event.id
    assert run.decision_service_id == sample_service.id
    assert run.provider == "laya"
    assert run.selected_choice == "POSITIVE"
    assert run.top_probability > 0.5
    # Laya conservative supervision must ALWAYS result in REVIEW for known choices
    assert run.supervision_outcome == "REVIEW"
    assert "conservative supervision" in run.supervision_reason

    # Snapshot validation
    assert run.input_snapshot["content"] == event.content
    assert run.instructions_snapshot == sample_service.instructions
    assert len(run.choices_snapshot) == 3
    assert any(c["key"] == "UNKNOWN" for c in run.choices_snapshot)


async def test_decision_executor_with_semantic_unknown(sample_service: DecisionService) -> None:
    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="129381724 912837198273 192837198273 non-language garbage",
    )

    provider = LayaDecisionProvider(allow_fallback=True)
    executor = DecisionExecutor(provider)

    run = await executor.execute(event, sample_service)

    assert run.selected_choice == "UNKNOWN"
    assert run.supervision_outcome == "UNKNOWN"
    assert "semantic UNKNOWN" in run.supervision_reason


async def test_decision_executor_provenance_recording(sample_service: DecisionService) -> None:
    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="Everything is fine",
    )

    # Real in-process Laya inference provenance. The in-process engine degrades
    # silently to the deterministic fallback when the laya model cannot load
    # (e.g. fresh CI runners), so skip instead of failing that environment.
    real_provider = LayaDecisionProvider(allow_fallback=True)
    real_run = await DecisionExecutor(real_provider).execute(event, sample_service)
    if real_run.execution_mode != "in_process":
        pytest.skip("laya in-process engine unavailable; deterministic fallback engaged")
    assert real_run.real_inference is True
    assert real_run.latency_ms >= 0

    # Deterministic fallback provenance
    fallback_provider = LayaDecisionProvider(prefer_local_process=False, allow_fallback=True)
    fallback_run = await DecisionExecutor(fallback_provider).execute(event, sample_service)
    assert fallback_run.execution_mode == "deterministic_test_fallback"
    assert fallback_run.real_inference is False


async def test_decision_executor_with_mock_provider(sample_service: DecisionService) -> None:
    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="Positive review text",
    )

    provider = MockDecisionProvider()
    executor = DecisionExecutor(provider)
    run = await executor.execute(event, sample_service)

    assert run.provider == "mock"
    assert run.supervision_outcome in ("TRUSTED", "REVIEW")
    assert run.margin >= 0


async def test_decision_executor_propagates_instructions_to_jev_and_laya_payloads(
    sample_service: DecisionService,
) -> None:
    import json

    import httpx
    from openclass_provider_jev import UNKNOWN as JEV_UNKNOWN
    from openclass_provider_jev import JevDecisionProvider
    from pydantic import SecretStr

    captured_jev_instructions: list[str] = []

    def jev_handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured_jev_instructions.append(body["questions"]["classification"]["instructions"])
        return httpx.Response(
            200,
            json={
                "model": "typesafe-ai/jev",
                "answers": {
                    "classification": {
                        "type": "choice",
                        "choice": "positive",
                        "confidence": 0.9,
                        "probabilities": {
                            "positive": 0.9,
                            "negative": 0.05,
                            JEV_UNKNOWN: 0.05,
                        },
                    }
                },
            },
        )

    jev = JevDecisionProvider(
        api_key=SecretStr("synthetic-test-key"),
        base_url="https://ai-gateway.vercel.sh/typesafe",
        model="typesafe-ai/jev",
        transport=httpx.MockTransport(jev_handle),
    )
    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="Great customer experience!",
    )
    run = await DecisionExecutor(jev).execute(event, sample_service)
    assert captured_jev_instructions
    assert (
        "Service instructions: Classify sentiment of user comment" in captured_jev_instructions[0]
    )
    assert run.instructions_snapshot == "Classify sentiment of user comment"


async def test_decision_executor_unknown_wins_ties_and_uses_deterministic_uuids(
    sample_service: DecisionService,
) -> None:
    from openclass_core.models import ChoiceRequest, ChoiceResult

    captured_requests: list[ChoiceRequest] = []

    class TiedProvider:
        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            captured_requests.append(request)
            return ChoiceResult(
                provider="jev",
                model="typesafe-ai/jev",
                probabilities={"positive": 0.50, "negative": 0.0},
                unknown_probability=0.50,
            )

    event = RawEvent(
        project_id=sample_service.project_id,
        source_type="text",
        content="Borderline message",
    )
    executor = DecisionExecutor(TiedProvider())
    run1 = await executor.execute(event, sample_service)
    run2 = await executor.execute(event, sample_service)

    assert run1.selected_choice == run2.selected_choice == "UNKNOWN"
    assert run1.supervision_outcome == "UNKNOWN"
    assert run1.margin == 0.0
    assert captured_requests[0].ontology.id == captured_requests[1].ontology.id
    assert [c.stable_class_id for c in captured_requests[0].ontology.classes] == [
        c.stable_class_id for c in captured_requests[1].ontology.classes
    ]


async def test_decision_executor_multi_node_traversal_and_state_compilation() -> None:
    from openclass_core.models import ChoiceRequest, ChoiceResult

    billing_node = DecisionServiceNode(
        name="billing-specialist",
        instructions="Classify specific billing action",
        choices=(
            DecisionServiceChoice(key="REFUND", label="Refund", description="Issue refund"),
            DecisionServiceChoice(key="INVOICE", label="Invoice", description="Send invoice"),
        ),
    )
    root_node = DecisionServiceNode(
        name="root-router",
        instructions="Route customer ticket to department",
        choices=(
            DecisionServiceChoice(
                key="BILLING",
                label="Billing Department",
                description="Billing questions",
                target_node_id=billing_node.id,
            ),
            DecisionServiceChoice(
                key="TECH",
                label="Tech Support",
                description="Technical bugs",
            ),
        ),
    )
    service = DecisionService(
        project_id=uuid4(),
        slug="multi-hop-router",
        name="Multi-Hop Router",
        instructions="Route and specialize support requests",
        nodes=(root_node, billing_node),
    )

    seen_instructions: list[str] = []

    class HierarchicalProvider:
        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            seen_instructions.append(request.instructions or "")
            class_names = {c.canonical_name for c in request.ontology.classes}
            if "billing" in class_names:
                return ChoiceResult(
                    provider="jev",
                    model="typesafe-ai/jev",
                    probabilities={"billing": 0.85, "tech": 0.10},
                    unknown_probability=0.05,
                    latency_ms=12.5,
                )
            return ChoiceResult(
                provider="jev",
                model="typesafe-ai/jev",
                probabilities={"refund": 0.80, "invoice": 0.10},
                unknown_probability=0.10,
                latency_ms=15.0,
            )

    event = RawEvent(
        project_id=service.project_id,
        source_type="webhook",
        content="I was double charged, please refund my card.",
        metadata={"account_tier": "enterprise", "auto_refund_blocked": False},
    )
    run = await DecisionExecutor(HierarchicalProvider()).execute(event, service)

    assert run.selected_choice == "REFUND"
    assert run.decision_node_id == billing_node.id
    assert len(run.steps) == 2
    assert run.steps[0]["node_name"] == "root-router"
    assert run.steps[0]["selected_choice"] == "BILLING"
    assert run.steps[1]["node_name"] == "billing-specialist"
    assert run.steps[1]["selected_choice"] == "REFUND"
    assert run.latency_ms == 27.5
    assert run.state_snapshot["facts"] == {
        "account_tier": "enterprise",
        "auto_refund_blocked": False,
    }
    assert len(run.state_snapshot["resolved_decisions"]) == 1
    assert run.state_snapshot["resolved_decisions"][0]["choice"] == "BILLING"
    assert "Structured state facts:" in seen_instructions[1]
    assert "Prior resolved decisions: root-router=BILLING" in seen_instructions[1]


async def test_decision_executor_cycle_detection_and_node_supervision_policy() -> None:
    from openclass_core.models import ChoiceRequest, ChoiceResult

    node_a_id = uuid4()
    node_b_id = uuid4()
    node_a = DecisionServiceNode(
        id=node_a_id,
        name="node-a",
        instructions="Step A",
        choices=(DecisionServiceChoice(key="TO_B", label="To B", target_node_id=node_b_id),),
    )
    node_b = DecisionServiceNode(
        id=node_b_id,
        name="node-b",
        instructions="Step B",
        choices=(DecisionServiceChoice(key="TO_A", label="To A", target_node_id=node_a_id),),
    )
    cyclic_service = DecisionService(
        project_id=uuid4(),
        slug="cyclic-service",
        name="Cyclic Service",
        instructions="Cyclic graph",
        nodes=(node_a, node_b),
    )

    class AlwaysFirstChoiceProvider:
        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            first = request.ontology.classes[0].canonical_name
            return ChoiceResult(
                provider="jev",
                model="typesafe-ai/jev",
                probabilities={first: 0.90},
                unknown_probability=0.10,
            )

    event = RawEvent(project_id=cyclic_service.project_id, content="test cycle")
    with pytest.raises(ValueError, match="Decision graph cycle detected"):
        await DecisionExecutor(AlwaysFirstChoiceProvider()).execute(event, cyclic_service)

    # High-risk node and max_unknown_probability supervision checks
    high_risk_node = DecisionServiceNode(
        name="high-risk",
        instructions="Approve wire transfer",
        risk_level="high",
        choices=(DecisionServiceChoice(key="APPROVE", label="Approve"),),
    )
    hr_service = DecisionService(
        project_id=uuid4(),
        slug="high-risk-service",
        name="High Risk Service",
        instructions="High risk",
        nodes=(high_risk_node,),
    )
    hr_run = await DecisionExecutor(AlwaysFirstChoiceProvider()).execute(
        RawEvent(project_id=hr_service.project_id, content="wire transfer"),
        hr_service,
    )
    assert hr_run.selected_choice == "APPROVE"
    assert hr_run.supervision_outcome == "REVIEW"
    assert "High-risk" in hr_run.supervision_reason
