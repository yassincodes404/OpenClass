from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.evaluation_metrics import Gates, accuracy
from openclass_core.project_evolution import (
    CandidateEvaluationResult,
    ChoiceCandidate,
    ChoiceCandidateRepository,
    ProjectEvolutionService,
    ProposalKind,
    service_hash,
)
from openclass_core.projects import (
    UNKNOWN_CHOICE,
    DecisionServiceChoice,
    ProjectAuditEvent,
    RawEvent,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider
from openclass_core.repositories import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.api.schemas import (
    PromoteCandidateRequest,
    PromoteCandidateResponse,
    ProposeFromEvidenceRequest,
    ProposeProjectChoiceRequest,
    RejectCandidateRequest,
)
from openclass_server.provider_config import reject_credentials, resolve_decision_provider
from openclass_server.settings import Settings


def evolution_router(
    config: Settings,
    projects: ProjectDomainService,
    project_repository: ChoiceCandidateRepository,
    evolution: ProjectEvolutionService,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    default_decision_provider: DecisionProvider | None = None,
) -> APIRouter:
    router = APIRouter(tags=["evolution"])

    @router.get("/api/v1/projects/{identifier}/candidates", response_model=list[ChoiceCandidate])
    async def project_candidates(identifier: str) -> list[ChoiceCandidate]:
        project = await projects.get(identifier)
        return await project_repository.list_choice_candidates(project.id)

    @router.get(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}", response_model=ChoiceCandidate
    )
    async def project_candidate(identifier: str, candidate_id: UUID) -> ChoiceCandidate:
        project = await projects.get(identifier)
        return await project_repository.get_choice_candidate(project.id, candidate_id)

    @router.post(
        "/api/v1/projects/{identifier}/decision-services/{service_id}/candidates",
        response_model=ChoiceCandidate,
        status_code=201,
    )
    async def propose_project_choice(
        identifier: str, service_id: str, body: ProposeProjectChoiceRequest
    ) -> ChoiceCandidate:
        project = await projects.get(identifier)
        return await evolution.propose(
            project.id, service_id, tuple(UUID(run_id) for run_id in body.run_ids), "local-user"
        )

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/reject",
        response_model=ChoiceCandidate,
    )
    async def reject_project_choice(
        identifier: str, candidate_id: UUID, body: RejectCandidateRequest
    ) -> ChoiceCandidate:
        reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        return await evolution.reject(project.id, candidate_id, body.reason, "local-user")

    @router.post(
        "/api/v1/projects/{identifier}/evolution/propose",
        response_model=ChoiceCandidate,
        status_code=201,
    )
    async def propose_from_evidence(
        identifier: str, body: ProposeFromEvidenceRequest
    ) -> ChoiceCandidate:
        reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        if body.evidence_case_id is not None:
            return await evolution.propose_from_case(
                project.id, body.evidence_case_id, "local-user"
            )
        assert body.evidence_ids is not None and body.service_id is not None
        return await evolution.propose_from_evidence(
            project.id, body.service_id, tuple(body.evidence_ids), "local-user"
        )

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/evaluate",
        response_model=CandidateEvaluationResult,
    )
    async def evaluate_project_candidate(
        identifier: str, candidate_id: UUID
    ) -> CandidateEvaluationResult:
        project = await projects.get(identifier)
        candidate = await project_repository.get_choice_candidate(project.id, candidate_id)
        if sessions is None or candidate.proposal.kind != ProposalKind.NEW_CHOICE:
            return await evolution.evaluate(project.id, candidate_id)

        async with sessions() as session:
            ds_row = await session.execute(
                sa.text(
                    "SELECT id FROM evaluation_sets"
                    " WHERE project_id = :pid AND sealed_at IS NOT NULL"
                    " ORDER BY sealed_at DESC LIMIT 1"
                ),
                {"pid": str(project.id)},
            )
            sealed_ds = ds_row.first()
            if sealed_ds is None:
                return await evolution.evaluate(project.id, candidate_id)
            ex_rows = await session.execute(
                sa.text(
                    "SELECT text, label FROM evaluation_examples"
                    " WHERE dataset_id = :did ORDER BY created_at"
                ),
                {"did": sealed_ds.id},
            )
            examples = [(r.text, r.label) for r in ex_rows]

        if not examples:
            return await evolution.evaluate(project.id, candidate_id)

        service = await project_repository.get_decision_service(
            project.id, str(candidate.decision_service_id)
        )
        assert candidate.proposal.key is not None and candidate.proposal.label is not None
        baseline_choices = [
            choice for choice in service.nodes[0].choices if choice.key != "UNKNOWN"
        ]
        candidate_choice = DecisionServiceChoice(
            key=candidate.proposal.key,
            label=candidate.proposal.label,
            description=candidate.proposal.description or candidate.proposal.label,
        )
        candidate_node = service.nodes[0].model_copy(
            update={"choices": (*baseline_choices, candidate_choice, UNKNOWN_CHOICE)}
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

        for text_val, gold in examples:
            raw_event = RawEvent(project_id=project.id, content=text_val, source_type="text")
            base_run = await executor.execute(raw_event, service)
            cand_run = await executor.execute(raw_event, candidate_service)
            baseline_pairs.append((gold, base_run.selected_choice))
            candidate_pairs.append((gold, cand_run.selected_choice))
            run_provider = cand_run.provider
            run_model = cand_run.model
            is_simulated = bool(
                cand_run.provider_metadata.get("simulated", not cand_run.real_inference)
            )

        baseline_labels = {choice.key for choice in baseline_choices}
        protected = sorted({gold for gold, _ in baseline_pairs if gold in baseline_labels})
        gates = Gates(protected_classes=protected).evaluate(
            baseline_pairs, candidate_pairs, known_labels=baseline_labels
        )
        known_pairs = [(g, p) for g, p in candidate_pairs if g in baseline_labels]
        acc_known = accuracy(known_pairs) if known_pairs else 1.0
        target_pairs = [(g, p) for g, p in candidate_pairs if g == candidate.proposal.key]
        disambig = accuracy(target_pairs) if target_pairs else 0.0
        gate_list = gates.get("gates")
        regressions = tuple(
            str(g["gate"])
            for g in (gate_list if isinstance(gate_list, list) else [])
            if isinstance(g, dict) and not g.get("passed")
        )

        async with sessions.begin() as session:
            existing_cc = await session.execute(
                sa.text("SELECT 1 FROM cluster_candidates WHERE id = :id"),
                {"id": str(candidate.id)},
            )
            if existing_cc.first() is None:
                await session.execute(
                    sa.text(
                        "INSERT INTO cluster_candidates"
                        " (id, project_id, cluster_id, type, canonical_name, display_name,"
                        "  definition, aliases, existing_match, confidence, reason, status,"
                        "  provider, created_at)"
                        " VALUES (:id, :pid, NULL, 'new_class', :cname, :dname, :def,"
                        "         :aliases, NULL, 0.9, :reason, 'approved', :prov, :now)"
                    ),
                    {
                        "id": str(candidate.id),
                        "pid": str(project.id),
                        "cname": candidate.proposal.key.lower(),
                        "dname": candidate.proposal.label,
                        "def": candidate.proposal.description or "",
                        "aliases": json.dumps([]),
                        "reason": candidate.proposal.rationale,
                        "prov": candidate.proposal.provider,
                        "now": datetime.now(UTC),
                    },
                )
            await session.execute(
                sa.text(
                    "INSERT INTO evaluation_runs"
                    " (id, project_id, dataset_id, candidate_id, overall_passed,"
                    "  is_simulated, provider, model, metrics, gates, created_at)"
                    " VALUES (:id, :pid, :did, :cid, :passed,"
                    "         :sim, :prov, :mod, :metrics, :gates, :now)"
                ),
                {
                    "id": str(uuid4()),
                    "pid": str(project.id),
                    "did": sealed_ds.id,
                    "cid": str(candidate.id),
                    "passed": bool(gates["overall_passed"]),
                    "sim": is_simulated,
                    "prov": run_provider,
                    "mod": run_model,
                    "metrics": json.dumps(
                        {
                            "accuracy_on_knowns": acc_known,
                            "disambiguation_rate": disambig,
                            "simulated": is_simulated,
                        }
                    ),
                    "gates": json.dumps(gates["gates"]),
                    "now": datetime.now(UTC),
                },
            )

        return CandidateEvaluationResult(
            candidate_id=candidate.id,
            decision_service_id=service.id,
            passed=bool(gates["overall_passed"]),
            accuracy_on_knowns=float(acc_known or 0.0),
            disambiguation_rate=float(disambig or 0.0),
            regressions=regressions,
        )

    @router.post(
        "/api/v1/projects/{identifier}/candidates/{candidate_id}/promote",
        response_model=PromoteCandidateResponse,
    )
    async def promote_project_candidate(
        identifier: str, candidate_id: UUID, body: PromoteCandidateRequest | None = None
    ) -> PromoteCandidateResponse:
        if body is not None:
            reject_credentials(body.model_dump(mode="json"), config)
        project = await projects.get(identifier)
        if sessions is not None:
            async with sessions() as session:
                eval_row = await session.execute(
                    sa.text(
                        "SELECT id, overall_passed FROM evaluation_runs"
                        " WHERE project_id = :pid AND candidate_id = :cid"
                        " ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"pid": str(project.id), "cid": str(candidate_id)},
                )
                latest_eval = eval_row.first()
            if latest_eval is not None and bool(latest_eval.overall_passed):
                candidate = await project_repository.get_choice_candidate(project.id, candidate_id)
                if candidate.status != "candidate":
                    msg = f"Candidate {candidate_id} is in status '{candidate.status}'"
                    raise ConflictError(f"{msg}, cannot promote")
                if candidate.proposal.kind != ProposalKind.NEW_CHOICE:
                    raise ConflictError("Only NEW_CHOICE candidates can be promoted")
                assert candidate.proposal.key is not None and candidate.proposal.label is not None
                service = await project_repository.get_decision_service(
                    project.id, str(candidate.decision_service_id)
                )
                if service.status != "active":
                    raise ConflictError("Target decision service is not active")
                if service_hash(service) != candidate.base_service_hash:
                    raise ConflictError(
                        "Decision service was modified after candidate was generated"
                    )
                existing_choices = [c for c in service.nodes[0].choices if c.key != "UNKNOWN"]
                if any(c.key == candidate.proposal.key for c in existing_choices):
                    raise ConflictError(
                        f"Choice {candidate.proposal.key} already exists in decision service"
                    )
                new_choice = DecisionServiceChoice(
                    key=candidate.proposal.key,
                    label=candidate.proposal.label,
                    description=candidate.proposal.description or candidate.proposal.label,
                )
                updated_node = service.nodes[0].model_copy(
                    update={"choices": (*existing_choices, new_choice, UNKNOWN_CHOICE)}
                )
                now_ts = datetime.now(UTC)
                updated_service = service.model_copy(
                    update={
                        "nodes": (updated_node, *service.nodes[1:]),
                        "version_number": service.version_number + 1,
                        "active_version_id": uuid4(),
                        "updated_at": now_ts,
                    }
                )
                updater = getattr(project_repository, "update_decision_service", None)
                if callable(updater):
                    await updater(updated_service)
                promoted_cand = candidate.model_copy(
                    update={"status": "promoted", "promoted_at": now_ts}
                )
                audit_event = ProjectAuditEvent(
                    project_id=project.id,
                    event_type="choice_candidate.promoted",
                    actor="local-user",
                    payload={
                        "candidate_id": str(candidate.id),
                        "service_id": str(service.id),
                        "added_choice": new_choice.key,
                        "version_number": updated_service.version_number,
                    },
                    created_at=now_ts,
                )
                async with sessions.begin() as session:
                    await session.execute(
                        sa.text(
                            "UPDATE project_choice_candidates"
                            " SET status = 'promoted', payload = :payload"
                            " WHERE id = :id AND project_id = :pid"
                        ),
                        {
                            "payload": json.dumps(promoted_cand.model_dump(mode="json")),
                            "id": str(candidate.id),
                            "pid": str(project.id),
                        },
                    )
                    await session.execute(
                        sa.text(
                            "INSERT INTO audit_events"
                            " (id, project_id, event_type, actor, created_at, payload)"
                            " VALUES (:id, :pid, :etype, :actor, :now, :payload)"
                        ),
                        {
                            "id": str(audit_event.id),
                            "pid": str(project.id),
                            "etype": audit_event.event_type,
                            "actor": audit_event.actor,
                            "now": now_ts,
                            "payload": json.dumps(audit_event.model_dump(mode="json")),
                        },
                    )
                return PromoteCandidateResponse(
                    candidate=promoted_cand, decision_service=updated_service
                )

        cand, serv = await evolution.promote(project.id, candidate_id, "local-user")
        return PromoteCandidateResponse(candidate=cand, decision_service=serv)

    return router
