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
    RawEvent,
    compute_service_hash,
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

    def _resolve_target_node(
        self,
        service: DecisionService,
        selected_choice_spec: DecisionServiceChoice | None,
    ) -> DecisionServiceNode | None:
        if selected_choice_spec is None:
            return None
        if selected_choice_spec.target_node_id is not None:
            for n in service.nodes:
                if n.id == selected_choice_spec.target_node_id:
                    return n
            raise ValueError(f"Target DecisionNode {selected_choice_spec.target_node_id} not found")
        if selected_choice_spec.target_node_name is not None:
            target_name = selected_choice_spec.target_node_name.strip().lower()
            for n in service.nodes:
                if n.name.strip().lower() == target_name:
                    return n
            raise ValueError(
                f"Target DecisionNode '{selected_choice_spec.target_node_name}' not found"
            )
        return None

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

        while current_node is not None:
            if current_node.id in visited_nodes:
                raise ValueError(f"Decision graph cycle detected at node {current_node.name}")
            if len(steps) >= self.max_steps:
                raise ValueError(f"Decision graph exceeded max_steps ({self.max_steps})")
            visited_nodes.add(current_node.id)
            last_node = current_node

            # 1. Compile OntologyVersion from bounded node choices
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
                        stable_class_id=uuid5(
                            service.id, f"node:{current_node.id}:choice:{canonical}"
                        )
                        if len(service.nodes) > 1
                        else uuid5(service.id, f"choice:{canonical}"),
                        canonical_name=canonical,
                        display_name=c.label,
                        description=c.description or c.label,
                        aliases=tuple(unique_aliases),
                    )
                )

            if not classes:
                raise ValueError(
                    "Decision service node must have at least one choice beside UNKNOWN"
                )

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
                facts_json = json.dumps(
                    state_snapshot["facts"], sort_keys=True, separators=(",", ":")
                )
                context_lines.append(f"Structured state facts: {facts_json}")
            if resolved_decisions:
                prior_summary = "; ".join(
                    f"{d['node_name']}={d['choice']} ({d['label']})" for d in resolved_decisions
                )
                context_lines.append(f"Prior resolved decisions: {prior_summary}")
            effective_instructions = "\n".join(context_lines).strip()
            last_instructions = effective_instructions

            request = ChoiceRequest(
                observation=observation,
                ontology=ontology,
                instructions=effective_instructions or None,
            )

            # 2. Invoke DecisionProvider
            try:
                result = await self.provider.choice(request)
            except ProviderError:
                raise
            except ValidationError as error:
                raise ProviderError(
                    "provider returned malformed output", kind="bad_response"
                ) from error

            # 3. Map canonical probabilities back to uppercase Choice keys
            key_lookup = {c.key.lower(): c.key for c in current_node.choices if c.key != "UNKNOWN"}

            probabilities: dict[str, float] = {}
            for canonical, prob in result.probabilities.items():
                key = key_lookup.get(canonical, canonical.upper())
                probabilities[key] = float(prob)
            probabilities["UNKNOWN"] = float(result.unknown_probability)

            total_p = sum(probabilities.values())
            if total_p > 0:
                probabilities = {k: v / total_p for k, v in probabilities.items()}

            # 4. Sort distribution to derive top_probability, second, margin (UNKNOWN wins ties)
            sorted_probs = sorted(
                probabilities.items(),
                key=lambda kv: (kv[1], kv[0] == "UNKNOWN", kv[0]),
                reverse=True,
            )
            top_choice, top_prob = sorted_probs[0]
            second_choice, second_prob = sorted_probs[1] if len(sorted_probs) > 1 else (None, 0.0)
            margin = float(top_prob - (second_prob or 0.0))
            unknown_prob = probabilities.get("UNKNOWN", 0.0)

            # 5. Apply Supervision Policy
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

            # Stop immediately on UNKNOWN
            if top_choice == "UNKNOWN" or supervision_outcome == "UNKNOWN":
                break

            selected_spec = next((c for c in current_node.choices if c.key == top_choice), None)
            next_node = self._resolve_target_node(service, selected_spec)
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

        # 6. Extract Provenance
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
            provider_metadata=meta,
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
