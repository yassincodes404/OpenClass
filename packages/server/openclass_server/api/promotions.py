"""Guarded ontology promotion, version history, diff, rollback."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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
                    "SELECT id, cluster_id, canonical_name, definition, aliases, status"
                    " FROM cluster_candidates"
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
            "cluster_id": record.cluster_id,
            "canonical_name": record.canonical_name,
            "definition": record.definition,
            "aliases": aliases or [],
            "status": record.status,
        }

    async def _latest_evaluation(project_id: UUID, candidate_id: str) -> dict[str, Any] | None:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, overall_passed, metrics FROM evaluation_runs"
                    " WHERE project_id = :pid AND candidate_id = :cid"
                    " ORDER BY created_at DESC LIMIT 1"
                ),
                {"pid": str(project_id), "cid": candidate_id},
            )
            record = row.first()
        if record is None:
            return None
        metrics = (
            json.loads(record.metrics)
            if isinstance(record.metrics, str)
            else (record.metrics or {})
        )
        return {
            "id": record.id,
            "overall_passed": bool(record.overall_passed),
            "metrics": metrics if isinstance(metrics, dict) else {},
        }

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

    async def _resolve_linked_unknowns(candidate_id: str, cluster_id: str | None) -> None:
        run_ids: set[str] = set()
        async with sessions() as session:
            ev_rows = await session.execute(
                sa.text("SELECT run_id FROM candidate_evidence WHERE candidate_id = :cid"),
                {"cid": candidate_id},
            )
            for row in ev_rows:
                if row.run_id:
                    run_ids.add(str(row.run_id))
            if cluster_id:
                cl_rows = await session.execute(
                    sa.text("SELECT run_id FROM cluster_members WHERE cluster_id = :clid"),
                    {"clid": str(cluster_id)},
                )
                for row in cl_rows:
                    if row.run_id:
                        run_ids.add(str(row.run_id))
        if not run_ids:
            return
        now_ts = datetime.now(UTC)
        async with sessions.begin() as session:
            for run_id in sorted(run_ids):
                await session.execute(
                    sa.text(
                        "INSERT INTO unknown_triage (run_id, status, updated_at)"
                        " VALUES (:run_id, 'resolved', :updated_at)"
                        " ON CONFLICT (run_id) DO UPDATE SET"
                        " status = 'resolved', updated_at = excluded.updated_at"
                    ),
                    {"run_id": run_id, "updated_at": now_ts},
                )

    @router.post("/api/v1/projects/{identifier}/discovery-candidates/{candidate_id}/promote")
    async def promote(identifier: str, candidate_id: str, body: PromoteRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        candidate = await _candidate(project.id, candidate_id)
        if not candidate["canonical_name"]:
            raise HTTPException(status_code=409, detail="candidate has no class to promote")
        if candidate["status"] == "active":
            raise HTTPException(status_code=409, detail="candidate is already active")
        if candidate["status"] != "approved":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"candidate status is '{candidate['status']}';"
                    " only human-approved candidates can promote"
                ),
            )
        evaluation = await _latest_evaluation(project.id, candidate_id)
        if evaluation is not None and evaluation["id"] != body.evaluation_id:
            # The referenced evaluation must be the current one for this candidate.
            raise HTTPException(
                status_code=409, detail="referenced evaluation is not the latest for this candidate"
            )
        if evaluation is not None:
            eval_metrics = evaluation.get("metrics") or {}
            reg_metrics = eval_metrics.get("regression_metrics") or {}
            regressions = int(
                reg_metrics.get("regressions", eval_metrics.get("regressions", 0)) or 0
            )
            if regressions > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Candidate evaluation recorded regressions on existing classes",
                )

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
        existing_terms: set[str] = set()
        for choice in current_choices:
            key_term = str(choice.get("key", "")).strip().casefold()
            if key_term:
                existing_terms.add(key_term)
                existing_terms.add(key_term.replace("_", " "))
            for alias in choice.get("aliases") or []:
                alias_term = str(alias).strip().casefold()
                if alias_term:
                    existing_terms.add(alias_term)

        proposed_key = str(candidate["canonical_name"]).strip().casefold()
        candidate_terms = {proposed_key, proposed_key.replace("_", " ")}
        for alias in candidate["aliases"]:
            alias_term = str(alias).strip().casefold()
            if alias_term:
                candidate_terms.add(alias_term)

        if existing_terms & candidate_terms:
            raise HTTPException(
                status_code=409,
                detail="Candidate key or alias collides with an existing active choice",
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

        await promotions.ensure_initial_version(service.id, current_choices)
        new_class = {
            "key": candidate["canonical_name"].upper(),
            "label": candidate["canonical_name"].replace("_", " ").title(),
            "description": candidate.get("definition") or f"Promoted from candidate {candidate_id}",
            "aliases": [str(alias) for alias in candidate["aliases"]][:10],
        }
        next_choices = current_choices + [new_class]
        version = await promotions.next_version(
            service.id,
            next_choices,
            origin="promotion",
            rationale=body.rationale,
            actor=body.reviewer,
        )
        await promotions.update_service_choices(
            service.id,
            next_choices,
            service_payload,
            version_id=version["id"],
            version_number=version["version_number"],
        )
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
        await _resolve_linked_unknowns(candidate_id, candidate.get("cluster_id"))
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
        await promotions.update_service_choices(
            service.id,
            target["choices"],
            service_payload,
            version_id=version["id"],
            version_number=version["version_number"],
        )
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
