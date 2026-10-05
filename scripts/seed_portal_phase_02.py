"""Print local-only deterministic Phase 2 browser test credentials."""
import json

manifest = {
    "simulated": True,
    "login_required": True,
    "owner": {
        "username": "owner@acme.openclass.test",
        "password": "OpenClass-Local-Owner-2026",
    },
    "reviewer": {
        "username": "reviewer@acme.openclass.test",
        "password": "OpenClass-Local-Reviewer-2026",
    },
}
print(json.dumps(manifest, indent=2))
