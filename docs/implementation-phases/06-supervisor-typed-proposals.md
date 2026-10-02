# Phase 06 — Supervisor Intelligence & Typed Evolution Proposals

Status: **planned, not audited complete**. Sequence: 6/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Supervisor Intelligence & Typed Evolution Proposals must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 05 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-006, OC-007, OC-016, OC-018, OC-019, OC-020. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect supervisor.py, project_evolution.py, discovery.py, GLM diagnosis/project_teacher adapters and candidate API. Identify overlapping classifier/project/cluster candidate representations before adding another lifecycle.
The challenge persisted real insufficient-evidence proposals and an existing-UNKNOWN Teacher recommendation. Inactivity is the required safety boundary; more ADD_CHOICE proposals would not by itself demonstrate better discovery.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Define a canonical typed candidate envelope spanning supported existing proposal families, with base version/hash, target, diagnosis, evidence cohort, structured change, rationale, provider provenance and lifecycle. Provide compatibility views/migrations instead of multiplying parallel models.
2. Implement diagnoses for bad prediction, decision-space gap, missing state, policy issue and operational/execution failure. Keep each diagnosis advisory; one UNKNOWN cannot establish a new concept.
3. Implement the minimum useful mutation families first: ADD_CHOICE, ALIAS, CHANGE_DECISION_INSTRUCTIONS and CHANGE_SUPERVISION_POLICY. Specify unsupported families explicitly; later transition/capability proposals depend on Phase 9 contracts.
4. Expose read-only Supervisor tools over scoped run/state/evidence/version records. The provider receives minimal necessary external content and no database handles, credentials or writable ontology ports.
5. Validate schema, canonical names/aliases, minimum distinct evidence, target compatibility and base version. Resolve synonyms/existing choices before proposing novelty. Repeated proposal requests use stable idempotency identities.
6. Add real structured reasoning adapters with timeout, malformed-response handling, prompt-injection confinement, budget/cancellation and usage capture. Scheduled/triggered reviews run outside the synchronous fast path and obey tenant budgets.
7. Implement draft/collecting/ready/rejected/superseded states, append-only edits as revisions and rejection reason/actor. A human correction is labeled as human feedback, not silently verified universal truth.
8. Deliver an evidence-linked candidate editor and optional management chat that invokes the same services. Chat can request a proposal/evaluation but cannot approve on behalf of a person or grant capabilities.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

CandidateRevision, Diagnosis, ProposalChange discriminated union, SupervisorRequest/Result and CandidateLifecycleTransition. Validate family-specific payloads and supported operations server-side.
Events: supervisor.started/completed/failed, candidate.created/revised/rejected/superseded. Candidate selection must include explicit base version and evidence identity. DRAFT and insufficient-evidence findings remain inspectable without pretending to be activatable knowledge.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- Real independently sourced evidence produces an inspectable typed proposal or a justified insufficient-evidence/existing-concept result through the UI.
- Ambiguity, synonym, missing state and provider outage examples do not all become ADD_CHOICE.
- Prompt content requesting direct mutation, foreign-tenant reads or credential disclosure cannot cross service boundaries.
- Duplicate/stale requests, invalid payloads, bad enums and failed provider calls preserve existing state and produce safe events/errors.
- Model output cannot activate a choice, mutate a spec, approve itself or mark labels verified.
- Candidate revisions and rejection remain attributable, source-linked and readable after restart.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Do not require a Supervisor to invent a class merely to make an E2E look successful. Do not implement all target proposal families, arbitrary code generation or autonomous promotion in this phase.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
