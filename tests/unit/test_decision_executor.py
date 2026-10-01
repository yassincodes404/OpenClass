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

    # Real in-process Laya inference provenance
    real_provider = LayaDecisionProvider(allow_fallback=True)
    real_run = await DecisionExecutor(real_provider).execute(event, sample_service)
    assert real_run.execution_mode == "in_process"
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
