"""Deterministic project run analytics; predictions are never accuracy labels."""

from collections import Counter
from math import ceil
from uuid import UUID

from pydantic import Field

from .models import Model
from .projects import DecisionRun


class CountByKey(Model):
    key: str
    count: int = Field(ge=0)


class ProjectAnalytics(Model):
    project_id: UUID
    total_events: int = Field(ge=0)
    total_runs: int = Field(ge=0)
    unknown_runs: int = Field(ge=0)
    unknown_rate: float | None = Field(default=None, ge=0, le=1)
    real_inference_runs: int = Field(ge=0)
    simulated_runs: int = Field(ge=0)
    p50_latency_ms: float | None = Field(default=None, ge=0)
    p95_latency_ms: float | None = Field(default=None, ge=0)
    choices: tuple[CountByKey, ...] = ()
    providers: tuple[CountByKey, ...] = ()
    services: tuple[CountByKey, ...] = ()


def _percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(proportion * len(ordered)) - 1)]


def summarize_project_runs(
    project_id: UUID, total_events: int, runs: list[DecisionRun]
) -> ProjectAnalytics:
    if any(run.project_id != project_id for run in runs):
        raise ValueError("Analytics cannot combine runs from different projects")
    total = len(runs)
    unknowns = sum(run.selected_choice == "UNKNOWN" for run in runs)
    real = sum(run.real_inference for run in runs)

    def counts(values: list[str]) -> tuple[CountByKey, ...]:
        return tuple(
            CountByKey(key=key, count=count)
            for key, count in sorted(Counter(values).items(), key=lambda pair: (-pair[1], pair[0]))
        )

    return ProjectAnalytics(
        project_id=project_id,
        total_events=total_events,
        total_runs=total,
        unknown_runs=unknowns,
        unknown_rate=unknowns / total if total else None,
        real_inference_runs=real,
        simulated_runs=total - real,
        p50_latency_ms=_percentile([run.latency_ms for run in runs], 0.5),
        p95_latency_ms=_percentile([run.latency_ms for run in runs], 0.95),
        choices=counts([run.selected_choice for run in runs]),
        providers=counts([run.provider for run in runs]),
        services=counts([str(run.decision_service_id) for run in runs]),
    )
