"""Public decisions routes over typed services and repository ports."""

from __future__ import annotations

import time
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.evidence import FeedbackAction
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceStatus,
    DecisionServiceUpdate,
    ProjectRepository,
    compute_service_hash,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider, ProviderError
from openclass_core.repositories import NotFoundError
from pydantic import BaseModel, Field

from openclass_server.api.schemas import (
    DecisionServiceCreate,
    DecisionServiceUpdateSchema,
    ExecuteDecisionRunRequest,
)
from openclass_server.provider_config import reject_credentials, resolve_decision_provider
from openclass_server.settings import Settings


class ResumeDecisionRunRequest(BaseModel):
    approved_choice: str | None = Field(default=None, min_length=1, max_length=120)
    operator: str = Field(default="operator", min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    strict_version_check: bool = False
    use_pinned_version: bool = True
    force_recover_stale_claim: bool = False


class RecoverDecisionRunCheckpointRequest(BaseModel):
    operator: str = Field(default="operator", min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    stale_after_seconds: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)


class CancelDecisionRunRequest(BaseModel):
    operator: str = Field(default="operator", min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=2000)


def _require_operator_permission(request: Request) -> None:
    role = (request.headers.get("X-OpenClass-Role") or "").strip().lower()
    if role in {"viewer", "readonly", "read_only", "guest"}:
        raise HTTPException(
            status_code=403,
            detail="Operator lacks permission to resume or cancel decision runs",
        )
    scopes = (request.headers.get("X-OpenClass-Scopes") or "").strip().lower()
    if scopes:
        scope_set = {s.strip() for s in scopes.replace(",", " ").split() if s.strip()}
        if not (scope_set & {"write", "resume", "cancel", "operator", "admin", "decisions:write"}):
            raise HTTPException(
                status_code=403,
                detail="Operator lacks permission to resume or cancel decision runs",
            )


def decisions_router(
    config: Settings,
    projects: ProjectDomainService,
    default_decision_provider: DecisionProvider,
    project_repository: ProjectRepository | None = None,
) -> APIRouter:
    router = APIRouter(tags=["decisions"])

    @router.post(
        "/api/v1/projects/{identifier}/decision-services",
        response_model=DecisionService,
        status_code=201,
    )
    async def create_decision_service(
        identifier: str, body: DecisionServiceCreate
    ) -> DecisionService:
        reject_credentials(body.model_dump(mode="json"), config)
        return await projects.create_decision_service(
            identifier=identifier,
            name=body.name,
            instructions=body.instructions,
            choices=[c.model_dump(mode="json") for c in body.choices],
            description=body.description,
            provider_override=body.provider_override,
            nodes=[n.model_dump(mode="json") for n in body.nodes]
            if body.nodes is not None
            else None,
            transitions=[t.model_dump(mode="json") for t in body.transitions],
        )

    @router.get(
        "/api/v1/projects/{identifier}/decision-services",
        response_model=list[DecisionService],
    )
    async def list_decision_services(identifier: str) -> list[DecisionService]:
        return await projects.list_decision_services(identifier=identifier)

    @router.get(
        "/api/v1/projects/{identifier}/decision-services/{service_id}",
        response_model=DecisionService,
    )
    async def get_decision_service(identifier: str, service_id: str) -> DecisionService:
        return await projects.get_decision_service(
            identifier=identifier, service_id_or_slug=service_id
        )

    @router.patch(
        "/api/v1/projects/{identifier}/decision-services/{service_id}",
        response_model=DecisionService,
    )
    async def update_decision_service(
        identifier: str, service_id: str, body: DecisionServiceUpdateSchema
    ) -> DecisionService:
        reject_credentials(body.model_dump(mode="json"), config)
        status_enum = DecisionServiceStatus(body.status) if body.status is not None else None
        default_inst = body.instructions or "Classify input"
        node_objs = (
            tuple(projects._build_node(n.model_dump(mode="json"), default_inst) for n in body.nodes)
            if body.nodes is not None
            else None
        )
        transition_objs = (
            tuple(projects._build_transition(t.model_dump(mode="json")) for t in body.transitions)
            if body.transitions is not None
            else None
        )
        update = DecisionServiceUpdate(
            name=body.name,
            description=body.description,
            instructions=body.instructions,
            status=status_enum,
            provider_override=body.provider_override,
            nodes=node_objs,
            transitions=transition_objs,
        )
        return await projects.update_decision_service(
            identifier=identifier,
            service_id_or_slug=service_id,
            update=update,
        )

    @router.post(
        "/api/v1/projects/{identifier}/decision-services/{service_id}/runs",
        response_model=list[DecisionRun],
        status_code=201,
    )
    async def execute_decision_runs(
        identifier: str, service_id: str, body: ExecuteDecisionRunRequest
    ) -> list[DecisionRun]:
        service = await projects.get_decision_service(identifier, service_id)
        if service.provider_override:
            try:
                exec_provider = resolve_decision_provider(config, service.provider_override)
            except ValueError as err:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported provider override: {service.provider_override}",
                ) from err
        else:
            exec_provider = default_decision_provider
        executor = DecisionExecutor(exec_provider)
        runs: list[DecisionRun] = []
        event_ids: list[UUID] = []
        if body.content:
            event, deduped = await projects.ingest_event(
                identifier=identifier, content=body.content, source_type="text"
            )
            event_ids.append(event.id)
        for raw_id_str in body.raw_event_ids:
            event_ids.append(UUID(raw_id_str))
        for run_event_id in event_ids:
            try:
                event = await projects.get_event(identifier, run_event_id)
            except NotFoundError as err:
                msg = f"Event not found: {run_event_id}"
                raise HTTPException(status_code=404, detail=msg) from err
            started = time.perf_counter()
            try:
                run = await executor.execute(event, service)
            except ProviderError:
                elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
                provider_name = (
                    service.provider_override
                    or str(getattr(exec_provider, "provider_name", "") or "")
                    or config.decision_provider
                )
                model_name = str(getattr(exec_provider, "model", "") or "")
                # Provider failures are observable (usage error counter + audit
                # event) but never persist a run or leak provider details.
                if project_repository is not None:
                    await project_repository.record_provider_error(
                        service.project_id, provider_name, model_name, elapsed_ms
                    )
                raise
            await projects.record_decision_run(run)
            runs.append(run)
        return runs

    @router.get(
        "/api/v1/projects/{identifier}/runs",
        response_model=list[DecisionRun],
    )
    async def list_decision_runs(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[DecisionRun]:
        return await projects.list_decision_runs(identifier=identifier, limit=limit, offset=offset)

    @router.get(
        "/api/v1/projects/{identifier}/runs/{run_id}",
        response_model=DecisionRun,
    )
    async def get_decision_run(identifier: str, run_id: UUID) -> DecisionRun:
        return await projects.get_decision_run(identifier=identifier, run_id=run_id)

    @router.post("/api/v1/projects/{identifier}/runs/{run_id}/resume")
    async def resume_decision_run(
        identifier: str,
        run_id: UUID,
        body: ResumeDecisionRunRequest,
        request: Request,
    ) -> dict[str, Any]:
        run = await projects.get_decision_run(identifier=identifier, run_id=run_id)
        service = await projects.get_decision_service(
            identifier=identifier, service_id_or_slug=str(run.decision_service_id)
        )
        _require_operator_permission(request)

        feedback_items = await projects.list_run_feedback(identifier=identifier, run_id=run_id)
        if (
            run.run_status == "cancelled"
            or run.state_snapshot.get("status") == "cancelled"
            or any(
                item.action == FeedbackAction.NOTE and (item.note or "").startswith("CANCELLED:")
                for item in feedback_items
            )
        ):
            raise HTTPException(status_code=409, detail="Decision run is already cancelled")

        # Resolve execution service (pinned snapshot if available) before validating choices
        current_hash = compute_service_hash(service)
        pinned_hash = run.pinned_service_hash or run.service_hash
        execution_service = service
        if pinned_hash and current_hash != pinned_hash and body.use_pinned_version:
            if isinstance(run.pending_operation, dict) and isinstance(
                run.pending_operation.get("service_snapshot"), dict
            ):
                try:
                    execution_service = DecisionService.model_validate(
                        run.pending_operation["service_snapshot"]
                    )
                except Exception:
                    pass
            elif project_repository is not None and hasattr(
                project_repository, "reconstruct_service_from_version"
            ):
                reconstructed = await project_repository.reconstruct_service_from_version(
                    service,
                    run.pinned_version_id or run.decision_service_version_id,
                    run.pinned_version_number,
                    run.pending_operation,
                )
                if reconstructed is not None:
                    execution_service = reconstructed

        valid_choices = (
            {choice.key for node in execution_service.nodes for choice in node.choices}
            | {choice.key for node in service.nodes for choice in node.choices}
            | {"UNKNOWN"}
        )
        if body.approved_choice is not None and body.approved_choice not in valid_choices:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid approved_choice '{body.approved_choice}' for service",
            )

        if body.strict_version_check and pinned_hash and current_hash != pinned_hash:
            raise HTTPException(
                status_code=409,
                detail="Decision service version or hash changed since run was checkpointed",
            )

        if execution_service.provider_override:
            try:
                exec_provider = resolve_decision_provider(
                    config, execution_service.provider_override
                )
            except ValueError as err:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported provider override: {execution_service.provider_override}",
                ) from err
        else:
            exec_provider = (
                getattr(request.app.state, "decision_provider", None) or default_decision_provider
            )

        claim_token = str(uuid4())
        if project_repository is not None and hasattr(
            project_repository, "claim_decision_run_for_resume"
        ):
            await project_repository.claim_decision_run_for_resume(
                str(service.project_id),
                str(run.id),
                operator=body.operator,
                claim_token=claim_token,
                stale_claim_timeout_seconds=config.decision_run_resume_claim_ttl_seconds,
                force_recover_stale_claim=body.force_recover_stale_claim,
            )
        else:
            if run.resumed_at is not None and run.run_status == "completed":
                raise HTTPException(
                    status_code=409,
                    detail="Decision run has already been resumed",
                )
            if run.run_status != "paused" and run.supervision_outcome not in {
                "REVIEW",
                "ESCALATE",
                "UNKNOWN",
            }:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Decision run cannot be resumed from supervision outcome "
                        f"'{run.supervision_outcome}'"
                    ),
                )

        run_for_executor = (
            run.model_copy(update={"run_status": "paused"}) if run.run_status == "resuming" else run
        )
        executor = DecisionExecutor(exec_provider)
        try:
            resumed_run = await executor.resume(
                run_for_executor,
                execution_service,
                approved_choice=body.approved_choice,
                operator=body.operator,
                rationale=body.rationale,
            )
        except ProviderError:
            if project_repository is not None and hasattr(
                project_repository, "mark_decision_run_failed"
            ):
                await project_repository.mark_decision_run_failed(
                    run.project_id,
                    run.id,
                    operator=body.operator,
                    failure_reason="Decision provider failed during resume",
                )
            raise
        except Exception:
            if project_repository is not None and hasattr(
                project_repository, "release_decision_run_claim"
            ):
                await project_repository.release_decision_run_claim(
                    str(service.project_id),
                    str(run.id),
                    claim_token=claim_token,
                )
            raise

        if project_repository is not None and hasattr(
            project_repository, "save_resumed_decision_run"
        ):
            await project_repository.save_resumed_decision_run(
                resumed_run,
                operator=body.operator,
                rationale=body.rationale,
                claim_token=claim_token,
            )

        if body.approved_choice is not None:
            final_approved = body.approved_choice
            action = (
                FeedbackAction.CORRECT
                if final_approved != run.selected_choice
                else FeedbackAction.CONFIRM
            )
            await projects.submit_run_feedback(
                identifier=identifier,
                run_id=run_id,
                action=action,
                corrected_choice=final_approved if action == FeedbackAction.CORRECT else None,
                note=body.rationale or f"Resumed by {body.operator}",
            )
        else:
            await projects.submit_run_feedback(
                identifier=identifier,
                run_id=run_id,
                action=FeedbackAction.CONFIRM,
                note=body.rationale or f"Resumed by {body.operator}",
            )

        if len(resumed_run.steps) <= 1 and resumed_run.run_status == "completed":
            return {
                "run_id": str(resumed_run.id),
                "status": "completed",
                "selected_choice": resumed_run.selected_choice,
                "supervision_outcome": resumed_run.supervision_outcome,
                "resumed_by": body.operator,
                "rationale": body.rationale,
            }

        return {
            "run_id": str(resumed_run.id),
            "status": resumed_run.run_status,
            "run_status": resumed_run.run_status,
            "selected_choice": resumed_run.selected_choice,
            "supervision_outcome": resumed_run.supervision_outcome,
            "resumed_by": body.operator,
            "rationale": body.rationale,
            "current_node_key": resumed_run.current_node_key,
            "next_node_key": resumed_run.next_node_key,
            "steps": resumed_run.steps,
            "completed_steps": resumed_run.completed_steps,
            "state_snapshot": resumed_run.state_snapshot,
            "pinned_version_id": (
                str(resumed_run.pinned_version_id) if resumed_run.pinned_version_id else None
            ),
            "pinned_version_number": resumed_run.pinned_version_number,
            "pinned_service_hash": resumed_run.pinned_service_hash,
            "pending_operation": resumed_run.pending_operation,
        }

    @router.post("/api/v1/projects/{identifier}/runs/{run_id}/recover-checkpoint")
    async def recover_decision_run_checkpoint(
        identifier: str,
        run_id: UUID,
        request: Request,
        body: Annotated[RecoverDecisionRunCheckpointRequest | None, Body()] = None,
    ) -> dict[str, Any]:
        _require_operator_permission(request)
        project = await projects.get(identifier)
        operator = body.operator if body is not None else "operator"
        rationale = body.rationale if body is not None else ""
        stale_after = body.stale_after_seconds if body is not None else 0.0
        if project_repository is None or not hasattr(
            project_repository, "recover_stale_decision_run_checkpoint"
        ):
            raise HTTPException(
                status_code=501, detail="Checkpoint recovery is not supported by repository"
            )
        recovered: DecisionRun = await project_repository.recover_stale_decision_run_checkpoint(
            str(project.id),
            str(run_id),
            operator=operator,
            rationale=rationale,
            stale_after_seconds=stale_after,
        )
        payload: dict[str, Any] = recovered.model_dump(mode="json")
        payload["run_id"] = str(recovered.id)
        payload["status"] = recovered.run_status
        return payload

    @router.post("/api/v1/projects/{identifier}/runs/{run_id}/cancel")
    async def cancel_decision_run(
        identifier: str,
        run_id: UUID,
        body: CancelDecisionRunRequest,
        request: Request,
    ) -> dict[str, Any]:
        _require_operator_permission(request)
        run = await projects.get_decision_run(identifier=identifier, run_id=run_id)
        if run.run_status == "cancelled" or run.state_snapshot.get("status") == "cancelled":
            raise HTTPException(status_code=409, detail="Decision run is already cancelled")
        if run.run_status == "completed":
            raise HTTPException(status_code=409, detail="Cannot cancel a completed decision run")
        if run.run_status == "resuming":
            raise HTTPException(
                status_code=409, detail="Cannot cancel a decision run while it is resuming"
            )
        if run.run_status != "paused":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel a decision run with status '{run.run_status}'",
            )

        if project_repository is not None and hasattr(
            project_repository, "cancel_decision_run_checkpoint"
        ):
            await project_repository.cancel_decision_run_checkpoint(
                run.project_id,
                run.id,
                operator=body.operator,
                reason=body.reason,
            )

        await projects.submit_run_feedback(
            identifier=identifier,
            run_id=run_id,
            action=FeedbackAction.NOTE,
            note=f"CANCELLED:{body.operator}:{body.reason}",
        )
        return {
            "run_id": str(run.id),
            "status": "cancelled",
            "cancelled_by": body.operator,
            "reason": body.reason,
        }

    return router
