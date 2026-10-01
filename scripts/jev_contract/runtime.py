"""Experimental compiled graph runner with append-only events and deterministic macros."""

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from openclass_core.models import ChoiceResult
from pydantic import Field

from .canonical import (
    Frozen,
    Macro,
    PolicyGraph,
    Predicate,
    ResolvedDecision,
    StateSnapshot,
    Step,
    compile_state,
)
from .jev import (
    UNKNOWN,
    CompiledDecision,
    DecisionTelemetry,
    EscalationPolicy,
    JevDecisionCompiler,
    telemetry,
)
from .knowledge import (
    JevProfile,
    ProfileEvent,
    ProfileJournal,
    ProviderIdentity,
    require_current,
    save_new,
)
from .teacher import Capability


class ProviderCall(Frozen):
    result: ChoiceResult | None
    failure: Literal["transport", "http", "invalid_response"] = "transport"
    retry_count: int = Field(default=0, ge=0)
    http_status: int | None = None
    simulated: bool = False


class World(Protocol):
    def observe(self) -> StateSnapshot: ...
    def execute(self, step: Step) -> bool: ...


class EventStore:
    """An event per exclusively created file. No provider error text is accepted."""

    def __init__(self, root: Path, secrets: tuple[str, ...] = ()) -> None:
        root.mkdir(parents=True, exist_ok=False)
        self.root = root
        self.secrets = secrets
        self.sequence = 0

    def append(self, event: dict[str, Any]) -> None:
        serialized = json.dumps(event, allow_nan=False)
        if any(secret and secret in serialized for secret in self.secrets):
            raise ValueError("secret-bearing event refused")
        self.sequence += 1
        save_new(self.root / f"{self.sequence:05d}-{uuid4().hex}.json", event)

    def freeze(self) -> None:
        save_new(
            self.root / "sha256.json",
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.root.iterdir())
                if p.is_file()
            },
        )


class RunResult(Frozen):
    status: Literal["completed", "escalated", "failed", "bounded"]
    diagnosis: str | None = None
    decisions: tuple[DecisionTelemetry, ...]


def execute_macro(macro: Macro, world: World, catalog: tuple[Capability, ...]) -> str | None:
    def holds(predicates: tuple[Predicate, ...]) -> bool:
        facts = world.observe().facts
        # Absent is not equivalent to an observed null/false value.
        return all(
            p.field in facts
            and type(facts[p.field]) is type(p.equals)
            and facts[p.field] == p.equals
            for p in predicates
        )

    if not holds(macro.preconditions):
        return "PRECONDITION"
    if not holds(macro.safety_guards):
        return "SAFETY_GUARD"
    capabilities = {c.id: c for c in catalog}
    # Validate the entire procedure before its first side effect.
    for step in macro.steps:
        if step.capability not in capabilities:
            return "MISSING_CAPABILITY"
        try:
            capabilities[step.capability].validate_step(step)
        except ValueError:
            return "MISSING_CAPABILITY"
    for step in macro.steps:
        try:
            if not world.execute(step):
                return "PROCEDURE"
        except Exception:
            return "INFRASTRUCTURE"
    return None if holds(macro.postconditions) else "POSTCONDITION"


async def run_graph(
    graph: PolicyGraph,
    world: World,
    profile: JevProfile,
    identity: ProviderIdentity,
    call: Callable[[CompiledDecision], Awaitable[ProviderCall]],
    policy: EscalationPolicy,
    catalog: tuple[Capability, ...],
    store: EventStore,
    journal: ProfileJournal,
    events: tuple[ProfileEvent, ...] = (),
    max_decisions: int = 8,
) -> RunResult:
    """No Teacher, mutation, approval, or activation callback exists in execution."""
    if not 1 <= max_decisions <= 100:
        raise ValueError("decision budget must be 1..100")
    stale = journal.observe(profile, identity)
    events = (*events, *journal.events())
    if stale:
        store.append(stale.model_dump(mode="json"))
        events = (*events, stale)
    require_current(profile, events)
    compiler = JevDecisionCompiler(profile, events)
    node_id = graph.entry_node
    nodes = {n.id: n for n in graph.nodes}
    macros = {m.id: m for m in graph.macros}
    resolved: tuple[ResolvedDecision, ...] = ()
    records: list[DecisionTelemetry] = []
    for _ in range(max_decisions):
        node = nodes[node_id]
        observed = world.observe()
        snapshot = compile_state(
            graph.state_schema, observed.facts, observed.raw_evidence, resolved
        )
        compiled = compiler.compile(node, snapshot)
        started = time.perf_counter()
        try:
            response = await call(compiled)
        except Exception:
            # Transport exceptions may contain credentials. Never persist their text.
            response = ProviderCall(result=None, failure="transport")
        latency = (time.perf_counter() - started) * 1000
        result = response.result
        failure: Literal["transport", "http", "invalid_response", "identity_drift"] = (
            response.failure
        )
        if result is not None and (result.provider, result.model) != (
            identity.provider,
            identity.model,
        ):
            changed = identity.model_copy(
                update={"provider": result.provider, "model": result.model}
            )
            stale = journal.observe(profile, changed)
            assert stale is not None
            store.append(stale.model_dump(mode="json"))
            result = None
            failure = "identity_drift"
        try:
            record = telemetry(
                compiled,
                profile,
                result,
                latency_ms=latency,
                retry_count=response.retry_count,
                simulated=response.simulated,
                failure=failure,
                http_status=response.http_status,
            )
        except ValueError:
            record = telemetry(
                compiled,
                profile,
                None,
                latency_ms=latency,
                retry_count=response.retry_count,
                simulated=response.simulated,
                failure="invalid_response",
                http_status=response.http_status,
            )
        store.append(record.model_dump(mode="json"))
        records.append(record)
        if policy.decide(record, node) != "continue":
            # UNKNOWN is not proof of DECISION_SPACE; needs deterministic diagnosis.
            diagnosis: str | None = (
                "INFRASTRUCTURE"
                if record.infrastructure_status != "ok"
                else "INSUFFICIENT_EVIDENCE"
            )
            store.append(
                {
                    "event": "decision.escalated",
                    "node_id": node.id,
                    "diagnosis": diagnosis,
                    "policy_id": policy.id,
                }
            )
            return RunResult(status="escalated", diagnosis=diagnosis, decisions=tuple(records))
        choice = next(c for c in node.choices if c.id == record.selected_choice)
        assert choice.id != UNKNOWN
        resolved += (
            ResolvedDecision(node_id=node.id, choice_id=choice.id, meaning=choice.meaning),
        )
        if choice.target_kind == "terminal":
            return RunResult(status="completed", decisions=tuple(records))
        if choice.target_kind == "node":
            node_id = str(choice.target_id)
            continue
        diagnosis = execute_macro(macros[str(choice.target_id)], world, catalog)
        store.append(
            {
                "event": "macro.verified",
                "macro_id": choice.target_id,
                "diagnosis": diagnosis,
                "state_after": world.observe().model_dump(mode="json"),
            }
        )
        return RunResult(
            status="failed" if diagnosis else "completed",
            diagnosis=diagnosis,
            decisions=tuple(records),
        )
    return RunResult(status="bounded", diagnosis="INSUFFICIENT_EVIDENCE", decisions=tuple(records))
