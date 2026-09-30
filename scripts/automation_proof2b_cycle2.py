"""Proof #2B cycle 2: one failure-informed re-proposal from the rejected cycle-1 candidate.

Cycle 1 (build/automation-proof2b/20260924T123534Z) returned a valid GENERALIZE_TRIGGER
that deterministic evaluation rejected: a literal phrase substitution which regressed
cases the approved baseline covered while still missing held-out wordings. This final
round adds that rejected candidate and its aggregate verdict to the evidence. Individual
evaluation cases remain undisclosed, the acceptance rule is unchanged, and the result is
still an inactive candidate: no repair loop, no third round, no policy activation.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from automation_proof2b import (
    FREEZE,
    SOURCE,
    build_evidence,
    discover,
    evaluate,
    fixtures,
    payload_for,
    save,
    sha,
    verify_frozen,
)

PRIOR = Path("build/automation-proof2b/20260924T123534Z")


def load_prior(prior: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    protocol = json.loads((prior / "protocol.json").read_text())
    candidate = json.loads((prior / "candidate.json").read_text())
    evaluation = json.loads((prior / "evaluation.json").read_text())
    if candidate["id"] != evaluation["candidate_id"]:
        raise ValueError("prior candidate and evaluation disagree")
    if evaluation["status"] != "failed":
        raise ValueError("cycle 2 continues only from a rejected proposal")
    if candidate["approved"] or candidate["status"] != "candidate":
        raise ValueError("prior candidate must be inactive")
    return protocol, candidate, evaluation


def verify_chain(protocol: dict[str, Any]) -> None:
    """Reused code must be byte-identical to what the prior round actually ran."""
    for name, expected in protocol["implementation_sha256"].items():
        if sha((Path(__file__).parent / name).read_bytes()) != expected:
            raise ValueError(f"reused implementation changed since the prior round: {name}")


def disclosed_verdict(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Aggregate verdict only: never case identities, labels or fixture contents."""
    return {
        "status": evaluation["status"],
        "case_count": len(evaluation["cases"]),
        "candidate_correct": evaluation["candidate_correct"],
        "baseline_correct": evaluation["baseline_correct"],
        "regression_count": len(evaluation["regressions"]),
        "cases_disclosed": False,
    }


def failure_informed(
    base_evidence: dict[str, Any],
    prior_candidate: dict[str, Any],
    prior_verdict: dict[str, Any],
) -> dict[str, Any]:
    evidence = dict(base_evidence)
    evidence["question"] = evidence["question"] + (
        " A later proposal was already produced, deterministically evaluated and rejected: "
        "it did not outperform the approved baseline and it regressed on cases the baseline "
        "covered. That rejected proposal and its aggregate verdict are included below; "
        "individual evaluation cases are not disclosed. This is the final applicability "
        "assessment for this policy."
    )
    evidence["prior_attempt"] = {
        "candidate_id": prior_candidate["id"],
        "proposal": prior_candidate["proposal"],
        "verdict": prior_verdict,
    }
    return evidence


def run(root_base: Path) -> int:
    verify_frozen()
    prior_protocol, prior_candidate, prior_evaluation = load_prior(PRIOR)
    verify_chain(prior_protocol)
    key = os.environ["AI_GATEWAY_API_KEY"]
    model = os.getenv("OPENCLASS_DISCOVERY_MODEL", "google/gemini-2.5-flash")
    policy = json.loads((SOURCE / "policy-v2.json").read_text())
    if prior_candidate["base_policy_id"] != policy["id"]:
        raise ValueError("prior candidate targets a different base policy")
    reports = [json.loads((SOURCE / f"run-{n}/report.json").read_text()) for n in (2, 3)]
    evidence = failure_informed(
        build_evidence(policy, reports),
        prior_candidate,
        disclosed_verdict(prior_evaluation),
    )
    cases = fixtures(reports)
    root = root_base / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True)
    save(root / "evaluation-fixtures.json", cases)
    save(root / "evidence.json", evidence)
    payload = payload_for(evidence, model)
    save(root / "request.json", payload)
    save(
        root / "protocol.json",
        {
            "experiment": "Proof #2B - Applicability Evolution, cycle 2 (final round)",
            "cycle": 2,
            "base_policy_id": policy["id"],
            "base_policy_sha256": sha((SOURCE / "policy-v2.json").read_bytes()),
            "frozen_source_manifest_sha256": sha(FREEZE.read_bytes()),
            "prior_root": str(PRIOR),
            "prior_artifacts_sha256": {
                name: sha((PRIOR / name).read_bytes())
                for name in ("protocol.json", "candidate.json", "evaluation.json", "report.json")
            },
            "prior_implementation_chain_verified": True,
            "prior_verdict_disclosure_fields": [
                "status",
                "case_count",
                "candidate_correct",
                "baseline_correct",
                "regression_count",
            ],
            "fixtures_sha256": sha((root / "evaluation-fixtures.json").read_bytes()),
            "request_sha256": sha((root / "request.json").read_bytes()),
            "discovery_sees_evaluation_cases": False,
            "acceptance": "all cases correct; no regressions",
            "implementation_sha256": {
                name: sha(Path(__file__).with_name(name).read_bytes())
                for name in (
                    "automation_proof2b_cycle2.py",
                    "automation_proof2b.py",
                    "automation_applicability.py",
                )
            },
            "no_live_runs_2_or_3": True,
            "no_third_round": True,
            "no_policy_activation": True,
        },
    )
    try:
        proposal, attempts = asyncio.run(discover(payload, key, root))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        failure_report: dict[str, Any] = {
            "status": "infrastructure_failed"
            if isinstance(exc, httpx.HTTPError)
            else "discovery_unusable",
            "error_type": type(exc).__name__,
            "root": str(root),
        }
        save(root / "report.json", failure_report)
        print(json.dumps(failure_report))
        verify_frozen()
        return 2
    procedure = policy["candidate"]["procedure"]
    candidate = {
        "id": str(uuid4()),
        "cycle": 2,
        "prior_candidate_id": prior_candidate["id"],
        "base_policy_id": policy["id"],
        "status": "candidate",
        "approved": False,
        "procedure_sha256": sha(json.dumps(procedure, sort_keys=True).encode()),
        "provider": "openai-compatible",
        "model": model,
        "proposal": proposal.model_dump(mode="json"),
    }
    save(root / "candidate.json", candidate)
    evaluation = evaluate(proposal, cases)
    save(root / "evaluation.json", {"candidate_id": candidate["id"], **evaluation})
    save(
        root / "events.json",
        [
            {
                "type": "applicability.candidate_created",
                "cycle": 2,
                "candidate_id": candidate["id"],
                "prior_candidate_id": prior_candidate["id"],
                "base_policy_id": policy["id"],
            },
            {
                "type": "applicability.evaluation_completed",
                "cycle": 2,
                "candidate_id": candidate["id"],
                "status": evaluation["status"],
            },
        ],
    )
    report: dict[str, Any] = {
        "experiment": "Proof #2B - Applicability Evolution, cycle 2",
        "root": str(root),
        "cycle": 2,
        "prior_candidate_id": prior_candidate["id"],
        "candidate_id": candidate["id"],
        "base_policy_id": policy["id"],
        "status": evaluation["status"],
        "proposal_type": proposal.proposal_type,
        "candidate_correct": evaluation.get("candidate_correct"),
        "case_count": len(cases),
        "approval_required": evaluation["status"] == "passed",
        "policy_v3_created": False,
        "provider_attempts": attempts,
    }
    verify_frozen()
    save(root / "report.json", report)
    print(json.dumps(report, indent=2))
    return 0 if evaluation["status"] == "passed" else 1


def main() -> int:
    return run(Path("build/automation-proof2b-cycle2"))


if __name__ == "__main__":
    raise SystemExit(main())
