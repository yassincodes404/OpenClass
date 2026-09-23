"""Prevent private cross-layer imports as the workspace grows."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "directory,forbidden",
    [
        (
            "packages/core",
            {"openclass_server", "openclass_sdk", "openclass_cli", "openclass_provider_mock"},
        ),
        ("packages/sdk-python", {"openclass_server", "openclass_core", "openclass_provider_mock"}),
        ("providers/mock", {"openclass_server", "openclass_sdk", "openclass_cli"}),
    ],
)
def test_dependency_direction(directory: str, forbidden: set[str]) -> None:
    for path in Path(directory).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = (
                [node.module]
                if isinstance(node, ast.ImportFrom) and node.module
                else [name.name for name in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not {module.split(".")[0] for module in modules} & forbidden, str(path)
