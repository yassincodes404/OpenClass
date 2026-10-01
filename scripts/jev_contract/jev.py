"""Jev-only compilation and neutral telemetry; never execute a provider argmax here."""

import math
import re
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from openclass_core.models import ChoiceRequest, ChoiceResult, Observation, OntologyClass
from openclass_core.models import OntologyVersion as ProviderChoices
from pydantic import Field, model_validator

from .canonical import DecisionNode, Frozen, StateSnapshot, digest
from .knowledge import JevProfile, ProfileEvent, require_current

UNKNOWN = "UNKNOWN"


class ProviderCompatibilityError(ValueError):
    """Canonical semantics cannot be represented within the measured profile."""


class CompiledDecision(Frozen):
    decision_spec_id: str
    profile_id: str
    profile_version: int
    profile_hash: str
    node_id: str
    state_snapshot: StateSnapshot
    choice_set_hash: str
    request: ChoiceRequest
    warnings: tuple[str, ...]


class DecisionCompiler(Protocol):
    def compile(self, node: DecisionNode, snapshot: StateSnapshot) -> CompiledDecision: ...


class JevDecisionCompiler:
    version = "jev-compiler-v1"

    def __init__(self, profile: JevProfile, events: tuple[ProfileEvent, ...] = ()) -> None:
        self.profile = profile
        self.events = events

    def compile(self, node: DecisionNode, snapshot: StateSnapshot) -> CompiledDecision:
        require_current(self.profile, self.events)
        if len(node.choices) > self.profile.max_tested_flat_choices:
            raise ProviderCompatibilityError("outside max_tested_flat_choices; re-characterize")
        texts = [node.question, *[c.meaning for c in node.choices]]
        if any(
            re.search(r"\b(the selected one|the chosen one|chosen response|chosen X)\b", t, re.I)
            for t in texts
        ):
            raise ProviderCompatibilityError("anaphoric semantics; explicitly name resolved state")
        warnings = ["Text checks cannot prove semantics are self-contained; review required."]
        if any(c.target_kind == "node" for c in node.choices) and not node.decomposition_reason:
            raise ProviderCompatibilityError(
                "hierarchy requires a real domain decomposition reason"
            )
        if self.profile.identity.model_revision is None:
            warnings.append("Provider exposes a model alias, not an immutable revision.")
        choice_hash = digest([c.model_dump(mode="json") for c in node.choices])
        spec_id = digest(
            {
                "compiler": self.version,
                "node": node.model_dump(mode="json"),
                "profile": self.profile.model_dump(mode="json"),
                "state_schema": [snapshot.schema_id, snapshot.schema_version],
            }
        )
        content = {
            "question": node.question,
            "instruction": "Choose one concrete alternative. Choose UNKNOWN when evidence "
            "is missing, conflicting, ambiguous, or no alternative fits.",
            "state": snapshot.facts,
            "resolved_prior_decisions": [d.model_dump() for d in snapshot.resolved_decisions],
            "raw_evidence": list(snapshot.raw_evidence),
        }
        import json

        request = ChoiceRequest(
            observation=Observation(
                id=uuid5(NAMESPACE_URL, snapshot.id),
                content=json.dumps(content, sort_keys=True),
                created_at=datetime(1970, 1, 1, tzinfo=UTC),
            ),
            ontology=ProviderChoices(
                id=uuid5(NAMESPACE_URL, spec_id),
                classifier_id=uuid5(NAMESPACE_URL, node.id),
                version_number=1,
                created_by=self.version,
                created_at=datetime(1970, 1, 1, tzinfo=UTC),
                classes=tuple(
                    OntologyClass(
                        stable_class_id=uuid5(NAMESPACE_URL, f"{node.id}/{c.id}"),
                        canonical_name=c.id,
                        display_name=c.meaning[:200],
                        description=c.meaning,
                    )
                    for c in node.choices
                ),
            ),
        )
        return CompiledDecision(
            decision_spec_id=spec_id,
            profile_id=self.profile.id,
            profile_version=self.profile.version,
            profile_hash=digest(self.profile.model_dump(mode="json")),
            node_id=node.id,
            state_snapshot=snapshot,
            choice_set_hash=choice_hash,
            request=request,
            warnings=tuple(warnings),
        )


class DecisionTelemetry(Frozen):
    event: Literal["decision.completed", "provider.failed"]
    profile_id: str
    profile_version: int
    profile_hash: str
    provider: str
    model: str
    node_id: str
    decision_spec_id: str
    state_snapshot_id: str
    state_snapshot: StateSnapshot
    choice_set_hash: str
    selected_choice: str | None = None
    distribution: dict[str, float] | None = None
    selected_probability: float | None = None
    top_probability: float | None = None
    second_probability: float | None = None
    margin: float | None = None
    unknown_probability: float | None = None
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reported_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    retry_count: int = Field(ge=0)
    infrastructure_status: Literal["ok", "transport", "http", "invalid_response", "identity_drift"]
    http_status: int | None = None
    simulated: bool

    @model_validator(mode="after")
    def separation(self) -> "DecisionTelemetry":
        if self.state_snapshot_id != self.state_snapshot.id:
            raise ValueError("state snapshot hash mismatch")
        semantic = (
            self.selected_choice,
            self.distribution,
            self.selected_probability,
            self.top_probability,
            self.second_probability,
            self.margin,
            self.unknown_probability,
        )
        if self.infrastructure_status != "ok":
            if self.event != "provider.failed" or any(v is not None for v in semantic):
                raise ValueError("infrastructure failure is not a semantic observation")
        else:
            if self.event != "decision.completed" or any(v is None for v in semantic):
                raise ValueError("successful decision requires full semantic telemetry")
            distribution = self.distribution
            assert distribution is not None
            if UNKNOWN not in distribution or len(distribution) < 2:
                raise ValueError("distribution must include known choices and UNKNOWN")
            if any(not math.isfinite(v) or not 0 <= v <= 1 for v in distribution.values()):
                raise ValueError("invalid probability")
            if abs(sum(distribution.values()) - 1) > 1e-6:
                raise ValueError("distribution must be normalized")
            ordered = sorted(distribution.values(), reverse=True)
            selected = max(distribution, key=lambda k: (distribution[k], k == UNKNOWN, k))
            if self.selected_choice != selected:
                raise ValueError("selected choice disagrees with deterministic selection rule")
            expected = (
                distribution[selected],
                ordered[0],
                ordered[1],
                ordered[0] - ordered[1],
                distribution[UNKNOWN],
            )
            actual = (
                self.selected_probability,
                self.top_probability,
                self.second_probability,
                self.margin,
                self.unknown_probability,
            )
            if any(
                v is None or not math.isfinite(v) or abs(v - e) > 1e-8
                for v, e in zip(actual, expected, strict=True)
            ):
                raise ValueError("derived probability telemetry mismatch")
        return self


def telemetry(
    compiled: CompiledDecision,
    profile: JevProfile,
    result: ChoiceResult | None,
    *,
    latency_ms: float,
    retry_count: int,
    simulated: bool,
    failure: Literal["transport", "http", "invalid_response", "identity_drift"] = "transport",
    http_status: int | None = None,
) -> DecisionTelemetry:
    common: dict[str, Any] = dict(
        profile_id=compiled.profile_id,
        profile_version=compiled.profile_version,
        profile_hash=compiled.profile_hash,
        provider=profile.identity.provider,
        model=profile.identity.model,
        node_id=compiled.node_id,
        decision_spec_id=compiled.decision_spec_id,
        state_snapshot_id=compiled.state_snapshot.id,
        state_snapshot=compiled.state_snapshot,
        choice_set_hash=compiled.choice_set_hash,
        latency_ms=latency_ms,
        retry_count=retry_count,
        simulated=simulated,
        http_status=http_status,
    )
    if result is None:
        return DecisionTelemetry(event="provider.failed", infrastructure_status=failure, **common)
    expected = {c.canonical_name for c in compiled.request.ontology.classes}
    if set(result.probabilities) != expected:
        raise ValueError("returned distribution differs from compiled choices")
    if (result.provider, result.model) != (profile.identity.provider, profile.identity.model):
        raise ProviderCompatibilityError("provider/model changed; mark profile STALE")
    distribution = {**result.probabilities, UNKNOWN: result.unknown_probability}
    ordered = sorted(distribution.values(), reverse=True)
    selected = max(distribution, key=lambda k: (distribution[k], k == UNKNOWN, k))
    return DecisionTelemetry(
        event="decision.completed",
        infrastructure_status="ok",
        selected_choice=selected,
        distribution=distribution,
        selected_probability=distribution[selected],
        top_probability=ordered[0],
        second_probability=ordered[1],
        margin=ordered[0] - ordered[1],
        unknown_probability=result.unknown_probability,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reported_cost=result.estimated_cost,
        **common,
    )


class EscalationPolicy(Frozen):
    """No default numeric threshold. Research rules require held-out evidence and review."""

    id: str
    profile_hash: str
    min_margin: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    max_unknown: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    validation_artifact_hash: str | None = None
    reviewed: bool = False

    def decide(
        self, record: DecisionTelemetry, node: DecisionNode
    ) -> Literal["continue", "escalate"]:
        if record.infrastructure_status != "ok" or record.profile_hash != self.profile_hash:
            return "escalate"
        if node.risk == "high" or record.selected_choice == UNKNOWN:
            return "escalate"
        if not self.reviewed or not self.validation_artifact_hash:
            return "escalate"
        if self.min_margin is None or self.max_unknown is None:
            return "escalate"
        assert record.margin is not None and record.unknown_probability is not None
        return (
            "continue"
            if record.margin >= self.min_margin and record.unknown_probability <= self.max_unknown
            else "escalate"
        )
