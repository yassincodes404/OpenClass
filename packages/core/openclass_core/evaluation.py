"""Verified evaluation datasets: ground truth with human/verified provenance.

Predictions can never become ground truth — `source=prediction` is rejected at
the model boundary. Datasets are immutable once sealed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .models import Model

ExampleSource = Literal["human", "verified_external"]
ExampleSlice = Literal["historical", "recent", "rare", "hard", "unknown", "adversarial"]
LABEL_UNKNOWN = "UNKNOWN"
VALID_SOURCES: tuple[str, ...] = ("human", "verified_external")
VALID_SLICES: tuple[str, ...] = ("historical", "recent", "rare", "hard", "unknown", "adversarial")


class EvaluationSet(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    sealed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationExample(Model):
    id: UUID = Field(default_factory=uuid4)
    dataset_id: UUID | None = None
    text: str = Field(min_length=1, max_length=10_000)
    label: str = Field(min_length=1, max_length=100)
    source: ExampleSource
    annotator: str = Field(min_length=2, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    slice_tag: ExampleSlice = "historical"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExampleDraft(Model):
    """Validation boundary for incoming examples."""

    text: str = Field(min_length=1, max_length=10_000)
    label: str = Field(min_length=1, max_length=100)
    source: str
    annotator: str = Field(min_length=2, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    slice_tag: str = "historical"

    def to_example(self, allowed_labels: tuple[str, ...]) -> EvaluationExample:
        if self.source == "prediction":
            raise ValueError("predictions cannot be ground truth")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}")
        if self.slice_tag not in VALID_SLICES:
            raise ValueError(f"slice_tag must be one of {VALID_SLICES}")
        if self.label != LABEL_UNKNOWN and self.label not in allowed_labels:
            raise ValueError(f"label '{self.label}' is not an existing class or UNKNOWN")
        return EvaluationExample(
            text=self.text.strip(),
            label=self.label.strip().upper(),
            source=self.source,  # type: ignore[arg-type]
            annotator=self.annotator.strip(),
            rationale=self.rationale.strip(),
            slice_tag=self.slice_tag,  # type: ignore[arg-type]
        )


def slice_coverage(examples: list[EvaluationExample]) -> dict[str, int]:
    coverage: dict[str, int] = {name: 0 for name in VALID_SLICES}
    for example in examples:
        coverage[example.slice_tag] = coverage.get(example.slice_tag, 0) + 1
    return coverage


def assert_not_sealed(dataset: EvaluationSet) -> None:
    if dataset.sealed_at is not None:
        raise ValueError("dataset is sealed and immutable")
