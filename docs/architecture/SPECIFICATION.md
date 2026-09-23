# OpenClass — canonical implementation specification

Initial architecture, supplied by the project founder. This checked-in implementation
reference captures the requirements of the founding specification; it is not a claim
that all features below exist. The original specification's section numbers are
retained as cross-references for milestone and ticket traceability.

**Working name:** OpenClass. **Tagline:** The open-world classification engine.
**Secondary message:** Start with what you know. Discover what you don't.
**First public product target:** v0.1.0 — Discovery. **Foundation:** v0.0.1 — Genesis.
**Model:** founder-led open source. **Initial reference provider:** TypeSafe Jev.
The project must never depend conceptually on Jev or any individual provider.

## Product contract (§1–5, §59–62)

OpenClass continuously maintains a classifier's decision space, rather than promising
automatic neural-model retraining. The decision model provides fast inference;
discovery models provide slow reasoning; the ontology holds persistent knowledge;
evaluation controls quality; deterministic code enforces safety; humans authorize
structural changes. No claim of automatically correct concept discovery is allowed.

UNKNOWN is permanent and is not equivalent to a new class. It may mean novelty,
ambiguity, overlapping classes, missing information, domain mismatch, or a bad schema.
All important decisions must be explainable, observable, versioned, replayable,
and reversible through new versions rather than rewriting history.

An observation is an input item. A classifier is a configured task. A class is a
canonical concept with identity, definition, aliases, examples, relationships,
status and history. An ontology is the semantic structure for a classifier. A
candidate is an inactive proposal supported by observations. Promotion activates a
validated candidate. Ground truth comes only from human or verified external labels.

## Learning loop (§6–17)

Observation → preprocessing → ontology routing → DecisionProvider → novelty assessment.
Known results return with explanations. Uncertain observations enter a persistent
unknown pool with provider/model, distribution, signals, score, version, timestamps,
and future embedding/cluster/candidate references.

Unknown observations → embedding → similarity grouping → DiscoveryProvider →
canonicalization → evidence → validation → replay evaluation → human review →
new immutable ontology version. Do not call a discovery model on every unknown.

Novelty features include unknown probability, top two probabilities, margin,
normalized entropy, optional semantic distance, recurrence, and provider confidence.
Outputs are `known`, `uncertain`, or `likely_novel`, with score and reasons. Strong
unknown probability is one signal; weak unknown plus semantic distance, low margin,
and low known confidence require abstention. Thresholds are configuration.

Candidate lifecycle: discovered → candidate → collecting evidence → validating →
approved → active, with rejection branches and later merged/deprecated states.
v0.1 may expose only candidate/rejected/active, but enum storage must evolve.

Discovery proposal types: NEW_CLASS, EXISTING_CLASS, ALIAS, INSUFFICIENT_EVIDENCE,
OUT_OF_DOMAIN, SCHEMA_ISSUE. A response includes canonical/display names, definition,
aliases, optional existing match, confidence, and a reason. Providers cannot write
ontology state. Canonicalization must resolve synonyms before adding classes.

v0.1 operations: ADD, ALIAS, REJECT. Later: MERGE, SPLIT, REPARENT, DEPRECATE,
CREATE_DIMENSION. Examples/aliases/statistics may evolve faster than structure;
semantic aliases still belong to immutable version history. No automatic promotion
in v0.1; no silent merges, rewrites, or promotion based on one observation.

Promotion requires minimum evidence, genuinely-new canonicalization, completed
baseline/candidate replay, passing regression limits, and explicit human review.
Evaluate the same verified set against both versions. Compare known accuracy,
macro F1, unknown precision/recall, false novelty, coverage, duplicate concepts,
latency, usage, and cost. Predictions never become ground truth automatically.
Historical, recent, rare, hard, unknown and adversarial cases must coexist.

Semantic events include OntologyCreated, ClassAdded, AliasAdded, ClassMerged,
ClassSplit, ClassDeprecated, ClassReparented, CandidateRejected and PolicyChanged.
Record actor, proposal/evaluation, previous/new versions, and timestamp. Rollback
creates a new snapshot derived from an older snapshot; never erase history.

## Architecture and product surfaces (§18–23, §36–38)

Canonical server → HTTP/events → SDK → CLI/TUI/web/external apps. No UI owns business
logic or imports backend repositories. Providers depend on core ports; core does
not depend on providers or clients. The default eventual `openclass` launches a TUI;
`openclass serve` starts the server; `openclass web` opens the local browser.

Python 3.12+, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL/pgvector, httpx.
TUI: Textual/Rich. Web: Next.js/React/TypeScript. Docker/Compose, GitHub Actions/GHCR.
No heavy ML dependencies until needed; later NumPy/scikit-learn/sentence-transformers,
possibly HDBSCAN/UMAP. No Redis, workers, or external vector database initially.

DecisionProvider ultimately supports choice/boolean/score; v0.1 single choice only.
Initial adapters: mock and Jev. Discovery: OpenAI-compatible/Ollama. Embeddings:
local sentence-transformers. Provider-specific details live in optional metadata.
No Jev-specific database requirement. No adapter is considered implemented without
contract tests and real normalization, error handling, and usage capture.

Text observations only initially; use classify/observe, not classify_text.
Schema retains classifier_type (single_choice now; multi_label/boolean/ordinal later),
stable class IDs and future hierarchy references. Defer hierarchy behavior.

## Data, API, configuration and privacy (§24–27, §39–41)

Target tables: projects, classifiers, observations, classification_runs,
classification_probabilities, ontology_versions, ontology_classes, class_aliases,
ontology_events, unknown_events, unknown_clusters, candidates, candidate_evidence,
evaluation_sets, evaluation_examples, evaluation_runs, evaluation_results,
providers, provider_usage, settings. Create tables as their features land; schema
changes require migrations. Version all aliases/definitions used for inference.

API base `/api/v1`: classifiers create/list/get; classify/observations; unknowns;
candidates list/get/promote/reject/merge; ontology/current/versions/diff;
evaluations create/get; providers list/test; events. SSE is the initial live
transport; WebSocket later. This is the target API, not a list of available routes.

Events: classification.completed, unknown.detected, cluster.updated,
candidate.created/updated/promoted, evaluation.started/completed,
ontology.version_created, provider.error. Persist relevant histories locally.
Provider call telemetry includes model, latency, tokens, cost, errors and retries.

Versioned project configuration will support classifier/classes, provider selection,
learning flags and thresholds. auto_promote and auto_alias default false. UI users
must eventually configure without hand-editing YAML. Send only provider-required
state outside the installation. Never log keys; secrets are environment supplied
or encrypted if later persisted. Redaction and optional request-content logging
are required before remote provider integrations.

## User experience, demo and benchmarks (§28–35, §44)

First run eventually offers demo, create classifier, or connect to server. TUI tabs:
Overview, Observe, Discoveries, Ontology, Evaluations, Providers. Web adds
Playground, Observations, Settings, ontology exploration and evaluation comparison.

No-key demo begins with billing/technical/sales. Hidden intents include cancellation,
password_reset, refund_status, shipping, account_compromise and feature_request.
Show recurring unknown evidence, proposed cancellation, evaluated improvement,
human Promote, immutable v2, and the same observations now correctly classified.

`benchmarks/hidden-intents` must produce measured reproducible results, not flattering
constants. Report discovery quality/duplicates, coverage/F1, unknown precision/recall,
calls/cost/runtime. Clearly separate deterministic mock checks from model research.

Drift, hierarchy, schema dimensions, multi-label and multimodal work come later.
Store enough history to investigate frequency, confidence, correction and semantic
shifts. Treat schema issues as distinct from missing labels.

## Delivery, repository and governance (§37, §42–58)

Monorepo areas: packages/{core,server,cli,tui,sdk-python,sdk-typescript}, apps/web,
providers/{jev,mock,ollama,openai-compatible}, benchmarks/hidden-intents,
examples/{colors,support-intents,ecommerce-products,incident-routing,email-routing,
agent-failures}, docs/{concepts,architecture,guides,providers,contributing,research},
scripts, tests/{unit,integration,contract,e2e}, .github, docker.

Genesis definition: clean clone, Compose database/migrations/server, health endpoint,
passing tests, workspaces, CI, repository policy. Ordered implementation (§57):
workspace → infrastructure → models/ports/schema → provider/mock/service → v1/events →
novelty/unknown storage → embeddings/grouping → discovery/canonicalization → lifecycle →
evaluation/regressions → promotion/vN+1 → API/SDK/CLI/TUI/web → Jev → benchmark/demo →
docs/release. An initial API can arrive earlier to validate the kernel end-to-end.

v0.1 release gate: CLI/TUI/web, no-key full demo, real Jev integration, creation and
classification, persistent unknown grouping, discovery/alias detection, replay
evaluation, guarded manual promotion, immutable history/diff, new-class inference,
reproducible benchmark, real demo assets, contributor policies and release builds.
Genesis must not be labeled v0.1 while these are absent.

Unit tests cover novelty, lifecycle, mutation/versioning, normalization and metrics.
Provider contracts are shared; integration tests use PostgreSQL/pgvector/routes/events.
The central E2E is known → unknowns → cluster → candidate → evaluate → approve →
new version → same observation known. Until implemented, do not fake a passing loop.

PR checks: formatting/lint/types/unit/contracts/integration/frontend/security/build.
Release automation ultimately builds artifacts, GHCR/Python/JS packages, checksums
and categorized releases. No invented installer URL, community link, or release badge.
Release targets: Genesis 0.0.1, Discovery 0.1, Memory 0.2, Evolution 0.3, Frontier 0.4,
Ecosystem 0.5, Open World 1.0. Pre-1.0 APIs are experimental.

Founder-led, community-contributed, maintainer-reviewed governance. Bug fixes,
adapters, tests/docs/examples/benchmarks welcome. Architecture, public API, UI,
novelty, lifecycle, and schema changes require design review/RFC. Founder controls
roadmap/releases/brand/appointments/governance/core architecture initially.
AGPL-3.0 source licensing is separate from branding/non-affiliation policy.

No Kubernetes, enterprise RBAC, multi-region, autonomous promotion, multimodal,
automatic hierarchy generation, billing, hosted cloud, or speculative provider count
in v0.1. Every feature requires types, tests, migrations when needed, documented API,
errors and observable events. Keep intermediate changes buildable.
