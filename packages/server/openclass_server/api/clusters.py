"""UNKNOWN clustering routes: deterministic grouping with provenance."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from openclass_core.embeddings import EmbeddedItem, group_into_clusters
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.unknown_pool import run_is_unknown
from pydantic import BaseModel, Field

from openclass_server.embeddings_local import HashLexicalEmbedder
from openclass_server.persistence.cluster_store import ClusterStore
from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.settings import Settings

ALGORITHM = "greedy-cosine-first-fit"
DEFAULT_THRESHOLD = 0.82


class ClusterRequest(BaseModel):
    threshold: float = Field(default=DEFAULT_THRESHOLD, gt=0.0, le=1.0)
    limit: int = Field(default=200, ge=2, le=1000)


def clusters_router(
    config: Settings,
    projects: ProjectDomainService,
    clusters: ClusterStore,
    triage_store: UnknownTriageStore,
) -> APIRouter:
    router = APIRouter(tags=["clusters"])
    embedder = HashLexicalEmbedder()

    async def _unknown_runs(identifier: str, scan_limit: int = 1000) -> list[Any]:
        runs = await projects.list_decision_runs(
            identifier=identifier, limit=scan_limit, offset=0
        )
        return [run for run in runs if run_is_unknown(run)]

    @router.post("/api/v1/projects/{identifier}/unknowns/cluster")
    async def run_clustering(identifier: str, body: ClusterRequest) -> dict[str, Any]:
        project = await projects.get(identifier)
        runs = (await _unknown_runs(identifier, scan_limit=max(body.limit, 1000)))[: body.limit]
        if len(runs) < 2:
            raise HTTPException(status_code=400, detail="clustering needs at least 2 UNKNOWN runs")
        texts = [str(run.input_snapshot.get("content", "")) for run in runs]
        vectors = await embedder.embed(texts)
        items = [
            EmbeddedItem(item_id=str(run.id), text=text, vector=vector)
            for run, text, vector in zip(runs, texts, vectors, strict=True)
        ]
        for item, vector in zip(items, vectors, strict=True):
            run_uuid = UUID_(item.item_id)
            if run_uuid is None:  # pragma: no cover - ids are engine-generated
                raise HTTPException(status_code=400, detail="invalid run id")
            await clusters.store_embedding(
                run_uuid, embedder.model_version, embedder.dimensions, vector
            )
        groups = group_into_clusters(items, body.threshold)
        payload_groups = [
            {
                "members": [
                    {"run_id": member, "similarity": similarity}
                    for member, similarity in zip(
                        group.member_ids, group.member_similarities, strict=True
                    )
                ],
                "centroid_similarity": group.centroid_similarity,
            }
            for group in groups
        ]
        ids = await clusters.replace_clusters(
            project.id,
            payload_groups,
            algorithm=ALGORITHM,
            model=embedder.model_version,
            threshold=body.threshold,
        )
        await triage_store.append_audit(
            project.id,
            "portal-user",
            "cluster.updated",
            f"clusters:{len(ids)}:threshold={body.threshold}",
        )
        return {
            "cluster_count": len(ids),
            "cluster_ids": ids,
            "algorithm": ALGORITHM,
            "model": embedder.model_version,
            "simulated": True,
            "threshold": body.threshold,
        }

    @router.get("/api/v1/projects/{identifier}/unknowns/clusters")
    async def list_clusters(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        listed = await clusters.list_clusters(project.id)
        for entry in listed:
            entry["simulated"] = entry["model"] == HashLexicalEmbedder.model_version
        return listed

    @router.get("/api/v1/projects/{identifier}/unknowns/clusters/{cluster_id}")
    async def cluster_detail(identifier: str, cluster_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        cluster_uuid = UUID_(cluster_id)
        if cluster_uuid is None:
            raise HTTPException(status_code=404, detail="Cluster not found")
        detail = await clusters.cluster_detail(project.id, cluster_uuid)
        if detail is None:
            raise HTTPException(status_code=404, detail="Cluster not found")
        detail["simulated"] = detail["model"] == HashLexicalEmbedder.model_version
        return detail

    return router


def UUID_(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
