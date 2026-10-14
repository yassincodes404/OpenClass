"""UNKNOWN workspace routes: pool listing, triage, transitions, trends."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from openclass_core.evidence import EvidenceStatus
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.repositories import ConflictError
from openclass_core.unknown_pool import (
    UnknownCategory,
    UnknownItem,
    UnknownStatus,
    UnknownTriage,
    run_is_unknown,
    summarize_unknowns,
    validate_transition,
)
from pydantic import BaseModel, Field

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.redaction import configured_blocklist, redact_text
from openclass_server.settings import Settings


class TriageRequest(BaseModel):
    category: UnknownCategory
    assignee: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class TransitionRequest(BaseModel):
    to: UnknownStatus


def unknowns_router(
    config: Settings, projects: ProjectDomainService, triage_store: UnknownTriageStore
) -> APIRouter:
    router = APIRouter(tags=["unknowns"])

    async def _sync_evidence_transition(
        identifier: str, run_uuid: UUID, target_unknown_status: UnknownStatus
    ) -> None:
        evidence_items = await projects.list_evidence(identifier=identifier, limit=200, offset=0)
        matching = [item for item in evidence_items if item.decision_run_id == run_uuid]
        for ev in matching:
            try:
                if target_unknown_status == "triaged" and ev.status == EvidenceStatus.PENDING:
                    await projects.transition_evidence(
                        identifier=identifier,
                        evidence_id=ev.id,
                        target_status=EvidenceStatus.TRIAGED,
                        rationale="Synchronized from unknown workspace triaged transition",
                    )
                elif target_unknown_status == "dismissed" and ev.status in {
                    EvidenceStatus.PENDING,
                    EvidenceStatus.TRIAGED,
                }:
                    await projects.transition_evidence(
                        identifier=identifier,
                        evidence_id=ev.id,
                        target_status=EvidenceStatus.DISMISSED,
                        rationale="Synchronized from unknown workspace dismissed transition",
                    )
            except ConflictError:
                pass

    async def _unknown_items(
        project_id: str, scan_limit: int = 1000
    ) -> tuple[list[UnknownItem], int]:
        project = await projects.get(project_id)
        runs = await projects.list_decision_runs(identifier=project_id, limit=scan_limit, offset=0)
        triage = await triage_store.list_all(project.id)
        items: list[UnknownItem] = []
        recurrence: dict[str, int] = {}
        for run in runs:
            content = str(run.input_snapshot.get("content", ""))
            hash_key = str(run.input_snapshot.get("content_hash", content))
            recurrence[hash_key] = recurrence.get(hash_key, 0) + 1
        for run in runs:
            if not run_is_unknown(run):
                continue
            content = str(run.input_snapshot.get("content", ""))
            hash_key = str(run.input_snapshot.get("content_hash", content))
            items.append(
                UnknownItem(
                    run_id=str(run.id),
                    raw_event_id=str(run.raw_event_id),
                    decision_service_id=str(run.decision_service_id),
                    content=content,
                    probabilities=dict(run.probabilities),
                    unknown_probability=run.unknown_probability,
                    supervision_reason=run.supervision_reason,
                    created_at=run.created_at,
                    triage=triage.get(str(run.id)) or UnknownTriage(run_id=str(run.id)),
                    recurrence=recurrence.get(hash_key, 1),
                )
            )
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items, len(runs)

    async def _resolve_unknown_item(identifier: str, run_id: str) -> UnknownItem:
        items, _ = await _unknown_items(identifier)
        item = next((entry for entry in items if entry.run_id == run_id), None)
        if item is not None:
            return item
        run_uuid = _uuid(run_id)
        if run_uuid is None:
            raise HTTPException(status_code=404, detail="Unknown event not found")
        try:
            run = await projects.get_decision_run(identifier=identifier, run_id=run_uuid)
        except Exception as err:
            raise HTTPException(status_code=404, detail="Unknown event not found") from err
        if not run_is_unknown(run):
            raise HTTPException(status_code=404, detail="Unknown event not found")
        existing_triage = await triage_store.get(run_uuid) or UnknownTriage(run_id=str(run.id))
        content = str(run.input_snapshot.get("content", ""))
        return UnknownItem(
            run_id=str(run.id),
            raw_event_id=str(run.raw_event_id),
            decision_service_id=str(run.decision_service_id),
            content=content,
            probabilities=dict(run.probabilities),
            unknown_probability=run.unknown_probability,
            supervision_reason=run.supervision_reason,
            created_at=run.created_at,
            triage=existing_triage,
            recurrence=1,
        )

    @router.get("/api/v1/projects/{identifier}/unknowns")
    async def list_unknowns(
        identifier: str,
        state: Annotated[str | None, Query()] = None,
        category: Annotated[str | None, Query()] = None,
        query: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        items, _total = await _unknown_items(identifier)
        if state:
            items = [item for item in items if item.triage.status == state]
        if category:
            items = [item for item in items if item.triage.category == category]
        if query:
            needle = query.lower()
            items = [item for item in items if needle in item.content.lower()]
        page = items[offset : offset + limit]
        blocklist = configured_blocklist(config.redaction_blocklist)
        # Previews are redacted; full content stays member-gated at the proxy.
        return {
            "items": [
                {
                    **item.model_dump(mode="json"),
                    "status": item.triage.status,
                    "content": redact_text(
                        item.content, blocklist, enabled=config.redaction_enabled
                    )[:160],
                }
                for item in page
            ],
            "next_cursor": str(offset + limit) if offset + limit < len(items) else None,
        }

    @router.get("/api/v1/projects/{identifier}/unknowns/stats")
    async def unknown_stats(
        identifier: str,
        bucket: Annotated[str | None, Query(pattern=r"^(day)$")] = "day",
    ) -> dict[str, Any]:
        if bucket != "day":
            raise HTTPException(status_code=400, detail="only day buckets are supported")
        items, total_runs = await _unknown_items(identifier)
        stats = summarize_unknowns(items, total_runs)
        return stats.model_dump(mode="json")

    @router.get("/api/v1/projects/{identifier}/unknowns/{run_id}")
    async def unknown_detail(identifier: str, run_id: str) -> dict[str, Any]:
        item = await _resolve_unknown_item(identifier, run_id)
        return {**item.model_dump(mode="json"), "status": item.triage.status}

    @router.post("/api/v1/projects/{identifier}/unknowns/{run_id}/triage")
    async def triage(identifier: str, run_id: str, body: TriageRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        await _resolve_unknown_item(identifier, run_id)
        run_uuid = _uuid(run_id)
        if run_uuid is None:
            raise HTTPException(status_code=404, detail="Unknown event not found")
        existing = await triage_store.get(run_uuid) or UnknownTriage(run_id=run_id)
        updated = existing.model_copy(
            update={"category": body.category, "assignee": body.assignee, "note": body.note}
        )
        await triage_store.upsert(updated)
        await triage_store.append_audit(
            project.id, "portal-user", "unknown.triaged", f"run:{run_id}:{body.category}"
        )
        return updated.model_dump(mode="json")

    @router.post("/api/v1/projects/{identifier}/unknowns/{run_id}/transition")
    async def transition(identifier: str, run_id: str, body: TransitionRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        await _resolve_unknown_item(identifier, run_id)
        run_uuid = _uuid(run_id)
        if run_uuid is None:
            raise HTTPException(status_code=404, detail="Unknown event not found")
        existing = await triage_store.get(run_uuid) or UnknownTriage(run_id=run_id)
        try:
            validate_transition(existing.status, body.to)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        updated = existing.model_copy(update={"status": body.to})
        await triage_store.upsert(updated)
        await _sync_evidence_transition(identifier, run_uuid, body.to)
        await triage_store.append_audit(
            project.id, "portal-user", "unknown.transitioned", f"run:{run_id}:{body.to}"
        )
        return updated.model_dump(mode="json")

    return router


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
