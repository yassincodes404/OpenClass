"""Unit tests for DecisionExecutor compilation, provider dispatch, and supervision."""

from uuid import uuid4

import pytest
from openclass_core.decision import StateFeature, StateSchema
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.projects import (
    DecisionService,
    DecisionServiceChoice,
    DecisionServiceNode,
    RawEvent,
)
from openclass_core.state_compiler import RuntimeDecisionConfig
from openclass_core.supervision import (
    InferenceProvenance,
    OperatingProfile,
    ProvenancedChoiceResult,
)
from openclass_provider_laya import LayaDecisionProvider
from openclass_provider_mock import MockDecisionProvider


@pytest.mark.parametrize("allow_simulated", [False, True])
async def test_calibrated_profile_cannot_authorize_actual_laya_lexical_fallback(
    monkeypatch,
    allow_simulated,
):
    import httpx

    # Exercise Laya.choice -> real _http_choice transport failure -> lexical fallback,
    # without contacting a daemon or replacing the adapter's fallback implementation.
    original_init = httpx.AsyncClient.__init__
    calls = []

    def unavailable(request):
        calls.append(request)
        raise httpx.ConnectError("synthetic offline daemon", request=request)

    def offline_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(unavailable)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", offline_init)
    downstream = DecisionServiceNode(
        name="downstream",
        instructions="Resolve billing",
        choices=(DecisionServiceChoice(key="DONE", label="Billing"),),
    )
    root = DecisionServiceNode(
        name="root",
        instructions="Route billing",
        choices=(
            DecisionServiceChoice(
                key="BILLING",
                label="Billing",
                target_node_id=downstream.id,
            ),
        ),
    )
    service = DecisionService(
        project_id=uuid4(),
        slug="fallback-proof",
        name="Fallback proof",
        instructions="Route billing",
        nodes=(root, downstream),
        runtime_config=RuntimeDecisionConfig(
            operating_profile=OperatingProfile(
                calibration_status="calibrated",
                validation_artifact_hash="synthetic-fixture-not-empirical",
                measured_max_choices=3,
                allow_simulated_continuation=allow_simulated,
            )
        ),
    )
    executor = DecisionExecutor(
        LayaDecisionProvider(
            prefer_local_process=False,
            allow_fallback=True,
        )
    )
    run = await executor.execute(
        RawEvent(project_id=service.project_id, content="billing"), service
    )
    assert run.execution_mode == "deterministic_test_fallback"
    assert run.real_inference is False
    assert run.provider_metadata["simulated"] is True
    assert run.supervision_outcome == "REVIEW"
    assert run.run_status == "paused"
    assert len(run.steps) == len(calls) == 1
    assert "calibrated operating thresholds satisfied" not in run.supervision_reason

    # Approval of the root node cannot lend authority to a new fallback inference.
    from openclass_core.projects import DecisionRun

    checkpoint = DecisionRun.model_validate_json(run.model_dump_json())
    restarted_executor = DecisionExecutor(
        LayaDecisionProvider(
            prefer_local_process=False,
            allow_fallback=True,
        )
    )
    resumed = await restarted_executor.resume(checkpoint, service, approved_choice="BILLING")
    assert resumed.run_status == "paused"
    assert resumed.current_node_key == "downstream"
    assert resumed.supervision_outcome == "REVIEW"
    assert resumed.steps[0]["supervision_outcome"] == "TRUSTED"
    assert resumed.steps[1]["supervision_outcome"] == "REVIEW"
    assert resumed.steps[1]["inference_provenance"] == {
        "execution_mode": "deterministic_test_fallback",
        "simulated": True,
    }
    assert len(calls) == 2


@pytest.mark.parametrize("provider_name", ["jev", "laya", "gateway", "arbitrary"])
async def test_plain_result_metadata_cannot_forge_calibrated_inference(
    sample_service,
    provider_name,
):
    from openclass_core.models import ChoiceResult

    class UnattributedProvider:
        async def choice(self, request):
            return ChoiceResult(
                provider=provider_name,
                model="unattributed-fixture",
                probabilities={"positive": 0.95, "negative": 0},
                unknown_probability=0.05,
                provider_metadata={
                    "real_inference": True,
                    "simulated": False,
                    "execution_mode": "api",
                    "calibration_status": "calibrated",
                    "inference_provenance": {"execution_mode": "api", "simulated": False},
                },
            )

    service = sample_service.model_copy(
        update={
            "runtime_config": RuntimeDecisionConfig(
                operating_profile=OperatingProfile(
                    calibration_status="calibrated",
                    validation_artifact_hash="synthetic-fixture-not-empirical",
                    measured_max_choices=3,
                ),
            )
        }
    )
    run = await DecisionExecutor(UnattributedProvider()).execute(
        RawEvent(project_id=service.project_id, content="positive"),
        service,
    )
    assert run.supervision_outcome == "REVIEW"
    assert run.real_inference is False
    assert run.steps[0]["inference_provenance"] is None
    assert run.provider_metadata["inference_provenance"] is None


@pytest.mark.parametrize("allow_simulated", [False, True])
async def test_mock_continuation_requires_explicit_simulation_opt_in(
    sample_service,
    allow_simulated,
):
    service = sample_service.model_copy(
        update={
            "runtime_config": RuntimeDecisionConfig(
                operating_profile=OperatingProfile(
                    calibration_status="simulated",
                    allow_simulated_continuation=allow_simulated,
                ),
            )
        }
    )
    run = await DecisionExecutor(MockDecisionProvider()).execute(
        RawEvent(project_id=service.project_id, content="positive"),
        service,
    )
    assert run.supervision_outcome == ("TRUSTED" if allow_simulated else "REVIEW")
    assert run.real_inference is False
    assert run.provider_metadata["simulated"] is True
    if allow_simulated:
        assert "Simulated fixture" in run.supervision_reason


def test_legacy_service_hash_is_preserved_without_runtime_configuration(sample_service):
    import json
    from hashlib import sha256

    from openclass_core.projects import compute_service_hash

    legacy_snapshot = sample_service.model_dump(mode="json")
    legacy_snapshot.pop("runtime_config")
    legacy_hash = sha256(
        json.dumps(legacy_snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert compute_service_hash(sample_service) == legacy_hash


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
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
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
        runtime_config=RuntimeDecisionConfig(
            state_schema=StateSchema(
                id="runtime_state",
                version=1,
                features=(
                    StateFeature(
                        id="account_tier",
                        kind="string",
                        sensor_field="account_tier",
                        required=False,
                    ),
                    StateFeature(
                        id="auto_refund_blocked",
                        kind="boolean",
                        sensor_field="auto_refund_blocked",
                        required=False,
                    ),
                    StateFeature(
                        id="customer_tier",
                        kind="string",
                        sensor_field="customer_tier",
                        required=False,
                    ),
                ),
            )
        ),
    )

    seen_instructions: list[str] = []
    seen_metadata: list[dict] = []

    class HierarchicalProvider:
        operating_profile = OperatingProfile(
            calibration_status="simulated", allow_simulated_continuation=True
        )

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            seen_instructions.append(request.instructions or "")
            seen_metadata.append(request.observation.metadata)
            class_names = {c.canonical_name for c in request.ontology.classes}
            if "billing" in class_names:
                return ProvenancedChoiceResult(
                    inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
                    provider="jev",
                    model="typesafe-ai/jev",
                    probabilities={"billing": 0.85, "tech": 0.10},
                    unknown_probability=0.05,
                    latency_ms=12.5,
                )
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
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
    assert seen_metadata[1]["state_facts"] == run.state_snapshot["facts"]
    assert seen_metadata[1]["resolved_decisions"][0]["choice"] == "BILLING"
    assert "enterprise" not in seen_instructions[1]  # data is not promoted to instructions


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
        operating_profile = OperatingProfile(
            calibration_status="simulated", allow_simulated_continuation=True
        )

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            first = request.ontology.classes[0].canonical_name
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
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
    assert hr_run.run_status == "paused"
    assert hr_run.current_node_key == high_risk_node.name
    assert hr_run.decision_node_id == high_risk_node.id


async def test_decision_executor_multi_node_pause_and_resume_downstream_execution() -> None:
    from openclass_core.models import ChoiceRequest, ChoiceResult
    from openclass_core.projects import DecisionServiceTransition

    billing_node = DecisionServiceNode(
        name="billing-specialist",
        instructions="Classify specific billing action",
        choices=(
            DecisionServiceChoice(key="REFUND", label="Refund", description="Issue refund"),
            DecisionServiceChoice(key="INVOICE", label="Invoice", description="Send invoice"),
            DecisionServiceChoice(key="UNKNOWN", label="Unknown", description="Unknown"),
        ),
    )
    root_node = DecisionServiceNode(
        name="root-router",
        instructions="Route customer ticket to department",
        pause_on_review=True,
        choices=(
            DecisionServiceChoice(
                key="BILLING",
                label="Billing Department",
                description="Billing questions",
            ),
            DecisionServiceChoice(
                key="TECH",
                label="Tech Support",
                description="Technical bugs",
            ),
            DecisionServiceChoice(
                key="UNKNOWN",
                label="Unknown",
                description="Unknown",
            ),
        ),
    )
    transition = DecisionServiceTransition(
        from_node_key="root-router",
        choice_key="BILLING",
        to_node_key="billing-specialist",
        require_approval=True,
    )
    service = DecisionService(
        project_id=uuid4(),
        slug="supervised-router",
        name="Supervised Router",
        instructions="Route and specialize support requests",
        nodes=(root_node, billing_node),
        runtime_config=RuntimeDecisionConfig(
            state_schema=StateSchema(
                id="runtime_state",
                version=1,
                features=(
                    StateFeature(
                        id="account_tier",
                        kind="string",
                        sensor_field="account_tier",
                        required=False,
                    ),
                    StateFeature(
                        id="auto_refund_blocked",
                        kind="boolean",
                        sensor_field="auto_refund_blocked",
                        required=False,
                    ),
                    StateFeature(
                        id="customer_tier",
                        kind="string",
                        sensor_field="customer_tier",
                        required=False,
                    ),
                ),
            )
        ),
        transitions=(transition,),
    )

    executed_nodes: list[str] = []

    class TwoStageProvider:
        operating_profile = OperatingProfile(
            calibration_status="simulated", allow_simulated_continuation=True
        )

        async def choice(self, request: ChoiceRequest) -> ChoiceResult:
            class_names = {c.canonical_name for c in request.ontology.classes}
            if "billing" in class_names:
                executed_nodes.append("root-router")
                return ProvenancedChoiceResult(
                    inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
                    provider="jev",
                    model="typesafe-ai/jev",
                    probabilities={"billing": 0.48, "tech": 0.42},
                    unknown_probability=0.10,
                    latency_ms=10.0,
                )
            executed_nodes.append("billing-specialist")
            return ProvenancedChoiceResult(
                inference_provenance=InferenceProvenance(execution_mode="mock", simulated=True),
                provider="jev",
                model="typesafe-ai/jev",
                probabilities={"refund": 0.90, "invoice": 0.05},
                unknown_probability=0.05,
                latency_ms=14.0,
            )

    event = RawEvent(
        project_id=service.project_id,
        source_type="webhook",
        content="Customer wants a billing review and refund.",
        metadata={"customer_tier": "vip"},
    )
    executor = DecisionExecutor(TwoStageProvider())
    paused_run = await executor.execute(event, service)

    # Node 2 MUST NOT execute while Node 1 is paused for supervision/approval
    assert executed_nodes == ["root-router"]
    assert paused_run.run_status == "paused"
    assert paused_run.current_node_key == "root-router"
    assert paused_run.next_node_key == "billing-specialist"
    assert paused_run.decision_node_id == root_node.id
    assert len(paused_run.steps) == 1
    assert paused_run.steps[0]["node_name"] == "root-router"
    assert paused_run.pending_operation is not None
    assert paused_run.pending_operation["node_key"] == "root-router"
    assert paused_run.pending_operation["next_node_key"] == "billing-specialist"

    # Resume with approved choice BILLING -> executes downstream Node 2
    resumed_run = await executor.resume(
        paused_run,
        service,
        approved_choice="BILLING",
        operator="senior-reviewer",
        rationale="Confirmed billing refund request.",
    )

    assert executed_nodes == ["root-router", "billing-specialist"]
    assert resumed_run.run_status == "completed"
    assert resumed_run.current_node_key == "billing-specialist"
    assert resumed_run.next_node_key is None
    assert resumed_run.pending_operation is None
    assert resumed_run.resumed_by == "senior-reviewer"
    assert resumed_run.resume_rationale == "Confirmed billing refund request."
    assert resumed_run.resumed_at is not None
    assert resumed_run.selected_choice == "REFUND"
    assert resumed_run.decision_node_id == billing_node.id
    assert len(resumed_run.steps) == 2
    assert resumed_run.steps[0]["selected_choice"] == "BILLING"
    assert resumed_run.steps[0]["supervision_outcome"] == "TRUSTED"
    assert resumed_run.steps[0]["approved_by"] == "senior-reviewer"
    assert resumed_run.steps[1]["node_name"] == "billing-specialist"
    assert resumed_run.steps[1]["selected_choice"] == "REFUND"
    assert resumed_run.state_snapshot["facts"] == {"customer_tier": "vip"}
    assert resumed_run.state_snapshot["resolved_decisions"][0]["choice"] == "BILLING"
