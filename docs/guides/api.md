# Genesis API

Base `/api/v1`; complete request/response models are served at `/openapi.json` and `/docs`.
IDs and classifier slugs both resolve classifier routes. No authentication in Genesis.

| Method | Route                                            | Behavior                                          |
| ------ | ------------------------------------------------ | ------------------------------------------------- |
| GET    | `/health`                                        | Liveness; no database dependency                  |
| GET    | `/health/ready`                                  | Database, migration, and pgvector readiness       |
| POST   | `/api/v1/classifiers`                            | Create classifier + immutable ontology v1 + event |
| GET    | `/api/v1/classifiers`                            | List classifiers                                  |
| GET    | `/api/v1/classifiers/{id}`                       | Inspect classifier                                |
| POST   | `/api/v1/classifiers/{id}/classify`              | Persist a text observation and decision           |
| GET    | `/api/v1/classifiers/{id}/runs`                  | Historical runs with their observations; paged    |
| GET    | `/api/v1/classifiers/{id}/runs/{run_id}`         | One historical run (scoped to the classifier)     |
| POST   | `/api/v1/classifiers/{id}/runs/{run_id}/reviews` | Advisory supervisor review of that run            |
| GET    | `/api/v1/classifiers/{id}/reviews`               | Review history; limit 1–200, offset ≥0            |
| GET    | `/api/v1/classifiers/{id}/unknowns`              | Unknown evidence; limit 1–200, offset ≥0          |
| GET    | `/api/v1/classifiers/{id}/ontology`              | Active immutable snapshot                         |
| GET    | `/api/v1/classifiers/{id}/ontology/versions`     | All snapshots in version order                    |
| GET    | `/api/v1/classifiers/{id}/events`                | Audit JSON; after sequence, limit 1–200           |
| GET    | `/api/v1/providers`                              | Available mock adapter capability                 |

Classify body: `{"observation":"Cancel my plan","metadata":{}}`.
Known results include selected_class and selected_class_id. Uncertain/likely_novel
results return both as null and persist an unknown event. Every result retains the
ontology version, provider distribution, novelty signals and human-readable reason codes.

Creation body is illustrated in `examples/support-intents/classifier.json`.
Names use lower snake_case; slugs use lower kebab-case. UNKNOWN/OTHER are reserved.
Ontology aliases must be nonblank and unique across concepts. Current ontologies are flat.

Creation emits `ontology.version_created`; successful classification emits
`classification.completed` and optionally `unknown.detected`. A completed review
emits `supervisor.review_completed` with review/run identifiers and the finding.
Audit payloads omit raw text; unknown records retain raw observations locally.
No SSE endpoint exists yet.

## Supervisor reviews

`POST .../runs/{run_id}/reviews` asks the configured `SupervisorProvider` to
re-examine one persisted run. The review body is optional (`{"trigger":"manual"}`)
because manual is the only trigger. The provider receives the observation, the
captured result, and the ontology version the run actually used — never the
active version. Responses are structured and bounded: a closed `finding` enum
(`no_issue`, `possible_misclassification`, `possible_missing_class`,
`class_definition_issue`, `instruction_issue`, `schema_issue`, `out_of_domain`,
`insufficient_evidence`), a `confidence`, a closed `recommendation` enum, and a
bounded `rationale`.

Reviews are advisory evidence. They never modify the reviewed run, the ontology,
or the unknown pool, and no apply/promote/auto-fix route exists. Multiple reviews
of the same run are allowed (different providers or moments); each is immutable.
Only the deterministic mock supervisor (`mock-supervisor`) is registered; its
findings report run shape and are explicitly marked `simulated`. Supervisor
provider failures return 502 with a generic message.

The target API in the architecture specification also includes candidates, evaluation,
promotion, merge, observation batch ingest, diffs and provider testing; these routes
are deliberately absent until their lifecycle rules are implemented.
