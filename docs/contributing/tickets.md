# Initial development tickets

Current priorities follow the founder-authorized 2026-10-02
[application proof program](../architecture/application-proof-program.md).
OC-034–045 below preserve existing IDs and evaluation/release gates.

The 2026-09-24 platform direction and experiment-to-product reconciliation are
recorded in [Discovery productionization](../architecture/discovery-productionization.md).
The expanded roadmap is proposed; Genesis and existing ticket IDs remain intact.

This file is the reviewable, local backlog derived from founding specification
§§37, 45, 56, 57. These are not already-created GitHub issues. IDs are stable so
maintainers can copy each ticket into GitHub without losing dependencies.

Current working-tree status is tracked in
[implementation status](../architecture/implementation-status.md). Product targets
and experimental endpoints are not proof that release gates have passed.

## OC-001 — Genesis repository and executable kernel

**Milestone:** v0.0.1. **Status:** Implemented; release administration remains OC-002.
**Scope:** Python/npm workspaces, core models/ports, mock provider, novelty,
PostgreSQL/pgvector, migration, API, SDK/CLI/web foundation, CI, policies.
**Acceptance:** clean dependency install; Compose health ready; known and unknown
classification survives restart; invalid distributions fail; immutable history;
unit/contracts/integration/type checks and builds pass. No v0.1 capability claims.
**Traceability:** §§37, 45 Phase 0–1/3, 56; §57 steps 01–18 and initial 33–35/37.

## OC-002 — Repository administration and Genesis release

**Depends on:** OC-001. **Status:** Ready for maintainer setup.
Enable private security reporting; establish private security/conduct contacts;
configure branch protection and required checks; confirm licensing/branding;
review CODEOWNERS; decide organization ownership (current repository remains in
founder's account). Create v0.0.1 only after clean-clone verification. Do not create
an organization or publish packages as a side effect of implementation.
**Acceptance:** documented contacts, protected main, signed/reviewed artifacts,
release notes separating shipped behavior and planned work.

## OC-003 — Provider protocol, configuration and privacy (RFC-0001)

**Depends on:** OC-001. **Priority:** P0 for real providers. **Status:** Implemented (PRs #32, #36, #39, #40, #50; `OC-BG-004`, `OC-BG-009`, `OC-BG-031`, `OC-BG-037` `VERIFIED`; `OC-BG-029` `PARTIAL` for Prometheus `/metrics`).
Define capabilities, structured safe errors, normalization, timeouts, bounded
retries, tokens/cost/latency, provider registry and environment-secret references.
Specify redaction and disabled-by-default request-content logging. Extend ports
only alongside tested implementations. Version project configuration and add UI setup.
**Acceptance:** malformed/nonfinite/incomplete distributions rejected; secrets never
appear in logs/errors; provider failures emit safe observable events; shared contract
suite; no provider imports or required vendor fields in core/storage.

## OC-004 — TypeSafe Jev adapter

**Depends on:** OC-003. **Priority:** P0. **Status:** Implemented (PRs #33, #36, #42, #45; `OC-BG-005`, `OC-BG-009`, `OC-BG-041` `VERIFIED`; `OC-BG-017` `PARTIAL`: no automated holdout ECE temperature-fitting pipeline).
Implement isolated `providers/jev`, verified against official API docs and credentials
supplied by operator. Map ontology plus UNKNOWN into choice; normalize output and
capture usage. No live key in repository or mandatory online CI.
**Acceptance:** shared contracts and replayable fixtures pass; opt-in live check
passes with user credentials; unsupported shapes/rate limits/timeouts are explicit.

## OC-005 — Unknown embeddings and similarity grouping

**Depends on:** OC-001, OC-003. **Priority:** P0. **Status:** Partially implemented (`OC-BG-008` & `OC-BG-041` `VERIFIED`, `OC-BG-022` `PARTIAL`, PRs #36, #45): `GatewayEmbedder` (`text-embedding-3-small`), `SentenceTransformerEmbedder`, `ClusterStore` (`content_hash`) embedding cache, greedy cosine clustering, and non-destructive re-clustering (`0023`) are shipped; HDBSCAN and Silhouette/Davies-Bouldin cluster metrics remain unimplemented.
Introduce EmbeddingProvider and optional local sentence-transformers adapter; migrate
embedding/cluster state using pgvector. Group recurring unknowns using configurable
similarity, retain evidence references and algorithm/model versions.
**Acceptance:** deterministic grouping tests; no cross-classifier evidence leakage;
retries do not duplicate evidence; cluster.updated event; restart-safe persisted state.

## OC-006 — Discovery providers and canonicalization

**Depends on:** OC-003, OC-005. **Priority:** P0. **Status:** Implemented (PRs #40, #45, #50, #54) across `mock`, `glm`, `openai-compatible`, `ollama`, and `gateway` (`GatewayClusterDiscovery`, `OpenAICompatibleChoiceTeacher`).
Typed DiscoveryRequest/Result, mock, OpenAI-compatible and Ollama adapters. Cluster
summaries with minimal external content. Handle all six initial proposal types;
compare aliases/existing concepts before recommending new classes.
**Acceptance:** synonyms cannot bypass canonicalization; insufficient evidence,
out-of-domain and schema issues stay inactive; validated structured output; contracts.

## OC-007 — Candidate evidence and lifecycle

**Depends on:** OC-006. **Priority:** P0. **Status:** Partially implemented (`OC-BG-008` `VERIFIED`, `OC-BG-014` & `OC-BG-021` `PARTIAL`, PRs #35, #36, #45, #46, #54): Track 2 (`ChoiceCandidate`) and Track 3 (`DiscoveryCandidate`) lifecycles and `unknown_triage` ↔ `evidence_items` sync are active; `candidates` (`0003`), `project_choice_candidates` (`0007`), and `cluster_candidates` (`0016`) remain separate SQL tables (`OC-BG-014` `PARTIAL`), and legacy Track 1 (`POST /api/v1/classifiers/{slug}/candidates`) remains fail-closed (`409`).
Migrate candidate/evidence tables, review state and explicit state machine. Implement
candidate inspect/list/reject; minimum distinct evidence policy and provenance.
**Acceptance:** illegal transitions and duplicate evidence rejected; rejection audited;
no provider can activate state; all candidates reference supporting observations.

## OC-008 — Verified datasets and replay evaluation

**Depends on:** OC-003, OC-007. **Priority:** P0. **Status:** Partially implemented (`OC-BG-011` & `OC-BG-040` `VERIFIED`, `OC-BG-012` `PARTIAL`, PRs #38, #54): `EvaluationExample` enforces `source_type` (`verified_holdout`, `regression_baseline`, `calibration_dev`), rejects `label_source="prediction"` (`422`), blocks discovery-to-holdout leakage (`409`), and replays through `DecisionExecutor` with Teacher disabled (`0019`/`0025`); per-example replay predictions are stored in `evaluation_runs.metrics` JSON (`0019_evaluation_runs.py`, `metrics["item_results"]`) rather than a dedicated normalized per-example `evaluation_predictions` SQL table (`OC-BG-012` `PARTIAL`).
Evaluation sets/examples/runs/results, human/verified label provenance, baseline and
candidate replay against the same immutable dataset, metrics and regression limits.
**Acceptance:** never infer ground truth from predictions; historical cases retained;
known accuracy/F1, unknown precision/recall and coverage validated on hand-computed
fixtures; empty/undefined metrics explicit; failure never marks evaluation passed.

## OC-009 — Semantic event log and safe ontology evolution (RFC-0002)

**Depends on:** OC-007, OC-008. **Priority:** P0. **Status:** Partially implemented (`OC-BG-010` `VERIFIED`, `OC-BG-013`, `OC-BG-014` & `OC-BG-036` `PARTIAL`, PRs #37, #38, #54): `promotions.py` and `project_evolution.py` enforce `overall_passed is True`, `zero_regressions`, `holdout_examples >= 1`, `409` alias/key collision rejection, immutable `service_versions` (`0020`/`0024`) `vN -> vN+1` promotion, rollback, and linked cluster `UnknownEventRow` auto-resolution; legacy `Classifier` ontology snapshots (`0001_genesis`) remain read-only after creation, historical raw events are not batch re-ingested automatically (`OC-BG-013` `PARTIAL`), and canary auto-rollback is not wired (`OC-BG-036` `PARTIAL`).
Normalize ontology classes and version-scoped aliases as needed. ADD/ALIAS/REJECT,
version diff and rollback-as-new-version. Guard activation with canonicalization,
distinct evidence, current successful evaluation and explicit human review.
**Acceptance:** concurrent/stale promotions conflict atomically; vN never changes;
all events identify actor/proposal/evaluation/from/to versions; replay reconstructs
snapshots; rollback leaves historical runs reproducible; failed evaluation blocks promotion.

## OC-010 — Public protocol, SDK models, SSE and ingest

**Depends on:** OC-007–009. **Priority:** P1. **Status:** Implemented (`OC-BG-007` & `OC-BG-028` `VERIFIED`, PRs #35, #44, #48, #53) across `openclass-sdk` (Python), `@openclass/sdk` (TypeScript `OpenClassClient` + `OpenClassControlClient`), and `openclass-cli`.
Complete target REST routes, observations/batch ingest, pagination, idempotency,
generated or contract-verified typed SDK models, resumable SSE and safe provider telemetry.
**Acceptance:** contract suite compares clients against OpenAPI; SSE resumes by cursor;
UI consumes no private repositories; disconnect/retry/backpressure behavior documented.

## OC-011 — First-run CLI and TUI

**Depends on:** OC-010. **Priority:** P1. **Status:** Implemented (`OC-BG-038` `VERIFIED`, PRs #48, #49) in `packages/cli` and `packages/tui` (`openclass-tui`).
Textual/Rich client, default `openclass` entry, create/connect/demo onboarding, tabs
Overview/Observe/Discoveries/Ontology/Evaluations/Providers. Extend doctor and configuration.
**Acceptance:** no-key onboarding works; reconnect/loading/error/empty states; keyboard
navigation; promotion displays actual evidence and evaluation; tests use public SDK.

## OC-012 — Web discovery workspace

**Depends on:** OC-010. **Priority:** P1. **Status:** Partially implemented (`OC-BG-042` `VERIFIED`, `OC-BG-027` & `OC-BG-033` `PARTIAL`, PRs #28, #49, #50, #53, #55): `apps/portal` is wired 100% through `@openclass/sdk` (`OpenClassControlClient`) with engine project reconciliation and workspace ownership (`0027`) in `services/control-plane` and `packages/server`, while both `apps/web` and `apps/portal` remain active rather than retiring `apps/web` (`OC-BG-027` `PARTIAL`) and Playwright specs in `tests/web/*.spec.ts` (`playwright.config.ts`) intercept API calls via `page.route()` mocks without a dedicated Playwright spec exercising `apps/portal` against a live control-plane + engine stack (`OC-BG-033` `PARTIAL`).
Extend current observation page into dashboard, discovery inbox, ontology explorer,
evaluation comparison and provider settings; web lifecycle command/container.
**Acceptance:** accessible responsive views; live events; real measured values;
no hidden learning policy in UI; guarded human promotion and error recovery tested.

## OC-013 — Full no-key demo and hidden-intents benchmark

**Depends on:** OC-004–012. **Priority:** Release blocker. **Status:** Implemented (`OC-BG-038` & `OC-BG-040` `VERIFIED`, `OC-BG-034` `PARTIAL`, PRs #41, #49, #54): `openclass demo`, `openclass-tui`, self-contained `python -m scripts.jev_contract.audit`, and end-to-end closed-loop evolution proof (`tests/e2e/test_closed_loop_evolution.py`), while `scripts/jev_contract/audit.py` evaluates against `SimpleProvider` / `OpenAICompatibleChoiceProvider` and in-memory `ClusterService` rather than routing every benchmark row end-to-end through `DecisionExecutor` (`OC-BG-034` `PARTIAL`).
Implement `openclass demo` and benchmark command, reviewed labels and documented
provenance, withheld-class split, deterministic seed, costs/calls/runtime reporting.
**Acceptance:** central E2E known → unknowns → cluster → candidate → evaluation →
review → ontology v2 → same input known passes; no one-observation promotion;
regression/duplicate cases included; real demo recording and measured report.

## OC-014 — Discovery distribution and release gates

**Depends on:** OC-013, OC-002. **Priority:** Release blocker.
Build reviewed Python/JS distributions, container images, platform artifacts,
checksums/SBOMs; explicit tag/release authorization; installers only after artifact
locations exist. Test clean clone and clean install on documented platforms.
**Acceptance:** all §58 gates checked with evidence; version consistency; package
contents/licenses validated; release credentials constrained; no automatic publish
from untrusted PRs. Current artifact workflow remains non-publishing.

## OC-015 — Future controlled automatic promotion (RFC-0003)

**Milestone:** beyond v0.1. **Status:** Deferred.
Specify bounded autonomy only after evidence from manual promotion benchmarks;
operator opt-in, policy/audit/rollback and regression controls. No implementation
or default activation is authorized by this ticket.

## OC-016 — Supervisor review foundation

**Depends on:** OC-001. **Status:** Implemented; unreleased;
release administration remains OC-002.
**Scope:** `SupervisorProvider` port, structured review models (`SupervisorFinding`,
`ReviewRecommendation`, `ReviewRequest`, `ReviewResult`, `SupervisorReview`),
historical run retrieval (`ClassificationRecord`), append-only review persistence
(migration `0002_supervisor_reviews`), `SupervisorService`, mock supervisor,
runs/reviews API, Python/TypeScript SDK support, CLI `runs`/`review`/`reviews`,
web review panel, `supervisor.review_completed` event, tests including the
confident-misclassification demonstration.
**Acceptance:** a review can disagree with a confident known result and nothing is
rewritten — the run, ontology and unknown pool stay byte-identical; reviews are
scoped to their classifier, survive restart, and reject SQL UPDATE/DELETE; provider
failures return a safe 502 without persisting reviews; supervisor output is bounded
advisory evidence, never ground truth. No remote LLM, no automatic action.

## OC-017 — Versioned DecisionSpec

**Depends on:** OC-016. **Status:** Implemented on `DecisionService` (`0020_service_versions`, `0024_decision_run_version_lineage`, `OC-BG-005` & `OC-BG-010` `VERIFIED`, PRs #33, #37).
Version the instructions controlling classification (task description, instruction,
UNKNOWN guidance) as immutable `DecisionSpecVersion` snapshots. Extend `Classifier`
with an active spec pointer, `ClassificationResult` with the spec version used,
and `ChoiceRequest` with the spec. Migrate existing classifiers/runs to a
deterministic default spec v1. Read APIs only; instruction changes must later pass
proposal/evaluation/review before activation. `ReviewRequest` gains the spec so the
Supervisor can distinguish instruction issues from ontology issues.
**Acceptance:** every run references both the ontology and spec versions actually
used; specs are append-only; historical reviews reason over historical specs;
migration preserves Genesis data without recreation.

## OC-018 — Supervisor reasoning providers

**Depends on:** OC-003, OC-016, OC-017. **Status:** Partially implemented (`OC-BG-020` `PARTIAL`, PRs #46, #50) via `OpenAICompatibleSupervisorProvider` supporting `ollama`, `openai-compatible`, `glm`, and `gateway` and `POST /api/v1/projects/{id}/runs/{run_id}/supervise`; automatic background sampling (`review_sampling_rate`) on `TRUSTED` runs is not wired.
Ollama first (local-first), then an OpenAI-compatible adapter. Structured
`ReviewResult` responses only (never prose parsing), timeouts, secret-safe
failures, redaction, disabled-by-default request-content logging, and
latency/token/cost telemetry. No vendor dependency in core.
**Acceptance:** shared contract suite covering malformed JSON, unknown enums,
out-of-range confidence, oversized rationale, timeouts, HTTP failures and
secret-bearing upstream errors; no online credentials in mandatory CI.

## OC-019 — AI management chat

**Depends on:** OC-006, OC-007, OC-008, OC-009, OC-016, OC-017, OC-018. **Status:** Planned.
Conversational Supervisor over read tools (inspect classifiers/ontology/runs/
unknowns/reviews/candidates/evaluations), proposal tools (propose class/alias/
definition/instruction/schema change, request evaluation) and guarded
human-approved actions. The model never receives SQL, credentials or repository
mutation; "approved" from a model has zero authority.
**Acceptance:** chat can produce candidates through the candidate service — never
direct ontology writes — and ungated activation is structurally impossible.

## OC-020 — Continuous audit policy

**Depends on:** OC-018, OC-019. **Status:** Partially implemented (`OC-BG-017` & `OC-BG-020` `PARTIAL`, PRs #42, #46) via node-level `DecisionServiceNode` thresholds (`min_margin`, `max_unknown_probability`, `risk_level`, `pause_on_review` in `projects.py:187-196`), `SupervisionPolicy`, and `SupervisorService`; automatic background sampling (`review_sampling_rate`) on `TRUSTED` runs is not wired.
Policy-driven review triggers: unknown/uncertain review, suspicious known results,
configurable random sampling of confident known results, statistical anomaly
review, summarized batch review, budgets and drift-triggered audits. No per-request
LLM dependency in the classification path.
**Acceptance:** sampling rates are configuration, never hard-coded; confident
systematic misclassification is discoverable without reviewing every run;
review volume and cost are observable.

## OC-033 — Foundation structure and authenticated ingestion

**Authorization:** founder's 2026-09-30 request to clean up structure and build real
core/integration behavior. **Status:** Implemented (PRs #31, #32, #38, #44, #47, #54, #55; `OC-BG-003`, `OC-BG-004`, `OC-BG-023`, `OC-BG-044` `VERIFIED`; `OC-BG-024`, `OC-BG-025`, `OC-BG-026` `PARTIAL`).
**Scope:** typed API route modules, separate integration adapters/repository,
environment-backed webhook authentication, scoped event identity, atomic observation/
audit/receipt persistence, migration `0010_webhook_receipts`, accurate health reports,
HTTP SDK support, honest UI, and implementation/documentation index.
**Core correction:** project evaluation and promotion fail closed until OC-008/009/017
provide independently verified replay and immutable activation. Evidence counts and
predictions cannot produce passing evaluation scores. Proposals/rejection remain usable.
**Acceptance:** concurrent identical deliveries commit once; changed payload conflicts;
missing/bad credentials cannot ingest; retries survive restart; project lookup prevents
cross-project access; source/audit/receipt history rejects UPDATE/DELETE; failures roll
back all ingestion writes; unsupported adapters cannot invent connected capabilities;
blocked activation leaves service/candidate/evidence/run/audit snapshots unchanged.

## OC-034 — Restore the target-branch CI baseline

**Priority:** P0. **Status:** Implemented and verified (`OC-BG-001` & `OC-BG-039` `VERIFIED`) across PR #20 (`c6545bf`), PR #29 (`9e776bf`), and PR #51 (`5a5542f`).
Evidence: [phase-0 evidence record](../implementation-phases/evidence/phase-0-baseline-and-oc-034.md).
Original failure at remote main `469482350102bddb00c55d773256cf10f60f997b`, CI run
`37004638713`: npm installation (`workspace:*` unsupported), Python formatting
(`scripts/seed_portal_phase_01.py`, superseded on the portal line) and Compose
classification (provider HTTP 502). Repairs: pnpm web job with pinned
`packageManager`, mock provider for the python and Compose jobs, Makefile pnpm
alignment, glm provider LICENSE, plus environment-honest test repairs recorded in
the evidence file and offline `.env` test isolation in PR #51 (`5a5542f`).
**Acceptance:** clean locked installs; all CI jobs pass on the reviewed target
commit, including disposable migrated PostgreSQL and Compose; no live credentials
or publication used to validate. Local passing checks alone do not close this ticket.

## OC-035 — Versioned transition, execution and verification vertical

**Depends on:** OC-034; OC-017 for immutable decision configuration references.
**Priority:** P0. **Status:** Partially implemented. `OC-BG-018` is now verified
through PR #59: runtime applicability, macro guards and independent step/final
verification are in core. PR #58 adds checkpoint revision CAS, transaction-bound
snapshots and renewable fenced leases (`0028`). The existing multi-node graph,
sandbox and checkpoint foundations remain verified. `OC-BG-016` still needs its
original typed-state, provenance, schema and budget requirements; closure does
not require a prescribed class or table name. The complete vertical acceptance
below remains authoritative and is not closed by these foundations alone.
Review typed state provenance/freshness, semantic Choice → Transition binding,
scoped capability registry, execution intent/outcome and independent verification.
Implement one bounded HTTP capability plus termination in customer operations.
Migrate append-only records explicitly; persist intent before side effects and
handle idempotency, ambiguous outcomes, bounded retries and reconciliation.
**Acceptance:** public API → SDK → UI action → external outcome → verifier →
persisted result survives restart; wrong project/version, unavailable capability,
malformed output, timeout and failed postcondition produce safe typed errors/events.
Retries never blindly repeat ambiguous non-idempotent effects. UNKNOWN does not
grant execution authority. No arbitrary shell or generated code in this slice.

## OC-036 — Shared integration manifests and generic adapters

**Depends on:** OC-033, OC-035. **Priority:** P0. **Status:** Partially implemented (`OC-BG-024` & `OC-BG-032` `PARTIAL`, PRs #32, #44, #49): `HTTPIntegrationProbe` actively probes REST, Webhook, MCP (JSON-RPC `tools/list`), Database, and Provider endpoints with SSRF protection, and `support.py` enforces idempotent `RouteOutcome` evaluation (`delivery_mode="simulated"`), without a background webhook delivery worker or retry queue.
Introduce manifests and project bindings for implemented SOURCE/QUERY/CAPABILITY/
TRIGGER/SINK roles, typed schemas and verifier/version identities. Reuse webhook
receipts and environment secret references. Ship HTTP and CSV/JSON first, then
read-only PostgreSQL and MQTT as application protocols need them.
**Acceptance:** two applications reuse the same adapter/binding mechanism;
unsupported roles remain explicit; auth/health/permissions are distinct; contracts
cover isolation, malformed input, redaction, deduplication and restart recovery.
No speculative queues, marketplace or writable ontology access for adapters.

## OC-037 — Persisted application proof reports

**Depends on:** OC-035/036; learning metrics additionally depend on OC-008/009/017.
**Priority:** P1. **Status:** Implemented (`OC-BG-040` & `OC-BG-043` `VERIFIED`, `OC-BG-036` `PARTIAL`, PRs #39, #48, #54) across `/analytics/trends`, `/alerts`, `/ops/summary` (disjoint 7-day window comparison), and `provider_usage` error/cost telemetry, while Phase 15 `AlertRule` (`0021_alert_rules.py`, `alerting.py`) is implemented without a `GET /api/v1/projects/{id}/decision-services/{sid}/drift` cohort drift detector or automatic post-promotion rollback trigger (`OC-BG-036` `PARTIAL`).
Implement typed report queries, HTTP SDKs and a minimal evidence/report view using
persisted decisions, executions, verifications, usage, reviews and version history.
Follow the program's metric definitions, provenance and denominators. Partial
reports mark unavailable metrics explicitly; no invented savings or passing scores.
**Acceptance:** hand-computed metric fixtures cover missing labels/costs, zero
denominators, pending outcomes, rejected evaluations and version/cohort comparison;
reports reproduce after restart and reject cross-project queries. Document API,
safe errors and report-generation events. Preserve success and failure evidence.

## OC-038 — Customer and developer operations proofs

**Depends on:** OC-035–037; reviewed learning depends on OC-008/009/017.
**Priority:** P1. **Status:** Implemented for customer/issue triage & closed-loop evolution proof (`OC-BG-040` `VERIFIED`, `OC-BG-029` & `OC-BG-034` `PARTIAL`, PRs #41, #50, #54: 60-issue `scikit-learn` proof, live Vercel AI Gateway proof `tests/contract/test_gemini_live.py`, and end-to-end closed-loop evolution proof `tests/e2e/test_closed_loop_evolution.py`). **Related:** OC-028/029/030.
First run authorized customer data through one externally verified routing action.
Then run a bounded developer recovery against a disposable OpenClass environment.
Declare hypotheses, labels, retained cases and postconditions before execution.
**Acceptance:** same Core and integration contracts; real ingestion/action evidence,
UNKNOWN cases and failed outcomes retained; measured reports expose evidence level.
Claims of learned reuse require actual evaluated, human-reviewed vN → vN+1 and
later replay/reuse. Developer actions are allowlisted and confined; verify Git and
filesystem state. Research artifacts remain frozen and separate from production.

## OC-039 — Smart-home and robot simulator proofs; cross-domain comparison

**Depends on:** OC-038 and fixes justified by its evidence.
**Priority:** P2. **Status:** Planned (simulator fixtures and cross-domain benchmark harness in `scripts/automation_*.py` and `benchmarks/jev-contract/v1` remain research-scoped).
Use MQTT/simulator state for smart-home behavior and structured perception plus
deterministic controls for a robot simulator. Record seeds, state freshness,
missing-input failures, outcomes and retention. Real devices require later scoped
application work. Compare all four protocols using persisted reports.
**Acceptance:** no domain-specific Core fork; adapter/configuration reuse is explicit;
both simulator proofs include failure scenarios and restart checks; simulated
results remain labeled. The comparison states sample sizes, provenance, unavailable
metrics and generalization limits without extrapolating scale or capability claims.

## OC-040 — Route deduplication, ambient `.env` test isolation, and Alembic version widening (`OC-BG-039`)

**Depends on:** OC-034. **Priority:** P0. **Status:** Implemented and verified (`OC-BG-039` `VERIFIED`, PRs #29, #37, #51).
Remove duplicate `support_router` mount in `packages/server/openclass_server/main.py`,
isolate offline `pytest` fixtures (`_isolate_provider_env` in `tests/conftest.py`) from
ambient `.env` or live gateway environment variables, and widen PostgreSQL
`alembic_version.version_num` from `VARCHAR(32)` to `VARCHAR(128)` (`0024`).
**Acceptance:** `support_router` routes appear once in OpenAPI; `uv run pytest -q -m "not postgres and not live"` passes with 0 failures even when `.env` contains live keys; revision IDs > 32 chars migrate cleanly on PostgreSQL 16.

## OC-041 — Disjoint evaluation leakage guards, collision rejection, and closed-loop E2E proof (`OC-BG-040`)

**Depends on:** OC-008, OC-009, OC-038. **Priority:** P0. **Status:** Implemented and verified (`OC-BG-040` `VERIFIED`, PRs #50, #54).
Enforce strictly disjoint discovery, calibration/dev, regression baseline, and holdout
splits (`assert_strictly_disjoint_datasets`), block discovery-to-holdout leakage (`409 Conflict`)
in `api/evaluations.py`, reject choice key/alias collisions (`409 Conflict`) on promotion,
support `discovery_provider="none"` fail-closed Teacher disablement, and execute both
offline deterministic and live Vercel AI Gateway (`OPENCLASS_RUN_LIVE_TESTS=1`)
end-to-end closed-loop evolution proofs (`tests/e2e/test_closed_loop_evolution.py`).
**Acceptance:** overlapping dataset splits fail immediately; discovery observations cannot
be added to holdout splits (`409`); duplicate keys/aliases fail promotion (`409`);
post-promotion holdout replay succeeds with Teacher disabled (`discovery_provider="none"`).

## OC-042 — Production Vercel AI Gateway decision, embedding, and cluster discovery providers (`OC-BG-041`)

**Depends on:** OC-003, OC-004, OC-005, OC-006. **Priority:** P1. **Status:** Implemented and verified (`OC-BG-041` `VERIFIED`, PR #45).
Promote `GatewayDecisionProvider`, `GatewayEmbedder` (`text-embedding-3-small`), and
`GatewayClusterDiscovery` into `providers/glm/openclass_provider_glm/gateway.py` and
wire `"gateway"` in `packages/server/openclass_server/provider_config.py` with bounded
JSON-schema probability distributions, temperature scaling (`temperature >= 0.5`),
upstream `429` retry handling, and token/cost/latency telemetry.
**Acceptance:** `tests/contract/test_gateway_providers.py` passes with zero credential
leakage, explicit `real_inference=True, simulated=False` provenance, and bounded retries.

## OC-043 — Control-Plane payload limits, Portal offline OIDC resilience, and landing consistency (`OC-BG-042`)

**Depends on:** OC-010, OC-012. **Priority:** P1. **Status:** Implemented and verified (`OC-BG-042` `VERIFIED`, PRs #44, #53).
Raise `services/control-plane` Express JSON body limit to `5mb`, fix `keycloak.init`
offline redirect fallback in `apps/portal/src/auth.tsx`, implement single-source
`deriveScenarioDistribution` (`known_billing = 0.900`, `review_compliance = 0.410 / 0.270`)
in `apps/portal/src/open-world-stage.tsx`, and split `apps/portal` route chunks
(`React.lazy` + Vite `manualChunks`).
**Acceptance:** 1MB+ batch payloads succeed through Control-Plane (`201`/`207`);
`apps/portal/src/portal.test.tsx` (including landing scenario distribution consistency checks) passes.

## OC-044 — Disjoint 7-day operations analytics comparison window (`OC-BG-043`)

**Depends on:** OC-037. **Priority:** P1. **Status:** Implemented and verified (`OC-BG-043` `VERIFIED`, PR #39).
Fix `packages/server/openclass_server/api/operations.py` so `previous` 7-day window
queries enforce an explicit upper bound (`created_at >= two_weeks_ago AND created_at < week_ago`),
making the previous (`[two_weeks_ago, week_ago)`) and current (`[week_ago, now)`)
windows strictly disjoint when computing `previous_unknown_rate` and `unknown_rate_delta`.
**Acceptance:** `tests/integration/test_operations_dashboard.py` verifies that current-week
runs never contaminate `previous_unknown_rate`.

## OC-045 — End-to-end workspace ownership isolation and atomic CAS checkpoint claiming (`OC-BG-044`)

**Depends on:** OC-033, OC-035. **Priority:** P0. **Status:** Implemented and verified (`OC-BG-044` `VERIFIED`, PR #55).
Add Alembic migration `0027_workspace_isolation_and_checkpoint_claims.py` (`workspace_id`
on `projects` and `claim_token`/`claimed_by`/`claimed_at` on `decision_run_checkpoints`),
enforce end-to-end engine and control-plane workspace ownership with explicit legacy
claiming (`POST /api/v1/projects/{id}/claim`), enforce atomic compare-and-swap (CAS)
checkpoint claiming before `DecisionExecutor.resume` with stale-claim crash recovery,
and validate cancellation against `run_status == "paused"` rather than `resumed_at is not None`
so a resumed run that pauses again at a downstream node can be cancelled cleanly while
completed runs return `409 Conflict`.
**Acceptance:** cross-workspace access and unowned project claiming across tenants fail
closed (`404`/`409`); concurrent `/resume` requests allow exactly one winner (`200`) and
reject the contender (`409`) with zero duplicate LLM calls; crashed claims recover after
stale timeout; cancelling a resumed run that paused at a downstream node succeeds (`200`)
while cancelling a completed run returns `409 Conflict`.

## OC-046 — Readable mobile landing diagram, simpler copy and purposeful motion (`OC-BG-045`)

**Depends on:** OC-012, OC-043. **Priority:** P1.
**Status:** Delivered in PR #61 with independent code/visual review, all five
PR checks and green post-merge main CI.

Preserve the horizontal desktop diagram and provide five connected, tappable
cards at narrow widths. Extract architecture/evidence/quickstart sections.
Keep copy concise, all examples explicitly simulated, UNKNOWN permanent, and
evaluation plus human approval mandatory. Use purposeful state/connector motion
with instant keyboard and reduced-motion alternatives.

**Acceptance:** preserve all scenario probabilities and manual controls; verify
desktop/tablet/mobile overflow, readable labels, keyboard tabs, playback,
clipboard feedback and working onboarding destinations. Save fresh screenshots,
a motion recording and tested-revision manifest. Run repository checks and
independent code/visual review before focused delivery.

Specification: `docs/agentic-engineering/09-landing-redesign-spec.md`.
Evidence: `artifacts/landing-redesign/README.md`.
