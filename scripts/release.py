"""Validate release metadata. Never publish or create tags."""

import argparse
import json
import tomllib
from pathlib import Path

PYPROJECT_FILES = (
    "packages/core/pyproject.toml",
    "packages/server/pyproject.toml",
    "packages/cli/pyproject.toml",
    "packages/tui/pyproject.toml",
    "packages/sdk-python/pyproject.toml",
    "providers/mock/pyproject.toml",
    "providers/jev/pyproject.toml",
    "providers/glm/pyproject.toml",
    "providers/laya/pyproject.toml",
    "providers/openai-compatible/pyproject.toml",
    "providers/ollama/pyproject.toml",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate workspace release metadata.")
    parser.add_argument(
        "--check",
        dest="expected_version",
        default=None,
        help="Optional expected version string to assert against workspace metadata.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if args.expected_version is not None:
        assert version == args.expected_version, f"Expected {args.expected_version}, got {version}"

    expected_paths = sorted(root / rel for rel in PYPROJECT_FILES)
    discovered_paths = sorted(root.glob("packages/*/pyproject.toml")) + sorted(
        root.glob("providers/*/pyproject.toml")
    )
    assert sorted(discovered_paths) == expected_paths, (discovered_paths, expected_paths)

    for path in expected_paths:
        assert tomllib.loads(path.read_text())["project"]["version"] == version, path
        assert (path.parent / "LICENSE").read_text(encoding="utf-8").replace("\r\n", "\n") == (
            root / "LICENSE"
        ).read_text(encoding="utf-8").replace("\r\n", "\n"), path
    for path in [
        root / "package.json",
        *root.glob("apps/*/package.json"),
        *root.glob("packages/*/package.json"),
        *root.glob("services/*/package.json"),
    ]:
        assert json.loads(path.read_text())["version"] == version, path
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (root / "LICENSE").read_text()
    assert f"v{version}" in (root / "CHANGELOG.md").read_text()
    print(f"Workspace versions agree: {version}. No publication performed.")


if __name__ == "__main__":
    main()
