"""Validate release metadata. Never publish or create tags."""

import json
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
for path in sorted(root.glob("packages/*/pyproject.toml")) + sorted(
    root.glob("providers/*/pyproject.toml")
):
    assert tomllib.loads(path.read_text())["project"]["version"] == version, path
    assert (path.parent / "LICENSE").read_bytes() == (root / "LICENSE").read_bytes(), path
for path in [
    root / "package.json",
    *root.glob("apps/*/package.json"),
    *root.glob("packages/*/package.json"),
]:
    assert json.loads(path.read_text())["version"] == version, path
assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (root / "LICENSE").read_text()
assert f"v{version}" in (root / "CHANGELOG.md").read_text()
print(f"Workspace versions agree: {version}. No publication performed.")
