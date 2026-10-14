"""Decision executor for the OPERATE plane.

Compiles RawEvents into bounded provider choice requests, invokes the
configured DecisionProvider (Laya / Jev / Mock), applies OpenClass supervision,
and creates immutable DecisionRuns with execution provenance and snapshots.
"""

import json
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError

from openclass_core.decision import content_digest
from openclass_core.models import (
    ChoiceRequest,
    Observation,
    OntologyClass,
    OntologyVersion,
)
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceChoice,
    DecisionServiceNode,
    DecisionServiceTransition,
    RawEvent,
    compute_service_hash,
    now,
)
from openclass_core.providers import DecisionProvider, ProviderError

MAX_STATE_FIELD_CHARS = 4096
MAX_GRAPH_STEPS = 8


def compile_event_state(
    metadata: dict[str, Any],
    resolved_decisions: list[dict[str, str]],
) -> dict[str, Any]:
    """Compile bounded, deterministic state facts and prior decisions without classifying text."""
    bounded_facts: dict[str, Any] = {}
    for key, value in sorted(metadata.items()):
        if value is None:
            continue
        if isinstance(value, str):
            bounded_facts[key] = value[:MAX_STATE_FIELD_CHARS]
        elif isinstance(value, (bool, int, float)):
            bounded_facts[key] = value
        else:
            rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
            bounded_facts[key] = rendered[:MAX_STATE_FIELD_CHARS]
    snapshot: dict[str, Any] = {
        "facts": bounded_facts,
        "resolved_decisions": list(resolved_decisions),
    }
    snapshot["snapshot_hash"] = content_digest(snapshot)
    return snapshot


class DecisionExecutor:
    """Executes bounded semantic decisions over raw events."""

    def __init__(self, provider: DecisionProvider, *, max_steps: int = MAX_GRAPH_STEPS) -> None:
        self.provider = provider
        self.max_steps = max_steps

    def _find_node_by_key(
        self, service: DecisionService, node_key: str | UUID
    ) -> DecisionServiceNode | None:
        key_str = str(node_key).strip().lower()
        for n in service.nodes:
            if str(n.id).strip().lower() == key_str or n.name.strip().lower() == key_str:
                return n
        return None

    def _resolve_target_node(
        self,
        service: DecisionService,
        current_node: DecisionServiceNode,
        choice_key: str,
        selected_choice_spec: DecisionServiceChoice | None = None,
    ) -> tuple[DecisionServiceNode | None, DecisionServiceTransition | None]:
        node_keys = {str(current_node.id).strip().lower(), current_node.name.strip().lower()}
        norm_choice = choice_key.strip().upper()

        matched_transition = next(
            (
                t
                for t in service.transitions
                if t.from_node_key.strip().lower() in node_keys
                and t.choice_key.strip().upper() == norm_choice
            ),
            None,
        )
        if matched_transition is None and norm_choice != "UNKNOWN":
            matched_transition = next(
                (
                    t
                    for t in service.transitions
                    if t.from_node_key.strip().lower() in node_keys and t.choice_key.strip() == "*"
                ),
                None,
            )

        if matched_transition is not None:
            target = self._find_node_by_key(service, matched_transition.to_node_key)
            if target is None:
                raise ValueError(
                    f"Target DecisionNode '{matched_transition.to_node_key}' not found"
                )
            return target, matched_transition

        if selected_choice_spec is None:
            selected_choice_spec = next(
                (c for c in current_node.choices if c.key.upper() == norm_choice), None
            )
        if selected_choice_spec is None:
            return None, None

        if selected_choice_spec.target_node_id is not None:
            for n in service.nodes:
                if n.id == selected_choice_spec.target_node_id:
                    return n, None
            raise ValueError(f"Target DecisionNode {selected_choice_spec.target_node_id} not found")
        if selected_choice_spec.target_node_name is not None:
            target_name = selected_choice_spec.target_node_name.strip().lower()
            for n in service.nodes:
                if n.name.strip().lower() == target_name:
                    return n, None
            raise ValueError(
                f"Target DecisionNode '{selected_choice_spec.target_node_name}' not found"
            )
        return None, None

    def _node_outgoing_transitions(
        self, service: DecisionService, current_node: DecisionServiceNode
    ) -> list[dict[str, Any]]:
        node_keys = {str(current_node.id).strip().lower(), current_node.name.strip().lower()}
        outgoing: list[dict[str, Any]] = []
        seen_choices: set[str] = set()
        for t in service.transitions:
            if t.from_node_key.strip().lower() in node_keys:
                ckey = t.choice_key.strip().upper()
                seen_choices.add(ckey)
                outgoing.append(
                    {
                        "choice_key": ckey,
                        "to_node_key": t.to_node_key,
                        "require_approval": t.require_approval,
                    }
                )
        for c in current_node.choices:
            if c.key.upper() in seen_choices:
                continue
            if c.target_node_id is not None or c.target_node_name is not None:
                target_label = c.target_node_name or str(c.target_node_id)
                if c.target_node_id is not None:
                    found = self._find_node_by_key(service, c.target_node_id)
                    if found is not None:
                        target_label = found.name
                outgoing.append(
                    {
                        "choice_key": c.key,
                        "to_node_key": target_label,
                        "require_approval": False,
                    }
                )
        return outgoing

    async def _score_node(
        self,
        *,
        event: RawEvent,
        service: DecisionService,
        current_node: DecisionServiceNode,
        version_id: UUID,
        resolved_decisions: list[dict[str, str]],
    ) -> tuple[
        Any,
        dict[str, float],
        str,
        float,
        float | None,
        float,
        float,
        Literal["TRUSTED", "REVIEW", "UNKNOWN"],
        str,
        str,
    ]:
        seen_terms: set[str] = {
            c.key.lower().strip().casefold() for c in current_node.choices if c.key != "UNKNOWN"
        }
        classes: list[OntologyClass] = []
        for c in current_node.choices:
            if c.key == "UNKNOWN":
                continue
            canonical = c.key.lower()
            unique_aliases: list[str] = []
            for raw_alias in c.aliases:
                cleaned = raw_alias.strip()
                if not cleaned:
                    continue
                folded = cleaned.casefold()
                if folded not in seen_terms:
                    seen_terms.add(folded)
                    unique_aliases.append(cleaned)
            classes.append(
                OntologyClass(
                    stable_class_id=uuid5(service.id, f"node:{current_node.id}:choice:{canonical}")
                    if len(service.nodes) > 1
                    else uuid5(service.id, f"choice:{canonical}"),
                    canonical_name=canonical,
                    display_name=c.label,
                    description=c.description or c.label,
                    aliases=tuple(unique_aliases),
                )
            )

        if not classes:
            raise ValueError("Decision service node must have at least one choice beside UNKNOWN")

        ontology = OntologyVersion(
            id=version_id,
            classifier_id=service.id,
            version_number=service.version_number,
            created_by="system",
            classes=tuple(classes),
        )

        state_snapshot = compile_event_state(dict(event.metadata), resolved_decisions)
        obs_metadata = dict(event.metadata)
        if resolved_decisions:
            obs_metadata["resolved_decisions"] = list(resolved_decisions)

        observation = Observation(
            content=event.content,
            metadata=obs_metadata,
        )

        base_instructions = (current_node.instructions or service.instructions).strip()
        context_lines: list[str] = []
        if base_instructions:
            context_lines.append(base_instructions)
        if state_snapshot["facts"]:
            facts_json = json.dumps(state_snapshot["facts"], sort_keys=True, separators=(",", ":"))
            context_lines.append(f"Structured state facts: {facts_json}")
        if resolved_decisions:
            prior_summary = "; ".join(
                f"{d['node_name']}={d['choice']} ({d['label']})" for d in resolved_decisions
            )
            context_lines.append(f"Prior resolved decisions: {prior_summary}")
        effective_instructions = "\n".join(context_lines).strip()

        request = ChoiceRequest(
            observation=observation,
            ontology=ontology,
            instructions=effective_instructions or None,
        )

        try:
            result = await self.provider.choice(request)
        except ProviderError:
            raise
        except ValidationError as error:
            raise ProviderError(
                "provider returned malformed output", kind="bad_response"
            ) from error

        key_lookup = {c.key.lower(): c.key for c in current_node.choices if c.key != "UNKNOWN"}

        probabilities: dict[str, float] = {}
        for canonical, prob in result.probabilities.items():
            key = key_lookup.get(canonical, canonical.upper())
            probabilities[key] = float(prob)
        probabilities["UNKNOWN"] = float(result.unknown_probability)

        total_p = sum(probabilities.values())
        if total_p > 0:
            probabilities = {k: v / total_p for k, v in probabilities.items()}

        sorted_probs = sorted(
            probabilities.items(),
            key=lambda kv: (kv[1], kv[0] == "UNKNOWN", kv[0]),
            reverse=True,
        )
        top_choice, top_prob = sorted_probs[0]
        second_choice, second_prob = sorted_probs[1] if len(sorted_probs) > 1 else (None, 0.0)
        margin = float(top_prob - (second_prob or 0.0))
        unknown_prob = probabilities.get("UNKNOWN", 0.0)

        supervision_outcome, supervision_reason = self._supervise(
            provider_name=result.provider,
            selected_choice=top_choice,
            top_prob=top_prob,
            second_prob=second_prob,
            margin=margin,
            unknown_prob=unknown_prob,
            metadata=result.provider_metadata,
            node=current_node,
        )

        return (
            result,
            probabilities,
            top_choice,
            top_prob,
            second_prob,
            margin,
            unknown_prob,
            supervision_outcome,
            supervision_reason,
            base_instructions,
        )

    async def execute(
        self,
        event: RawEvent,
        service: DecisionService,
        node_id: UUID | None = None,
    ) -> DecisionRun:
        # Select starting node (default to first node if not specified)
        current_node: DecisionServiceNode | None = None
        if node_id is not None:
            for n in service.nodes:
                if n.id == node_id:
                    current_node = n
                    break
            if current_node is None:
                raise ValueError(f"DecisionNode {node_id} not found in service {service.id}")
        else:
            current_node = service.nodes[0]

        shash = compute_service_hash(service)
        version_id = service.active_version_id or uuid5(
            service.id, f"version:{service.version_number}:{shash}"
        )

        visited_nodes: set[UUID] = set()
        resolved_decisions: list[dict[str, str]] = []
        steps: list[dict[str, Any]] = []
        total_latency_ms = 0.0

        last_node = current_node
        last_result: Any = None
        last_probabilities: dict[str, float] = {}
        last_top_choice = "UNKNOWN"
        last_top_prob = 0.0
        last_second_prob: float | None = None
        last_margin = 0.0
        last_unknown_prob = 1.0
        last_supervision_outcome: Literal["TRUSTED", "REVIEW", "UNKNOWN"] = "UNKNOWN"
        last_supervision_reason = ""
        last_instructions = ""

        is_paused = False
        paused_next_node: DecisionServiceNode | None = None
        pending_op: dict[str, Any] | None = None

        while current_node is not None:
            if current_node.id in visited_nodes:
                raise ValueError(f"Decision graph cycle detected at node {current_node.name}")
            if len(steps) >= self.max_steps:
                raise ValueError(f"Decision graph exceeded max_steps ({self.max_steps})")
            visited_nodes.add(current_node.id)
            last_node = current_node

            (
                result,
                probabilities,
                top_choice,
                top_prob,
                second_prob,
                margin,
                unknown_prob,
                supervision_outcome,
                supervision_reason,
                base_instructions,
            ) = await self._score_node(
                event=event,
                service=service,
                current_node=current_node,
                version_id=version_id,
                resolved_decisions=resolved_decisions,
            )

            selected_spec = next((c for c in current_node.choices if c.key == top_choice), None)
            next_node: DecisionServiceNode | None = None
            matched_transition: DecisionServiceTransition | None = None
            if top_choice != "UNKNOWN":
                next_node, matched_transition = self._resolve_target_node(
                    service, current_node, top_choice, selected_spec
                )

            if (
                matched_transition is not None
                and matched_transition.require_approval
                and supervision_outcome == "TRUSTED"
            ):
                supervision_outcome = "REVIEW"
                target_label = next_node.name if next_node else matched_transition.to_node_key
                supervision_reason = f"Transition to '{target_label}' requires operator approval"

            total_latency_ms += float(result.latency_ms)
            steps.append(
                {
                    "step_index": len(steps),
                    "node_id": str(current_node.id),
                    "node_name": current_node.name,
                    "selected_choice": top_choice,
                    "probabilities": probabilities,
                    "top_probability": top_prob,
                    "second_probability": second_prob,
                    "margin": margin,
                    "unknown_probability": unknown_prob,
                    "supervision_outcome": supervision_outcome,
                    "supervision_reason": supervision_reason,
                    "latency_ms": float(result.latency_ms),
                }
            )

            last_result = result
            last_probabilities = probabilities
            last_top_choice = top_choice
            last_top_prob = top_prob
            last_second_prob = second_prob
            last_margin = margin
            last_unknown_prob = unknown_prob
            last_supervision_outcome = supervision_outcome
            last_supervision_reason = supervision_reason
            last_instructions = base_instructions

            candidate_transitions = self._node_outgoing_transitions(service, current_node)
            if (
                top_choice == "UNKNOWN"
                or supervision_outcome in ("REVIEW", "UNKNOWN")
                or (matched_transition is not None and matched_transition.require_approval)
            ):
                is_paused = True
                paused_next_node = next_node
                pending_op = {
                    "type": "node_supervision_gate",
                    "node_id": str(current_node.id),
                    "node_key": current_node.name,
                    "proposed_choice": top_choice,
                    "supervision_outcome": supervision_outcome,
                    "supervision_reason": supervision_reason,
                    "next_node_key": next_node.name if next_node is not None else None,
                    "candidate_transitions": candidate_transitions,
                    "service_snapshot": service.model_dump(mode="json"),
                }
                break

            if next_node is None:
                break

            resolved_decisions.append(
                {
                    "node_id": str(current_node.id),
                    "node_name": current_node.name,
                    "choice": top_choice,
                    "label": selected_spec.label if selected_spec is not None else top_choice,
                }
            )
            current_node = next_node

        assert last_result is not None
        final_state_snapshot = compile_event_state(dict(event.metadata), resolved_decisions)

        # Extract Provenance
        meta = dict(last_result.provider_metadata)
        if last_result.input_tokens is not None:
            meta.setdefault("input_tokens", last_result.input_tokens)
        if last_result.output_tokens is not None:
            meta.setdefault("output_tokens", last_result.output_tokens)
        if last_result.estimated_cost is not None:
            meta.setdefault("estimated_cost", last_result.estimated_cost)
        default_mode = "mock" if last_result.provider == "mock" else "daemon"
        execution_mode = str(meta.get("execution_mode", default_mode))
        real_inference = bool(meta.get("real_inference", False))

        return DecisionRun(
            id=uuid4(),
            project_id=service.project_id,
            raw_event_id=event.id,
            decision_service_id=service.id,
            decision_node_id=last_node.id,
            decision_service_version_id=version_id,
            service_hash=shash,
            provider=last_result.provider,
            model=last_result.model,
            execution_mode=execution_mode,  # type: ignore[arg-type]
            real_inference=real_inference,
            selected_choice=last_top_choice,
            probabilities=last_probabilities,
            top_probability=last_top_prob,
            second_probability=last_second_prob,
            margin=last_margin,
            unknown_probability=last_unknown_prob,
            supervision_outcome=last_supervision_outcome,
            supervision_reason=last_supervision_reason,
            latency_ms=total_latency_ms,
            input_snapshot=event.model_dump(mode="json"),
            instructions_snapshot=last_instructions,
            choices_snapshot=[c.model_dump(mode="json") for c in last_node.choices],
            steps=steps,
            state_snapshot=final_state_snapshot,
            run_status="paused" if is_paused else "completed",
            current_node_key=last_node.name,
            next_node_key=paused_next_node.name
            if is_paused and paused_next_node is not None
            else None,
            completed_steps=list(steps),
            pinned_version_id=version_id,
            pinned_version_number=service.version_number,
            pinned_service_hash=shash,
            pending_operation=pending_op if is_paused else None,
            provider_metadata=meta,
        )

    async def resume(
        self,
        run: DecisionRun,
        service: DecisionService,
        *,
        approved_choice: str | None = None,
        operator: str = "operator",
        rationale: str = "",
    ) -> DecisionRun:
        if run.run_status == "cancelled":
            raise ValueError("Cannot resume a cancelled decision run")
        is_resumable = (run.run_status == "paused") or (
            run.supervision_outcome in ("REVIEW", "UNKNOWN") and run.resumed_at is None
        )
        if not is_resumable:
            raise ValueError(
                f"Decision run {run.id} is not paused and cannot be resumed "
                f"(status={run.run_status}, outcome={run.supervision_outcome})"
            )

        paused_node: DecisionServiceNode | None = None
        if run.current_node_key:
            paused_node = self._find_node_by_key(service, run.current_node_key)
        if paused_node is None:
            paused_node = self._find_node_by_key(service, run.decision_node_id)
        if paused_node is None and len(service.nodes) == 1:
            paused_node = service.nodes[0]
        if paused_node is None:
            raise ValueError(
                f"Paused DecisionNode '{run.current_node_key or run.decision_node_id}' "
                f"not found in service {service.id}"
            )

        final_choice = (approved_choice or run.selected_choice).strip().upper()
        valid_node_choices = {c.key.upper() for c in paused_node.choices} | {"UNKNOWN"}
        if final_choice not in valid_node_choices:
            raise ValueError(
                f"Invalid approved_choice '{final_choice}' for node '{paused_node.name}'"
            )

        selected_spec = next(
            (c for c in paused_node.choices if c.key.upper() == final_choice), None
        )

        steps = [dict(s) for s in (run.completed_steps or run.steps)]
        if not steps:
            steps = [
                {
                    "step_index": 0,
                    "node_id": str(paused_node.id),
                    "node_name": paused_node.name,
                    "selected_choice": run.selected_choice,
                    "probabilities": dict(run.probabilities),
                    "top_probability": run.top_probability,
                    "second_probability": run.second_probability,
                    "margin": run.margin,
                    "unknown_probability": run.unknown_probability,
                    "supervision_outcome": run.supervision_outcome,
                    "supervision_reason": run.supervision_reason,
                    "latency_ms": run.latency_ms,
                }
            ]

        approval_reason = rationale or f"Approved by operator {operator}"
        steps[-1] = {
            **steps[-1],
            "selected_choice": final_choice,
            "approved_choice": final_choice,
            "supervision_outcome": "TRUSTED",
            "supervision_reason": approval_reason,
            "approved_by": operator,
            "approval_rationale": rationale,
        }

        visited_nodes: set[UUID] = {paused_node.id}
        for s in steps:
            if s.get("node_id"):
                try:
                    visited_nodes.add(UUID(str(s["node_id"])))
                except ValueError:
                    pass
            if s.get("node_name"):
                matched_n = self._find_node_by_key(service, str(s["node_name"]))
                if matched_n is not None:
                    visited_nodes.add(matched_n.id)

        raw_prior = list(run.state_snapshot.get("resolved_decisions") or [])
        resolved_decisions: list[dict[str, str]] = [dict(d) for d in raw_prior]
        if not any(
            d.get("node_id") == str(paused_node.id) or d.get("node_name") == paused_node.name
            for d in resolved_decisions
        ):
            resolved_decisions.append(
                {
                    "node_id": str(paused_node.id),
                    "node_name": paused_node.name,
                    "choice": final_choice,
                    "label": selected_spec.label if selected_spec is not None else final_choice,
                }
            )
        else:
            for d in resolved_decisions:
                if (
                    d.get("node_id") == str(paused_node.id)
                    or d.get("node_name") == paused_node.name
                ):
                    d["choice"] = final_choice
                    d["label"] = selected_spec.label if selected_spec is not None else final_choice

        next_node: DecisionServiceNode | None = None
        if final_choice != "UNKNOWN":
            next_node, _ = self._resolve_target_node(
                service, paused_node, final_choice, selected_spec
            )

        event = RawEvent.model_validate(run.input_snapshot)
        shash = run.pinned_service_hash or run.service_hash or compute_service_hash(service)
        version_num = run.pinned_version_number or service.version_number
        version_id = (
            run.pinned_version_id
            or run.decision_service_version_id
            or service.active_version_id
            or uuid5(service.id, f"version:{version_num}:{shash}")
        )
        resume_time = now()

        if next_node is None:
            final_state_snapshot = compile_event_state(dict(event.metadata), resolved_decisions)
            return run.model_copy(
                update={
                    "decision_node_id": paused_node.id,
                    "decision_service_version_id": version_id,
                    "service_hash": shash,
                    "selected_choice": final_choice,
                    "supervision_outcome": "TRUSTED",
                    "supervision_reason": approval_reason,
                    "steps": steps,
                    "completed_steps": list(steps),
                    "state_snapshot": final_state_snapshot,
                    "run_status": "completed",
                    "current_node_key": paused_node.name,
                    "next_node_key": None,
                    "pinned_version_id": version_id,
                    "pinned_version_number": version_num,
                    "pinned_service_hash": shash,
                    "pending_operation": None,
                    "resumed_by": operator,
                    "resumed_at": resume_time,
                    "resume_rationale": rationale,
                }
            )

        current_node: DecisionServiceNode | None = next_node
        total_latency_ms = float(run.latency_ms)
        last_node = paused_node
        last_probabilities = dict(run.probabilities)
        last_top_choice = final_choice
        last_top_prob = run.top_probability
        last_second_prob = run.second_probability
        last_margin = run.margin
        last_unknown_prob = run.unknown_probability
        last_supervision_outcome: Literal["TRUSTED", "REVIEW", "UNKNOWN"] = "TRUSTED"
        last_supervision_reason = approval_reason
        last_instructions = run.instructions_snapshot

        is_paused = False
        paused_next_node: DecisionServiceNode | None = None
        pending_op: dict[str, Any] | None = None

        while current_node is not None:
            if current_node.id in visited_nodes:
                raise ValueError(f"Decision graph cycle detected at node {current_node.name}")
            if len(steps) >= self.max_steps:
                raise ValueError(f"Decision graph exceeded max_steps ({self.max_steps})")
            visited_nodes.add(current_node.id)
            last_node = current_node

            (
                result,
                probabilities,
                top_choice,
                top_prob,
                second_prob,
                margin,
                unknown_prob,
                supervision_outcome,
                supervision_reason,
                base_instructions,
            ) = await self._score_node(
                event=event,
                service=service,
                current_node=current_node,
                version_id=version_id,
                resolved_decisions=resolved_decisions,
            )

            sub_spec = next((c for c in current_node.choices if c.key == top_choice), None)
            sub_next_node: DecisionServiceNode | None = None
            sub_transition: DecisionServiceTransition | None = None
            if top_choice != "UNKNOWN":
                sub_next_node, sub_transition = self._resolve_target_node(
                    service, current_node, top_choice, sub_spec
                )

            if (
                sub_transition is not None
                and sub_transition.require_approval
                and supervision_outcome == "TRUSTED"
            ):
                supervision_outcome = "REVIEW"
                target_label = sub_next_node.name if sub_next_node else sub_transition.to_node_key
                supervision_reason = f"Transition to '{target_label}' requires operator approval"

            total_latency_ms += float(result.latency_ms)
            steps.append(
                {
                    "step_index": len(steps),
                    "node_id": str(current_node.id),
                    "node_name": current_node.name,
                    "selected_choice": top_choice,
                    "probabilities": probabilities,
                    "top_probability": top_prob,
                    "second_probability": second_prob,
                    "margin": margin,
                    "unknown_probability": unknown_prob,
                    "supervision_outcome": supervision_outcome,
                    "supervision_reason": supervision_reason,
                    "latency_ms": float(result.latency_ms),
                }
            )

            last_probabilities = probabilities
            last_top_choice = top_choice
            last_top_prob = top_prob
            last_second_prob = second_prob
            last_margin = margin
            last_unknown_prob = unknown_prob
            last_supervision_outcome = supervision_outcome
            last_supervision_reason = supervision_reason
            last_instructions = base_instructions

            candidate_transitions = self._node_outgoing_transitions(service, current_node)
            if (
                top_choice == "UNKNOWN"
                or supervision_outcome in ("REVIEW", "UNKNOWN")
                or (sub_transition is not None and sub_transition.require_approval)
            ):
                is_paused = True
                paused_next_node = sub_next_node
                pending_op = {
                    "type": "node_supervision_gate",
                    "node_id": str(current_node.id),
                    "node_key": current_node.name,
                    "proposed_choice": top_choice,
                    "supervision_outcome": supervision_outcome,
                    "supervision_reason": supervision_reason,
                    "next_node_key": sub_next_node.name if sub_next_node is not None else None,
                    "candidate_transitions": candidate_transitions,
                    "service_snapshot": service.model_dump(mode="json"),
                }
                break

            if sub_next_node is None:
                break

            resolved_decisions.append(
                {
                    "node_id": str(current_node.id),
                    "node_name": current_node.name,
                    "choice": top_choice,
                    "label": sub_spec.label if sub_spec is not None else top_choice,
                }
            )
            current_node = sub_next_node

        final_state_snapshot = compile_event_state(dict(event.metadata), resolved_decisions)
        return run.model_copy(
            update={
                "decision_node_id": last_node.id,
                "decision_service_version_id": version_id,
                "service_hash": shash,
                "selected_choice": last_top_choice,
                "probabilities": last_probabilities,
                "top_probability": last_top_prob,
                "second_probability": last_second_prob,
                "margin": last_margin,
                "unknown_probability": last_unknown_prob,
                "supervision_outcome": last_supervision_outcome,
                "supervision_reason": last_supervision_reason,
                "latency_ms": total_latency_ms,
                "instructions_snapshot": last_instructions,
                "choices_snapshot": [c.model_dump(mode="json") for c in last_node.choices],
                "steps": steps,
                "completed_steps": list(steps),
                "state_snapshot": final_state_snapshot,
                "run_status": "paused" if is_paused else "completed",
                "current_node_key": last_node.name,
                "next_node_key": paused_next_node.name
                if is_paused and paused_next_node is not None
                else None,
                "pinned_version_id": version_id,
                "pinned_version_number": version_num,
                "pinned_service_hash": shash,
                "pending_operation": pending_op if is_paused else None,
                "resumed_by": operator,
                "resumed_at": resume_time,
                "resume_rationale": rationale,
            }
        )

    def _supervise(
        self,
        provider_name: str,
        selected_choice: str,
        top_prob: float,
        second_prob: float | None,
        margin: float,
        unknown_prob: float,
        metadata: dict[str, Any],
        node: DecisionServiceNode | None = None,
    ) -> tuple[Literal["TRUSTED", "REVIEW", "UNKNOWN"], str]:
        # Semantic UNKNOWN is always UNKNOWN
        if selected_choice == "UNKNOWN":
            return "UNKNOWN", "Provider selected semantic UNKNOWN outcome"

        if (
            node is not None
            and node.max_unknown_probability is not None
            and unknown_prob > node.max_unknown_probability
        ):
            return (
                "REVIEW",
                f"Unknown probability ({unknown_prob:.2f} > {node.max_unknown_probability:.2f})"
                " exceeds node threshold",
            )

        if node is not None and node.risk_level == "high":
            return "REVIEW", "High-risk decision node requires supervisor or human review"

        if node is not None and node.pause_on_review:
            return "REVIEW", "Decision node configured with pause_on_review requires human review"

        # Laya or explicitly uncalibrated research profile: conservative supervision requires REVIEW
        if provider_name == "laya" or metadata.get("calibration_status") == "uncalibrated":
            reason = "Laya provider operates under research calibration (conservative supervision)"
            return "REVIEW", reason

        # Jev or calibrated providers: margin-based supervision
        if provider_name == "jev":
            req_margin = (
                node.min_margin if (node is not None and node.min_margin is not None) else 0.20
            )
            if margin >= req_margin and top_prob >= 0.50:
                return "TRUSTED", "Calibrated confidence and margin thresholds satisfied"
            return (
                "REVIEW",
                f"Low decision margin ({margin:.2f} < {req_margin:.2f}) warrants supervisor review",
            )

        # Mock / default provider
        req_margin = node.min_margin if (node is not None and node.min_margin is not None) else 0.25
        if margin >= req_margin:
            return "TRUSTED", "Decision margin threshold satisfied"
        return "REVIEW", "Low decision margin requires human review"
