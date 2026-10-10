"""Verified evaluation dataset routes (ground truth with provenance)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from openclass_core.evaluation import ExampleDraft, slice_coverage
from openclass_core.projects import ProjectService as ProjectDomainService
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.settings import Settings


class DatasetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)


class ExampleCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    label: str = Field(min_length=1, max_length=100)
    source: str
    annotator: str = Field(min_length=2, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    slice_tag: str = "historical"


def evaluations_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    triage_store: UnknownTriageStore,
) -> APIRouter:
    router = APIRouter(tags=["evaluations"])

    async def _dataset_row(project_id: UUID, dataset_id: str) -> dict[str, Any]:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, name, description, sealed_at, created_at"
                    " FROM evaluation_sets WHERE id = :id AND project_id = :pid"
                ),
                {"id": dataset_id, "pid": str(project_id)},
            )
            record = row.first()
        if record is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return {
            "id": record.id,
            "name": record.name,
            "description": record.description,
            "sealed_at": record.sealed_at,
            "created_at": record.created_at,
        }

    async def _allowed_labels(identifier: str) -> tuple[str, ...]:
        services = await projects.list_decision_services(identifier=identifier)
        labels: set[str] = set()
        for service in services:
            for node in service.nodes:
                labels.update(choice.key for choice in node.choices if choice.key != "UNKNOWN")
        labels.add("UNKNOWN")
        return tuple(sorted(labels))

    async def _examples(dataset_id: str) -> list[dict[str, Any]]:
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, text, label, source, annotator, rationale, slice_tag, created_at"
                    " FROM evaluation_examples WHERE dataset_id = :did ORDER BY created_at"
                ),
                {"did": dataset_id},
            )
            return [
                {
                    "id": row.id,
                    "text": row.text,
                    "label": row.label,
                    "source": row.source,
                    "annotator": row.annotator,
                    "rationale": row.rationale,
                    "slice_tag": row.slice_tag,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    @router.post("/api/v1/projects/{identifier}/eval-datasets", status_code=201)
    async def create_dataset(identifier: str, body: DatasetCreate) -> dict[str, Any]:
        project = await projects.get(identifier)
        dataset_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO evaluation_sets (id, project_id, name, description, created_at)"
                    " VALUES (:id, :pid, :name, :description, :created_at)"
                ),
                {
                    "id": dataset_id,
                    "pid": str(project.id),
                    "name": body.name.strip(),
                    "description": body.description.strip(),
                    "created_at": datetime.now(UTC),
                },
            )
        await triage_store.append_audit(
            project.id, "portal-user", "evaluation.dataset_created", f"dataset:{dataset_id}"
        )
        return {
            "id": dataset_id,
            "name": body.name.strip(),
            "description": body.description.strip(),
            "sealed_at": None,
        }

    @router.post(
        "/api/v1/projects/{identifier}/eval-datasets/{dataset_id}/examples", status_code=201
    )
    async def add_example(identifier: str, dataset_id: str, body: ExampleCreate) -> dict[str, Any]:
        project = await projects.get(identifier)
        dataset = await _dataset_row(project.id, dataset_id)
        if dataset["sealed_at"] is not None:
            raise HTTPException(status_code=409, detail="dataset is sealed and immutable")
        try:
            draft = ExampleDraft.model_validate(body.model_dump())
            example = draft.to_example(await _allowed_labels(identifier))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        async with sessions() as session:
            duplicate = await session.execute(
                sa.text(
                    "SELECT 1 FROM evaluation_examples WHERE dataset_id = :did AND text = :text"
                ),
                {"did": dataset_id, "text": example.text},
            )
            if duplicate.first() is not None:
                raise HTTPException(status_code=409, detail="duplicate text already in dataset")
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO evaluation_examples"
                    " (id, dataset_id, text, label, source, annotator,"
                    "  rationale, slice_tag, created_at)"
                    " VALUES (:id, :did, :text, :label, :source, :annotator,"
                    "         :rationale, :slice, :created_at)"
                ),
                {
                    "id": str(example.id),
                    "did": dataset_id,
                    "text": example.text,
                    "label": example.label,
                    "source": example.source,
                    "annotator": example.annotator,
                    "rationale": example.rationale,
                    "slice": example.slice_tag,
                    "created_at": datetime.now(UTC),
                },
            )
        return example.model_dump(mode="json")

    @router.post("/api/v1/projects/{identifier}/eval-datasets/{dataset_id}/seal")
    async def seal_dataset(identifier: str, dataset_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        dataset = await _dataset_row(project.id, dataset_id)
        if dataset["sealed_at"] is not None:
            raise HTTPException(status_code=409, detail="dataset is already sealed")
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "UPDATE evaluation_sets SET sealed_at = :now"
                    " WHERE id = :id AND sealed_at IS NULL"
                ),
                {"now": datetime.now(UTC), "id": dataset_id},
            )
        await triage_store.append_audit(
            project.id, "portal-user", "evaluation.dataset_sealed", f"dataset:{dataset_id}"
        )
        return {"id": dataset_id, "sealed": True}

    @router.get("/api/v1/projects/{identifier}/eval-datasets")
    async def list_datasets(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, name, description, sealed_at, created_at FROM evaluation_sets"
                    " WHERE project_id = :pid ORDER BY created_at"
                ),
                {"pid": str(project.id)},
            )
            datasets = [
                {
                    "id": row.id,
                    "name": row.name,
                    "description": row.description,
                    "sealed_at": row.sealed_at,
                }
                for row in rows
            ]
        for dataset in datasets:
            examples = await _examples(dataset["id"])
            dataset["size"] = len(examples)
            dataset["coverage"] = slice_coverage([_as_example(entry) for entry in examples])
        return datasets

    @router.get("/api/v1/projects/{identifier}/eval-datasets/{dataset_id}")
    async def dataset_detail(identifier: str, dataset_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        dataset = await _dataset_row(project.id, dataset_id)
        examples = await _examples(dataset_id)
        return {
            **dataset,
            "examples": examples,
            "size": len(examples),
            "coverage": slice_coverage([_as_example(entry) for entry in examples]),
        }

    return router


def _as_example(entry: dict[str, Any]) -> Any:
    from openclass_core.evaluation import EvaluationExample

    return EvaluationExample.model_validate(
        {**entry, "dataset_id": "00000000-0000-4000-8000-000000000000"}
    )
