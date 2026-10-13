"""Quality alert rules: configurable thresholds evaluated on measured values."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import Model

AlertMetric = Literal["unknown_rate", "recurring_unknowns", "latency", "cost"]


class AlertRule(Model):
    id: str
    project_id: str
    metric: AlertMetric
    threshold: float = Field(gt=0)
    window: str = "1h"  # informational at Genesis; evaluation is per-check
    enabled: bool = True


def evaluate_rule(rule: AlertRule, measured: float | None) -> dict[str, object] | None:
    """Return an alert payload when the measured value breaches the threshold.

    Undefined measurements (None) never fire — alerts are based on real values
    only, never invented ones.
    """
    if measured is None or not rule.enabled:
        return None
    if measured > rule.threshold:
        return {
            "rule_id": rule.id,
            "metric": rule.metric,
            "measured": round(measured, 4),
            "threshold": rule.threshold,
            "message": f"{rule.metric} {measured:.4f} exceeded threshold {rule.threshold}",
        }
    return None


def evaluate_rules(
    rules: list[AlertRule], measurements: dict[str, float | None]
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for rule in rules:
        alert = evaluate_rule(rule, measurements.get(rule.metric))
        if alert is not None:
            alerts.append(alert)
    return alerts
