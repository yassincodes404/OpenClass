"""Cluster discovery → inactive candidates (never an ontology write)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from openclass_core.candidates import (
    ClusterDiscoveryRequest,
    MockClusterDiscoveryProvider,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.settings import Settings


def candidates_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    triage_store: UnknownTriageStore,
) -> APIRouter:
    router = APIRouter(tags=["candidates"])
    provider = MockClusterDiscoveryProvider()

    async def _member_texts(project_id: str, cluster_id: str) -> list[str]:
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT r.payload FROM cluster_members m"
                    " JOIN decision_runs r ON r.id = m.run_id"
                    " WHERE m.cluster_id = :cluster_id"
                ),
                {"cluster_id": cluster_id},
            )
        texts: list[str] = []
        for row in rows:
            payload = row.payload
            if isinstance(payload, str):
                payload = json.loads(payload)
            payload = payload if isinstance(payload, dict) else {}
            snapshot = payload.get("input_snapshot", {})
            snapshot = snapshot if isinstance(snapshot, dict) else {}
            texts.append(str(snapshot.get("content", "")))
        return texts

    async def _existing_classes(identifier: str) -> list[str]:
        services = await projects.list_decision_services(identifier=identifier)
        classes: list[str] = []
        for service in services:
            for node in service.nodes:
                classes.extend(
                    choice.key.lower() for choice in node.choices if choice.key != "UNKNOWN"
                )
        return classes

    @router.post(
        "/api/v1/projects/{identifier}/clusters/{cluster_id}/discover",
        status_code=201,
    )
    async def discover(identifier: str, cluster_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        async with sessions() as session:
            exists = await session.execute(
                sa.text(
                    "SELECT 1 FROM unknown_clusters WHERE id = :id AND project_id = :project_id"
                ),
                {"id": cluster_id, "project_id": str(project.id)},
            )
            if exists.first() is None:
                raise HTTPException(status_code=404, detail="Cluster not found")
        member_texts = await _member_texts(str(project.id), cluster_id)
        if not member_texts:
            raise HTTPException(status_code=400, detail="cluster has no members")
        result = await provider.discover(
            ClusterDiscoveryRequest(
                cluster_id=UUID(cluster_id),
                member_texts=tuple(member_texts[:20]),
                existing_classes=tuple(await _existing_classes(identifier)),
            )
        )
        candidate_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO cluster_candidates"
                    " (id, project_id, cluster_id, type, canonical_name, display_name,"
                    "  definition, aliases, existing_match, confidence, reason, status,"
                    "  provider, created_at)"
                    " VALUES (:id, :project_id, :cluster_id, :type, :canonical_name,"
                    "         :display_name, :definition, :aliases, :existing_match,"
                    "         :confidence, :reason, 'candidate', :provider, :created_at)"
                ),
                {
                    "id": candidate_id,
                    "project_id": str(project.id),
                    "cluster_id": cluster_id,
                    "type": result.type,
                    "canonical_name": result.canonical_name,
                    "display_name": result.display_name,
                    "definition": result.definition,
                    "aliases": json.dumps(list(result.aliases)),
                    "existing_match": result.existing_match,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "provider": "mock",
                    "created_at": datetime.now(UTC),
                },
            )
            for text_owner in await _member_run_ids(cluster_id):
                await session.execute(
                    sa.text(
                        "INSERT INTO candidate_evidence (candidate_id, run_id)"
                        " VALUES (:candidate_id, :run_id)"
                    ),
                    {"candidate_id": candidate_id, "run_id": text_owner},
                )
        await triage_store.append_audit(
            project.id,
            "portal-user",
            "candidate.created",
            f"candidate:{candidate_id}:{result.type}",
        )
        return {
            "id": candidate_id,
            "type": result.type,
            "canonical_name": result.canonical_name,
            "display_name": result.display_name,
            "definition": result.definition,
            "aliases": list(result.aliases),
            "existing_match": result.existing_match,
            "confidence": result.confidence,
            "reason": result.reason,
            "status": "candidate",
            "provider": "mock",
            "simulated": True,
        }

    @router.get("/api/v1/projects/{identifier}/discovery-candidates")
    async def list_candidates(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT c.id, c.cluster_id, c.type, c.canonical_name, c.display_name,"
                    " c.confidence, c.status, c.provider, c.created_at,"
                    " (SELECT count(*) FROM candidate_evidence e"
                    "  WHERE e.candidate_id = c.id) AS evidence"
                    " FROM cluster_candidates c WHERE c.project_id = :project_id"
                    " ORDER BY c.created_at DESC"
                ),
                {"project_id": str(project.id)},
            )
            return [
                {
                    "id": row.id,
                    "cluster_id": row.cluster_id,
                    "type": row.type,
                    "canonical_name": row.canonical_name,
                    "display_name": row.display_name,
                    "confidence": row.confidence,
                    "status": row.status,
                    "provider": row.provider,
                    "simulated": row.provider == "mock",
                    "evidence_count": row.evidence,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    @router.get("/api/v1/projects/{identifier}/discovery-candidates/{candidate_id}")
    async def candidate_detail(identifier: str, candidate_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        async with sessions() as session:
            result = await session.execute(
                sa.text(
                    "SELECT id, cluster_id, type, canonical_name, display_name, definition,"
                    " aliases, existing_match, confidence, reason, status, provider, created_at"
                    " FROM cluster_candidates WHERE id = :id AND project_id = :project_id"
                ),
                {"id": candidate_id, "project_id": str(project.id)},
            )
            record = result.first()
            if record is None:
                raise HTTPException(status_code=404, detail="Candidate not found")
            evidence = await session.execute(
                sa.text("SELECT run_id FROM candidate_evidence WHERE candidate_id = :candidate_id"),
                {"candidate_id": candidate_id},
            )
        return {
            "id": record.id,
            "cluster_id": record.cluster_id,
            "type": record.type,
            "canonical_name": record.canonical_name,
            "display_name": record.display_name,
            "definition": record.definition,
            "aliases": json.loads(record.aliases)
            if isinstance(record.aliases, str)
            else record.aliases,
            "existing_match": record.existing_match,
            "confidence": record.confidence,
            "reason": record.reason,
            "status": record.status,
            "provider": record.provider,
            "simulated": record.provider == "mock",
            "evidence_run_ids": [e.run_id for e in evidence],
            "created_at": record.created_at,
        }

    async def _member_run_ids(cluster_id: str) -> list[str]:
        async with sessions() as session:
            rows = await session.execute(
                sa.text("SELECT run_id FROM cluster_members WHERE cluster_id = :cluster_id"),
                {"cluster_id": cluster_id},
            )
            return [row.run_id for row in rows]

    return router
