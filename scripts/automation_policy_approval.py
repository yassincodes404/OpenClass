"""Experimental file-backed approval service; no production activation path."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5

from openclass_core.models import OntologyClass, OntologyVersion
from pydantic import BaseModel, ConfigDict


class ApprovalError(ValueError):
    pass


class HumanApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate_id: UUID
    base_policy_id: UUID
    candidate_sha256: str
    authority: Literal["human_user_in_conversation"]
    scope: Literal["experimental_policy_v2_and_runs_2_3_only"]
    statement: str
    recorded_at: datetime


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_policy_v2(source: Path, destination: Path, approval: HumanApproval) -> dict[str, Any]:
    """Validate exact reviewed evidence and exclusively create one snapshot."""
    expected = json.loads((source / "review/sha256.json").read_text())
    for name in ("store.json", "review/candidate.json", "review/replay.json"):
        if digest((source / name).read_bytes()) != expected[name]:
            raise ApprovalError("reviewed artifact changed")
    store = json.loads((source / "store.json").read_text())
    candidate_bytes = (source / "review/candidate.json").read_bytes()
    candidate = json.loads(candidate_bytes)
    base = OntologyVersion.model_validate(store["policy_v1"])
    evaluation = json.loads((source / "review/replay.json").read_text())
    if (
        str(approval.candidate_id) != candidate["id"]
        or str(approval.base_policy_id) != str(base.id)
        or candidate["base_policy_version_id"] != str(base.id)
        or digest(candidate_bytes) != approval.candidate_sha256
        or candidate != store["macro_candidate"]
        or candidate["status"] != "candidate"
        or evaluation != store["evaluation"]
        or evaluation["status"] != "passed"
        or not evaluation["postcondition_verified"]
    ):
        raise ApprovalError("approval does not match the evaluated candidate and base")
    proposal = candidate["proposal"]
    if candidate["procedure"]["steps"] != proposal["steps"]:
        raise ApprovalError("candidate procedure differs from proposal")
    policy_id = uuid5(base.id, approval.candidate_sha256)
    macro = OntologyClass(
        stable_class_id=uuid5(policy_id, proposal["canonical_name"]),
        canonical_name=proposal["canonical_name"],
        display_name=proposal["canonical_name"],
        description=json.dumps(
            {key: proposal[key] for key in ("description", "trigger", "steps", "success_condition")}
        ),
    )
    space = OntologyVersion(
        id=policy_id,
        classifier_id=base.classifier_id,
        version_number=2,
        parent_version_id=base.id,
        classes=(*base.classes, macro),
        created_by="human-approved-experiment",
        created_at=approval.recorded_at,
    )
    payload = {
        "id": str(policy_id),
        "version_number": 2,
        "parent_version_id": str(base.id),
        "scope": approval.scope,
        "base_policy": store["policy_v1"],
        "candidate": candidate,
        "candidate_sha256": approval.candidate_sha256,
        "base_policy_sha256": digest(json.dumps(store["policy_v1"], sort_keys=True).encode()),
        "source_store_sha256": expected["store.json"],
        "approval": approval.model_dump(mode="json"),
        "decision_space": space.model_dump(mode="json"),
        "events": [
            {
                "type": "automation.candidate_approved",
                "actor": approval.authority,
                "candidate_id": candidate["id"],
                "candidate_sha256": approval.candidate_sha256,
                "base_policy_id": str(base.id),
                "recorded_at": approval.recorded_at.isoformat(),
            },
            {
                "type": "automation_policy.version_created",
                "actor": approval.authority,
                "from_version_id": str(base.id),
                "to_version_id": str(policy_id),
                "candidate_id": candidate["id"],
            },
        ],
    }
    # Exclusive creation: neither v1 nor a previously created v2 can be overwritten.
    with destination.open("x") as stream:
        stream.write(json.dumps(payload, indent=2) + "\n")
    return payload


def approved_now(statement: str) -> HumanApproval:
    """Exact human authorization from this conversation, not model output."""
    return HumanApproval(
        candidate_id=UUID("d23d7342-71a7-4db6-876f-51edea836a2f"),
        base_policy_id=UUID("b28e35ee-7f33-451c-89a0-ee9a43dc86c3"),
        candidate_sha256="5d8986a2ce3252bfbb81bff8285891a96f97bc28a92d840a3a10f8ea37e76acf",
        authority="human_user_in_conversation",
        scope="experimental_policy_v2_and_runs_2_3_only",
        statement=statement,
        recorded_at=datetime.now(UTC),
    )
