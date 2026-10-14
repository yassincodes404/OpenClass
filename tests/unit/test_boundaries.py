"""Prevent private cross-layer imports as the workspace grows."""

import ast
import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "directory,forbidden",
    [
        (
            "packages/core",
            {
                "openclass_server",
                "openclass_sdk",
                "openclass_cli",
                "openclass_provider_mock",
                "openclass_provider_jev",
                "openclass_provider_laya",
                "openclass_provider_glm",
                "fastapi",
                "httpx",
                "sqlalchemy",
            },
        ),
        (
            "packages/sdk-python",
            {
                "openclass_server",
                "openclass_core",
                "openclass_provider_mock",
                "openclass_provider_jev",
                "openclass_provider_laya",
                "openclass_provider_glm",
            },
        ),
        (
            "packages/tui",
            {
                "openclass_server",
                "openclass_core",
                "openclass_provider_mock",
                "openclass_provider_jev",
                "openclass_provider_laya",
                "openclass_provider_glm",
            },
        ),
        ("providers/jev", {"openclass_server", "openclass_sdk", "openclass_cli"}),
        ("providers/mock", {"openclass_server", "openclass_sdk", "openclass_cli"}),
        ("providers/laya", {"openclass_server", "openclass_sdk", "openclass_cli"}),
        ("providers/glm", {"openclass_server", "openclass_sdk", "openclass_cli"}),
        (
            "providers/openai-compatible",
            {"openclass_server", "openclass_sdk", "openclass_cli"},
        ),
        ("providers/ollama", {"openclass_server", "openclass_sdk", "openclass_cli"}),
    ],
)
def test_dependency_direction(directory: str, forbidden: set[str]) -> None:
    for path in Path(directory).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = (
                [node.module]
                if isinstance(node, ast.ImportFrom) and node.module
                else [name.name for name in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not {module.split(".")[0] for module in modules} & forbidden, str(path)


def test_portal_uses_sdk_without_raw_fetch() -> None:
    portal_api = Path("apps/portal/src/api.ts").read_text(encoding="utf-8")
    assert "@openclass/sdk" in portal_api

    raw_fetch_pattern = re.compile(r"(?<![A-Za-z0-9_$.])fetch\s*\(")
    for path in Path("apps/portal/src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if path.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            continue
        content = path.read_text(encoding="utf-8")
        assert not raw_fetch_pattern.search(content), f"Raw fetch() call found in {path}"
