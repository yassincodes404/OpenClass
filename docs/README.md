# OpenClass documentation

OpenClass is an unreleased Genesis foundation with additional local runtime work.
Product targets and research evidence do not establish shipped capabilities.

Start with [current implementation status](architecture/implementation-status.md)
and the [development guide](guides/development.md).

| Document                                                                                   | Role                                                                                        |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| [Canonical specification](architecture/SPECIFICATION.md)                                   | Domain invariants, architecture and release gates                                           |
| [Genesis decisions](architecture/genesis.md)                                               | Original foundation decisions and limits                                                    |
| [Development tickets](contributing/tickets.md)                                             | Scoped work and acceptance criteria                                                         |
| [Application proof program](architecture/application-proof-program.md)                     | Current founder-authorized priorities, four application protocols and metric evidence gates |
| [Product experience specification](OpenClass_Product_Experience_Platform_Spec.md)          | Target adaptive runtime and user experience; not a feature inventory                        |
| [Master product specification](OpenClass_Master_Product_Technical_Specification_v1.0.docx) | Supplied product/technical source                                                           |
| [Research completion ADR](architecture/adr-research-phase-complete.md)                     | Proven research findings, caveats and core handoff                                          |
| [Productionization reconciliation](architecture/discovery-productionization.md)            | Experiment reuse assessment and implementation sequencing                                   |
| [API guide](guides/api.md)                                                                 | Public HTTP contracts                                                                       |
| [Webhook guide](guides/integrations.md)                                                    | Authenticated external ingestion and retry semantics                                        |
| [Foundation hardening](architecture/foundation-hardening.md)                               | Current cleanup boundaries and deliberate deferrals                                         |
| [Agentic Engineering & Harness Blueprint](agentic-engineering/README.md)                   | 14-workstream audit, capability matrix, P0–P3 backlog & roadmap                             |

Research runners in `scripts/`, fixtures in `benchmarks/`, and historical `build/`
artifacts support reproducibility. They are not imported into the canonical server
to supply production state, evaluation scores or activation authority.
