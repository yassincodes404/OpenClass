"""Replay evaluation metrics — pure, hand-checkable math.

Every metric is computed from (gold, predicted) pairs. Empty inputs produce
explicit None values, never a fake pass.
"""

from __future__ import annotations

from collections.abc import Iterable

Prediction = tuple[str, str]  # (gold_label, predicted_label)


def accuracy(pairs: list[Prediction]) -> float | None:
    if not pairs:
        return None
    correct = sum(1 for gold, predicted in pairs if gold == predicted)
    return correct / len(pairs)


def per_class_accuracy(pairs: list[Prediction], label: str) -> float | None:
    subset = [(gold, predicted) for gold, predicted in pairs if gold == label]
    if not subset:
        return None
    correct = sum(1 for gold, predicted in subset if predicted == label)
    return correct / len(subset)


def macro_f1(pairs: list[Prediction]) -> float | None:
    labels = {gold for gold, _ in pairs} | {predicted for _, predicted in pairs}
    if not pairs or not labels:
        return None
    scores: list[float] = []
    for label in labels:
        tp = sum(1 for gold, predicted in pairs if gold == label and predicted == label)
        fp = sum(1 for gold, predicted in pairs if gold != label and predicted == label)
        fn = sum(1 for gold, predicted in pairs if gold == label and predicted != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def unknown_precision_recall(pairs: list[Prediction]) -> tuple[float | None, float | None]:
    predicted_unknown = [(gold, predicted) for gold, predicted in pairs if predicted == "UNKNOWN"]
    gold_unknown = [(gold, predicted) for gold, predicted in pairs if gold == "UNKNOWN"]
    precision = (
        sum(1 for gold, _ in predicted_unknown if gold == "UNKNOWN") / len(predicted_unknown)
        if predicted_unknown
        else None
    )
    recall = (
        sum(1 for _, predicted in gold_unknown if predicted == "UNKNOWN") / len(gold_unknown)
        if gold_unknown
        else None
    )
    return precision, recall


def coverage(pairs: list[Prediction]) -> float | None:
    """Fraction of examples the system resolved to a domain class (not UNKNOWN)."""
    if not pairs:
        return None
    known = sum(1 for _, predicted in pairs if predicted != "UNKNOWN")
    return known / len(pairs)


def false_novelty_rate(
    pairs: list[Prediction], known_labels: set[str] | None = None
) -> float | None:
    """Known-labeled examples incorrectly returned as UNKNOWN.

    When known_labels is given (the baseline ontology), only examples whose gold
    label the system already knows are counted — a newly proposed class still
    matching imperfectly is not a regression of existing knowledge.
    """
    if known_labels is None:
        known_gold = [(gold, predicted) for gold, predicted in pairs if gold != "UNKNOWN"]
    else:
        known_gold = [(gold, predicted) for gold, predicted in pairs if gold in known_labels]
    if not known_gold:
        return None
    wrong_unknown = sum(1 for _, predicted in known_gold if predicted == "UNKNOWN")
    return wrong_unknown / len(known_gold)


class Gates:
    """Configurable regression gates; all must pass for promotion eligibility."""

    def __init__(
        self,
        *,
        min_delta_accuracy: float = 0.0,
        false_novelty_max: float = 0.2,
        protected_classes: Iterable[str] = (),
    ) -> None:
        self.min_delta_accuracy = min_delta_accuracy
        self.false_novelty_max = false_novelty_max
        self.protected_classes = tuple(protected_classes)

    def evaluate(
        self,
        baseline_pairs: list[Prediction],
        candidate_pairs: list[Prediction],
        known_labels: set[str] | None = None,
    ) -> dict[str, object]:
        baseline_accuracy = accuracy(baseline_pairs)
        candidate_accuracy = accuracy(candidate_pairs)
        checks: dict[str, object] = {
            "accuracy_delta": None
            if baseline_accuracy is None or candidate_accuracy is None
            else round(candidate_accuracy - baseline_accuracy, 4),
            "baseline_accuracy": None if baseline_accuracy is None else round(baseline_accuracy, 4),
            "candidate_accuracy": None
            if candidate_accuracy is None
            else round(candidate_accuracy, 4),
        }
        gate_results: list[dict[str, object]] = []

        if baseline_accuracy is None or candidate_accuracy is None:
            gate_results.append(
                {"gate": "accuracy_delta", "passed": False, "reason": "undefined metrics"}
            )
        else:
            delta = candidate_accuracy - baseline_accuracy
            gate_results.append(
                {
                    "gate": "accuracy_delta",
                    "passed": delta >= self.min_delta_accuracy,
                    "value": round(delta, 4),
                    "threshold": self.min_delta_accuracy,
                }
            )

        novelty = false_novelty_rate(candidate_pairs, known_labels)
        if novelty is None:
            gate_results.append(
                {"gate": "false_novelty", "passed": False, "reason": "no known-labeled examples"}
            )
        else:
            gate_results.append(
                {
                    "gate": "false_novelty",
                    "passed": novelty <= self.false_novelty_max,
                    "value": round(novelty, 4),
                    "threshold": self.false_novelty_max,
                }
            )

        for label in self.protected_classes:
            before = per_class_accuracy(baseline_pairs, label)
            after = per_class_accuracy(candidate_pairs, label)
            if before is None or after is None:
                gate_results.append(
                    {
                        "gate": f"no_{label.lower()}_regression",
                        "passed": False,
                        "reason": "class missing from dataset",
                    }
                )
            else:
                gate_results.append(
                    {
                        "gate": f"no_{label.lower()}_regression",
                        "passed": after >= before,
                        "before": round(before, 4),
                        "after": round(after, 4),
                    }
                )

        checks["gates"] = gate_results
        checks["overall_passed"] = all(bool(gate["passed"]) for gate in gate_results)
        return checks
