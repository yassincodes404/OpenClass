"""Cluster discovery → inactive candidate proposals.

Candidates are evidence-backed suggestions, never active behavior. The six
proposal types cover every outcome; canonicalization resolves synonyms before
suggesting a new class so "cancel plan" and "close subscription" merge.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field

from .models import Model
from .unknown_pool import STOPWORDS

ProposalType = Literal[
    "NEW_CLASS",
    "EXISTING_CLASS",
    "ALIAS",
    "INSUFFICIENT_EVIDENCE",
    "OUT_OF_DOMAIN",
    "SCHEMA_ISSUE",
]

# Synonym map applied after normalization; both sides canonicalize to the left term.
SYNONYMS: dict[str, str] = {
    "close subscription": "cancel plan",
    "end subscription": "cancel plan",
    "unsubscribe": "cancel plan",
    "terminate plan": "cancel plan",
    "stop renewal": "cancel plan",
    "hijacked": "account takeover",
    "account hijacked": "account takeover",
}

MIN_CLUSTER_MEMBERS = 3


class DiscoveryCandidate(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    cluster_id: UUID
    type: ProposalType
    canonical_name: str | None = None
    display_name: str | None = None
    definition: str | None = Field(default=None, max_length=2000)
    aliases: tuple[str, ...] = ()
    existing_match: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=2000)
    status: Literal["candidate", "rejected"] = "candidate"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClusterDiscoveryRequest(Model):
    cluster_id: UUID
    member_texts: tuple[str, ...]
    existing_classes: tuple[str, ...]
    provider: str = "mock"


class ClusterDiscoveryResult(Model):
    type: ProposalType
    canonical_name: str | None = None
    display_name: str | None = None
    definition: str | None = None
    aliases: tuple[str, ...] = ()
    existing_match: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class ClusterDiscoveryProvider(Protocol):
    """Port: propose an (inactive) candidate from a cluster of unknown texts."""

    async def discover(self, request: ClusterDiscoveryRequest) -> ClusterDiscoveryResult: ...


def normalize_phrase(text: str) -> str:
    normalized = " ".join(text.lower().split())
    for source, target in SYNONYMS.items():
        if source in normalized:
            normalized = normalized.replace(source, target)
    return normalized.strip()


def significant_tokens(text: str) -> list[str]:
    return [
        token
        for token in normalize_phrase(text).split()
        if token not in STOPWORDS and len(token) > 2
    ]


def dominant_phrase(texts: Sequence[str]) -> str:
    """Most common significant token bigram-or-unigram across member texts."""
    counter: Counter[str] = Counter()
    for text in texts:
        tokens = significant_tokens(text)
        counter.update(tokens)
        for first, second in zip(tokens, tokens[1:], strict=False):
            counter.update([f"{first} {second}"])
    if not counter:
        return "unknown theme"
    top = counter.most_common(1)[0][1]
    contenders = [phrase for phrase, count in counter.items() if count >= max(2, int(top * 0.4))]
    # Prefer multi-word phrases among near-top contenders: class names read better.
    return max(contenders, key=lambda phrase: (len(phrase.split()), counter[phrase]))


def matches_existing(phrase: str, existing_classes: Sequence[str]) -> str | None:
    phrase_tokens = set(phrase.split())
    for existing in existing_classes:
        existing_tokens = set(existing.replace("_", " ").split())
        if not phrase_tokens or not existing_tokens:
            continue
        # Exact, phrase-within-class, or class-within-phrase (qualifiers like
        # "billing question" still point at the existing class).
        if (
            phrase == existing
            or phrase_tokens <= existing_tokens
            or existing_tokens <= phrase_tokens
        ):
            return existing
    return None


def canonicalize_name(phrase: str) -> tuple[str, str]:
    snake = "_".join(phrase.split())
    display = phrase.title()
    return snake, display


def decide_proposal(
    member_texts: Sequence[str],
    existing_classes: Sequence[str],
    *,
    min_members: int = MIN_CLUSTER_MEMBERS,
) -> ClusterDiscoveryResult:
    """Deterministic canonicalizer: synonyms merge, existing concepts win, small clusters defer."""
    if len(member_texts) < min_members:
        return ClusterDiscoveryResult(
            type="INSUFFICIENT_EVIDENCE",
            confidence=0.2,
            reason=f"cluster has {len(member_texts)} members; at least {min_members} required",
        )
    phrase = dominant_phrase(member_texts)
    normalized = normalize_phrase(phrase)
    existing = matches_existing(normalized, tuple(existing_classes))
    if existing:
        return ClusterDiscoveryResult(
            type="EXISTING_CLASS",
            existing_match=existing,
            canonical_name=existing,
            display_name=existing.replace("_", " ").title(),
            confidence=0.85,
            reason=f"'{normalized}' already matches existing class '{existing}'",
        )
    canonical, display = canonicalize_name(normalized)
    variants = sorted({normalize_phrase(text) for text in member_texts})[:5]
    aliases = tuple(variant for variant in variants if variant != normalized)[:4]
    return ClusterDiscoveryResult(
        type="NEW_CLASS",
        canonical_name=canonical,
        display_name=display,
        definition=(
            f"Recurring intent observed across {len(member_texts)} UNKNOWN runs,"
            f" centered on '{normalized}'."
        ),
        aliases=aliases,
        confidence=round(min(0.5 + 0.1 * len(member_texts), 0.9), 2),
        reason=f"'{normalized}' is not covered by existing classes after synonym canonicalization",
    )


class MockClusterDiscoveryProvider:
    """Deterministic simulated discovery over the canonicalizer (no LLM calls)."""

    async def discover(self, request: ClusterDiscoveryRequest) -> ClusterDiscoveryResult:
        return decide_proposal(request.member_texts, request.existing_classes)


CandidateStatus = Literal[
    "discovered",
    "candidate",
    "collecting_evidence",
    "validating",
    "approved",
    "active",
    "rejected",
]

# v0.1 exposes candidate/rejected/approved, but storage allows the full enum.
CANDIDATE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "discovered": ("candidate", "rejected"),
    # Discovery already attaches cluster evidence, so a candidate with enough
    # evidence can go straight to review without a redundant collect step.
    "candidate": ("collecting_evidence", "validating", "rejected"),
    "collecting_evidence": ("validating", "rejected"),
    "validating": ("approved", "collecting_evidence", "rejected"),
    "approved": ("active",),
    "active": (),
    "rejected": (),
}

MIN_DISTINCT_EVIDENCE = 5


def validate_candidate_transition(current: str, target: str) -> None:
    if target not in CANDIDATE_TRANSITIONS.get(current, ()):
        raise ValueError(f"illegal candidate transition from '{current}' to '{target}'")


def review_gaps(evidence_count: int, minimum: int = MIN_DISTINCT_EVIDENCE) -> str | None:
    """Human-review gate: returns a blocking message or None when satisfied."""
    if evidence_count < minimum:
        return f"collect more evidence ({evidence_count}/{minimum})"
    return None
