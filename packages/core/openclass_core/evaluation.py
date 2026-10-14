"""Verified evaluation datasets: ground truth with human/verified provenance.

Predictions can never become ground truth — `source=prediction` is rejected at
the model boundary. Datasets are immutable once sealed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .models import Model

ExampleSource = Literal["human", "verified_external"]
ExampleSlice = Literal["historical", "recent", "rare", "hard", "unknown", "adversarial"]
ExampleSplit = Literal["calibration", "regression", "holdout"]
LABEL_UNKNOWN = "UNKNOWN"
VALID_SOURCES: tuple[str, ...] = ("human", "verified_external")
VALID_SLICES: tuple[str, ...] = ("historical", "recent", "rare", "hard", "unknown", "adversarial")
VALID_SPLITS: tuple[str, ...] = ("calibration", "regression", "holdout")
FORBIDDEN_LABEL_SOURCES: frozenset[str] = frozenset(
    {"prediction", "model_prediction", "unverified_prediction"}
)


class EvaluationSet(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    dataset_hash: str | None = None
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
    split: ExampleSplit = "holdout"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _reject_prediction_ground_truth(self) -> EvaluationExample:
        label_source = str(self.metadata.get("label_source", "")).strip().lower()
        source_type = str(self.metadata.get("source_type", "")).strip().lower()
        if label_source in FORBIDDEN_LABEL_SOURCES or source_type in FORBIDDEN_LABEL_SOURCES:
            raise ValueError("Predictions cannot be used as evaluation ground truth")
        return self


class ExampleDraft(Model):
    """Validation boundary for incoming examples."""

    text: str = Field(min_length=1, max_length=10_000)
    label: str = Field(min_length=1, max_length=100)
    source: str
    annotator: str = Field(min_length=2, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    slice_tag: str = "historical"
    split: str = "holdout"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_example(self, allowed_labels: tuple[str, ...]) -> EvaluationExample:
        if self.source == "prediction":
            raise ValueError("predictions cannot be ground truth")
        label_source = str(self.metadata.get("label_source", "")).strip().lower()
        source_type = str(self.metadata.get("source_type", "")).strip().lower()
        if label_source in FORBIDDEN_LABEL_SOURCES or source_type in FORBIDDEN_LABEL_SOURCES:
            raise ValueError("Predictions cannot be used as evaluation ground truth")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}")
        if self.slice_tag not in VALID_SLICES:
            raise ValueError(f"slice_tag must be one of {VALID_SLICES}")
        if self.split not in VALID_SPLITS:
            raise ValueError(f"split must be one of {VALID_SPLITS}")
        if self.label != LABEL_UNKNOWN and self.label not in allowed_labels:
            raise ValueError(f"label '{self.label}' is not an existing class or UNKNOWN")
        return EvaluationExample(
            text=self.text.strip(),
            label=self.label.strip().upper(),
            source=self.source,  # type: ignore[arg-type]
            annotator=self.annotator.strip(),
            rationale=self.rationale.strip(),
            slice_tag=self.slice_tag,  # type: ignore[arg-type]
            split=self.split,  # type: ignore[arg-type]
            metadata=dict(self.metadata),
        )


def slice_coverage(examples: list[EvaluationExample]) -> dict[str, int]:
    coverage: dict[str, int] = {name: 0 for name in VALID_SLICES}
    for example in examples:
        coverage[example.slice_tag] = coverage.get(example.slice_tag, 0) + 1
    return coverage


def compute_dataset_hash(examples: list[EvaluationExample]) -> str:
    """Compute a deterministic SHA-256 fingerprint of a sealed evaluation dataset."""
    canonical = sorted(
        (
            {
                "text": ex.text,
                "label": ex.label,
                "source": ex.source,
                "slice_tag": ex.slice_tag,
                "split": ex.split,
            }
            for ex in examples
        ),
        key=lambda item: (item["text"], item["label"], item["slice_tag"], item["split"]),
    )
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_not_sealed(dataset: EvaluationSet) -> None:
    if dataset.sealed_at is not None:
        raise ValueError("dataset is sealed and immutable")
