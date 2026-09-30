# Current implementation status

Date: 2026-09-30. This describes the local working tree, not a released version.
The repository remains v0.0.1 Genesis. The tree contains substantial unreleased
work beyond the last committed baseline; structural cleanup does not constitute
review or publication of that whole tree.

| Area                              | Present behavior                                                                                          | Remaining gate                                                   |
| --------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Classification                    | Typed provider port, novelty, persistent UNKNOWN, historical runs and ontology snapshots                  | Wider-domain/provider quality and production calibration         |
| Projects/data                     | Project-scoped CRUD, raw ingestion and persistent source events                                           | Organization/auth boundary and retention policy                  |
| Decision services                 | Bounded choices, provider execution, run provenance and evidence                                          | Complete immutable configuration/version history                 |
| Evidence                          | UNKNOWN/low-trust items, human feedback, triage and cases                                                 | Independent verified evaluation datasets                         |
| Teacher candidates                | Inactive proposals with base hash and evidence provenance; rejection                                      | Durable baseline/candidate replay, approval and activation       |
| Evaluation/activation             | Unsupported routes return 409; UI controls disabled                                                       | OC-008/009/017; no passing scores fabricated from counts         |
| Webhook integration               | Environment token auth, scoped event identity, atomic ingestion/audit/receipt, restart-safe deduplication | Vendor-specific signed envelopes, timestamp windows and adapters |
| REST integration                  | Bounded endpoint reachability probe, optional environment bearer credential, sanitized errors             | Capability execution, permissions, verifier and delivery outbox  |
| MCP/database/provider connections | Persisted configuration; connectivity checks explicitly unimplemented                                     | Actual protocol-specific adapters and contracts                  |
| System diagnostics                | Database/schema state and Genesis version; configured provider status separated from daemon probe         | Production monitoring and measured inference readiness           |
| Analytics                         | Deterministic summaries of persisted runs                                                                 | Versioned AnalyticsSpec, richer queries/backfill                 |
| Research                          | Frozen proofs, profiles, runners and negative findings                                                    | Domain/scale/reliability validation beyond authored experiments  |

No hosted auth, billing, distributed job queue, S3 artifact service, enterprise RBAC,
generic production capability runtime or automatic promotion is claimed here.

See [foundation hardening](foundation-hardening.md), [tickets](../contributing/tickets.md),
and the [product target](../OpenClass_Product_Experience_Platform_Spec.md).
