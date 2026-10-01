"""Deterministic import of frozen local evidence. Never runs or modifies old proofs."""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from .canonical import digest
from .knowledge import (
    Evidence,
    JevKnowledgeBase,
    JevProfile,
    Observation,
    ProviderIdentity,
    save_new,
)

BASE = Path("benchmarks/jev-contract/v1")
SUMMARY = Path("build/jev-characterization/20260924T140824Z/summary.json")
LIMITS = (
    "Authored bounded benchmark; no universal Jev accuracy claim.",
    "Above 32 known choices untested; 32 is not a maximum capability.",
    "Top probability is not demonstrated calibrated correctness.",
    "Margin association does not establish a supervision threshold or causation.",
    "Long-term and model-version stability unproven; immutable model revision not reported.",
    "Complex real-world domains remain uncharacterized; no safety-critical claim.",
    "Missing reported cost is unknown, not proof of free inference.",
)
RECOMMENDATIONS = (
    "Prefer flat concrete self-contained choices within the measured bound.",
    "Explicitly propagate resolved prior decisions; avoid anaphoric references.",
    "Retain relevant raw semantic evidence alongside sensor facts.",
    "Always offer UNKNOWN; use deterministic safety, execution and postcondition checks.",
    "Use few semantic decisions around verified deterministic macros.",
    "Treat borderline known selections as provisional; calibrate margin and UNKNOWN jointly.",
    "Use hierarchy only for genuine domain decomposition, retaining leaf semantics.",
)


def ref(path: Path, pointer: str = "") -> Evidence:
    return Evidence(
        path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        pointer=pointer,
        format="text" if path.suffix == ".py" else "json",
    )


def build() -> tuple[JevKnowledgeBase, JevProfile]:
    records: list[Observation] = []

    def add(
        path: Path,
        pointer: str,
        claim: str,
        *,
        status: Literal["OBSERVED", "INFERRED", "UNKNOWN"] = "OBSERVED",
        recommendation: str | None = None,
        strength: Literal[
            "strong_within_benchmark", "limited", "hypothesis", "unestablished"
        ] = "limited",
    ) -> None:
        evidence = ref(path, pointer)
        data = json.loads(path.read_text())
        raw = path.read_text()
        # Identity appears explicitly in the artifact or its frozen protocol/code.
        supporting = next(
            (
                p
                for p in (
                    path.parent / "protocol.json",
                    path.parent.parent / "code/decision_graph_proof.py",
                    path.parent / "code/decision_graph_proof.py",
                )
                if p.exists() and "typesafe-ai/jev" in p.read_text()
            ),
            None,
        )
        known = "typesafe-ai/jev" in raw or supporting is not None
        # Code isn't JSON evidence: identity scope discloses inherited protocol below.
        date = re.search(r"20\d{6}T\d{6}Z", str(path))
        records.append(
            Observation(
                id="obs-" + digest([str(path), pointer, claim])[:20],
                claim=claim,
                status=status,
                provider="jev" if known else None,
                model="typesafe-ai/jev" if known else None,
                observed_at=data.get("started_at") or (date.group() if date else None),
                benchmark=path.parts[1],
                run=str(path.parent),
                evidence=(evidence, ref(supporting)) if supporting else (evidence,),
                observed_value=evidence.read(Path.cwd()) if status == "OBSERVED" else None,
                scope="Only this artifact/run and authored cases. Pipeline/Teacher outcomes "
                "are not isolated Jev semantic measurements. Identity may be inherited "
                "from the run's frozen protocol; null means unrecorded here.",
                limitations=LIMITS
                + (
                    ("Pilot labels were proposed, not human-verified.",)
                    if "pilot" in str(path)
                    else ()
                ),
                strength=strength,
                recommendation=recommendation,
            )
        )

    useful = {
        "status",
        "passed",
        "all_passed",
        "reason",
        "error_category",
        "failure_type",
        "macro_selected_by_jev",
        "macro_selected_at_observed_inspected_conflict",
        "postconditions_verified",
        "discovery_calls",
        "candidate_correct",
        "case_count",
        "policy_v3_created",
        "summary",
        "unknown_count",
        "jev_accepted",
        "discovery_accepted",
        "accepted_inferences",
        "rate_limited_requests",
        "budget_used_including_this_run",
        "discovery_budget",
        "jev_budget",
        "requests_issued",
        "trace_steps",
        "blocked",
    }
    roots = [
        p
        for p in Path("build").iterdir()
        if p.is_dir()
        and p.name.startswith(
            (
                "jev-pilot",
                "self-expansion",
                "automation-proof2",
                "decision-graph",
                "jev-characterization",
            )
        )
    ]
    for root in sorted(roots):
        for path in sorted(root.rglob("*.json")):
            if path.name not in {
                "report.json",
                "summary.json",
                "result.json",
                "evaluation.json",
                "final.json",
                "discovery.json",
            }:
                continue
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                continue
            if path.name == "summary.json":
                keys = set(data)
            else:
                keys = data.keys() & useful
            for key in sorted(keys):
                add(path, "/" + key, f"{path.parent.name}: recorded {key}")
            if path.name == "report.json" and "pilot" in str(path):
                for i, row in enumerate(data.get("rows", [])):
                    if "http_status" in row:
                        add(
                            path,
                            f"/rows/{i}/http_status",
                            f"Pilot {path.parent.name} row {i}: HTTP outcome",
                        )
                    if data.get("mode") == "smoke" and "result" in row:
                        add(
                            path,
                            f"/rows/{i}/result",
                            "Smoke returned a decision; no accuracy claim",
                        )
            if path.name == "discovery.json":
                for i, item in enumerate(data.get("classifications", [])):
                    if "http_status" in item:
                        add(
                            path,
                            f"/classifications/{i}/http_status",
                            f"Proof #1 attempt {path.parent.name}, observation {i}: HTTP status",
                        )
            if path.name == "evaluation.json" and "dataset" in data:
                add(path, "/dataset", "Proof #1 frozen baseline/candidate replay observations")
            if path.name == "final.json":
                for pointer, claim in [
                    ("/approval/evaluation_passed", "Proof #1 evaluation gate recorded pass"),
                    ("/restart/v1_byte_identical", "Proof #1 historical ontology preservation"),
                    (
                        "/restart/replay_persisted/result/selected_class",
                        "Proof #1 persisted post-approval replay selected tablet",
                    ),
                ]:
                    add(path, pointer, claim)
            if path.name == "result.json":
                for key in ("results", "runs", "flat", "hierarchical", "v1", "v2", "regressions"):
                    if key in data:
                        add(path, "/" + key, f"{path.parent.name}: recorded {key} outcomes")

    curated = {
        "B_accuracy_by_size": "Flat known-choice suites from 2 through 32 recorded accuracy 1.0",
        "C_accuracy_by_similarity": (
            "Near-synonym/overlapping authored choice suites performed well"
        ),
        "D_accuracy_by_style": "Tested choice representations performed well",
        "E_accuracy_by_style": "Raw, structured and evidence-bearing states performed well",
        "F_paraphrase_disagreement_rate": "No paraphrase disagreement measured in this suite",
        "G_order_stable_rate": "Choice ordering did not change tested selections",
        "H_selections_by_grade": "Borderline ambiguity included false-known selections",
        "I_repeat_groups": "Repeated characterization decisions were stable in the short run",
        "J_flat_accuracy": "Flat routing accuracy in matched characterization suite",
        "J_hierarchy_path_accuracy": "Abstract 4-to-4 hierarchy had lower observed path accuracy",
        "K_path_success_by_depth": "Deeper anaphoric chains degraded; depth and wording confounded",
        "L_positive_wording_accuracy": "Port-conflict wording variants recognized without aliases",
        "M_accuracy_by_noise": "Authored heavy distractors did not degrade measured accuracy",
        "N_both_steps_correct_rate": "Re-observation two-step path outcomes were imperfect",
        "margin_when_correct_mean": "Mean margin for correct decisions within characterization",
        "margin_when_wrong_mean": "Mean margin for incorrect decisions within characterization",
        "overall_accuracy": (
            "167 of 174 accepted cases correct; 176 planned; two infrastructure failures"
        ),
    }
    for key, claim in curated.items():
        add(SUMMARY, "/" + key, claim, strength="strong_within_benchmark")
    for recommendation in RECOMMENDATIONS:
        add(
            SUMMARY,
            "",
            "Architectural recommendation: " + recommendation,
            status="INFERRED",
            strength="hypothesis",
            recommendation=recommendation,
        )
    for limit in LIMITS:
        add(SUMMARY, "", limit, status="UNKNOWN", strength="unestablished")
    kb = JevKnowledgeBase(
        id="jev-empirical-knowledge",
        version=1,
        imported_at="2026-09-25",
        observations=tuple(records),
    )
    profile = JevProfile(
        id="jev-operating-profile",
        version=1,
        identity=ProviderIdentity(
            provider="jev",
            model="typesafe-ai/jev",
            model_revision=None,
            api_behavior="systemone-v1-via-vercel-typesafe",
            distribution_schema="core-choice-result-v1",
            major_version="1",
        ),
        measured_at="2026-09-24",
        knowledge_base_hash=digest(kb.model_dump(mode="json")),
        observation_ids=tuple(r.id for r in records),
        limitations=LIMITS,
        max_tested_flat_choices=max(
            int(n) for n in json.loads(SUMMARY.read_text())["B_accuracy_by_size"]
        ),
        count_convention="known_choices_excluding_unknown",
        recommendations=RECOMMENDATIONS,
    )
    return kb, profile


def render(kb: JevKnowledgeBase, profile: JevProfile) -> str:
    lines = [
        "# Jev empirical operating profile",
        "",
        "Generated by `python -m scripts.jev_contract.import_evidence`; research only.",
        "",
        profile.manual(),
        "",
        "## Provenance and qualifications",
        "",
        f"Registry: `{BASE}/knowledge.json` ({len(kb.observations)} records). Each OBSERVED "
        "value is verified against a hash and JSON pointer; recommendations are INFERRED.",
        "",
        "Early pilot labels were agent-authored and awaiting review. Proof #2 Run 3 "
        "transferred macro selection and verified its postconditions but ended premature_done; "
        "it is not a fully successful transferred workflow. Teacher failures in D/E are "
        "not Jev failures. UNKNOWN alone does not establish a missing choice.",
        "",
        "The old report's 95.98% denominator is 174 accepted cases, not 176 planned. "
        "Margin means show association, not superiority over a probability baseline; "
        "the new independent calibration experiment must test that comparison.",
        "",
        "## Selected measured observations",
        "",
    ]
    for r in kb.observations:
        if r.strength == "strong_within_benchmark":
            e = r.evidence[0]
            lines += [
                f"- **{r.claim}**: `{json.dumps(r.observed_value, sort_keys=True)}`. "
                f"Evidence `{e.path}{e.pointer}`, SHA-256 `{e.sha256}`."
            ]
    lines += [
        "",
        "## Current gates",
        "",
        "No calibrated execution threshold. Default: escalate. "
        "No new live calls made by this consolidation. Calibration and Teacher comparison "
        "are prepared, unrun. F/G remain blocked pending review of steps 1–7.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    kb, profile = build()
    kb.verify(Path.cwd())
    save_new(BASE / "knowledge.json", kb.model_dump(mode="json"))
    save_new(BASE / "profile.json", profile.model_dump(mode="json"))
    with Path("docs/research/jev-operating-profile.md").open("x") as stream:
        stream.write(render(kb, profile))
    print(f"Imported {len(kb.observations)} provenance-checked observations")


if __name__ == "__main__":
    main()
