# Roadmap

The [architecture specification](docs/architecture/SPECIFICATION.md) is the design
contract. The [ticket backlog](docs/contributing/tickets.md) defines actionable work.
Release names are branding, not API concepts. Dates are intentionally uncommitted.

| Milestone         | Scope                                                                                                     | Status                 |
| ----------------- | --------------------------------------------------------------------------------------------------------- | ---------------------- |
| v0.0.1 — Genesis  | Workspaces, core/kernel, API, DB/migrations, clients, CI, policies                                        | Initial implementation |
| v0.1 — Discovery  | Jev, unknown clustering, discovery/canonicalization, replay evaluation, reviewed promotion, TUI/web, demo | Planned                |
| v0.2 — Memory     | Stronger evidence, aliases, verified corrections, discovery history                                       | Planned                |
| v0.3 — Evolution  | Merge/deprecate, drift monitoring, controlled automatic aliases                                           | Planned                |
| v0.4 — Frontier   | Hierarchies, routing/path search, large ontologies                                                        | Planned                |
| v0.5 — Ecosystem  | Provider/plugin SDK, event sources and webhooks                                                           | Planned                |
| v1.0 — Open World | Stable protocol and proven evolution workflows                                                            | Future                 |

Genesis must pass clean installation, Compose startup, migration, health, and test
checks. Administrative release tasks (branch protection, private security reporting,
license/brand confirmation, signing and publication permissions) remain maintainer work.

The v0.1 gate is the complete unknown → evidence → candidate → evaluation → human
promotion → new ontology → correct reclassification experience. A passing mock
kernel is not evidence that open-world discovery works.

No autonomous structural promotion, multimodal input, distributed workers, enterprise
RBAC, Kubernetes, multi-region, billing, or hosted cloud in v0.1.
