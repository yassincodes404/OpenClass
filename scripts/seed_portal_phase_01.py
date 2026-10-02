"""Deterministic, simulated seed manifest for the separate portal Phase 1."""

import json

manifest = {
    "seed": "portal-phase-01",
    "simulated": True,
    "login_required": False,
    "project": "acme-support-phase-01-demo",
    "routes": ["/", "/projects", "/projects/acme-support-phase-01-demo"],
}
print(json.dumps(manifest, indent=2))
