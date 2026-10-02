"""Embedding port and deterministic cosine clustering.

Clusters are observation groupings, never classes. Grouping is greedy over a
stable (id-sorted) order so reruns are idempotent for unchanged inputs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from .models import Model


class EmbeddingProvider(Protocol):
    """Port: batch text embedding with an explicit model version."""

    @property
    def model_version(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddedItem(Model):
    item_id: str
    text: str
    vector: list[float]


class ClusterGroup(Model):
    member_ids: tuple[str, ...]
    member_similarities: tuple[float, ...] = ()
    centroid_similarity: float


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions must match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def group_into_clusters(items: Sequence[EmbeddedItem], threshold: float) -> list[ClusterGroup]:
    """Greedy deterministic grouping: first-fit over id-sorted items.

    Each item joins the earliest cluster whose centroid similarity reaches the
    threshold; otherwise it starts a new cluster. Identical inputs always
    produce identical groupings.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    centroids: list[list[float]] = []
    groups: list[list[str]] = []
    similarities: list[list[float]] = []
    for item in sorted(items, key=lambda entry: entry.item_id):
        best_index = -1
        best_score = threshold
        for index, centroid in enumerate(centroids):
            score = cosine_similarity(item.vector, centroid)
            if score >= best_score:
                best_index = index
                best_score = score
        if best_index == -1:
            centroids.append(list(item.vector))
            groups.append([item.item_id])
            similarities.append([1.0])
        else:
            member_count = len(groups[best_index])
            centroid = centroids[best_index]
            for dimension, value in enumerate(item.vector):
                centroid[dimension] = (centroid[dimension] * member_count + value) / (
                    member_count + 1
                )
            groups[best_index].append(item.item_id)
            similarities[best_index].append(best_score)
    return [
        ClusterGroup(
            member_ids=tuple(members),
            member_similarities=tuple(round(score, 4) for score in scores),
            centroid_similarity=round(sum(scores) / len(scores), 4),
        )
        for members, scores in zip(groups, similarities, strict=True)
    ]
