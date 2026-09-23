"""Run against a disposable server: uv run python scripts/smoke.py [URL]."""

import sys
from uuid import uuid4

from openclass_sdk import OpenClass

with OpenClass(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7331") as client:
    assert client.health()["status"] == "ready"
    slug = f"smoke-{uuid4().hex}"
    classifier = client.create_classifier(
        slug=slug,
        name="Smoke check",
        classes=[{"canonical_name": "billing", "display_name": "Billing", "aliases": ["charged"]}],
    )
    known = client.classify(classifier=slug, observation="charged twice")
    assert known["selected_class"] == "billing"
    unknown = client.classify(classifier=slug, observation="cancel my plan")
    assert unknown["selected_class"] is None
    assert unknown["ontology_version_id"] == classifier["active_ontology_version_id"]
    assert len(client.unknowns(slug)) == 1
    print("Genesis smoke passed: readiness, creation, known, unknown, persisted evidence")
