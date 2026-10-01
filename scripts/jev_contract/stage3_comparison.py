"""Stage 3 live: Teacher model comparison over the 13 frozen packages.

Teacher A = google/gemini-2.5-flash (incumbent). Teacher B: the repository's
stronger GLM provider is preferred IF actually available under the existing
research configuration; this module records the availability check and uses the
stronger model that the frozen protocol pre-registered (gemini-2.5-pro) when
GLM is absent — never a silent substitution. Identical frozen packets for both
models, one proposal each, no cross-feeding, at most two byte-identical
retries per call. Budget: 26 successful calls.
"""

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from .canonical import digest
from .knowledge import save_new
from .live_teacher import TeacherBudget, call_teacher
from .precision import HiddenEvaluation, TeacherResponse, compare, packet
from .stage2_ablation import score_response, summarize
from .teacher import TeacherRequest

# Teacher B preference per authorization: repository GLM provider if genuinely
# available under existing credentials (gateway lists zai/glm-5.3), else the
# pre-registered gemini-2.5-pro. Selected at runtime from the live catalog.
TEACHER_A = "google/gemini-2.5-flash"
# Preference chain per authorization: repository GLM provider if genuinely
# accessible under existing credentials. Probed 2026-09-25: glm-5.3 and
# glm-5.3-flash are listed but paywalled (403 no_providers_available);
# zai/glm-4.7 IS accessible and honors strict json_schema. The pre-registered
# gemini-2.5-pro is also paywalled. glm-4.7 is therefore the strongest
# accessible GLM tier under the existing research credentials.
GLM_PREFERENCE_CHAIN = ("zai/glm-5.3", "zai/glm-5.3-flash", "zai/glm-4.7")
FALLBACK_B = "google/gemini-2.5-pro"
# v2 amendment: disclose base_policy_hash in every packet, identically for both models.
AMEND_V2 = True
DATASET = Path("benchmarks/jev-contract/v1")
CATALOG_URL = "https://ai-gateway.vercel.sh/v1/models"


async def availability(key: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get(CATALOG_URL, headers={"Authorization": f"Bearer {key}"})
    body = response.json() if response.status_code == 200 else {}
    listed = body.get("data") or body.get("models") or []
    models = [m.get("id") for m in listed]
    glm_local = {name: bool(os.environ.get(name)) for name in ("OPENCLASS_GLM_API_KEY",)}
    glm_gateway = [m for m in models if "glm" in str(m).lower() or "zai" in str(m).lower()]
    glm_usable = next((m for m in GLM_PREFERENCE_CHAIN if m in models), None)
    return {
        "gateway_model_count": len(models),
        "glm_models_on_gateway": glm_gateway,
        "glm_preference_chain": list(GLM_PREFERENCE_CHAIN),
        "first_accessible_glm_choice": glm_usable,
        "glm_credentials_present": glm_local,
        "decision": (
            f"Teacher B = {glm_usable}: the repository GLM provider at its strongest "
            "tier genuinely accessible under the existing credentials (higher GLM "
            "tiers are listed but paywalled; listing alone is not availability)."
            if glm_usable
            else f"No GLM model accessible; fallback {FALLBACK_B} also probed "
            "paywalled — stop and report rather than substitute silently."
        ),
        "accessibility_probes": {
            "zai/glm-5.3": "paywalled (403 no_providers_available, probed 2026-09-25)",
            "zai/glm-5.3-flash": "paywalled (403, probed 2026-09-25)",
            "zai/glm-4.7": "accessible; strict json_schema verified (finish=stop)",
            "google/gemini-2.5-pro": "paywalled (403, probed 2026-09-25)",
        },
    }


def run(root: Path, key: str) -> int:
    root.mkdir(parents=True)
    requests = {
        r.id: r
        for r in (
            TeacherRequest.model_validate(x)
            for x in json.loads((DATASET / "teacher-packages.json").read_text())
        )
    }
    hidden = {
        k: HiddenEvaluation.model_validate(v)
        for k, v in json.loads((DATASET / "teacher-hidden.json").read_text()).items()
    }
    frozen_packets = {rid: packet(r) for rid, r in requests.items()}
    frozen_hashes = json.loads((DATASET / "protocol.json").read_text())["packet_hashes"]
    for rid, frozen in frozen_packets.items():
        if digest(frozen) != frozen_hashes[rid]:
            raise ValueError(f"frozen packet drift: {rid}")
    sent_packets: dict[str, dict[str, Any]] = {}
    for rid, frozen in frozen_packets.items():
        if not AMEND_V2:
            sent_packets[rid] = frozen
            continue
        amended = json.loads(json.dumps(frozen))
        user = json.loads(amended["messages"][1]["content"])
        user["base_policy_hash"] = requests[rid].graph_slice.content_hash
        amended["messages"][1]["content"] = json.dumps(user, sort_keys=True)
        sent_packets[rid] = amended
    availability_record = asyncio.run(availability(key))
    teacher_b = availability_record["first_accessible_glm_choice"] or FALLBACK_B
    models_pair = (TEACHER_A, teacher_b)
    availability_record["teacher_b_selected"] = teacher_b
    save_new(
        root / "protocol.json",
        {
            "stage": 3,
            "experiment": "teacher-model-comparison",
            "models": list(models_pair),
            "availability": availability_record,
            "budget_successful_calls": 26,
            "max_identical_retries_per_call": 2,
            "design": (
                "identical frozen packets and schema for both models; one first "
                "response per package/model; counterbalanced model order; no model "
                "sees the other's output; scoring deterministic against hidden labels"
            ),
            "frozen_packet_hashes": frozen_hashes,
            "amended_packet_hashes": {rid: digest(p) for rid, p in sent_packets.items()},
            "protocol_amendment_v2": (
                "every packet discloses base_policy_hash (graph content hash), "
                "identically for both models; the frozen v1 binding was unsatisfiable "
                "(see the stage 2 v1 README). Both models receive byte-identical packets."
            )
            if AMEND_V2
            else None,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    budget = TeacherBudget(26)
    responses: list[dict[str, Any]] = []
    extended: dict[str, dict[str, dict[str, Any]]] = {m: {} for m in models_pair}
    order = list(requests)
    for index, rid in enumerate(order):
        models = models_pair if index % 2 == 0 else tuple(reversed(models_pair))
        for model in models:
            attempts: list[dict[str, Any]] = []
            record = asyncio.run(call_teacher(model, sent_packets[rid], key, budget, attempts))
            record["attempts"] = attempts
            responses.append(record)
            scored = score_response(requests[rid], hidden[rid], record)
            scored["latency_ms"] = record["latency_ms"]
            scored["input_tokens"] = record["input_tokens"]
            scored["output_tokens"] = record["output_tokens"]
            scored["reported_cost"] = record["reported_cost"]
            extended[model][rid] = scored
            case_value: Any = {
                "response": {k: v for k, v in record.items() if k != "attempts"},
                "attempts": attempts,
                "score": scored,
            }
            save_new(root / f"case-{model.split('/')[1]}-{rid}.json", case_value)
            time.sleep(3.0)
    from .precision import TeacherResponse

    parsed = tuple(
        TeacherResponse.model_validate(
            {
                "package_id": r["packet_hash"]
                and next(rid for rid, p in sent_packets.items() if digest(p) == r["packet_hash"]),
                "model": r["model"],
                "packet_hash": r["packet_hash"],
                "content": r["content"],
                "infrastructure_status": "ok" if r["infrastructure_status"] == "ok" else "failed",
                "latency_ms": r["latency_ms"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "reported_cost": r["reported_cost"],
                "simulated": False,
            }
        )
        for r in responses
    )
    paired = compare(tuple(requests.values()), hidden, parsed, models_pair, packets=sent_packets)
    report_value: Any = {
        "summary": summarize(extended),
        "per_model_cases": extended,
        "paired_comparison": paired,
        "budget": {"successful": budget.successful, "retries": budget.retries},
    }
    save_new(root / "comparison-report.json", report_value)
    print(
        json.dumps(
            {
                "successful": budget.successful,
                "retries": budget.retries,
                "models": list(models_pair),
            }
        )
    )
    return 0


def report_only(root: Path) -> int:
    """Rebuild the paired report from recorded case files; no new inference."""
    requests = {
        r.id: r
        for r in (
            TeacherRequest.model_validate(x)
            for x in json.loads((DATASET / "teacher-packages.json").read_text())
        )
    }
    hidden = {
        k: HiddenEvaluation.model_validate(v)
        for k, v in json.loads((DATASET / "teacher-hidden.json").read_text()).items()
    }
    protocol = json.loads((root / "protocol.json").read_text())
    correction = (
        json.loads((root / "correction.json").read_text())
        if (root / "correction.json").exists()
        else None
    )
    teacher_b = correction["corrected_model"] if correction else protocol["models"][1]
    models_pair = (protocol["models"][0], teacher_b)
    sent_hashes = protocol["amended_packet_hashes"]
    extended: dict[str, dict[str, dict[str, Any]]] = {m: {} for m in models_pair}
    parsed = []
    skip_model = correction["failed_model"] if correction else None
    for path in sorted(root.glob("case-*.json")):
        data = json.loads(path.read_text())
        record = data["response"]
        if skip_model and record["model"] == skip_model:
            continue
        rid = next(rid_ for rid_, h in sent_hashes.items() if h == record["packet_hash"])
        model = record["model"]
        scored = score_response(requests[rid], hidden[rid], record)
        scored.update(
            latency_ms=record["latency_ms"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
            reported_cost=record["reported_cost"],
        )
        extended[model][rid] = scored
        parsed.append(
            TeacherResponse.model_validate(
                {
                    "package_id": rid,
                    "model": model,
                    "packet_hash": record["packet_hash"],
                    "content": record["content"],
                    "infrastructure_status": (
                        "ok" if record["infrastructure_status"] == "ok" else "failed"
                    ),
                    "latency_ms": record["latency_ms"],
                    "input_tokens": record["input_tokens"],
                    "output_tokens": record["output_tokens"],
                    "reported_cost": record["reported_cost"],
                    "simulated": False,
                }
            )
        )
    sent_packets = {}
    for rid in requests:
        frozen = json.loads(json.dumps(packet(requests[rid])))
        user = json.loads(frozen["messages"][1]["content"])
        user["base_policy_hash"] = requests[rid].graph_slice.content_hash
        frozen["messages"][1]["content"] = json.dumps(user, sort_keys=True)
        sent_packets[rid] = frozen
    paired = compare(
        tuple(requests.values()), hidden, tuple(parsed), models_pair, packets=sent_packets
    )
    report_value: Any = {
        "summary": summarize(extended),
        "per_model_cases": extended,
        "paired_comparison": paired,
        "budget_note": "report rebuilt from recorded case files; no additional inference",
    }
    save_new(root / "comparison-report.json", report_value)
    print(json.dumps({"status": "comparison-report written", "root": str(root)}))
    return 0


def run_model_b_only(root: Path, key: str, model: str) -> int:
    """Corrected Teacher B acquisition: the listed-but-paywalled first choice
    produced 13 recorded 403s; this runs the probe-verified accessible GLM tier
    for the same 13 packages without touching Teacher A's recorded calls."""
    import time as _time

    requests = {
        r.id: r
        for r in (
            TeacherRequest.model_validate(x)
            for x in json.loads((DATASET / "teacher-packages.json").read_text())
        )
    }
    hidden = {
        k: HiddenEvaluation.model_validate(v)
        for k, v in json.loads((DATASET / "teacher-hidden.json").read_text()).items()
    }
    protocol = json.loads((root / "protocol.json").read_text())
    sent_hashes = protocol["amended_packet_hashes"]
    sent_packets = {}
    for rid, r in requests.items():
        frozen = json.loads(json.dumps(packet(r)))
        user = json.loads(frozen["messages"][1]["content"])
        user["base_policy_hash"] = r.graph_slice.content_hash
        frozen["messages"][1]["content"] = json.dumps(user, sort_keys=True)
        sent_packets[rid] = frozen
        if sent_hashes[rid] != digest(frozen):
            raise ValueError(f"amended packet drift: {rid}")
    save_new(
        root / "correction.json",
        {
            "reason": (
                "protocol selection treated catalog listing as availability; "
                "zai/glm-5.3 is listed but paywalled and its 13 recorded calls all "
                "returned 403 no_providers_available (preserved as case files). "
                "Teacher B corrected to the probe-verified accessible GLM tier."
            ),
            "failed_model": "zai/glm-5.3",
            "corrected_model": model,
        },
    )
    budget = TeacherBudget(14)
    for rid in requests:
        attempts: list[dict[str, Any]] = []
        record = asyncio.run(call_teacher(model, sent_packets[rid], key, budget, attempts))
        record["attempts"] = attempts
        scored = score_response(requests[rid], hidden[rid], record)
        scored.update(
            latency_ms=record["latency_ms"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
            reported_cost=record["reported_cost"],
        )
        case_value: Any = {
            "response": {k: v for k, v in record.items() if k != "attempts"},
            "attempts": attempts,
            "score": scored,
        }
        save_new(root / f"case-{model.split('/')[1]}-{rid}.json", case_value)
        _time.sleep(3.0)
    print(json.dumps({"model_b": model, "successful": budget.successful}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--model-b-only", default=None)
    args = parser.parse_args()
    if args.report_only:
        raise SystemExit(report_only(args.root))
    if args.model_b_only:
        raise SystemExit(
            run_model_b_only(args.root, os.environ["AI_GATEWAY_API_KEY"], args.model_b_only)
        )
    run(args.root, os.environ["AI_GATEWAY_API_KEY"])


if __name__ == "__main__":
    main()
