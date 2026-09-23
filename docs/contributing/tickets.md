# Initial development tickets

This file is the reviewable, local backlog derived from founding specification
§§37, 45, 56, 57. These are not already-created GitHub issues. IDs are stable so
maintainers can copy each ticket into GitHub without losing dependencies.

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

**Depends on:** OC-001. **Priority:** P0 for real providers.
Define capabilities, structured safe errors, normalization, timeouts, bounded
retries, tokens/cost/latency, provider registry and environment-secret references.
Specify redaction and disabled-by-default request-content logging. Extend ports
only alongside tested implementations. Version project configuration and add UI setup.
**Acceptance:** malformed/nonfinite/incomplete distributions rejected; secrets never
appear in logs/errors; provider failures emit safe observable events; shared contract
suite; no provider imports or required vendor fields in core/storage.

## OC-004 — TypeSafe Jev adapter

**Depends on:** OC-003. **Priority:** P0.
Implement isolated `providers/jev`, verified against official API docs and credentials
supplied by operator. Map ontology plus UNKNOWN into choice; normalize output and
capture usage. No live key in repository or mandatory online CI.
**Acceptance:** shared contracts and replayable fixtures pass; opt-in live check
passes with user credentials; unsupported shapes/rate limits/timeouts are explicit.

## OC-005 — Unknown embeddings and similarity grouping

**Depends on:** OC-001, OC-003. **Priority:** P0.
Introduce EmbeddingProvider and optional local sentence-transformers adapter; migrate
embedding/cluster state using pgvector. Group recurring unknowns using configurable
similarity, retain evidence references and algorithm/model versions.
**Acceptance:** deterministic grouping tests; no cross-classifier evidence leakage;
retries do not duplicate evidence; cluster.updated event; restart-safe persisted state.

## OC-006 — Discovery providers and canonicalization

**Depends on:** OC-003, OC-005. **Priority:** P0.
Typed DiscoveryRequest/Result, mock, OpenAI-compatible and Ollama adapters. Cluster
summaries with minimal external content. Handle all six initial proposal types;
compare aliases/existing concepts before recommending new classes.
**Acceptance:** synonyms cannot bypass canonicalization; insufficient evidence,
out-of-domain and schema issues stay inactive; validated structured output; contracts.

## OC-007 — Candidate evidence and lifecycle

**Depends on:** OC-006. **Priority:** P0.
Migrate candidate/evidence tables, review state and explicit state machine. Implement
candidate inspect/list/reject; minimum distinct evidence policy and provenance.
**Acceptance:** illegal transitions and duplicate evidence rejected; rejection audited;
no provider can activate state; all candidates reference supporting observations.

## OC-008 — Verified datasets and replay evaluation

**Depends on:** OC-003, OC-007. **Priority:** P0.
Evaluation sets/examples/runs/results, human/verified label provenance, baseline and
candidate replay against the same immutable dataset, metrics and regression limits.
**Acceptance:** never infer ground truth from predictions; historical cases retained;
known accuracy/F1, unknown precision/recall and coverage validated on hand-computed
fixtures; empty/undefined metrics explicit; failure never marks evaluation passed.

## OC-009 — Semantic event log and safe ontology evolution (RFC-0002)

**Depends on:** OC-007, OC-008. **Priority:** P0.
Normalize ontology classes and version-scoped aliases as needed. ADD/ALIAS/REJECT,
version diff and rollback-as-new-version. Guard activation with canonicalization,
distinct evidence, current successful evaluation and explicit human review.
**Acceptance:** concurrent/stale promotions conflict atomically; vN never changes;
all events identify actor/proposal/evaluation/from/to versions; replay reconstructs
snapshots; rollback leaves historical runs reproducible; failed evaluation blocks promotion.

## OC-010 — Public protocol, SDK models, SSE and ingest

**Depends on:** OC-007–009. **Priority:** P1.
Complete target REST routes, observations/batch ingest, pagination, idempotency,
generated or contract-verified typed SDK models, resumable SSE and safe provider telemetry.
**Acceptance:** contract suite compares clients against OpenAPI; SSE resumes by cursor;
UI consumes no private repositories; disconnect/retry/backpressure behavior documented.

## OC-011 — First-run CLI and TUI

**Depends on:** OC-010. **Priority:** P1.
Textual/Rich client, default `openclass` entry, create/connect/demo onboarding, tabs
Overview/Observe/Discoveries/Ontology/Evaluations/Providers. Extend doctor and configuration.
**Acceptance:** no-key onboarding works; reconnect/loading/error/empty states; keyboard
navigation; promotion displays actual evidence and evaluation; tests use public SDK.

## OC-012 — Web discovery workspace

**Depends on:** OC-010. **Priority:** P1.
Extend current observation page into dashboard, discovery inbox, ontology explorer,
evaluation comparison and provider settings; web lifecycle command/container.
**Acceptance:** accessible responsive views; live events; real measured values;
no hidden learning policy in UI; guarded human promotion and error recovery tested.

## OC-013 — Full no-key demo and hidden-intents benchmark

**Depends on:** OC-004–012. **Priority:** Release blocker.
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

**Depends on:** OC-001. **Status:** Implemented on `oc-016-supervisor-review-foundation`;
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

**Depends on:** OC-016. **Status:** Planned.
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

**Depends on:** OC-003, OC-016, OC-017. **Status:** Planned.
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

**Depends on:** OC-018, OC-019. **Status:** Planned.
Policy-driven review triggers: unknown/uncertain review, suspicious known results,
configurable random sampling of confident known results, statistical anomaly
review, summarized batch review, budgets and drift-triggered audits. No per-request
LLM dependency in the classification path.
**Acceptance:** sampling rates are configuration, never hard-coded; confident
systematic misclassification is discoverable without reviewing every run;
review volume and cost are observable.
