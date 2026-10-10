"""Verified evaluation dataset routes (ground truth with provenance)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from openclass_core.evaluation import ExampleDraft, slice_coverage
from openclass_core.evaluation_metrics import (
    Gates,
    accuracy,
    coverage,
    macro_f1,
    unknown_precision_recall,
)
from openclass_core.models import (
    ChoiceRequest,
    Observation,
    OntologyClass,
    OntologyVersion,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_provider_mock import MockDecisionProvider
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.settings import Settings


class EvaluationCreate(BaseModel):
    dataset_id: str = Field(min_length=36, max_length=36)
    candidate_id: str = Field(min_length=36, max_length=36)
    service_id: str | None = None


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
        project = await projects.get(identifier)
        labels = await _class_labels(identifier)
        # Ground truth may also be annotated against a proposed candidate class.
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT canonical_name, aliases FROM cluster_candidates WHERE project_id = :pid"
                ),
                {"pid": str(project.id)},
            )
            for row in rows:
                if row.canonical_name:
                    labels.add(row.canonical_name.upper())
                aliases = row.aliases
                if isinstance(aliases, str):
                    aliases = json.loads(aliases)
                for alias in aliases or []:
                    labels.add(str(alias).upper())
        labels.add("UNKNOWN")
        return tuple(sorted(labels))

    async def _class_labels(identifier: str) -> set[str]:
        services = await projects.list_decision_services(identifier=identifier)
        labels: set[str] = set()
        for service in services:
            for node in service.nodes:
                labels.update(choice.key for choice in node.choices if choice.key != "UNKNOWN")
        return labels

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

    @router.post("/api/v1/projects/{identifier}/evaluations", status_code=201)
    async def run_evaluation(identifier: str, body: EvaluationCreate) -> dict[str, Any]:
        """Deterministic replay: same sealed dataset against baseline and candidate."""
        project = await projects.get(identifier)
        dataset = await _dataset_row(project.id, body.dataset_id)
        if dataset["sealed_at"] is None:
            raise HTTPException(status_code=400, detail="dataset must be sealed before evaluation")
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT canonical_name, aliases, status FROM cluster_candidates"
                    " WHERE id = :id AND project_id = :pid"
                ),
                {"id": body.candidate_id, "pid": str(project.id)},
            )
            candidate = row.first()
        if candidate is None or not candidate.canonical_name:
            raise HTTPException(status_code=404, detail="Candidate not found or has no class")
        services = await projects.list_decision_services(identifier=identifier)
        service = next(
            (entry for entry in services if body.service_id in (None, entry.id, entry.slug)),
            services[0] if services else None,
        )
        if service is None:
            raise HTTPException(
                status_code=400, detail="project has no decision service for replay"
            )
        baseline_choices = [
            choice for choice in service.nodes[0].choices if choice.key != "UNKNOWN"
        ]
        aliases = candidate.aliases
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        candidate_class = {
            "key": candidate.canonical_name.upper(),
            "label": candidate.canonical_name.replace("_", " ").title(),
            "aliases": [str(alias) for alias in aliases or []],
        }

        examples = await _examples(body.dataset_id)
        provider = MockDecisionProvider()
        baseline_pairs: list[tuple[str, str]] = []
        candidate_pairs: list[tuple[str, str]] = []
        for example in examples:
            gold = example["label"]
            baseline_pairs.append(
                (gold, await _replay(provider, baseline_choices, example["text"]))
            )
            candidate_choices = baseline_choices + [candidate_class]
            candidate_pairs.append(
                (gold, await _replay(provider, candidate_choices, example["text"]))
            )

        protected = sorted({gold for gold, _ in baseline_pairs if gold != "UNKNOWN"})
        baseline_labels = {choice.key for choice in baseline_choices}
        gates = Gates(protected_classes=protected).evaluate(
            baseline_pairs, candidate_pairs, known_labels=baseline_labels
        )
        unknown_p, unknown_r = unknown_precision_recall(candidate_pairs)
        metrics = {
            "baseline": {
                "accuracy": accuracy(baseline_pairs),
                "macro_f1": macro_f1(baseline_pairs),
                "coverage": coverage(baseline_pairs),
            },
            "candidate": {
                "accuracy": accuracy(candidate_pairs),
                "macro_f1": macro_f1(candidate_pairs),
                "coverage": coverage(candidate_pairs),
                "unknown_precision": unknown_p,
                "unknown_recall": unknown_r,
            },
            "examples": len(examples),
            "simulated": True,
        }
        evaluation_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO evaluation_runs"
                    " (id, project_id, dataset_id, candidate_id, overall_passed,"
                    "  metrics, gates, created_at)"
                    " VALUES (:id, :pid, :did, :cid, :passed, :metrics, :gates, :created_at)"
                ),
                {
                    "id": evaluation_id,
                    "pid": str(project.id),
                    "did": body.dataset_id,
                    "cid": body.candidate_id,
                    "passed": bool(gates["overall_passed"]),
                    "metrics": json.dumps(metrics),
                    "gates": json.dumps(gates["gates"]),
                    "created_at": datetime.now(UTC),
                },
            )
        await triage_store.append_audit(
            project.id, "portal-user", "evaluation.completed", f"evaluation:{evaluation_id}"
        )
        return {
            "id": evaluation_id,
            "dataset_id": body.dataset_id,
            "candidate_id": body.candidate_id,
            "overall_passed": gates["overall_passed"],
            "metrics": metrics,
            "gates": gates["gates"],
        }

    @router.get("/api/v1/projects/{identifier}/evaluations")
    async def list_evaluations(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, dataset_id, candidate_id, overall_passed, created_at"
                    " FROM evaluation_runs WHERE project_id = :pid ORDER BY created_at DESC"
                ),
                {"pid": str(project.id)},
            )
            return [
                {
                    "id": row.id,
                    "dataset_id": row.dataset_id,
                    "candidate_id": row.candidate_id,
                    "overall_passed": bool(row.overall_passed),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    @router.get("/api/v1/projects/{identifier}/evaluations/{evaluation_id}")
    async def evaluation_detail(identifier: str, evaluation_id: str) -> dict[str, Any]:
        project = await projects.get(identifier)
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, dataset_id, candidate_id, overall_passed,"
                    " metrics, gates, created_at"
                    " FROM evaluation_runs WHERE id = :id AND project_id = :pid"
                ),
                {"id": evaluation_id, "pid": str(project.id)},
            )
            record = row.first()
        if record is None:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        def _loads(value: object) -> object:
            return json.loads(value) if isinstance(value, str) else value

        return {
            "id": record.id,
            "dataset_id": record.dataset_id,
            "candidate_id": record.candidate_id,
            "overall_passed": bool(record.overall_passed),
            "metrics": _loads(record.metrics),
            "gates": _loads(record.gates),
            "created_at": record.created_at,
        }

    return router


def _choice_field(choice: object, key: str, default: Any = None) -> Any:
    if isinstance(choice, dict):
        return choice.get(key, default)
    return getattr(choice, key, default)


async def _replay(provider: MockDecisionProvider, choices: list[Any], text: str) -> str:
    """Classify one text against a choice list with the deterministic mock."""
    classes = tuple(
        OntologyClass(
            canonical_name=str(_choice_field(choice, "key")).lower(),
            display_name=str(_choice_field(choice, "label") or _choice_field(choice, "key")),
            aliases=tuple(str(alias) for alias in (_choice_field(choice, "aliases") or [])),
        )
        for choice in choices
    )
    ontology = OntologyVersion(
        classifier_id=uuid4(), version_number=1, classes=classes, created_by="replay"
    )
    result = await provider.choice(
        ChoiceRequest(observation=Observation(content=text), ontology=ontology)
    )
    best = max(result.probabilities, key=lambda key: result.probabilities[key])
    if result.probabilities.get(best, 0.0) <= result.unknown_probability:
        return "UNKNOWN"
    return best.upper()


def _as_example(entry: dict[str, Any]) -> Any:
    from openclass_core.evaluation import EvaluationExample

    return EvaluationExample.model_validate(
        {**entry, "dataset_id": "00000000-0000-4000-8000-000000000000"}
    )
