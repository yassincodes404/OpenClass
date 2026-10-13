"""Safe support routing: known → configured action; UNKNOWN → escalate.

UNKNOWN never triggers an automatic reply or assignment beyond a human triage
queue. Adapters record simulated outcomes; they cannot act on their own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import Model

RouteAction = Literal["tag", "assign_queue"]

ESCALATE_ACTION = "escalate"


class RoutingRule(Model):
    id: str
    project_id: str
    integration_id: str
    match_choice: str = Field(min_length=1, max_length=100)
    action: RouteAction
    action_value: str = Field(default="", max_length=200)


def match_rule(rules: list[RoutingRule], selected_choice: str) -> RoutingRule | None:
    """First matching rule for a known choice. UNKNOWN never matches."""
    if selected_choice == "UNKNOWN":
        return None
    for rule in rules:
        if rule.match_choice == selected_choice:
            return rule
    return None


def decide_routing(rules: list[RoutingRule], selected_choice: str) -> dict[str, str]:
    """Known → rule action (or default tag); UNKNOWN → fixed escalation."""
    rule = match_rule(rules, selected_choice)
    if rule is None and selected_choice == "UNKNOWN":
        return {
            "action": ESCALATE_ACTION,
            "queue": "triage",
            "detail": "UNKNOWN path is fixed: human triage queue + needs-review tag; no auto-reply",
        }
    if rule is None:
        return {
            "action": "tag",
            "detail": f"no explicit rule for '{selected_choice}'; default tag applied",
        }
    if rule.action == "tag":
        return {"action": "tag", "tag": rule.action_value or rule.match_choice.lower()}
    return {"action": "assign_queue", "queue": rule.action_value or "general"}


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
