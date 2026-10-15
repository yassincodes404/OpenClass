"""Public decisions routes over typed services and repository ports."""

from __future__ import annotations

import time
from collections.abc import Coroutine
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request
from openclass_core.decision_executor import DecisionExecutor
from openclass_core.evidence import FeedbackAction
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceNode,
    DecisionServiceStatus,
    DecisionServiceUpdate,
    ProjectRepository,
    compute_service_hash,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider, ProviderError
from openclass_core.repositories import ConflictError, NotFoundError
from pydantic import BaseModel, Field

from openclass_server.api.schemas import (
    DecisionServiceCreate,
    DecisionServiceUpdateSchema,
    ExecuteDecisionRunRequest,
)
from openclass_server.checkpoint_lease import CheckpointLease
from openclass_server.provider_config import reject_credentials, resolve_decision_provider
from openclass_server.settings import Settings


class ResumeDecisionRunRequest(BaseModel):
    approved_choice: str | None = Field(default=None, min_length=1, max_length=120)
    operator: str = Field(default="operator", min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    strict_version_check: bool = False
    use_pinned_version: bool = True
    force_recover_stale_claim: bool = False
    expected_checkpoint_revision: int | None = Field(default=None, ge=1)
    expected_node_key: str | None = Field(default=None, min_length=1, max_length=200)


class RecoverDecisionRunCheckpointRequest(BaseModel):
    operator: str = Field(default="operator", min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    stale_after_seconds: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    force: bool = False


class CancelDecisionRunRequest(BaseModel):
    operator: str = Field(default="operator", min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=2000)


def _require_operator_permission(request: Request, *, force_recovery: bool = False) -> None:
    role = (request.headers.get("X-OpenClass-Role") or "").strip().lower()
    if role in {"viewer", "readonly", "read_only", "guest"}:
        raise HTTPException(
            status_code=403,
            detail="Operator lacks permission to resume or cancel decision runs",
        )
    scopes = (request.headers.get("X-OpenClass-Scopes") or "").strip().lower()
    if scopes:
        scope_set = {s.strip() for s in scopes.replace(",", " ").split() if s.strip()}
        allowed = {"write", "resume", "cancel", "operator", "admin", "decisions:write"}
        if force_recovery:
            allowed |= {"decisions:force-recover", "checkpoint:force-recover"}
        if not scope_set & allowed:
            raise HTTPException(
                status_code=403,
                detail="Operator lacks permission to resume or cancel decision runs",
            )


def _require_force_recovery_permission(request: Request, *, rationale: str) -> None:
    role = getattr(request.state, "trusted_role", "")
    scope_set: frozenset[str] = getattr(request.state, "trusted_scopes", frozenset())
    has_privileged_role = role in {"admin", "recovery_admin", "system_admin", "owner"}
    has_privileged_scope = bool(
        scope_set & {"admin", "decisions:force-recover", "checkpoint:force-recover"}
    )
    if not (
        getattr(request.state, "internal_authenticated", False)
        and getattr(request.state, "trusted_actor", None)
        and (has_privileged_role or has_privileged_scope)
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Privileged admin role or force-recover scope is required "
                "to force-recover an active checkpoint claim"
            ),
        )
    if len((rationale or "").strip()) < 3:
        raise HTTPException(
            status_code=422,
            detail="A non-empty rationale is required for force checkpoint recovery",
        )


def _checkpoint_operator(request: Request, fallback: str, *, trusted: bool = False) -> str:
    operator = str(
        (getattr(request.state, "trusted_actor", None) or "") if trusted else fallback
    ).strip()
    if not operator or len(operator) > 80:
        raise HTTPException(status_code=422, detail="Operator identity must be 1 to 80 characters")
    return operator


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
        reject_credentials(body.model_dump(mode="json"), config)
        _require_operator_permission(request, force_recovery=body.force_recover_stale_claim)
        if body.force_recover_stale_claim:
            _require_force_recovery_permission(request, rationale=body.rationale)
        operator = _checkpoint_operator(
            request, body.operator, trusted=body.force_recover_stale_claim
        )
        reject_credentials(operator, config)

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

        current_hash = compute_service_hash(service)

        async def _resolve_execution_service(
            target_run: DecisionRun,
        ) -> tuple[DecisionService, str | None]:
            target_pinned_hash = target_run.pinned_service_hash or target_run.service_hash
            resolved_service = service
            if (
                target_pinned_hash
                and current_hash != target_pinned_hash
                and body.use_pinned_version
            ):
                if isinstance(target_run.pending_operation, dict) and isinstance(
                    target_run.pending_operation.get("service_snapshot"), dict
                ):
                    try:
                        resolved_service = DecisionService.model_validate(
                            target_run.pending_operation["service_snapshot"]
                        )
                    except ValueError as err:
                        raise HTTPException(
                            status_code=409, detail="Pinned decision service snapshot is invalid"
                        ) from err
                elif project_repository is not None and hasattr(
                    project_repository, "reconstruct_service_from_version"
                ):
                    reconstructed = await project_repository.reconstruct_service_from_version(
                        service,
                        target_run.pinned_version_id or target_run.decision_service_version_id,
                        target_run.pinned_version_number,
                        target_run.pending_operation,
                    )
                    if reconstructed is not None:
                        resolved_service = reconstructed
                if compute_service_hash(resolved_service) != target_pinned_hash:
                    raise HTTPException(
                        status_code=409, detail="Pinned decision service snapshot is unavailable"
                    )
            if (
                resolved_service.id != target_run.decision_service_id
                or resolved_service.project_id != target_run.project_id
            ):
                raise HTTPException(status_code=409, detail="Checkpoint service identity changed")
            return resolved_service, target_pinned_hash

        # Resolve execution service (pinned snapshot if available) before validating choices
        execution_service, pinned_hash = await _resolve_execution_service(run)

        valid_choices = (
            {choice.key for node in execution_service.nodes for choice in node.choices}
            | {choice.key for node in service.nodes for choice in node.choices}
            | {"UNKNOWN"}
        )
        approved_choice = (
            body.approved_choice.strip().upper() if body.approved_choice is not None else None
        )
        if approved_choice is not None and approved_choice not in valid_choices:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid approved_choice '{body.approved_choice}' for service",
            )

        if body.strict_version_check and pinned_hash and current_hash != pinned_hash:
            raise HTTPException(
                status_code=409,
                detail="Decision service version or hash changed since run was checkpointed",
            )

        def _find_paused_node(
            target_service: DecisionService, target_run: DecisionRun
        ) -> DecisionServiceNode | None:
            if target_run.current_node_key:
                key_lower = target_run.current_node_key.strip().lower()
                matches = [
                    n
                    for n in target_service.nodes
                    if n.name.strip().lower() == key_lower or str(n.id).strip().lower() == key_lower
                ]
                if len(matches) != 1 or matches[0].id != target_run.decision_node_id:
                    return None
                return matches[0]
            return next(
                (n for n in target_service.nodes if n.id == target_run.decision_node_id), None
            )

        def _validate_checkpoint_node(
            target_service: DecisionService, target_run: DecisionRun
        ) -> None:
            paused_node = _find_paused_node(target_service, target_run)
            if paused_node is None:
                raise HTTPException(
                    status_code=409, detail="Current checkpoint node is unavailable"
                )
            if approved_choice is not None and approved_choice not in {
                choice.key for choice in paused_node.choices
            } | {"UNKNOWN"}:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Approved choice '{approved_choice}' is not valid for "
                        f"current checkpoint node '{paused_node.name}'"
                    ),
                )

        # Reject known-invalid input without mutating a generation; this is only
        # an early rejection, never authorization. Recheck the actual claimed node.
        if (
            run.run_status in {"paused", "resuming"}
            and body.expected_checkpoint_revision in {None, run.checkpoint_revision}
            and body.expected_node_key in {None, run.current_node_key}
        ):
            _validate_checkpoint_node(execution_service, run)

        expected_rev = (
            body.expected_checkpoint_revision
            if body.expected_checkpoint_revision is not None
            else run.checkpoint_revision
        )
        expected_node = (
            body.expected_node_key if body.expected_node_key is not None else run.current_node_key
        )

        claim_token = str(uuid4())
        if project_repository is None or not all(
            callable(getattr(project_repository, method, None))
            for method in (
                "claim_decision_run_for_resume",
                "renew_decision_run_claim",
                "release_decision_run_claim",
                "save_resumed_decision_run",
                "mark_decision_run_failed",
            )
        ):
            raise HTTPException(
                status_code=501,
                detail="Renewable checkpoint claims are not supported by repository",
            )
        # hasattr also narrows the structural repository boundary for type checkers.
        assert hasattr(project_repository, "claim_decision_run_for_resume")
        assert hasattr(project_repository, "renew_decision_run_claim")
        assert hasattr(project_repository, "release_decision_run_claim")
        assert hasattr(project_repository, "save_resumed_decision_run")
        assert hasattr(project_repository, "mark_decision_run_failed")
        claimed_run: DecisionRun = await project_repository.claim_decision_run_for_resume(
            str(service.project_id),
            str(run.id),
            operator=operator,
            claim_token=claim_token,
            stale_claim_timeout_seconds=config.decision_run_resume_claim_ttl_seconds,
            force_recover_stale_claim=body.force_recover_stale_claim,
            expected_checkpoint_revision=expected_rev,
            expected_node_key=expected_node,
            require_expected_node_match=True,
            rationale=body.rationale,
        )
        if (
            not isinstance(claimed_run, DecisionRun)
            or claimed_run.claim_token != claim_token
            or claimed_run.run_status != "resuming"
            or claimed_run.id != run.id
            or claimed_run.project_id != service.project_id
            or claimed_run.decision_service_id != service.id
        ):
            raise ConflictError("Repository did not return the claimed checkpoint generation")
        claimed_revision = claimed_run.checkpoint_revision
        ttl = config.decision_run_resume_claim_ttl_seconds

        async def release_unstarted_claim() -> None:
            await project_repository.release_decision_run_claim(
                claimed_run.project_id,
                claimed_run.id,
                claim_token=claim_token,
                expected_checkpoint_revision=claimed_revision,
                stale_claim_timeout_seconds=ttl,
            )

        try:
            execution_service, pinned_hash = await _resolve_execution_service(claimed_run)
            if body.strict_version_check and pinned_hash and current_hash != pinned_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Decision service version or hash changed since run was checkpointed",
                )
            _validate_checkpoint_node(execution_service, claimed_run)
            if execution_service.provider_override:
                try:
                    exec_provider = resolve_decision_provider(
                        config, execution_service.provider_override
                    )
                except ValueError as err:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Unsupported provider override: {execution_service.provider_override}"
                        ),
                    ) from err
            else:
                exec_provider = (
                    getattr(request.app.state, "decision_provider", None)
                    or default_decision_provider
                )
        except Exception:
            await release_unstarted_claim()
            raise

        async def renew_claim() -> None:
            await project_repository.renew_decision_run_claim(
                claimed_run.project_id,
                claimed_run.id,
                claim_token=claim_token,
                expected_checkpoint_revision=claimed_revision,
                stale_claim_timeout_seconds=ttl,
            )

        lease = CheckpointLease(renew_claim, ttl)
        run_for_executor = claimed_run.model_copy(update={"run_status": "paused"})
        executor = DecisionExecutor(lease.provider(exec_provider))

        def execute_resume() -> Coroutine[Any, Any, DecisionRun]:
            return executor.resume(
                run_for_executor,
                execution_service,
                approved_choice=approved_choice,
                operator=operator,
                rationale=body.rationale,
            )

        try:
            resumed_run = await lease.run(execute_resume)
        except ProviderError:
            await project_repository.mark_decision_run_failed(
                claimed_run.project_id,
                claimed_run.id,
                operator=operator,
                failure_reason="Decision provider failed during resume",
                claim_token=claim_token,
                expected_checkpoint_revision=claimed_revision,
                stale_claim_timeout_seconds=ttl,
            )
            raise
        except ConflictError:
            # A superseded worker must not reset the taker's checkpoint.
            raise
        except Exception:
            if not lease.provider_started:
                await release_unstarted_claim()
            # After starting a remote call its outcome may be ambiguous. Keep
            # the claim for explicit stale recovery rather than blindly retry.
            raise

        resumed_run = await project_repository.save_resumed_decision_run(
            resumed_run,
            operator=operator,
            rationale=body.rationale,
            claim_token=claim_token,
            expected_checkpoint_revision=claimed_revision,
            stale_claim_timeout_seconds=ttl,
            record_feedback=True,
            approved_choice=approved_choice,
            feedback_source_run=claimed_run,
        )

        if len(resumed_run.steps) <= 1 and resumed_run.run_status == "completed":
            return {
                "run_id": str(resumed_run.id),
                "status": "completed",
                "checkpoint_revision": resumed_run.checkpoint_revision,
                "selected_choice": resumed_run.selected_choice,
                "supervision_outcome": resumed_run.supervision_outcome,
                "resumed_by": operator,
                "rationale": body.rationale,
            }

        return {
            "run_id": str(resumed_run.id),
            "status": resumed_run.run_status,
            "run_status": resumed_run.run_status,
            "selected_choice": resumed_run.selected_choice,
            "supervision_outcome": resumed_run.supervision_outcome,
            "resumed_by": operator,
            "rationale": body.rationale,
            "current_node_key": resumed_run.current_node_key,
            "next_node_key": resumed_run.next_node_key,
            "checkpoint_revision": resumed_run.checkpoint_revision,
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
        if body is not None:
            reject_credentials(body.model_dump(mode="json"), config)
        _require_operator_permission(request, force_recovery=bool(body and body.force))
        project = await projects.get(identifier)
        operator = body.operator if body is not None else "operator"
        rationale = body.rationale if body is not None else ""
        force = bool(body.force) if body is not None else False
        if force:
            _require_force_recovery_permission(request, rationale=rationale)
            effective_stale_after = 0.0
        else:
            configured_ttl = float(config.decision_run_resume_claim_ttl_seconds)
            effective_stale_after = (
                configured_ttl
                if (body is None or body.stale_after_seconds is None)
                else max(float(body.stale_after_seconds), configured_ttl)
            )
        operator = _checkpoint_operator(request, operator, trusted=force)
        reject_credentials(operator, config)
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
            stale_after_seconds=effective_stale_after,
            force=force,
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
        reject_credentials(body.model_dump(mode="json"), config)
        operator = _checkpoint_operator(request, body.operator)
        reject_credentials(operator, config)
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
                operator=operator,
                reason=body.reason,
                expected_checkpoint_revision=run.checkpoint_revision,
                record_feedback=True,
            )
        else:
            raise HTTPException(
                status_code=501, detail="Checkpoint cancellation is not supported by repository"
            )
        return {
            "run_id": str(run.id),
            "status": "cancelled",
            "cancelled_by": operator,
            "reason": body.reason,
        }

    return router
