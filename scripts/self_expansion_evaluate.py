"""Evaluate the persisted tablet candidate without changing the active ontology."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from openclass_core.models import ChoiceRequest, Observation, OntologyClass, OntologyVersion
from openclass_core.novelty import assess, signals_from
from openclass_core.providers import ProviderError
from openclass_provider_jev import JevDecisionProvider
from openclass_server.main import create_app
from openclass_server.settings import Settings
from pydantic import SecretStr

RUN = Path(os.environ["OPENCLASS_EXPERIMENT_RUN"])


def main() -> int:
    database_url = f"sqlite+aiosqlite:///{RUN / 'experiment.db'}"
    settings = Settings(
        database_url=database_url,
        decision_provider="jev",
        jev_api_key=SecretStr(os.environ["OPENCLASS_JEV_API_KEY"]),
        provider_max_retries=2,
    )
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/classifiers/device-type"
        ontology = client.get(f"{base}/ontology").json()
        candidates = client.get(f"{base}/candidates").json()
        candidate = next(c for c in candidates if c["canonical_name"] == "tablet")
        base_model = OntologyVersion.model_validate(ontology)
        tablet = OntologyClass(
            canonical_name="tablet",
            display_name="Tablet",
            description=candidate["description"] or "",
            aliases=("tab",),
        )
        proposed = base_model.model_copy(update={"classes": (*base_model.classes, tablet)})
        dataset: list[dict[str, Any]] = [
            {"content": "iPhone 17", "label": "phone", "group": "known"},
            {"content": "MacBook Pro", "label": "laptop", "group": "known"},
            {"content": "Samsung Galaxy Tab", "label": "tablet", "group": "tablet"},
            {"content": "iPad Pro", "label": "tablet", "group": "tablet"},
            {"content": "Google Pixel Tablet", "label": "tablet", "group": "tablet"},
            {"content": "refrigerator", "label": None, "group": "unrelated"},
            {"content": "blue whale", "label": None, "group": "unrelated"},
        ]
        provider = JevDecisionProvider(
            api_key=settings.jev_api_key,
            base_url=settings.jev_base_url,
            model=settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            max_retries=0,
        )

        async def run() -> dict[str, Any]:
            outputs: list[dict[str, Any]] = []
            for item in dataset:
                row: dict[str, Any] = {**item}
                for name, version in (("baseline_v1", base_model), ("candidate_v2", proposed)):
                    decision = await provider.choice(
                        ChoiceRequest(
                            observation=Observation(content=item["content"]), ontology=version
                        )
                    )
                    novelty = assess(signals_from(decision), settings.novelty)
                    top = max(decision.probabilities, key=lambda name: decision.probabilities[name])
                    row[name] = {
                        "top_class": top,
                        "novelty_state": novelty.state,
                        "unknown_probability": decision.unknown_probability,
                        "latency_ms": decision.latency_ms,
                        "input_tokens": decision.input_tokens,
                        "output_tokens": decision.output_tokens,
                        "estimated_cost": decision.estimated_cost,
                    }
                outputs.append(row)
            return {"dataset": outputs}

        try:
            evaluation = asyncio.run(run())
        except ProviderError:
            evaluation = {
                "report_type": "candidate_evaluation_before_human_approval",
                "status": "failed",
                "error": "Jev provider failed during evaluation; no evaluation gate was completed.",
                "ontology_v1_id": ontology["id"],
                "candidate": candidate,
            }
            (RUN / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
            print(json.dumps(evaluation, indent=2))
            return 1
        rows = evaluation["dataset"]
        known = [r for r in rows if r["group"] == "known"]
        tablets = [r for r in rows if r["group"] == "tablet"]
        unrelated = [r for r in rows if r["group"] == "unrelated"]

        def accuracy(rows: list[dict[str, Any]], key: str) -> float:
            return float(sum(r[key]["top_class"] == r["label"] for r in rows) / len(rows))

        evaluation["metrics"] = {
            "existing_class_accuracy_before": accuracy(known, "baseline_v1"),
            "existing_class_accuracy_after": accuracy(known, "candidate_v2"),
            "tablet_accuracy": accuracy(tablets, "candidate_v2"),
            "unknown_behavior_unrelated_before": sum(
                r["baseline_v1"]["novelty_state"] != "known" for r in unrelated
            )
            / len(unrelated),
            "unknown_behavior_unrelated_after": sum(
                r["candidate_v2"]["novelty_state"] != "known" for r in unrelated
            )
            / len(unrelated),
            "regressions": [
                r["content"]
                for r in known
                if r["baseline_v1"]["top_class"] == r["label"]
                and r["candidate_v2"]["top_class"] != r["label"]
            ],
        }
        passed = (
            evaluation["metrics"]["existing_class_accuracy_after"]
            >= evaluation["metrics"]["existing_class_accuracy_before"]
            and evaluation["metrics"]["tablet_accuracy"] >= 0.5
            and not evaluation["metrics"]["regressions"]
        )
        evaluation["status"] = "passed" if passed else "failed"
        if passed:
            evaluated = client.post(f"{base}/candidates/{candidate['id']}/evaluate")
            if evaluated.status_code != 200:
                evaluation["gate_error"] = evaluated.json()
                passed = False
                evaluation["status"] = "failed"
            evaluation["candidate"] = (
                evaluated.json() if evaluated.status_code == 200 else candidate
            )
        else:
            evaluation["candidate"] = candidate
        evaluation["ontology_v1_id"] = ontology["id"]
        evaluation["active_ontology_after_evaluation"] = client.get(f"{base}/ontology").json()
        evaluation["report_type"] = "candidate_evaluation_before_human_approval"
        (RUN / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
        print(
            json.dumps({"status": evaluation["status"], "metrics": evaluation["metrics"]}, indent=2)
        )
        print(f"Report: {RUN / 'evaluation.json'}")
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
