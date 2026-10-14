"""UNKNOWN workspace: descriptive triage over project decision runs.

The unknown pool is a *view* over immutable decision runs. Triage state lives
beside the runs and never mutates them or any ontology. Categories are advisory
only — assigning one never creates a class.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .models import Model
from .projects import DecisionRun

UnknownCategory = Literal[
    "truly_novel", "ambiguous", "out_of_scope", "missing_info", "schema_problem"
]
UnknownStatus = Literal["needs_evidence", "triaged", "dismissed", "resolved"]

VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "needs_evidence": ("triaged", "dismissed", "resolved"),
    "triaged": ("dismissed", "resolved"),
    "dismissed": (),
    "resolved": (),
}

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "my",
    "me",
    "i",
    "is",
    "are",
    "was",
    "were",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "at",
    "by",
    "it",
    "this",
    "that",
    "be",
    "have",
    "has",
    "do",
    "does",
    "not",
    "no",
    "yes",
    "please",
    "can",
    "could",
    "would",
}


class UnknownTriage(Model):
    run_id: str
    status: UnknownStatus = "needs_evidence"
    category: UnknownCategory | None = None
    assignee: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    updated_at: datetime | None = None


class UnknownItem(Model):
    run_id: str
    raw_event_id: str
    decision_service_id: str
    content: str
    probabilities: dict[str, float]
    unknown_probability: float
    supervision_reason: str
    created_at: datetime
    triage: UnknownTriage
    recurrence: int = 1


class UnknownStats(Model):
    total_unknown: int
    total_runs: int
    unknown_rate: float
    by_status: dict[str, int]
    by_category: dict[str, int]
    top_phrases: list[str]
    daily: list[dict[str, Any]]


def run_is_unknown(run: DecisionRun) -> bool:
    return run.selected_choice == "UNKNOWN" or run.supervision_outcome == "UNKNOWN"


def summarize_unknowns(
    unknowns: list[UnknownItem],
    total_runs: int,
    *,
    redact: Callable[[str], str] | None = None,
    top_phrase_limit: int = 8,
) -> UnknownStats:
    by_status: Counter[str] = Counter(item.triage.status for item in unknowns)
    by_category: Counter[str] = Counter(
        item.triage.category for item in unknowns if item.triage.category
    )
    words: Counter[str] = Counter()
    daily: Counter[str] = Counter()
    for item in unknowns:
        for token in item.content.lower().split():
            cleaned = token.strip(".,!?;:'\"()[]")
            if len(cleaned) > 2 and cleaned not in STOPWORDS:
                words[cleaned] += 1
        daily[item.created_at.date().isoformat()] += 1
    phrases = [word for word, _ in words.most_common(top_phrase_limit)]
    if redact is not None:
        phrases = [redact(phrase) for phrase in phrases]
    return UnknownStats(
        total_unknown=len(unknowns),
        total_runs=total_runs,
        unknown_rate=round(len(unknowns) / total_runs, 4) if total_runs else 0.0,
        by_status=dict(by_status),
        by_category=dict(by_category),
        top_phrases=phrases,
        daily=[{"date": day, "unknowns": count} for day, count in sorted(daily.items())],
    )


def validate_transition(current: str, target: str) -> None:
    allowed = VALID_TRANSITIONS.get(current, ())
    if target not in allowed:
        raise ValueError(f"cannot transition from '{current}' to '{target}'")
