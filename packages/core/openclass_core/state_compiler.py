"""Strict runtime state compilation and deterministic serialization bounds.

Token units are conservatively estimated as UTF-8 bytes, not measured tokens.
No tokenizer or classification is performed. Provenance records origin only.
"""

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from .decision import Predicate, StateSchema, compile_state, content_digest
from .models import ChoiceRequest, Model
from .supervision import OperatingProfile, RuntimeSupervisionPolicy

if TYPE_CHECKING:
    from .projects import RawEvent


class StateCompilationError(ValueError):
    """Safe representation failure; never converted to semantic UNKNOWN."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"State compilation failed ({code})")


class StateBudgets(Model):
    max_field_chars: int = Field(default=4096, ge=1, le=100000)
    max_field_bytes: int = Field(default=16384, ge=1, le=400000)
    max_total_bytes: int = Field(default=131072, ge=1, le=4000000)
    max_estimated_tokens: int = Field(default=131072, ge=1, le=4000000)


class RuntimeDecisionConfig(Model):
    """Versioned service JSON configuration; supplied through operator configuration."""

    version: Literal[1] = 1
    state_schema: StateSchema | None = None
    budgets: StateBudgets = Field(default_factory=StateBudgets)
    supervision: RuntimeSupervisionPolicy = Field(default_factory=RuntimeSupervisionPolicy)
    operating_profile: OperatingProfile | None = None
    node_preconditions: dict[str, tuple[Predicate, ...]] = Field(default_factory=dict)


def strict_json(value: Any) -> str:
    try:
        # json.dumps accepts int keys/tuples by default; those are not our JSON contract.
        def validate(item: Any) -> None:
            if type(item) is str:
                item.encode("utf-8")
                return
            if item is None or type(item) in (bool, int, float):
                return
            if type(item) is list:
                for child in item:
                    validate(child)
                return
            if type(item) is dict and all(type(k) is str for k in item):
                for key in item:
                    key.encode("utf-8")
                for child in item.values():
                    validate(child)
                return
            raise StateCompilationError("unsupported_value")

        validate(value)
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except StateCompilationError:
        # Keep unsupported_value distinct from serialization failures.
        raise
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        raise StateCompilationError("invalid_json") from None


def check_total(value: Any, budgets: StateBudgets) -> str:
    rendered = strict_json(value)
    size = len(rendered.encode("utf-8"))
    if size > budgets.max_total_bytes or size > budgets.max_estimated_tokens:
        raise StateCompilationError("total_budget_exceeded")
    return rendered


def compile_runtime_state(
    event: "RawEvent",
    prior_steps: list[dict[str, str]],
    schema: StateSchema | None,
    budgets: StateBudgets,
) -> dict[str, Any]:
    # Reject invalid source representations without echoing submitted content.
    strict_json(event.metadata)
    facts: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    if schema is not None:
        sources: dict[str, Any] = {}
        for feature in schema.features:
            present = feature.sensor_field in event.metadata
            value = event.metadata.get(feature.sensor_field)
            source: dict[str, Any] = {
                "source": feature.source,
                "field": feature.sensor_field,
                "event_id": str(event.id),
                "verified_ground_truth": False,
            }
            if feature.source == "prior_decision":
                decision = next(
                    (
                        d
                        for d in reversed(prior_steps)
                        if feature.sensor_field in (d["node_name"], d["node_id"])
                    ),
                    None,
                )
                present = decision is not None
                value = decision["choice"] if decision else None
                if decision:
                    source["node_id"] = decision["node_id"]
            source["status"] = "missing" if not present else "null" if value is None else "present"
            provenance[feature.id] = source
            if not present:
                if feature.required:
                    raise StateCompilationError("missing_required_field")
                continue
            rendered = strict_json(value)
            if (isinstance(value, str) and len(value) > budgets.max_field_chars) or len(
                rendered.encode("utf-8")
            ) > budgets.max_field_bytes:
                raise StateCompilationError("field_budget_exceeded")
            # Reuse strict research compiler semantics, with a private key per feature.
            sources[feature.id] = deepcopy(value)
        mapped = schema.model_copy(
            update={
                "features": tuple(
                    f.model_copy(update={"sensor_field": f.id}) for f in schema.features
                )
            }
        )
        try:
            facts = compile_state(mapped, sources).facts
        except ValueError:
            raise StateCompilationError("wrong_field_type") from None
    snapshot: dict[str, Any] = {
        "schema_id": schema.id if schema else None,
        "schema_version": schema.version if schema else None,
        "facts": facts,
        "provenance": provenance,
        "resolved_decisions": deepcopy(prior_steps),
    }
    snapshot["snapshot_hash"] = content_digest(snapshot)
    check_total(snapshot, budgets)
    return snapshot


def provider_state(request: ChoiceRequest) -> str:
    """Serialize compiled facts as data, never blend them into trusted instructions."""
    state = request.observation.metadata.get("state_facts")
    if state is None:
        return request.observation.content
    return strict_json(
        {
            "untrusted_observation": request.observation.content,
            "untrusted_state_facts": state,
            "state_provenance": request.observation.metadata.get("state_provenance", {}),
            "prior_decisions": request.observation.metadata.get("resolved_decisions", []),
        }
    )


def check_provider_payload(payload: dict[str, Any], request: ChoiceRequest) -> None:
    """Bound the actual adapter serialization, including instructions and choices."""
    budgets = StateBudgets.model_validate(request.observation.metadata.get("state_budgets", {}))
    strict_json(payload)
    # HTTP clients use default JSON separators, so account for those bytes too.
    rendered = json.dumps(payload, allow_nan=False)
    size = len(rendered.encode("utf-8"))
    if size > budgets.max_total_bytes or size > budgets.max_estimated_tokens:
        raise StateCompilationError("provider_payload_budget_exceeded")
