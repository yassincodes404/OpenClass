# Phase 05 — Evidence Cohorts, UNKNOWN Clustering & Gap Discovery

Status: **planned, not audited complete**. Sequence: 5/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Evidence Cohorts, UNKNOWN Clustering & Gap Discovery must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 04 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-005, OC-006, OC-007, OC-020. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect evidence.py, discovery.py, api/evidence.py and clustering/discovery routes if present on the target branch. Trace foreign-key deletion behavior, cohort query bounds and source identity.
The real challenge used Cohere embeddings, but the original portal endpoints were simulated. Latest-200 selection, unsourced extra observations and code-inspected delete/cascade behavior are specific gaps. INSUFFICIENT_EVIDENCE is a legitimate outcome, not a failed product state.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Model immutable EvidenceCohortVersion with project/service/spec/policy/model filters, period, inclusion/exclusion rules, source identity rule and a materialized member list/hash. Query all eligible rows through stable pagination instead of a latest-N shortcut.
2. Distinguish observation, attempt, decision and verified feedback. Count distinct sources for novelty evidence; repeated calls or model variants do not create independent support. Missing provenance is quarantined or explicitly excluded.
3. Bind embeddings to content hash, provider/model/dimension/normalizer version and privacy settings. Cache only within approved scope. Never combine incompatible vectors or treat simulated embeddings as real evidence.
4. Persist each clustering run as a new snapshot with algorithm/settings, cohort version, embedding identities and memberships. Remove destructive replace/cascade paths; previous clusters, candidate links and reviews remain addressable.
5. Implement new grouping/split/merge snapshots with lineage instead of rewriting membership. Manual grouping records actor/reason and retains original evidence. Add cancellation/resumption and bounded processing appropriate to measured load.
6. Configure minimum distinct evidence, recurrence and domain checks. Infrastructure failures are a separate operational cohort, not proof of a new semantic concept.
7. Deliver evidence/cohort filters, cluster comparison, source lineage, excluded rows and Ask Supervisor through public SDK/UI.
8. Re-run clustering on the original frozen sources and a separately authorized customer cohort. Preserve negative findings and compare versions without changing old proposals.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

EvidenceItem, EvidenceCohortVersion, EmbeddingArtifact, ClusteringRun, ClusterSnapshot, ClusterMembership and ClusterLineage. New database ownership and immutable-history constraints require migrations.
Events: cohort.frozen, embedding.completed/failed, clustering.started/completed/failed and cluster.lineage_created. API supports paginated member inspection and version selection; a candidate always references the frozen evidence used to create it.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- Re-clustering twice cannot delete or alter an earlier cluster, review, proposal or evidence link, including through foreign-key cascades.
- A cohort exceeding 200 runs is processed completely; retries and multi-provider attempts do not inflate distinct-source counts.
- Unprovenanced rows and wrong-project/service records are rejected/excluded with inspectable reasons.
- Real embedding provenance and settings reproduce membership on deterministic fixtures; live algorithm nondeterminism is recorded, not concealed.
- UI displays current and previous cluster snapshots and follows any candidate back to exact frozen source events after restart.
- Fewer than the required distinct sources produces insufficient evidence without manufacturing members.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Do not add heavyweight clustering packages or an external vector database merely to expand the stack. Start with a documented deterministic grouping algorithm and existing PostgreSQL/pgvector capabilities if adequate.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
