"""Independent calibration/held-out evaluation. No characterization rows or live calls."""

import argparse
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .canonical import DecisionNode, Frozen, StateSnapshot, digest
from .jev import UNKNOWN, DecisionTelemetry
from .knowledge import save_new


class CalibrationCase(Frozen):
    id: str
    family: str
    split: Literal["calibration", "validation"]
    stratum: Literal[
        "clear_known",
        "near_known",
        "genuine_unknown",
        "ambiguous_overlap",
        "dangerous_false_known",
        "close_top_two",
    ]
    node: DecisionNode
    snapshot: StateSnapshot


class CalibrationDataset(Frozen):
    id: str
    label_provenance: str
    cases: tuple[CalibrationCase, ...]
    labels: dict[str, str]

    @model_validator(mode="after")
    def disjoint(self) -> "CalibrationDataset":
        ids = [c.id for c in self.cases]
        if len(set(ids)) != len(ids) or set(ids) != set(self.labels):
            raise ValueError("duplicate cases or mismatched labels")
        families = {
            s: {c.family for c in self.cases if c.split == s} for s in ("calibration", "validation")
        }
        if not all(families.values()) or families["calibration"] & families["validation"]:
            raise ValueError("split families must be nonempty and disjoint")
        for case in self.cases:
            if self.labels[case.id] not in {UNKNOWN, *[c.id for c in case.node.choices]}:
                raise ValueError("label outside decision space")
        return self


class Rule(Frozen):
    family: Literal["probability_only", "margin_unknown"]
    min_top: float = Field(ge=0, le=1, allow_inf_nan=False)
    min_margin: float = Field(ge=0, le=1, allow_inf_nan=False)
    max_unknown: float = Field(ge=0, le=1, allow_inf_nan=False)

    def accepts(self, record: DecisionTelemetry) -> bool:
        if record.infrastructure_status != "ok" or record.selected_choice == UNKNOWN:
            return False
        assert record.top_probability is not None
        assert record.margin is not None and record.unknown_probability is not None
        return (
            record.top_probability >= self.min_top
            if self.family == "probability_only"
            else record.margin >= self.min_margin and record.unknown_probability <= self.max_unknown
        )


def grid() -> tuple[Rule, ...]:
    values = [i / 10 for i in range(11)]
    return tuple(
        [Rule(family="probability_only", min_top=p, min_margin=0, max_unknown=1) for p in values]
        + [
            Rule(family="margin_unknown", min_top=0, min_margin=m, max_unknown=u)
            for m in values
            for u in values
        ]
    )


def wilson(errors: int, total: int) -> list[float] | None:
    if not total:
        return None
    p, z = errors / total, 1.96
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0, center - half), min(1, center + half)]


def score(
    rule: Rule,
    cases: tuple[CalibrationCase, ...],
    labels: dict[str, str],
    results: dict[str, DecisionTelemetry],
) -> dict[str, Any]:
    accepted = [c for c in cases if rule.accepts(results[c.id])]
    ok = [c for c in cases if results[c.id].infrastructure_status == "ok"]
    errors = [c for c in accepted if results[c.id].selected_choice != labels[c.id]]
    false_known = [c for c in errors if labels[c.id] == UNKNOWN]
    known = [c for c in ok if labels[c.id] != UNKNOWN]
    return {
        "rule": rule.model_dump(),
        "attempted": len(cases),
        "semantic_responses": len(ok),
        "infrastructure_failures": len(cases) - len(ok),
        "continued": len(accepted),
        "coverage": len(accepted) / len(ok) if ok else None,
        "coverage_all_attempted": len(accepted) / len(cases) if cases else None,
        "selective_errors": len(errors),
        "false_known": len(false_known),
        "selective_error_rate": len(errors) / len(accepted) if accepted else None,
        "error_interval_95_wilson": wilson(len(errors), len(accepted)),
        "correct_known_coverage": (len(accepted) - len(errors)) / len(known) if known else None,
        "dangerous_false_known": sum(c.stratum == "dangerous_false_known" for c in false_known),
    }


def select_on_calibration(curve: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    # Predeclared research objective, NOT a production safety threshold.
    eligible = [
        r
        for r in curve
        if r["rule"]["family"] == family
        and r["semantic_responses"] >= 12
        and (r["correct_known_coverage"] or 0) >= 0.5
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda r: (
            r["false_known"],
            r["selective_errors"],
            -r["continued"],
            json.dumps(r["rule"], sort_keys=True),
        ),
    )


def evaluate(dataset: CalibrationDataset, results: dict[str, DecisionTelemetry]) -> dict[str, Any]:
    if set(results) != {c.id for c in dataset.cases}:
        raise ValueError("one result including failures required for every frozen case")
    profile_hashes = {r.profile_hash for r in results.values()}
    if len(profile_hashes) != 1 or any(r.simulated for r in results.values()):
        raise ValueError("empirical calibration requires one profile and nonsimulated records")
    for case in dataset.cases:
        record = results[case.id]
        if record.node_id != case.node.id or record.state_snapshot_id != case.snapshot.id:
            raise ValueError("result does not belong to the frozen case")
        if record.choice_set_hash != digest([c.model_dump(mode="json") for c in case.node.choices]):
            raise ValueError("result uses a different choice set")
    train = tuple(c for c in dataset.cases if c.split == "calibration")
    holdout = tuple(c for c in dataset.cases if c.split == "validation")
    curve = [score(r, train, dataset.labels, results) for r in grid()]
    selected = {f: select_on_calibration(curve, f) for f in ("probability_only", "margin_unknown")}
    # Holdout is read only after candidate selection. Never reselect on this report.
    validation = {
        f: score(Rule(**r["rule"]), holdout, dataset.labels, results) if r else None
        for f, r in selected.items()
    }
    return {
        "dataset_hash": digest(dataset.model_dump(mode="json")),
        "profile_hash": next(iter(profile_hashes)),
        "calibration_curve": curve,
        "selected_on_calibration": selected,
        "held_out_validation": validation,
        "validation_curve_descriptive_only": [
            score(r, holdout, dataset.labels, results) for r in grid()
        ],
        "activation_authorized": False,
        "status": "research_comparison_only",
        "limitations": "Authored small sample; labels unreviewed; no safety-critical claim. "
        "Held-out results cannot authorize execution or retrospective tuning.",
    }


def load_dataset(root: Path) -> CalibrationDataset:
    public = json.loads((root / "calibration-cases.json").read_text())
    return CalibrationDataset(
        **public, labels=json.loads((root / "calibration-labels.json").read_text())
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/jev-contract/v1"))
    args = parser.parse_args()
    results = {
        k: DecisionTelemetry.model_validate(v)
        for k, v in json.loads(args.results.read_text()).items()
    }
    save_new(args.output, evaluate(load_dataset(args.dataset), results))


if __name__ == "__main__":
    main()
