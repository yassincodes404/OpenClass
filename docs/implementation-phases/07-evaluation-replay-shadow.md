# Phase 07 — Evaluation, Replay, Regression & Shadow Testing

Status: **planned, not audited complete**. Sequence: 7/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Evaluation, Replay, Regression & Shadow Testing must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 06 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-008, OC-013, OC-017, OC-037. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect evaluation endpoints and fail-closed 409 behavior, evolution services, benchmark/report code and verified feedback. Distinguish stored evidence counts from evaluation outcomes.
The tested branch explicitly lacked verified replay evaluation. Keep activation blocked until this phase supplies genuine comparison evidence. Do not interpret 28 adapter tests as a learned-quality evaluation.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Define immutable EvaluationSetVersion with independently reviewed/verified label provenance, split membership, hashes and scope. Separate discovery/calibration data from held-out evaluation; predictions and Supervisor suggestions never become reference labels automatically.
2. Cover known/rare/hard historical cases, withheld concepts, ambiguous/out-of-domain cases, missing/stale state and relevant hostile inputs. Record disagreements and reviewer resolution; retain unresolved cases outside claimed accuracy denominators.
3. Materialize a candidate overlay without activating it. Freeze baseline/candidate spec, ontology, policy and provider profiles; replay exactly the same eligible inputs under both configurations.
4. Persist EvaluationRun, every item/attempt, missing/failure/cancel state, protocol/metric version, labels, latency and usage. Provide bounded concurrency, tenant budgets, progress and resumable work; do not introduce a broker before establishing the need.
5. Compute hand-verifiable retention, per-class quality, UNKNOWN behavior, selective risk/coverage, completion, regression counts and costs. Null/undefined values and missing-cost coverage remain explicit. Use declared noninferiority/improvement gates and sample uncertainty.
6. Enforce schema/canonicalization/security checks plus per-risk quality and cost/latency limits. Provider failure, partial completion, missing labels or insufficient sample size cannot produce PASS by omission.
7. Implement read-only shadow decisions on later real traffic with no external side effects; compare against baseline using delayed independent outcomes. Historical replay is distinguishable from new-traffic shadow evidence.
8. Deliver evaluation start/progress/cancel, baseline-candidate comparison, per-item replay and gate explanations through API/SDK/UI. Emit immutable result artifacts/hashes suitable for Phase 8 approval.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

EvaluationProtocolVersion, EvaluationSetVersion, VerifiedReference, CandidateOverlay, EvaluationRun/ItemResult and GateResult(PASS/FAIL/INCOMPLETE). PASS refers to a specific complete manifest, base/candidate/config identities and gate policy.
Events: evaluation.started/progressed/completed/failed/cancelled and regression.blocked. Replay does not perform writes to external systems. Phase 9 verifier outcomes can later extend the same protocol without relabeling earlier evidence.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- Hand-computed fixtures validate all metrics including zero denominators, sparse labels, failures and missing costs.
- Known regression or increased unsafe trust fails evaluation even if new-concept recall improves.
- Invalid/incomplete/cancelled evaluation cannot be approved; dataset/provider/spec changes invalidate the comparison rather than reusing a stale PASS.
- Run a real baseline/candidate comparison on frozen independently reviewed business cases with retained source hashes and complete attempt accounting.
- Shadow mode proves it does not execute outbound actions and isolates each tenant's budget/data.
- Results and per-case disagreements remain inspectable and reproduce from saved manifests after restart; hosted model variation is documented, not claimed bit-identical.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

A live-provider test can be opt-in; offline CI uses marked fixtures. Real-business quality gates additionally require live data/providers. No forced percentage improvements, invented costs or automatic gold labels.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
