"""Configurable multi-signal abstention; likely novel is not a new-class verdict."""

import math

from pydantic import model_validator

from openclass_core.models import (
    ChoiceResult,
    Model,
    NoveltyAssessment,
    NoveltySignals,
    Probability,
)


class NoveltyPolicy(Model):
    strong_unknown_threshold: Probability = 0.7
    weak_unknown_threshold: Probability = 0.35
    semantic_distance_threshold: Probability = 0.75
    minimum_top_margin: Probability = 0.15
    minimum_known_probability: Probability = 0.5

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "NoveltyPolicy":
        if self.weak_unknown_threshold > self.strong_unknown_threshold:
            raise ValueError("weak threshold must not exceed strong threshold")
        return self


def signals_from(result: ChoiceResult) -> NoveltySignals:
    ranked = sorted(result.probabilities.values(), reverse=True)
    top1, top2 = (ranked + [0.0, 0.0])[:2]
    distribution = [*ranked, result.unknown_probability]
    entropy = -sum(p * math.log(p) for p in distribution if p > 0)
    normalized_entropy = entropy / math.log(len(distribution)) if len(distribution) > 1 else 0
    return NoveltySignals(
        unknown_probability=result.unknown_probability,
        top1_probability=top1,
        top2_probability=top2,
        top_margin=top1 - top2,
        entropy=min(1.0, max(0.0, normalized_entropy)),
    )


def assess(signals: NoveltySignals, policy: NoveltyPolicy) -> NoveltyAssessment:
    reasons: list[str] = []
    if signals.unknown_probability >= policy.strong_unknown_threshold:
        return NoveltyAssessment(
            score=signals.unknown_probability,
            state="likely_novel",
            reasons=("strong_unknown_probability",),
        )
    if signals.unknown_probability >= policy.weak_unknown_threshold:
        reasons.append("elevated_unknown_probability")
        if (
            signals.semantic_distance is not None
            and signals.semantic_distance >= policy.semantic_distance_threshold
        ):
            return NoveltyAssessment(
                score=max(signals.unknown_probability, signals.semantic_distance),
                state="likely_novel",
                reasons=(*reasons, "high_semantic_distance"),
            )
    if signals.unknown_probability >= signals.top1_probability:
        reasons.append("unknown_is_top_choice")
    if signals.top_margin < policy.minimum_top_margin:
        reasons.append("low_top_class_margin")
    if signals.top1_probability < policy.minimum_known_probability:
        reasons.append("low_known_confidence")
    score = max(signals.unknown_probability, 1 - signals.top1_probability)
    return NoveltyAssessment(
        score=score,
        state="uncertain" if reasons else "known",
        reasons=tuple(reasons) or ("known_class_supported",),
    )
