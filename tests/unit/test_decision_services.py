"""Unit tests for DecisionService and DecisionRun domain rules."""

import pytest
from openclass_core.projects import (
    DecisionRun,
    DecisionServiceStatus,
    DecisionServiceUpdate,
    ProjectService,
)

from tests.unit.test_projects import InMemoryProjects, SlowClock


@pytest.fixture
def service() -> ProjectService:
    return ProjectService(InMemoryProjects(), clock=SlowClock())


async def test_create_decision_service_ensures_unknown_choice(service: ProjectService) -> None:
    project = await service.create("Support System", "Project for customer support")

    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Support Routing",
        instructions="Route support tickets to correct department",
        choices=[
            {"key": "BILLING", "label": "Billing Support", "description": "Payment issues"},
            {"key": "TECH", "label": "Technical Support", "description": "Software bugs"},
        ],
    )

    assert ds.name == "Support Routing"
    assert ds.slug == "support-routing"
    assert ds.status == DecisionServiceStatus.ACTIVE
    assert len(ds.nodes) == 1
    node = ds.nodes[0]
    choice_keys = [c.key for c in node.choices]
    # UNKNOWN must be automatically included
    assert "UNKNOWN" in choice_keys
    assert "BILLING" in choice_keys
    assert "TECH" in choice_keys


async def test_decision_service_requires_non_empty_name_and_instructions(
    service: ProjectService,
) -> None:
    project = await service.create("Project A", "Test")

    with pytest.raises(ValueError, match="decision service name is required"):
        await service.create_decision_service(
            identifier=str(project.id),
            name="   ",
            instructions="Route",
            choices=[{"key": "A", "label": "A"}],
        )

    with pytest.raises(ValueError, match="decision service instructions are required"):
        await service.create_decision_service(
            identifier=str(project.id),
            name="Service",
            instructions="   ",
            choices=[{"key": "A", "label": "A"}],
        )


async def test_update_decision_service(service: ProjectService) -> None:
    project = await service.create("Project B", "Test")

    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Routing",
        instructions="Route",
        choices=[{"key": "A", "label": "Choice A"}],
    )

    updated = await service.update_decision_service(
        identifier=str(project.id),
        service_id_or_slug=ds.slug,
        update=DecisionServiceUpdate(
            name="Advanced Routing", status=DecisionServiceStatus.ARCHIVED
        ),
    )

    assert updated.name == "Advanced Routing"
    assert updated.status == DecisionServiceStatus.ARCHIVED


async def test_decision_runs_persistence_and_counting(service: ProjectService) -> None:
    project = await service.create("Project C", "Test")

    ds = await service.create_decision_service(
        identifier=str(project.id),
        name="Triage",
        instructions="Triage incoming requests",
        choices=[{"key": "URGENT", "label": "Urgent"}],
    )

    event = await service.ingest_event(
        identifier=str(project.id),
        content="System down! Need help!",
        source_type="text",
    )

    run = DecisionRun(
        project_id=project.id,
        raw_event_id=event.id,
        decision_service_id=ds.id,
        decision_node_id=ds.nodes[0].id,
        provider="laya",
        model="laya-router",
        execution_mode="in_process",
        real_inference=True,
        selected_choice="URGENT",
        probabilities={"URGENT": 0.95, "UNKNOWN": 0.05},
        top_probability=0.95,
        second_probability=0.05,
        margin=0.90,
        unknown_probability=0.05,
        supervision_outcome="REVIEW",
        supervision_reason=(
            "Laya provider operates under research calibration (conservative supervision)"
        ),
        latency_ms=12.5,
        input_snapshot=event.model_dump(mode="json"),
        instructions_snapshot=ds.instructions,
        choices_snapshot=[c.model_dump(mode="json") for c in ds.nodes[0].choices],
    )

    await service.record_decision_run(run)

    runs = await service.list_decision_runs(str(project.id))
    assert len(runs) == 1
    assert runs[0].id == run.id
    assert runs[0].selected_choice == "URGENT"
    assert runs[0].real_inference is True
    assert runs[0].supervision_outcome == "REVIEW"

    fetched = await service.get_decision_run(str(project.id), run.id)
    assert fetched.id == run.id
    assert fetched.top_probability == 0.95

    # Check project summary counts decision runs
    summary = await service.summary(str(project.id))
    assert summary.decision_runs == 1
    assert summary.events == 1
