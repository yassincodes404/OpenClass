"""Unit tests for the Project domain service (in-memory repository)."""

import pytest
from openclass_core.projects import (
    Project,
    ProjectAuditEvent,
    ProjectRepository,
    ProjectService,
    ProjectStatus,
    ProjectUpdate,
    slugify,
)
from openclass_core.repositories import NotFoundError


class InMemoryProjects(ProjectRepository):
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.events: list[ProjectAuditEvent] = []

    async def create_project(self, project, audit_event) -> None:
        if project.slug in self.projects:
            from openclass_core.repositories import ConflictError

            raise ConflictError("Project slug already exists")
        self.projects[project.slug] = project
        self.events.append(audit_event)

    async def get_project(self, identifier: str) -> Project:
        if identifier in self.projects:
            return self.projects[identifier]
        for project in self.projects.values():
            if str(project.id) == identifier:
                return project
        from openclass_core.repositories import NotFoundError

        raise NotFoundError("Project not found")

    async def list_projects(self) -> list[Project]:
        return list(self.projects.values())

    async def slug_exists(self, slug: str) -> bool:
        return slug in self.projects

    async def update_project(self, project, audit_event) -> None:
        self.projects[project.slug] = project
        self.events.append(audit_event)

    async def audit_events(self, project_id) -> list[ProjectAuditEvent]:
        return [e for e in self.events if e.project_id == project_id]

    async def create_raw_event(self, event) -> None:
        if not hasattr(self, "raw_events"):
            self.raw_events: list = []
        # Mirrors the (project_id, content_hash) unique index from migration 0012.
        from openclass_core.repositories import ConflictError

        if any(
            e.project_id == event.project_id and e.content_hash == event.content_hash
            for e in self.raw_events
        ):
            raise ConflictError("Raw event already exists")
        self.raw_events.append(event)

    async def create_raw_events(self, events) -> None:
        if not hasattr(self, "raw_events"):
            self.raw_events = []
        self.raw_events.extend(events)

    async def list_raw_events(self, project_id, limit=50, offset=0):
        if not hasattr(self, "raw_events"):
            self.raw_events = []
        matched = [e for e in self.raw_events if e.project_id == project_id]
        return matched[offset : offset + limit]

    async def get_raw_event_by_hash(self, project_id, content_hash):
        if not hasattr(self, "raw_events"):
            self.raw_events = []
        return next(
            (
                e
                for e in self.raw_events
                if e.project_id == project_id and e.content_hash == content_hash
            ),
            None,
        )

    async def get_raw_event(self, project_id, event_id):
        if not hasattr(self, "raw_events"):
            self.raw_events = []
        for e in self.raw_events:
            if e.project_id == project_id and e.id == event_id:
                return e
        raise NotFoundError("Event not found")

    async def count_raw_events(self, project_id) -> int:
        if not hasattr(self, "raw_events"):
            self.raw_events = []
        return len([e for e in self.raw_events if e.project_id == project_id])

    async def create_decision_service(self, service) -> None:
        if not hasattr(self, "decision_services"):
            self.decision_services = []
        for s in self.decision_services:
            if s.project_id == service.project_id and s.slug == service.slug:
                from openclass_core.repositories import ConflictError

                raise ConflictError("Decision service slug already exists")
        self.decision_services.append(service)

    async def get_decision_service(self, project_id, identifier):
        if not hasattr(self, "decision_services"):
            self.decision_services = []
        for s in self.decision_services:
            if s.project_id == project_id and (str(s.id) == identifier or s.slug == identifier):
                return s
        raise NotFoundError("Decision service not found")

    async def list_decision_services(self, project_id):
        if not hasattr(self, "decision_services"):
            self.decision_services = []
        return [s for s in self.decision_services if s.project_id == project_id]

    async def update_decision_service(self, service) -> None:
        if not hasattr(self, "decision_services"):
            self.decision_services = []
        for i, s in enumerate(self.decision_services):
            if s.project_id == service.project_id and s.id == service.id:
                self.decision_services[i] = service
                return
        raise NotFoundError("Decision service not found")

    async def create_decision_run(self, run) -> None:
        if not hasattr(self, "decision_runs"):
            self.decision_runs = []
        self.decision_runs.append(run)

    async def list_decision_runs(self, project_id, limit=50, offset=0):
        if not hasattr(self, "decision_runs"):
            self.decision_runs = []
        matched = [r for r in self.decision_runs if r.project_id == project_id]
        return matched[offset : offset + limit]

    async def get_decision_run(self, project_id, run_id):
        if not hasattr(self, "decision_runs"):
            self.decision_runs = []
        for r in self.decision_runs:
            if r.project_id == project_id and r.id == run_id:
                return r
        raise NotFoundError("Decision run not found")

    async def count_decision_runs(self, project_id) -> int:
        if not hasattr(self, "decision_runs"):
            self.decision_runs = []
        return len([r for r in self.decision_runs if r.project_id == project_id])

    async def count_unknown_decision_runs(self, project_id) -> int:
        if not hasattr(self, "decision_runs"):
            self.decision_runs = []
        return len(
            [
                r
                for r in self.decision_runs
                if r.project_id == project_id and r.selected_choice == "UNKNOWN"
            ]
        )

    async def count_pending_choice_candidates(self, project_id) -> int:
        if not hasattr(self, "choice_candidates"):
            self.choice_candidates = []
        return len(
            [
                c
                for c in self.choice_candidates
                if c.project_id == project_id and c.status == "candidate"
            ]
        )

    # ── Evidence In-Memory Methods ────────────────────────────

    async def create_evidence_item(self, item, audit_event) -> None:
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        self.evidence_items.append(item)
        await self.audit_events_list.append(audit_event) if hasattr(
            self, "audit_events_list"
        ) else None

    async def list_evidence_items(
        self,
        project_id,
        *,
        status=None,
        trigger_type=None,
        decision_service_id=None,
        limit=50,
        offset=0,
    ):
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        res = [e for e in self.evidence_items if e.project_id == project_id]
        if status:
            res = [e for e in res if e.status == status]
        if trigger_type:
            res = [e for e in res if e.trigger_type == trigger_type]
        if decision_service_id:
            res = [e for e in res if e.decision_service_id == decision_service_id]
        return res[offset : offset + limit]

    async def get_evidence_item(self, project_id, evidence_id):
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        for e in self.evidence_items:
            if e.project_id == project_id and e.id == evidence_id:
                return e
        raise NotFoundError("Evidence item not found")

    async def update_evidence_item(self, item, audit_event) -> None:
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        for idx, e in enumerate(self.evidence_items):
            if e.project_id == item.project_id and e.id == item.id:
                self.evidence_items[idx] = item
                if hasattr(self, "audit_events_list"):
                    self.audit_events_list.append(audit_event)
                return
        raise NotFoundError("Evidence item not found")

    async def count_evidence_by_status(self, project_id) -> dict[str, int]:
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        counts: dict[str, int] = {}
        for e in self.evidence_items:
            if e.project_id == project_id:
                counts[e.status.value] = counts.get(e.status.value, 0) + 1
        return counts

    async def create_evidence_case(self, case, audit_event) -> None:
        if not hasattr(self, "evidence_cases"):
            self.evidence_cases = []
        self.evidence_cases.append(case)
        if hasattr(self, "audit_events_list"):
            self.audit_events_list.append(audit_event)

    async def get_evidence_case(self, project_id, case_id):
        if not hasattr(self, "evidence_cases"):
            self.evidence_cases = []
        for c in self.evidence_cases:
            if c.project_id == project_id and c.id == case_id:
                return c
        raise NotFoundError("Evidence case not found")

    async def list_evidence_cases(self, project_id, *, limit=50, offset=0):
        if not hasattr(self, "evidence_cases"):
            self.evidence_cases = []
        res = [c for c in self.evidence_cases if c.project_id == project_id]
        return res[offset : offset + limit]

    async def update_evidence_case(self, case, audit_event) -> None:
        if not hasattr(self, "evidence_cases"):
            self.evidence_cases = []
        for idx, c in enumerate(self.evidence_cases):
            if c.project_id == case.project_id and c.id == case.id:
                self.evidence_cases[idx] = case
                if hasattr(self, "audit_events_list"):
                    self.audit_events_list.append(audit_event)
                return
        raise NotFoundError("Evidence case not found")

    async def list_case_evidence(self, project_id, case_id):
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        return [
            e
            for e in self.evidence_items
            if e.project_id == project_id and e.evidence_case_id == case_id
        ]

    async def create_run_feedback(self, feedback, audit_event) -> None:
        if not hasattr(self, "run_feedbacks"):
            self.run_feedbacks = []
        self.run_feedbacks.append(feedback)
        if hasattr(self, "audit_events_list"):
            self.audit_events_list.append(audit_event)

    async def list_run_feedback(self, project_id, run_id):
        if not hasattr(self, "run_feedbacks"):
            self.run_feedbacks = []
        return [
            f
            for f in self.run_feedbacks
            if f.project_id == project_id and f.decision_run_id == run_id
        ]

    async def evolution_summary(self, project_id):
        from openclass_core.evidence import EvolutionSummary

        counts = await self.count_evidence_by_status(project_id)
        cases = await self.list_evidence_cases(project_id)
        open_cases = len([c for c in cases if c.status not in ("resolved", "dismissed")])
        total = sum(counts.values())
        return EvolutionSummary(
            pending_evidence=counts.get("pending", 0),
            triaged_evidence=counts.get("triaged", 0),
            ready_for_evolution=counts.get("ready_for_evolution", 0),
            resolved_evidence=counts.get("resolved", 0),
            dismissed_evidence=counts.get("dismissed", 0),
            total_evidence=total,
            open_cases=open_cases,
        )

    async def get_evidence_for_run(self, project_id, run_id):
        if not hasattr(self, "evidence_items"):
            self.evidence_items = []
        for e in self.evidence_items:
            if e.project_id == project_id and e.decision_run_id == run_id:
                return e
        return None


class SlowClock:
    """Deterministic clock whose every call advances time."""

    def __init__(self) -> None:
        self.ticks = 0

    def __call__(self):
        from datetime import UTC, datetime, timedelta

        self.ticks += 1
        return datetime(2026, 9, 25, tzinfo=UTC) + timedelta(minutes=self.ticks)


@pytest.fixture
def service() -> ProjectService:
    return ProjectService(InMemoryProjects(), clock=SlowClock())


async def test_create_generates_slug_and_audit(service: ProjectService) -> None:
    project = await service.create("GymHolic Intelligence", "Customer intelligence experiment")
    assert project.slug == "gymholic-intelligence"
    assert project.name == "GymHolic Intelligence"
    assert project.description == "Customer intelligence experiment"
    assert project.status == ProjectStatus.ACTIVE
    events = await service.audit(str(project.id))
    assert [e.event_type for e in events] == ["project.created"]
    assert events[0].payload["slug"] == "gymholic-intelligence"


async def test_create_rejects_blank_name(service: ProjectService) -> None:
    with pytest.raises(ValueError, match="name is required"):
        await service.create("   ")


async def test_slug_collisions_get_numeric_suffixes(service: ProjectService) -> None:
    first = await service.create("GymHolic Intelligence")
    second = await service.create("GymHolic Intelligence")
    third = await service.create("GymHolic Intelligence")
    assert [p.slug for p in (first, second, third)] == [
        "gymholic-intelligence",
        "gymholic-intelligence-2",
        "gymholic-intelligence-3",
    ]


def test_slugify_strips_and_dashes() -> None:
    assert slugify("  Hello, World!  ") == "hello-world"
    assert slugify("!!!") == "project"


async def test_update_records_only_real_changes(service: ProjectService) -> None:
    project = await service.create("GymHolic Intelligence")
    updated = await service.update(
        project.slug, ProjectUpdate(description="Now with a description")
    )
    assert updated.description == "Now with a description"
    assert updated.name == project.name
    events = await service.audit(str(project.id))
    assert [e.event_type for e in events] == ["project.created", "project.updated"]
    assert events[-1].payload == {"changes": {"description": "Now with a description"}}


async def test_no_change_update_records_nothing(service: ProjectService) -> None:
    project = await service.create("GymHolic Intelligence")
    same = await service.update(
        project.slug, ProjectUpdate(name=project.name, description=project.description)
    )
    assert same.updated_at == project.updated_at
    assert len(await service.audit(str(project.id))) == 1
    with pytest.raises(ValueError, match="at least one field"):
        ProjectUpdate()


async def test_status_archive_roundtrip(service: ProjectService) -> None:
    project = await service.create("GymHolic Intelligence")
    archived = await service.update(project.slug, ProjectUpdate(status=ProjectStatus.ARCHIVED))
    assert archived.status == ProjectStatus.ARCHIVED


async def test_get_accepts_id_or_slug_and_missing_raises(service: ProjectService) -> None:
    project = await service.create("GymHolic Intelligence")
    assert (await service.get(project.slug)).id == project.id
    assert (await service.get(str(project.id))).slug == project.slug
    with pytest.raises(NotFoundError):
        await service.get("missing-project")


async def test_raw_event_ingestion_and_summary_count(service: ProjectService) -> None:
    project = await service.create("Event Test Project")
    summary = await service.summary(project.slug)
    assert summary.events == 0

    event1, deduped = await service.ingest_event(
        project.slug,
        "Customer says: please add dark mode support",
        source_type="text",
        metadata={"author": "alice"},
    )
    assert deduped is False
    assert event1.project_id == project.id
    assert event1.content == "Customer says: please add dark mode support"
    assert event1.source_type == "text"
    assert event1.metadata["author"] == "alice"

    summary_after = await service.summary(project.slug)
    assert summary_after.events == 1

    events_list = await service.list_events(project.slug)
    assert len(events_list) == 1
    assert events_list[0].id == event1.id

    fetched = await service.get_event(project.slug, event1.id)
    assert fetched.content == event1.content

    repeat, repeat_deduped = await service.ingest_event(
        project.slug, "Customer says: please add dark mode support", source_type="text"
    )
    assert repeat_deduped is True
    assert repeat.id == event1.id


async def test_raw_event_batch_ingestion(service: ProjectService) -> None:
    project = await service.create("Batch Event Project")
    batch = [
        {"content": "First event message", "metadata": {"row": 1}},
        {"content": "Second event message", "metadata": {"row": 2}},
        {"content": "   "},  # blank, should be skipped
    ]
    created = await service.ingest_events_batch(project.slug, batch, source_type="csv")
    assert len(created) == 2
    assert created[0][0].source_type == "csv"
    assert created[1][0].source_type == "csv"
    assert all(deduped is False for _, deduped in created)

    events_list = await service.list_events(project.slug)
    assert len(events_list) == 2

    summary = await service.summary(project.slug)
    assert summary.events == 2
