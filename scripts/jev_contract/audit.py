"""Offline, secret-safe evidence and prepared-packet integrity audit."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .canonical import digest
from .knowledge import JevKnowledgeBase, JevProfile, save_new
from .precision import packet
from .teacher import TeacherRequest


def verify_manifest(manifest: Path, root: Path) -> int:
    inventory = json.loads(manifest.read_text())
    for name, expected in inventory.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f"artifact preservation failed: {name}")
        raw = path.read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != expected
            and hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != expected
        ):
            raise ValueError(f"artifact preservation failed: {name}")
    return len(inventory)


def verify_inputs(
    base: Path, root: Path, *, require_build_files: bool = False
) -> dict[str, Any]:
    kb = JevKnowledgeBase.model_validate_json((base / "knowledge.json").read_text())
    if require_build_files or all(
        (root / e.path).is_file() for obs in kb.observations for e in obs.evidence
    ):
        kb.verify(root)
    profile = JevProfile.model_validate_json((base / "profile.json").read_text())
    if profile.knowledge_base_hash != digest(kb.model_dump(mode="json")):
        raise ValueError("profile knowledge base hash mismatch")
    protocol = json.loads((base / "protocol.json").read_text())
    packets = json.loads((base / "teacher-packets.json").read_text())
    requests = [
        TeacherRequest.model_validate(p)
        for p in json.loads((base / "teacher-packages.json").read_text())
    ]
    for request in requests:
        if request.profile != profile:
            raise ValueError("Teacher packet uses another profile")
        if packets[request.id] != packet(request):
            raise ValueError("prepared Teacher packet differs from executable protocol")
        if protocol["packet_hashes"][request.id] != digest(packet(request)):
            raise ValueError("packet hash mismatch")
        for reference in request.evidence_refs:
            if require_build_files or (root / reference.path).is_file():
                reference.read(root)
    return {
        "observations": len(kb.observations),
        "teacher_packets": len(requests),
        "profile_hash": digest(profile.model_dump(mode="json")),
    }


def scan_secrets(paths: list[Path]) -> int:
    patterns = [
        rb"vck_[A-Za-z0-9]{24,}",
        rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}",
        rb"AIza[A-Za-z0-9_-]{30,}",
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ]
    count = 0
    for path in paths:
        if not path.is_file():
            continue
        content = path.read_bytes()
        if any(re.search(pattern, content) for pattern in patterns):
            raise ValueError(f"possible secret detected; contents suppressed: {path}")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=None)
    parser.add_argument("--base", type=Path, default=Path("benchmarks/jev-contract/v1"))
    parser.add_argument(
        "--historical", type=Path, default=Path("build/jev-contract-v1/historical-sha256.json")
    )
    args = parser.parse_args()
    report = verify_inputs(args.base, Path.cwd())
    if args.historical.is_file():
        report["historical_files_preserved"] = verify_manifest(args.historical, Path.cwd())
    else:
        report["historical_files_preserved"] = 0
    report["prepared_files_verified"] = verify_manifest(
        args.base / "benchmark-sha256.json", args.base
    )
    files = [
        p
        for directory in (args.base, Path("scripts/jev_contract"), Path("docs"), Path("tests"))
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    if args.historical.is_file():
        files += [Path(p) for p in json.loads(args.historical.read_text())]
    report["secret_scan_files"] = scan_secrets(files)
    report["secret_scan_status"] = "No matching credential patterns; not a general DLP guarantee"
    if args.output is not None:
        save_new(args.output, report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
