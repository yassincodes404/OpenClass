"""Persistence for embeddings and UNKNOWN clusters (engine side)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class ClusterStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def store_embedding(
        self, run_id: UUID, model: str, dimensions: int, vector: list[float]
    ) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO embeddings (run_id, model, dimensions, vector, created_at)"
                    " VALUES (:run_id, :model, :dimensions, :vector, :created_at)"
                    " ON CONFLICT (run_id) DO UPDATE SET"
                    " model = excluded.model, dimensions = excluded.dimensions,"
                    " vector = excluded.vector"
                ),
                {
                    "run_id": str(run_id),
                    "model": model,
                    "dimensions": dimensions,
                    "vector": json.dumps(vector),
                    "created_at": datetime.now(UTC),
                },
            )

    async def get_cached_embeddings(
        self, run_ids: list[UUID], model: str
    ) -> dict[str, list[float]]:
        if not run_ids:
            return {}
        id_strs = [str(run_id) for run_id in run_ids]
        stmt = sa.text(
            "SELECT run_id, vector FROM embeddings WHERE model = :model AND run_id IN :run_ids"
        ).bindparams(sa.bindparam("run_ids", expanding=True))
        async with self.sessions() as session:
            rows = await session.execute(stmt, {"model": model, "run_ids": id_strs})
            cached: dict[str, list[float]] = {}
            for row in rows:
                vec = json.loads(row.vector) if isinstance(row.vector, str) else row.vector
                if isinstance(vec, list):
                    cached[str(row.run_id)] = [float(v) for v in vec]
            return cached

    async def replace_clusters(
        self,
        project_id: UUID,
        groups: list[dict[str, Any]],
        *,
        algorithm: str,
        model: str,
        threshold: float,
    ) -> list[str]:
        """Idempotent rerun: detach existing candidates, drop clusters, and write the new set."""
        async with self.sessions.begin() as session:
            await session.execute(
                sa.text(
                    "UPDATE cluster_candidates SET cluster_id = NULL WHERE project_id = :project_id"
                ),
                {"project_id": str(project_id)},
            )
            await session.execute(
                sa.text("DELETE FROM unknown_clusters WHERE project_id = :project_id"),
                {"project_id": str(project_id)},
            )
            ids: list[str] = []
            now = datetime.now(UTC)
            for group in groups:
                cluster_id = str(uuid4())
                ids.append(cluster_id)
                await session.execute(
                    sa.text(
                        "INSERT INTO unknown_clusters"
                        " (id, project_id, algorithm, model, threshold, created_at)"
                        " VALUES (:id, :project_id, :algorithm, :model, :threshold, :created_at)"
                    ),
                    {
                        "id": cluster_id,
                        "project_id": str(project_id),
                        "algorithm": algorithm,
                        "model": model,
                        "threshold": threshold,
                        "created_at": now,
                    },
                )
                for member in group["members"]:
                    await session.execute(
                        sa.text(
                            "INSERT INTO cluster_members (cluster_id, run_id, similarity)"
                            " VALUES (:cluster_id, :run_id, :similarity)"
                        ),
                        {
                            "cluster_id": cluster_id,
                            "run_id": member["run_id"],
                            "similarity": member["similarity"],
                        },
                    )
            return ids

    async def list_clusters(self, project_id: UUID) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT c.id, c.algorithm, c.model, c.threshold, c.created_at,"
                    " (SELECT count(*) FROM cluster_members m WHERE m.cluster_id = c.id) AS size"
                    " FROM unknown_clusters c WHERE c.project_id = :project_id"
                    " ORDER BY size DESC, c.created_at"
                ),
                {"project_id": str(project_id)},
            )
            return [
                {
                    "id": row.id,
                    "algorithm": row.algorithm,
                    "model": row.model,
                    "threshold": row.threshold,
                    "created_at": row.created_at,
                    "size": row.size,
                }
                for row in rows
            ]

    async def cluster_detail(self, project_id: UUID, cluster_id: UUID) -> dict[str, Any] | None:
        async with self.sessions() as session:
            cluster = await session.execute(
                sa.text(
                    "SELECT id, algorithm, model, threshold, created_at FROM unknown_clusters"
                    " WHERE id = :id AND project_id = :project_id"
                ),
                {"id": str(cluster_id), "project_id": str(project_id)},
            )
            record = cluster.first()
            if record is None:
                return None
            members = await session.execute(
                sa.text(
                    "SELECT m.run_id, m.similarity FROM cluster_members m"
                    " WHERE m.cluster_id = :cluster_id ORDER BY m.similarity DESC"
                ),
                {"cluster_id": str(cluster_id)},
            )
            return {
                "id": record.id,
                "algorithm": record.algorithm,
                "model": record.model,
                "threshold": record.threshold,
                "created_at": record.created_at,
                "members": [
                    {"run_id": row.run_id, "similarity": row.similarity} for row in members
                ],
            }
