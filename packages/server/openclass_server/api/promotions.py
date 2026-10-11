"""Guarded ontology promotion, version history, diff, rollback."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.promotion import (
    PromotionBlocked,
    diff_choices,
    ensure_promotion_guards,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.promotion_store import PromotionStore
from openclass_server.settings import Settings


class PromoteRequest(BaseModel):
    evaluation_id: str = Field(min_length=36, max_length=36)
    reviewer: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=5, max_length=2000)


class RollbackRequest(BaseModel):
    from_version: int = Field(ge=1)
    rationale: str = Field(min_length=5, max_length=2000)


def promotions_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    promotions: PromotionStore,
) -> APIRouter:
    router = APIRouter(tags=["promotion"])

    async def _service(identifier: str) -> tuple[Any, Any]:
        services = await projects.list_decision_services(identifier=identifier)
        if not services:
            raise HTTPException(status_code=400, detail="project has no decision service")
        return services[0].model_dump(mode="json"), services[0]

    async def _candidate(project_id: UUID, candidate_id: str) -> dict[str, Any]:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, canonical_name, aliases, status FROM cluster_candidates"
                    " WHERE id = :id AND project_id = :pid"
                ),
                {"id": candidate_id, "pid": str(project_id)},
            )
            record = row.first()
        if record is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        aliases = record.aliases
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        return {
            "id": record.id,
            "canonical_name": record.canonical_name,
            "aliases": aliases or [],
            "status": record.status,
        }

    async def _latest_evaluation(project_id: UUID, candidate_id: str) -> dict[str, Any] | None:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, overall_passed FROM evaluation_runs"
                    " WHERE project_id = :pid AND candidate_id = :cid"
                    " ORDER BY created_at DESC LIMIT 1"
                ),
                {"pid": str(project_id), "cid": candidate_id},
            )
            record = row.first()
        if record is None:
            return None
        return {"id": record.id, "overall_passed": bool(record.overall_passed)}

    async def _evidence_count(candidate_id: str) -> int:
        async with sessions() as session:
            count = await session.execute(
                sa.text("SELECT count(*) FROM candidate_evidence WHERE candidate_id = :cid"),
                {"cid": candidate_id},
            )
            return int(count.scalar() or 0)

    async def _set_candidate_status(candidate_id: str, status: str) -> None:
        async with sessions.begin() as session:
            await session.execute(
                sa.text("UPDATE cluster_candidates SET status = :status WHERE id = :id"),
                {"status": status, "id": candidate_id},
            )

    @router.post("/api/v1/projects/{identifier}/discovery-candidates/{candidate_id}/promote")
    async def promote(identifier: str, candidate_id: str, body: PromoteRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        candidate = await _candidate(project.id, candidate_id)
        if not candidate["canonical_name"]:
            raise HTTPException(status_code=409, detail="candidate has no class to promote")
        if candidate["status"] == "active":
            raise HTTPException(status_code=409, detail="candidate is already active")
        evaluation = await _latest_evaluation(project.id, candidate_id)
        if evaluation is not None and evaluation["id"] != body.evaluation_id:
            # The referenced evaluation must be the current one for this candidate.
            raise HTTPException(
                status_code=409, detail="referenced evaluation is not the latest for this candidate"
            )
        try:
            ensure_promotion_guards(
                candidate_status=candidate["status"],
                evidence_count=await _evidence_count(candidate_id),
                evaluation_passed=None if evaluation is None else evaluation["overall_passed"],
                rationale=body.rationale,
                reviewer=body.reviewer,
            )
        except PromotionBlocked as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        service_payload, service = await _service(identifier)
        current_choices = [
            {
                "key": choice.key,
                "label": choice.label,
                "description": choice.description,
                "aliases": list(getattr(choice, "aliases", ()) or ()),
            }
            for choice in service.nodes[0].choices
            if choice.key != "UNKNOWN"
        ]
        await promotions.ensure_initial_version(service.id, current_choices)
        new_class = {
            "key": candidate["canonical_name"].upper(),
            "label": candidate["canonical_name"].replace("_", " ").title(),
            "description": f"Promoted from candidate {candidate_id}",
            "aliases": [str(alias) for alias in candidate["aliases"]][:10],
        }
        # The engine's choice model forbids extra fields: aliases live only in
        # the version snapshot and replay, not in the live service payload.
        next_choices = current_choices + [new_class]
        engine_choices = [
            {k: v for k, v in choice.items() if k != "aliases"} for choice in next_choices
        ]
        version = await promotions.next_version(
            service.id,
            next_choices,
            origin="promotion",
            rationale=body.rationale,
            actor=body.reviewer,
        )
        await promotions.update_service_choices(service.id, engine_choices, service_payload)
        await promotions.record_event(
            project.id,
            service.id,
            "ontology.class_added",
            body.reviewer,
            version["version_number"],
            {"class": new_class["key"], "candidate_id": candidate_id},
            from_version=version["parent"],
        )
        await _set_candidate_status(candidate_id, "active")
        return {
            "candidate_id": candidate_id,
            "status": "active",
            "version": version,
            "added_class": new_class["key"],
        }

    @router.get("/api/v1/projects/{identifier}/ontology")
    async def ontology(identifier: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        _payload, service = await _service(identifier)
        current_choices = [
            {
                "key": choice.key,
                "label": choice.label,
                "aliases": list(getattr(choice, "aliases", ()) or ()),
            }
            for choice in service.nodes[0].choices
        ]
        versions = await promotions.list_versions(service.id)
        events = await promotions.list_events(project.id)
        return {
            "service_id": str(service.id),
            "current_choices": current_choices,
            "versions": [
                {
                    "version_number": v["version_number"],
                    "origin": v["origin"],
                    "rationale": v["rationale"],
                    "actor": v["actor"],
                    "created_at": v["created_at"],
                    "choices": v["choices"],
                }
                for v in versions
            ],
            "events": events,
        }

    @router.get("/api/v1/projects/{identifier}/ontology/diff")
    async def ontology_diff(
        identifier: str,
        from_version: int,
        to_version: int,
    ) -> dict[str, Any]:
        _payload, service = await _service(identifier)
        before = await promotions.version_by_number(service.id, from_version)
        after = await promotions.version_by_number(service.id, to_version)
        if before is None or after is None:
            raise HTTPException(status_code=404, detail="version not found")
        return {
            "from_version": from_version,
            "to_version": to_version,
            "changes": diff_choices(before["choices"], after["choices"]),
        }

    @router.post("/api/v1/projects/{identifier}/ontology/rollback")
    async def rollback(identifier: str, body: RollbackRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        service_payload, service = await _service(identifier)
        current_choices = [
            {
                "key": choice.key,
                "label": choice.label,
                "description": choice.description,
                "aliases": list(getattr(choice, "aliases", ()) or ()),
            }
            for choice in service.nodes[0].choices
            if choice.key != "UNKNOWN"
        ]
        await promotions.ensure_initial_version(service.id, current_choices)
        target = await promotions.version_by_number(service.id, body.from_version)
        if target is None:
            raise HTTPException(status_code=404, detail="version not found")
        versions = await promotions.list_versions(service.id)
        latest = max(v["version_number"] for v in versions)
        if body.from_version == latest:
            raise HTTPException(status_code=409, detail="cannot roll back to the current version")
        version = await promotions.next_version(
            service.id,
            target["choices"],
            origin="rollback",
            rationale=body.rationale,
            actor="portal-user",
        )
        await promotions.update_service_choices(service.id, target["choices"], service_payload)
        await promotions.record_event(
            project.id,
            service.id,
            "ontology.rollback",
            "portal-user",
            version["version_number"],
            {"rolled_back_to": body.from_version, "rationale": body.rationale},
            from_version=version["parent"],
        )
        return {
            "version": version,
            "restored_choices": target["choices"],
            "rolled_back_to": body.from_version,
        }

    return router
