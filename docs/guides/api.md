# Genesis API

Base `/api/v1`; complete request/response models are served at `/openapi.json` and `/docs`.
IDs and classifier slugs both resolve classifier routes. No authentication in Genesis.

| Method | Route                                        | Behavior                                          |
| ------ | -------------------------------------------- | ------------------------------------------------- |
| GET    | `/health`                                    | Liveness; no database dependency                  |
| GET    | `/health/ready`                              | Database, migration, and pgvector readiness       |
| POST   | `/api/v1/classifiers`                        | Create classifier + immutable ontology v1 + event |
| GET    | `/api/v1/classifiers`                        | List classifiers                                  |
| GET    | `/api/v1/classifiers/{id}`                   | Inspect classifier                                |
| POST   | `/api/v1/classifiers/{id}/classify`          | Persist a text observation and decision           |
| GET    | `/api/v1/classifiers/{id}/unknowns`          | Unknown evidence; limit 1–200, offset ≥0          |
| GET    | `/api/v1/classifiers/{id}/ontology`          | Active immutable snapshot                         |
| GET    | `/api/v1/classifiers/{id}/ontology/versions` | All snapshots in version order                    |
| GET    | `/api/v1/classifiers/{id}/events`            | Audit JSON; after sequence, limit 1–200           |
| GET    | `/api/v1/providers`                          | Available mock adapter capability                 |

Classify body: `{"observation":"Cancel my plan","metadata":{}}`.
Known results include selected_class and selected_class_id. Uncertain/likely_novel
results return both as null and persist an unknown event. Every result retains the
ontology version, provider distribution, novelty signals and human-readable reason codes.

Creation body is illustrated in `examples/support-intents/classifier.json`.
Names use lower snake_case; slugs use lower kebab-case. UNKNOWN/OTHER are reserved.
Ontology aliases must be nonblank and unique across concepts. Current ontologies are flat.

Creation emits `ontology.version_created`; successful classification emits
`classification.completed` and optionally `unknown.detected`. Audit payloads omit raw
text; unknown records retain raw observations locally. No SSE endpoint exists yet.

The target API in the architecture specification also includes candidates, evaluation,
promotion, merge, observation batch ingest, diffs and provider testing; these routes
are deliberately absent until their lifecycle rules are implemented.
