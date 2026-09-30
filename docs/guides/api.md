# Genesis API

Base `/api/v1`; complete request/response models are served at `/openapi.json` and `/docs`.
IDs and classifier slugs both resolve classifier routes. No authentication in Genesis.

## Project decision runs (unreleased)

The project workspace uses these HTTP routes through the TypeScript SDK:

| Method | Route                                               | Behavior                                                                                     |
| ------ | --------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| GET    | `/api/v1/projects/{project}/runs?limit=50&offset=0` | Newest persisted runs for one project (limit 1–200)                                          |
| GET    | `/api/v1/projects/{project}/runs/{run_id}`          | One run with its input, instructions, choices, provider provenance, and supervision snapshot |

`{project}` accepts a project ID or slug. A run ID owned by another project returns 404. Both routes are read-only; history is created by
`POST /api/v1/projects/{project}/decision-services/{service}/runs` with a
`raw_event_ids` array. The UI filters the runs already loaded and offers pagination.
The no-key `mock` provider is simulated; `real_inference: false` and
`provider_metadata.simulated: true` make that visible in the run record.
`GET /api/v1/projects/{project}/summary` counts persisted project runs whose
selected choice is `UNKNOWN`; it does not treat those observations as new classes.

## Classifier API

| Method | Route                                                      | Behavior                                          |
| ------ | ---------------------------------------------------------- | ------------------------------------------------- |
| GET    | `/health`                                                  | Liveness; no database dependency                  |
| GET    | `/health/ready`                                            | Database, migration, and pgvector readiness       |
| POST   | `/api/v1/classifiers`                                      | Create classifier + immutable ontology v1 + event |
| GET    | `/api/v1/classifiers`                                      | List classifiers                                  |
| GET    | `/api/v1/classifiers/{id}`                                 | Inspect classifier                                |
| POST   | `/api/v1/classifiers/{id}/classify`                        | Persist a text observation and decision           |
| GET    | `/api/v1/classifiers/{id}/runs`                            | Historical runs with their observations; paged    |
| GET    | `/api/v1/classifiers/{id}/runs/{run_id}`                   | One historical run (scoped to the classifier)     |
| POST   | `/api/v1/classifiers/{id}/runs/{run_id}/reviews`           | Advisory supervisor review of that run            |
| GET    | `/api/v1/classifiers/{id}/reviews`                         | Review history; limit 1–200, offset ≥0            |
| GET    | `/api/v1/classifiers/{id}/unknowns`                        | Unknown evidence; limit 1–200, offset ≥0          |
| POST   | `/api/v1/classifiers/{id}/discoveries`                     | Analyze explicitly selected UNKNOWN evidence      |
| GET    | `/api/v1/classifiers/{id}/candidates`                      | List inactive discovery candidates                |
| POST   | `/api/v1/classifiers/{id}/candidates/{candidate}/reject`   | Reject an inactive candidate with a reason        |
| POST   | `/api/v1/classifiers/{id}/candidates/{candidate}/evaluate` | Returns 409 until verified replay exists          |
| POST   | `/api/v1/classifiers/{id}/candidates/{candidate}/approve`  | Returns 409 until verified replay exists          |
| GET    | `/api/v1/classifiers/{id}/ontology`                        | Active immutable snapshot                         |
| GET    | `/api/v1/classifiers/{id}/ontology/versions`               | All snapshots in version order                    |
| GET    | `/api/v1/classifiers/{id}/events`                          | Audit JSON; after sequence, limit 1–200           |
| GET    | `/api/v1/providers`                                        | Configured decision and supervisor capabilities   |

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

Discovery is an experimental vertical slice. The request must name at least three
distinct persisted UNKNOWN IDs. The configured DiscoveryProvider receives only the
classifier, captured ontology and selected evidence; it cannot access repositories
or mutate ontology state. A proposal is stored as an inactive candidate. A pending
candidate can be rejected with `{"reason":"..."}`; rejection and its event commit
atomically, and a second rejection conflicts. Evaluation and approval currently
return 409 because the earlier evidence-count check was not a verified replay.
Legacy `evaluation_passed` flags cannot authorize activation. The default discovery
provider is the simulated mock. GLM is opt-in through environment configuration.

Decision provider failures return a generic 502 and append `provider.error` with
the operation and captured ontology version. No completed run is stored for that
failure. Request validation returns a generic 422 without echoing submitted values;
classifier creation and classification reject content containing configured
credentials. This check is not a general detector for other sensitive data.

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

The architecture specification also describes verified evaluation, activation,
merge, diffs and provider testing. The current local tree exposes inactive proposals
and batch source ingestion, while verified evaluation/activation remain blocked.
Other target routes remain absent until their lifecycle rules are implemented.

Supervisor review context must refer to the same observation, classifier and ontology
version as the historical run. Repository writes reject a missing run or conflicting
review references before inserting audit history; review and completion event commit
atomically. Review text fields reject whitespace-only values and trim surrounding
whitespace. TypeScript review results expose provider metadata and latency, token and
cost telemetry; unavailable token/cost values are null.

## Foundation status and integrations

The local API is Genesis 0.0.1, not a completed Discovery release. Project and
classifier evaluation/activation routes return 409 until verified replay and
immutable activation are implemented. Inactive proposals can still be inspected
and rejected. No evidence-count metric is an evaluation result.

See the [webhook contract](integrations.md) for authenticated ingestion,
`event_key` deduplication, retry status codes, secret references and supported
health checks. System diagnostics at `/api/v1/system/health` report the stored
schema revision and migration state. Provider configuration/installation does not
prove inference readiness.
