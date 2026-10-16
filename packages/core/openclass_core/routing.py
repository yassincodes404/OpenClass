"""Safe support routing: known → configured action; UNKNOWN → escalate.

UNKNOWN never triggers an automatic reply or assignment beyond a human triage
queue. Simulation is the default. The legacy ``webhook_verified`` mode requests
an operator-enabled durable intent, NOT verified delivery or a business outcome.
Providers and normalizers cannot authorize dispatch.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import Model

RouteAction = Literal["tag", "assign_queue"]
DeliveryMode = Literal["simulated", "webhook_verified"]

ESCALATE_ACTION = "escalate"


class RoutingRule(Model):
    id: str
    project_id: str
    integration_id: str
    match_choice: str = Field(min_length=1, max_length=100)
    action: RouteAction
    action_value: str = Field(default="", max_length=200)


class RouteOutcome(Model):
    run_id: str = ""
    route_id: str = "default"
    selected_choice: str = "UNKNOWN"
    action: str = ESCALATE_ACTION
    tag: str | None = None
    queue: str | None = None
    detail: str | None = None
    delivery_mode: Literal["simulated", "webhook_verified"] = "simulated"
    idempotency_key: str = ""

    @model_validator(mode="after")
    def _populate_idempotency_key(self) -> RouteOutcome:
        if not self.idempotency_key:
            object.__setattr__(self, "idempotency_key", f"{self.run_id}:{self.route_id}")
        return self

    def to_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {"action": self.action}
        if self.tag is not None:
            payload["tag"] = self.tag
        if self.queue is not None:
            payload["queue"] = self.queue
        if self.detail is not None:
            payload["detail"] = self.detail
        payload["route_id"] = self.route_id
        payload["delivery_mode"] = self.delivery_mode
        payload["idempotency_key"] = self.idempotency_key
        return payload

    def __getitem__(self, key: str) -> str:
        payload = self.to_payload()
        if key in payload:
            return payload[key]
        value = getattr(self, key)
        return str(value)


def match_rule(rules: list[RoutingRule], selected_choice: str) -> RoutingRule | None:
    """First matching rule for a known choice. UNKNOWN never matches."""
    if selected_choice == "UNKNOWN":
        return None
    for rule in rules:
        if rule.match_choice == selected_choice:
            return rule
    return None


def evaluate_routing(
    rules: list[RoutingRule],
    selected_choice: str,
    *,
    run_id: str = "",
    delivery_mode: DeliveryMode = "simulated",
) -> RouteOutcome:
    """Evaluate routing into a typed RouteOutcome with deterministic idempotency_key."""
    rule = match_rule(rules, selected_choice)
    if rule is None and selected_choice == "UNKNOWN":
        return RouteOutcome(
            run_id=run_id,
            route_id="escalate",
            selected_choice=selected_choice,
            action=ESCALATE_ACTION,
            queue="triage",
            detail="UNKNOWN path is fixed: human triage queue + needs-review tag; no auto-reply",
            delivery_mode=delivery_mode,
            idempotency_key=f"{run_id}:escalate",
        )
    if rule is None:
        return RouteOutcome(
            run_id=run_id,
            route_id="default",
            selected_choice=selected_choice,
            action="tag",
            detail=f"no explicit rule for '{selected_choice}'; default tag applied",
            delivery_mode=delivery_mode,
            idempotency_key=f"{run_id}:default",
        )
    if rule.action == "tag":
        return RouteOutcome(
            run_id=run_id,
            route_id=rule.id,
            selected_choice=selected_choice,
            action="tag",
            tag=rule.action_value or rule.match_choice.lower(),
            delivery_mode=delivery_mode,
            idempotency_key=f"{run_id}:{rule.id}",
        )
    return RouteOutcome(
        run_id=run_id,
        route_id=rule.id,
        selected_choice=selected_choice,
        action="assign_queue",
        queue=rule.action_value or "general",
        delivery_mode=delivery_mode,
        idempotency_key=f"{run_id}:{rule.id}",
    )


def decide_routing(
    rules: list[RoutingRule],
    selected_choice: str,
    *,
    run_id: str = "",
    delivery_mode: DeliveryMode = "simulated",
) -> dict[str, str]:
    """Known → rule action (or default tag); UNKNOWN → fixed escalation."""
    return evaluate_routing(
        rules,
        selected_choice,
        run_id=run_id,
        delivery_mode=delivery_mode,
    ).to_payload()


ADAPTERS: dict[str, dict[str, object]] = {
    "zendesk": {"implemented": True, "kind": "support-desk"},
    "intercom": {"implemented": True, "kind": "support-desk"},
    "webhook": {"implemented": True, "kind": "generic"},
    "freshdesk": {"implemented": False, "kind": "support-desk"},
    "salesforce": {"implemented": False, "kind": "crm"},
    "slack": {"implemented": False, "kind": "chat"},
}


def adapter_status(source: str) -> dict[str, object]:
    info = ADAPTERS.get(source, {"implemented": False, "kind": "unknown"})
    return {
        "source": source,
        "implemented": info["implemented"],
        "kind": info["kind"],
        "note": "" if info["implemented"] else "connectivity checks not implemented in this slice",
    }
