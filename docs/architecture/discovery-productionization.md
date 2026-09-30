# Discovery productionization reconciliation

Date: 2026-09-24. Status: implementation plan for review, not a release claim.
Baseline supplied by the founder: `9118f21042508ec60deae4e68270b9e3e2f16e80`.
The working tree contains uncommitted experiments beyond that baseline. Their
presence does not establish that public main ships Discovery.

## Direction and sequencing

OpenClass converts novel reasoning into validated, reusable decision knowledge.
The platform direction is independent projects with explicit domain types sharing
evidence, candidate, evaluation, approval, immutable version and audit disciplines.
Models propose; deterministic services evaluate and apply authorized changes.
UNKNOWN remains permanent. Infrastructure failure is never semantic evidence.

Preserve frozen Proof #1 at `build/self-expansion/20260923T225905Z/`, including its
manifest and database. It is historical mechanism evidence, not a production
reliability benchmark. Do not run migrations or revised scripts against that DB.
Proof #2 requires real Jev failure, real discovery, behavioral evaluation, explicit
human approval, identical replay with discovery disabled, and a different-instance
replay with discovery disabled. Offline scripted replay only verifies the evaluator.

Immediate order: repair Proof #2 Stage A; stop at a passing candidate for human
approval; complete Runs 2/3 only after approval. Separately productize OC-003–009
on a reviewed branch. Then OC-017/018, Project isolation, and the broader platform.
Do not implement analytics, n8n, or the multi-project UI before this reconciliation
is presented and the production Discovery foundation is established.

## Experiment reuse assessment

| Existing code                                    | Reuse decision                                     | Required work before product integration                                                                                                                                                   |
| ------------------------------------------------ | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `providers/jev/` and its contracts               | Reuse adapter/fixtures after review                | Shared provider contracts, bounded retry/error taxonomy, secret-safe telemetry, privacy policy, unsupported-response tests; real model success remains a separate opt-in gate.             |
| `provider_config.py`, server settings            | Reuse configuration concepts                       | Provider-neutral bindings, opaque environment secret references, safe validation and minimal context; later project scoping.                                                               |
| `providers/glm/`                                 | Reuse transport/structured response lessons        | Reconcile vendor naming with OpenAI-compatible discovery, shared contracts and Ollama implementation; preserve all six proposal types and alias/existing-match fields.                     |
| `core/discovery.py`                              | Reuse evidence lookup and base-version intent only | Replace evidence-count-only evaluation, hard-coded tablet alias, shallow canonicalization and limited evidence lookup. Require persistent evaluation identity and lifecycle transitions.   |
| Candidate models/repository and migration `0003` | Review schema as a prototype                       | Explicit evidence relations, reject/transition rules, immutable evaluation records, approval provenance, transactional current-version comparison. Never mutate the frozen proof database. |
| Self-expansion scripts                           | Reuse scenario as acceptance evidence              | Convert into reproducible E2E fixtures with independently verified labels and separate baseline/candidate replay. No production activation through experiment shortcuts.                   |
| Automation models/executor/Stage A               | Keep experimental                                  | File-backed records are not production persistence. Complete three-run proof and review typed state/macro execution, confinement and postconditions before OC-029 integration.             |
| Current experimental web changes                 | Review separately                                  | UI must use public SDKs; no lifecycle rules in UI. No platform UI expansion now.                                                                                                           |

The current `DiscoveryService.evaluate()` emits a passing event based solely on
three evidence IDs. `approve()` adds a `tab` alias specifically for `tablet`.
Neither behavior is acceptable production evaluation/canonicalization. Historical
Proof #1 had a separate replay script; that does not make the API evaluation gate
safe. Existing experiments must not be advertised as the production lifecycle.

## Reviewable implementation slices

1. **OC-003/004: providers.** Extract shared contracts, configuration/privacy policy,
   safe error categories, timeout/retry bounds and usage provenance. Capture Jev
   output with UNKNOWN intact; never manufacture success or missing usage. Validate
   provider failures without credentials in mandatory CI.
2. **OC-005/006: evidence and discovery.** Add explicit migrations for grouping and
   embedding provenance. Group only within the owning classifier (and project once
   projects exist). Implement reproducible grouping, idempotent evidence membership,
   all six proposal outcomes, canonicalization against names/aliases, and bounded
   structured responses. Add heavy embedding dependencies only with an implemented
   adapter and contracts.
3. **OC-007: candidate lifecycle.** Persist exact base version, observation evidence,
   proposal provenance and review transitions. Reject duplicate/unavailable evidence,
   illegal transitions and unsupported activation types. Add inspect/list/reject
   APIs, typed SDK access, minimal review UI and safe events.
4. **OC-008: verified evaluation.** Migrate immutable datasets/examples, verified-label
   provenance, evaluation runs/results and version/dataset hashes. Replay identical
   verified data against baseline and candidate. Persist known accuracy/macro F1,
   unknown precision/recall, coverage and regression limits, with undefined metrics
   explicit. A failed/incomplete provider call cannot pass; predictions cannot label
   the test set. Independently hand-check metric fixtures.
5. **OC-009: guarded evolution.** Require a passing evaluation tied to candidate,
   base version, dataset and policy; explicit human authority; current-state checks
   in the same transaction as version creation and pointer update. Test concurrent
   promotions on disposable PostgreSQL. Implement versioned ADD/ALIAS/REJECT, diffs,
   replayable events and rollback as a new version. Keep prior snapshots byte-identical.
6. **Public vertical.** Complete API errors/docs and SDK contracts for each slice,
   then minimal CLI/web evidence → diff → evaluation → approval UX. Reproduce the
   tablet story in a new database, including regressions and failure paths. Never
   overwrite or relabel historical artifacts.

Each slice requires core types/ports → repository/migration → service → API → SDK
→ minimal UI as appropriate, with meaningful tests and events. Use isolated reviewed
commits; do not bulk-copy this dirty experiment tree into main. Establish a clean
baseline branch only after preserving the current work and selecting reusable files.

## DecisionSpec and Project migration plans

**OC-017:** Introduce immutable DecisionSpecVersion, deterministic default v1 for
existing classifiers, active pointer and run/review references. Backfill historical
runs to the actual legacy default semantics with migration provenance, not a claim
that an unrecorded custom instruction was captured. New requests atomically capture
both ontology/spec identities. Read APIs first; spec activation later uses the same
evaluation/approval boundary. Compatibility tests retain old classifier routes.

**OC-021:** Add Project/ProjectConfig and scoped ProviderBinding. Migrate legacy data
into an explicit default project; backfill scope through classifier ownership,
including ontology, observations, unknowns, candidates, evaluations and events.
Until Project lands, new Discovery objects inherit classifier ownership; this is a
transitional scope, not independent multi-project support. Add foreign keys and
repository methods requiring owner scope, then project routes and SDK methods.
Keep existing routes as documented default-project compatibility routes during a
migration window. Global UUIDs remain unambiguous; every lookup still checks scope.
Prefer project deactivation to deleting append-only history. Test two projects with
different bindings, cross-project ID rejection, evidence isolation, and independent
activation/deactivation. No enterprise RBAC or managed workflow runtime now.

## Expansion backlog (proposed, not implemented)

Preserve OC-001–020 numbering and dependencies.

| Ticket | Scope and gate                                                                                            |
| ------ | --------------------------------------------------------------------------------------------------------- |
| OC-021 | Project workspace/isolation; two-project persistence/API tests.                                           |
| OC-022 | Extend OC-019 into project chat; typed audited tools, external approval authority.                        |
| OC-023 | Versioned AnalyticsSpec, dimensions, deterministic metrics, queries and backfill; direct ingestion first. |
| OC-024 | Analytical evolution; evaluated/approved changes and version-aware backfill without raw-event rewrites.   |
| OC-025 | Declarative QuerySpec/ViewSpec and versioned dashboards; no generated JavaScript.                         |
| OC-026 | WorkflowProvider only alongside a real implementation and contract suite.                                 |
| OC-027 | BYO n8n adapter; symbolic secrets, project scope, audited drafts and guarded activation.                  |
| OC-028 | Customer-intelligence showcase using authorized/test feedback; emerging feature discovery and backfill.   |
| OC-029 | Automation module only after full three-run proof and persistence review.                                 |
| OC-030 | Support example: known workflow, novel assistance, verified reusable resolution, analytics.               |
| OC-031 | Project-centric UI after underlying capabilities exist.                                                   |
| OC-032 | Frontier-only comparison: quality, latency, measured costs/calls, review burden and reuse.                |

OpenClass owns project semantics and governance; optional workflow integrations own
external plumbing. A no-n8n deployment remains fully supported. Managed n8n, arbitrary
shell, generated frontend code, enterprise infrastructure and automatic promotion
are outside the immediate scope.

## Release/expansion checkpoint

- Proof #1 preserved and reproducible in a separate environment.
- Proof #2 completed or its failure understood; no adaptive automation claim yet.
- Reviewed Discovery branch with persistent candidate/evaluation/version lifecycle.
- Real decision/discovery adapters behind configuration; retry/redaction/failure tests.
- DecisionSpec and Project migration plans reviewed and compatibility tested.
- Reports/artifacts secret-safe; no invented quality or economic claims.
- `make check`, `make test`, `npm run build`, `uv build --all-packages`; PostgreSQL
  integration and migration checks against a disposable migrated database.

No publication, release, activation or approval is implied by this plan.
