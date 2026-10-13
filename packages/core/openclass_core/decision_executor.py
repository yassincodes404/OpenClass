"""Decision executor for the OPERATE plane.

Compiles RawEvents into bounded provider choice requests, invokes the
configured DecisionProvider (Laya / Jev / Mock), applies OpenClass supervision,
and creates immutable DecisionRuns with execution provenance and snapshots.
"""

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import ValidationError

from openclass_core.models import (
    ChoiceRequest,
    Observation,
    OntologyClass,
    OntologyVersion,
)
from openclass_core.projects import (
    DecisionRun,
    DecisionService,
    DecisionServiceNode,
    RawEvent,
)
from openclass_core.providers import DecisionProvider, ProviderError


class DecisionExecutor:
    """Executes bounded semantic decisions over raw events."""

    def __init__(self, provider: DecisionProvider) -> None:
        self.provider = provider

    async def execute(
        self,
        event: RawEvent,
        service: DecisionService,
        node_id: UUID | None = None,
    ) -> DecisionRun:
        # Select target node (default to first node if not specified)
        node: DecisionServiceNode | None = None
        if node_id is not None:
            for n in service.nodes:
                if n.id == node_id:
                    node = n
                    break
            if node is None:
                raise ValueError(f"DecisionNode {node_id} not found in service {service.id}")
        else:
            node = service.nodes[0]

        # 1. Compile OntologyVersion from bounded node choices
        # (UNKNOWN is already guaranteed to be in node.choices)
        classes: list[OntologyClass] = []
        for c in node.choices:
            if c.key == "UNKNOWN":
                continue
            canonical = c.key.lower()
            classes.append(
                OntologyClass(
                    canonical_name=canonical,
                    display_name=c.label,
                    description=c.description or c.label,
                )
            )

        if not classes:
            raise ValueError("Decision service node must have at least one choice beside UNKNOWN")

        ontology = OntologyVersion(
            classifier_id=service.id,
            version_number=1,
            created_by="system",
            classes=tuple(classes),
        )

        observation = Observation(
            content=event.content,
            metadata=dict(event.metadata),
        )

        effective_instructions = (node.instructions or service.instructions).strip()
        request = ChoiceRequest(
            observation=observation,
            ontology=ontology,
            instructions=effective_instructions or None,
        )

        # 2. Invoke DecisionProvider
        # Provider failures are operational and MUST raise ProviderError;
        # malformed adapter output (validation failures) is normalized to one too.
        try:
            result = await self.provider.choice(request)
        except ProviderError:
            raise
        except ValidationError as error:
            raise ProviderError(
                "provider returned malformed output", kind="bad_response"
            ) from error

        # 3. Map canonical probabilities back to uppercase Choice keys
        key_lookup = {c.key.lower(): c.key for c in node.choices if c.key != "UNKNOWN"}

        probabilities: dict[str, float] = {}
        for canonical, prob in result.probabilities.items():
            key = key_lookup.get(canonical, canonical.upper())
            probabilities[key] = float(prob)
        probabilities["UNKNOWN"] = float(result.unknown_probability)

        # Normalize to ensure sum is exactly 1.0
        total_p = sum(probabilities.values())
        if total_p > 0:
            probabilities = {k: v / total_p for k, v in probabilities.items()}

        # 4. Sort distribution to derive top_probability, second, margin
        sorted_probs = sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)
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
        )

        # 6. Extract Provenance
        meta = dict(result.provider_metadata)
        # Usage telemetry travels in metadata so the run snapshot stays self-contained.
        if result.input_tokens is not None:
            meta.setdefault("input_tokens", result.input_tokens)
        if result.output_tokens is not None:
            meta.setdefault("output_tokens", result.output_tokens)
        if result.estimated_cost is not None:
            meta.setdefault("estimated_cost", result.estimated_cost)
        default_mode = "mock" if result.provider == "mock" else "daemon"
        execution_mode = str(meta.get("execution_mode", default_mode))
        real_inference = bool(meta.get("real_inference", False))

        return DecisionRun(
            id=uuid4(),
            project_id=service.project_id,
            raw_event_id=event.id,
            decision_service_id=service.id,
            decision_node_id=node.id,
            provider=result.provider,
            model=result.model,
            execution_mode=execution_mode,  # type: ignore[arg-type]
            real_inference=real_inference,
            selected_choice=top_choice,
            probabilities=probabilities,
            top_probability=top_prob,
            second_probability=second_prob,
            margin=margin,
            unknown_probability=unknown_prob,
            supervision_outcome=supervision_outcome,
            supervision_reason=supervision_reason,
            latency_ms=result.latency_ms,
            input_snapshot=event.model_dump(mode="json"),
            instructions_snapshot=effective_instructions,
            choices_snapshot=[c.model_dump(mode="json") for c in node.choices],
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
    ) -> tuple[Literal["TRUSTED", "REVIEW", "UNKNOWN"], str]:
        # Semantic UNKNOWN is always UNKNOWN
        if selected_choice == "UNKNOWN":
            return "UNKNOWN", "Provider selected semantic UNKNOWN outcome"

        # Laya is uncalibrated research profile: conservative supervision requires REVIEW
        if provider_name == "laya":
            reason = "Laya provider operates under research calibration (conservative supervision)"
            return "REVIEW", reason

        # Jev or calibrated providers: margin-based supervision
        if provider_name == "jev":
            if margin >= 0.20 and top_prob >= 0.50:
                return "TRUSTED", "Calibrated confidence and margin thresholds satisfied"
            return "REVIEW", f"Low decision margin ({margin:.2f} < 0.20) warrants supervisor review"

        # Mock / default provider
        if margin >= 0.25:
            return "TRUSTED", "Decision margin threshold satisfied"
        return "REVIEW", "Low decision margin requires human review"
