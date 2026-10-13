"""Guarded ontology promotion: human-only activation into immutable versions."""

from __future__ import annotations

from .candidates import MIN_DISTINCT_EVIDENCE


class PromotionBlocked(Exception):
    """A promotion guard failed; the message is safe to show."""


def ensure_promotion_guards(
    *,
    candidate_status: str,
    evidence_count: int,
    evaluation_passed: bool | None,
    rationale: str,
    reviewer: str,
) -> None:
    """All guards must pass; failures raise PromotionBlocked (→ 409)."""
    if not reviewer.strip():
        raise PromotionBlocked("an explicit human reviewer is required")
    if len(rationale.strip()) < 5:
        raise PromotionBlocked("a promotion rationale is required")
    if candidate_status != "approved":
        raise PromotionBlocked(
            f"candidate status is '{candidate_status}'; only human-approved candidates can promote"
        )
    if evidence_count < MIN_DISTINCT_EVIDENCE:
        raise PromotionBlocked(f"insufficient evidence ({evidence_count}/{MIN_DISTINCT_EVIDENCE})")
    if evaluation_passed is None:
        raise PromotionBlocked(
            "no evaluation found for this candidate; run a passing evaluation first"
        )
    if evaluation_passed is False:
        raise PromotionBlocked("the latest evaluation failed; a failed evaluation blocks promotion")


def diff_choices(
    before: list[dict[str, object]],
    after: list[dict[str, object]],
) -> dict[str, list[str]]:
    """Added / modified / removed choice keys between two versions."""
    before_keys = {str(choice.get("key")) for choice in before}
    after_keys = {str(choice.get("key")) for choice in after}
    return {
        "added": sorted(after_keys - before_keys),
        "removed": sorted(before_keys - after_keys),
        "modified": sorted(
            key
            for key in before_keys & after_keys
            if _choice_signature(key, before) != _choice_signature(key, after)
        ),
    }


def _choice_signature(key: str, choices: list[dict[str, object]]) -> tuple[object, ...]:
    for choice in choices:
        if str(choice.get("key")) == key:
            raw_aliases = choice.get("aliases") or []
            alias_list = (
                [str(alias) for alias in raw_aliases]
                if isinstance(raw_aliases, (list, tuple))
                else []
            )
            return (str(choice.get("label")), tuple(alias_list))
    return ()
