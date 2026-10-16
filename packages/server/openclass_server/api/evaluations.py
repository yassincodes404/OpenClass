"""Verified evaluation dataset routes (ground truth with provenance)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.evaluation import ExampleDraft, compute_dataset_hash, slice_coverage
from openclass_core.evaluation_metrics import (
    Gates,
    accuracy,
    coverage,
    macro_f1,
    unknown_precision_recall,
)
from openclass_core.projects import (
    UNKNOWN_CHOICE,
    DecisionRun,
    DecisionService,
    DecisionServiceChoice,
    RawEvent,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider, ProviderError
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.provider_config import resolve_decision_provider
from openclass_server.settings import Settings

FORBIDDEN_LABEL_SOURCES: frozenset[str] = frozenset(
    {"prediction", "model_prediction", "unverified_prediction"}
)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().casefold().split())


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
    source_type: str | None = None
    annotator: str = Field(min_length=2, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    slice_tag: str = "historical"
    split: str = "holdout"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_prediction_metadata(self) -> ExampleCreate:
        label_source = str(self.metadata.get("label_source", "")).strip().lower()
        meta_source_type = str(self.metadata.get("source_type", "")).strip().lower()
        top_source_type = (self.source_type or "").strip().lower()
        if (
            label_source in FORBIDDEN_LABEL_SOURCES
            or meta_source_type in FORBIDDEN_LABEL_SOURCES
            or top_source_type in FORBIDDEN_LABEL_SOURCES
        ):
            raise ValueError("Predictions cannot be used as evaluation ground truth")
        return self


def evaluations_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    triage_store: UnknownTriageStore,
    default_decision_provider: DecisionProvider | None = None,
) -> APIRouter:
    router = APIRouter(tags=["evaluations"])

    async def _dataset_row(project_id: UUID, dataset_id: str) -> dict[str, Any]:
        async with sessions() as session:
            row = await session.execute(
                sa.text(
                    "SELECT id, name, description, dataset_hash, sealed_at, created_at"
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
            "dataset_hash": record.dataset_hash,
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
            choice_rows = await session.execute(
                sa.text("SELECT payload FROM project_choice_candidates WHERE project_id = :pid"),
                {"pid": str(project.id)},
            )
            for crow in choice_rows:
                payload = (
                    json.loads(crow.payload) if isinstance(crow.payload, str) else crow.payload
                )
                if isinstance(payload, dict):
                    prop = payload.get("proposal") or {}
                    if isinstance(prop, dict) and prop.get("key"):
                        labels.add(str(prop["key"]).upper())
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
                    "SELECT id, text, label, source, annotator, rationale, slice_tag,"
                    " split, example_metadata, created_at"
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
                    "split": row.split or "holdout",
                    "metadata": (
                        json.loads(row.example_metadata)
                        if isinstance(row.example_metadata, str)
                        else (row.example_metadata or {})
                    ),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    async def _discovery_texts(project_id: UUID, candidate_id: str | None = None) -> set[str]:
        async with sessions() as session:
            if candidate_id is not None:
                # No DISTINCT/GROUP BY on r.payload: PostgreSQL json has no
                # equality operator; duplicates are removed by normalization.
                rows = await session.execute(
                    sa.text(
                        "SELECT r.payload FROM decision_runs r"
                        " WHERE r.project_id = :pid AND ("
                        "   r.id IN ("
                        "     SELECT run_id FROM candidate_evidence WHERE candidate_id = :cid"
                        "   )"
                        "   OR r.id IN ("
                        "     SELECT m.run_id FROM cluster_members m"
                        "     JOIN cluster_candidates c ON c.cluster_id = m.cluster_id"
                        "     WHERE c.id = :cid"
                        "   )"
                        " )"
                    ),
                    {"pid": str(project_id), "cid": candidate_id},
                )
            else:
                # See above: deduplication happens after content normalization.
                rows = await session.execute(
                    sa.text(
                        "SELECT r.payload FROM decision_runs r"
                        " WHERE r.project_id = :pid AND ("
                        "   r.id IN ("
                        "     SELECT m.run_id FROM cluster_members m"
                        "     JOIN unknown_clusters uc ON uc.id = m.cluster_id"
                        "     WHERE uc.project_id = :pid"
                        "   )"
                        "   OR r.id IN ("
                        "     SELECT ce.run_id FROM candidate_evidence ce"
                        "     JOIN cluster_candidates cc ON cc.id = ce.candidate_id"
                        "     WHERE cc.project_id = :pid"
                        "   )"
                        " )"
                    ),
                    {"pid": str(project_id)},
                )
        normalized: set[str] = set()
        for row in rows:
            payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
            if isinstance(payload, dict):
                snapshot = payload.get("input_snapshot")
                if isinstance(snapshot, dict):
                    content = str(snapshot.get("content", "")).strip()
                    if content:
                        normalized.add(_normalize_text(content))
        return normalized

    async def _assert_no_holdout_leakage(
        project_id: UUID,
        examples: list[dict[str, Any]],
        candidate_id: str | None = None,
    ) -> None:
        holdout_entries = [
            ex
            for ex in examples
            if str((ex.get("metadata") or {}).get("source_type", "")).strip().lower()
            == "verified_holdout"
        ]
        if not holdout_entries:
            return
        discovery_norms = await _discovery_texts(project_id, candidate_id)
        if not discovery_norms:
            return
        for ex in holdout_entries:
            if _normalize_text(str(ex.get("text", ""))) in discovery_norms:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Holdout leakage detected: verified_holdout example"
                        " overlaps candidate discovery evidence"
                    ),
                )

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
            "dataset_hash": None,
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
            payload = body.model_dump(exclude={"source_type"})
            if body.source_type is not None:
                payload["metadata"] = {
                    **payload.get("metadata", {}),
                    "source_type": body.source_type,
                }
            draft = ExampleDraft.model_validate(payload)
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
                    "  rationale, slice_tag, split, example_metadata, created_at)"
                    " VALUES (:id, :did, :text, :label, :source, :annotator,"
                    "         :rationale, :slice, :split, :meta, :created_at)"
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
                    "split": example.split,
                    "meta": json.dumps(example.metadata),
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
        examples = await _examples(dataset_id)
        await _assert_no_holdout_leakage(project.id, examples)
        dhash = compute_dataset_hash([_as_example(entry) for entry in examples])
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "UPDATE evaluation_sets SET sealed_at = :now, dataset_hash = :hash"
                    " WHERE id = :id AND sealed_at IS NULL"
                ),
                {"now": datetime.now(UTC), "hash": dhash, "id": dataset_id},
            )
        await triage_store.append_audit(
            project.id, "portal-user", "evaluation.dataset_sealed", f"dataset:{dataset_id}"
        )
        return {"id": dataset_id, "sealed": True, "dataset_hash": dhash}

    @router.get("/api/v1/projects/{identifier}/eval-datasets")
    async def list_datasets(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, name, description, dataset_hash, sealed_at, created_at"
                    " FROM evaluation_sets WHERE project_id = :pid ORDER BY created_at"
                ),
                {"pid": str(project.id)},
            )
            datasets = [
                {
                    "id": row.id,
                    "name": row.name,
                    "description": row.description,
                    "dataset_hash": row.dataset_hash,
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
                    "SELECT canonical_name, definition, aliases, status FROM cluster_candidates"
                    " WHERE id = :id AND project_id = :pid"
                ),
                {"id": body.candidate_id, "pid": str(project.id)},
            )
            candidate = row.first()
        if candidate is None or not candidate.canonical_name:
            raise HTTPException(status_code=404, detail="Candidate not found or has no class")
        examples = await _examples(body.dataset_id)
        await _assert_no_holdout_leakage(project.id, examples, body.candidate_id)

        services = await projects.list_decision_services(identifier=identifier)
        service = next(
            (entry for entry in services if body.service_id in (None, str(entry.id), entry.slug)),
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
        candidate_choice = DecisionServiceChoice(
            key=candidate.canonical_name.upper(),
            label=candidate.canonical_name.replace("_", " ").title(),
            description=candidate.definition or f"Candidate {body.candidate_id}",
            aliases=tuple(str(alias) for alias in (aliases or [])),
        )
        candidate_node = service.nodes[0].model_copy(
            update={"choices": (candidate_choice, *baseline_choices, UNKNOWN_CHOICE)}
        )
        candidate_service = service.model_copy(
            update={
                "nodes": (candidate_node, *service.nodes[1:]),
                "version_number": service.version_number + 1,
            }
        )

        if service.provider_override:
            exec_provider = resolve_decision_provider(config, service.provider_override)
        elif default_decision_provider is not None:
            exec_provider = default_decision_provider
        else:
            exec_provider = resolve_decision_provider(config, config.decision_provider)

        executor = DecisionExecutor(exec_provider)
        baseline_pairs: list[tuple[str, str]] = []
        candidate_pairs: list[tuple[str, str]] = []
        run_provider = "mock"
        run_model = "lexical-demo-v1"
        is_simulated = True

        async def _execute_with_retry(
            raw_event: RawEvent, target_service: DecisionService
        ) -> DecisionRun:
            for attempt in range(6):
                try:
                    return await executor.execute(raw_event, target_service)
                except ProviderError as error:
                    if error.kind == "rate_limit" and attempt < 5:
                        await asyncio.sleep(5.0 * (attempt + 1))
                        continue
                    raise
            raise RuntimeError("unreachable")

        for example in examples:
            gold = example["label"]
            raw_event = RawEvent(
                project_id=project.id,
                content=example["text"],
                source_type="text",
            )
            base_run = await _execute_with_retry(raw_event, service)
            cand_run = await _execute_with_retry(raw_event, candidate_service)
            base_pred = (
                "UNKNOWN"
                if base_run.selected_choice != "UNKNOWN" and base_run.margin == 0.0
                else base_run.selected_choice
            )
            cand_pred = (
                "UNKNOWN"
                if cand_run.selected_choice != "UNKNOWN" and cand_run.margin == 0.0
                else cand_run.selected_choice
            )
            baseline_pairs.append((gold, base_pred))
            candidate_pairs.append((gold, cand_pred))
            run_provider = cand_run.provider
            run_model = cand_run.model
            is_simulated = bool(
                cand_run.provider_metadata.get("simulated", not cand_run.real_inference)
            )

        protected = sorted({gold for gold, _ in baseline_pairs if gold != "UNKNOWN"})
        baseline_labels = {choice.key for choice in baseline_choices}
        gates = Gates(protected_classes=protected).evaluate(
            baseline_pairs, candidate_pairs, known_labels=baseline_labels
        )
        unknown_p, unknown_r = unknown_precision_recall(candidate_pairs)
        regression_metrics = {
            "regressions": gates["regressions"],
            "zero_regressions": gates["zero_regressions"],
        }
        holdout_examples = sum(
            1
            for ex in examples
            if (ex.get("metadata") or {}).get("source_type") == "verified_holdout"
            or ex.get("split") == "holdout"
            or ex.get("source") == "verified_holdout"
        )
        holdout_metrics = {"holdout_examples": holdout_examples}
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
            "regressions": gates["regressions"],
            "zero_regressions": gates["zero_regressions"],
            "regression_metrics": regression_metrics,
            "holdout_metrics": holdout_metrics,
            "examples": len(examples),
            "simulated": is_simulated,
            "provider": run_provider,
            "model": run_model,
        }
        evaluation_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO evaluation_runs"
                    " (id, project_id, dataset_id, candidate_id, overall_passed,"
                    "  is_simulated, provider, model, metrics, gates, created_at)"
                    " VALUES (:id, :pid, :did, :cid, :passed,"
                    "         :sim, :prov, :mod, :metrics, :gates, :created_at)"
                ),
                {
                    "id": evaluation_id,
                    "pid": str(project.id),
                    "did": body.dataset_id,
                    "cid": body.candidate_id,
                    "passed": bool(gates["overall_passed"]),
                    "sim": is_simulated,
                    "prov": run_provider,
                    "mod": run_model,
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
            "is_simulated": is_simulated,
            "provider": run_provider,
            "model": run_model,
            "metrics": metrics,
            "regression_metrics": regression_metrics,
            "holdout_metrics": holdout_metrics,
            "gates": gates["gates"],
        }

    @router.get("/api/v1/projects/{identifier}/evaluations")
    async def list_evaluations(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT id, dataset_id, candidate_id, overall_passed,"
                    " is_simulated, provider, model, created_at"
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
                    "is_simulated": (
                        bool(row.is_simulated) if row.is_simulated is not None else True
                    ),
                    "provider": row.provider or "mock",
                    "model": row.model or "lexical-demo-v1",
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
                    " is_simulated, provider, model, metrics, gates, created_at"
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
            "is_simulated": (
                bool(record.is_simulated) if record.is_simulated is not None else True
            ),
            "provider": record.provider or "mock",
            "model": record.model or "lexical-demo-v1",
            "metrics": _loads(record.metrics),
            "gates": _loads(record.gates),
            "created_at": record.created_at,
        }

    return router


def _as_example(entry: dict[str, Any]) -> Any:
    from openclass_core.evaluation import EvaluationExample

    return EvaluationExample.model_validate(
        {**entry, "dataset_id": "00000000-0000-4000-8000-000000000000"}
    )
