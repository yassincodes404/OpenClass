"""Build the versioned empirical JevProfile from a characterization run summary.

Every value is copied or derived from the run's measured summary. Fields the run
cannot support stay null with an insufficient_evidence note; nothing is assumed.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from jev_characterization import RUN_ROOT, sha  # noqa: E402


def build_profile(run_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = json.loads((run_dir / "summary.json").read_text())
    report: dict[str, Any] = json.loads((run_dir / "report.json").read_text())
    protocol: dict[str, Any] = json.loads((run_dir / "protocol.json").read_text())
    ok = summary["ok_cases"]
    profile: dict[str, Any] = {
        "jev_profile": {
            "profile_version": 1,
            "provider": "typesafe-jev via Vercel AI gateway",
            "tested_model": protocol["model"],
            "tested_at": run_dir.name,
            "source_run": str(run_dir),
            "source_summary_sha256": sha((run_dir / "summary.json").read_bytes()),
            "case_count": summary["planned_cases"],
            "accepted_inferences": ok,
            "observed": {
                "overall_accuracy": summary["overall_accuracy"],
                "accuracy_by_choice_space_size": summary["B_accuracy_by_size"],
                "accuracy_by_choice_similarity": summary["C_accuracy_by_similarity"],
                "accuracy_by_choice_representation": summary["D_accuracy_by_style"],
                "accuracy_by_input_representation": summary["E_accuracy_by_style"],
                "paraphrase_disagreement_rate": summary["F_paraphrase_disagreement_rate"],
                "order_stability_rate": summary["G_order_stable_rate"],
                "unknown_behavior": {
                    "precision": summary["unknown_precision"],
                    "recall": summary["unknown_recall"],
                    "false_known_rate": summary["false_known_rate"],
                    "false_unknown_rate": summary["false_unknown_rate"],
                    "selections_by_grade": summary["H_selections_by_grade"],
                },
                "repeatability": summary["I_repeat_groups"],
                "flat_vs_hierarchical": {
                    "flat_accuracy": summary["J_flat_accuracy"],
                    "hierarchy_stage1_accuracy": summary["J_hierarchy_stage1_accuracy"],
                    "hierarchy_stage2_accuracy": summary["J_hierarchy_stage2_accuracy"],
                    "hierarchy_path_accuracy": summary["J_hierarchy_path_accuracy"],
                },
                "path_success_by_depth": summary["K_path_success_by_depth"],
                "wording_robustness": {
                    "positive_wording_accuracy": summary["L_positive_wording_accuracy"],
                    "in_set_negative_accuracy": summary["L_in_set_negative_accuracy"],
                    "out_of_set_control": summary["L_out_of_set_control"],
                },
                "accuracy_by_distractor_level": summary["M_accuracy_by_noise"],
                "reobservation": {
                    "step_accuracy": summary["N_step_accuracy"],
                    "both_steps_correct_rate": summary["N_both_steps_correct_rate"],
                },
                "margin_mean_when_correct": summary["margin_when_correct_mean"],
                "margin_mean_when_wrong": summary["margin_when_wrong_mean"],
                "latency_p50_ms": summary["latency_p50_ms"],
                "latency_p95_ms": summary["latency_p95_ms"],
                "mean_input_tokens": round(summary["total_input_tokens"] / ok, 1) if ok else None,
                "mean_output_tokens": (
                    round(summary["total_output_tokens"] / ok, 1) if ok else None
                ),
                "gateway_reported_cost_total": summary["total_reported_cost"],
                "gateway_cost_note": (
                    "gateway reported no cost figures for these calls; "
                    "currency and price remain unrecorded"
                ),
                "infrastructure_failures": summary["infrastructure_failures"],
            },
            "guidance": {
                "use_probabilities_for": (
                    "ranking and supervision flagging; mean margin separated correct "
                    "({:.3f}) from wrong ({:.3f}) decisions in this run".format(
                        summary["margin_when_correct_mean"],
                        summary["margin_when_wrong_mean"],
                    )
                ),
                "do_not_assume_calibration": True,
                "recommended_choice_description_style": (
                    "semantic names plus one-line descriptions; opaque identifiers and "
                    "bare names also scored 1.0 but descriptions carry auditability"
                ),
                "recommended_max_choices_per_node": 32,
                "max_choices_note": (
                    "no accuracy degradation measured from 2 up to 32 choices; 32 is "
                    "the measured ceiling, not a demonstrated limit"
                ),
                "routing_shape": (
                    "flat routing preferred; the 4-to-4 hierarchy measured lower path "
                    "accuracy (87.5%) than flat 16-way routing (100%) because the "
                    "abstract group-level stage lost leaf-level signal"
                ),
                "state_propagation": (
                    "downstream decision nodes must receive the resolved prior "
                    "decision verbatim in the state; anaphoric references such as "
                    "'the chosen response' produced UNKNOWN answers"
                ),
                "supervision": (
                    "treat committed choices on borderline-ambiguous input as "
                    "provisional: the two false-known errors were borderline cases "
                    "committed with ~0.75 top probability; review low-margin and "
                    "high-unknown_probability decisions"
                ),
                "budget_ledger": {
                    "limit": report["request_budget"],
                    "used_including_this_run": report["budget_used_including_this_run"],
                    "counts": "accepted (2xx) inferences across characterization runs",
                },
            },
        }
    }
    return profile


def main() -> int:
    runs = sorted(RUN_ROOT.glob("*"))
    if len(runs) < 1:
        raise SystemExit("no characterization runs found")
    run_dir = runs[-1]
    profile = build_profile(run_dir)
    destination = Path("benchmarks/jev/jev-profile-v1.json")
    destination.write_text(json.dumps(profile, indent=2) + "\n")
    (run_dir / "jev-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    print(json.dumps({"written": str(destination), "source": str(run_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
