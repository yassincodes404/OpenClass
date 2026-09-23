import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openclass_core.models import OntologyClass, OntologyVersion
from openclass_server.main import create_app
from openclass_server.settings import Settings


@pytest.fixture
def ontology() -> OntologyVersion:
    from uuid import uuid4

    return OntologyVersion(
        classifier_id=uuid4(),
        version_number=1,
        created_by="test",
        classes=(
            OntologyClass(canonical_name="billing", display_name="Billing", aliases=("charged",)),
            OntologyClass(
                canonical_name="technical", display_name="Technical", aliases=("broken",)
            ),
        ),
    )


@pytest.fixture
def classifier_body() -> dict:
    return {
        "slug": "support-intent",
        "name": "Support intent",
        "classes": [
            {"canonical_name": "billing", "display_name": "Billing", "aliases": ["charged"]},
            {"canonical_name": "technical", "display_name": "Technical", "aliases": ["broken"]},
            {"canonical_name": "sales", "display_name": "Sales", "aliases": ["purchase"]},
        ],
    }


@pytest.fixture
def database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    return url


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(database_url=database_url))) as client:
        yield client


@pytest.fixture
def postgres_url(monkeypatch: pytest.MonkeyPatch) -> str:
    url = os.getenv("OPENCLASS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set OPENCLASS_TEST_DATABASE_URL to a disposable PostgreSQL database")
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("PostgreSQL tests require a postgresql+asyncpg URL")
    monkeypatch.setenv("OPENCLASS_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    return url
