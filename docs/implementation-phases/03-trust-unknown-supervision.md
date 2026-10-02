# Phase 03 — Trust, UNKNOWN & Deterministic Supervision

Status: **planned, not audited complete**. Sequence: 3/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Trust, UNKNOWN & Deterministic Supervision must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 02 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-003, OC-008, OC-017, OC-020. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Trace novelty.py, decision_executor.py, stored supervision reasons, evidence routing and UI badges. Identify which scores are vendor confidence, self-assessment or calibrated estimates.
In the frozen challenge GPT had 12/51 and Gemini 7/36 TRUSTED-reference disagreements. Completed-case withheld detection was 4/11 and 2/3, with substantial failures. These are probe findings, not universal model accuracy or grounds for ranking.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Separate semantic prediction, uncertainty assessment, supervision disposition and action authority. Define known/uncertain/likely_novel plus reasons; UNKNOWN remains permanent and can mean ambiguity, missing state or domain mismatch.
2. Version deterministic SupervisionPolicy per service/risk tier. Inputs include score provenance, margin, UNKNOWN signal, required-state completeness/freshness, provider health and applicable cost/latency budgets. Unsupported signals are unavailable, never fabricated zeros.
3. Default uncalibrated providers to advisory/review dispositions. A generic high-margin threshold cannot earn TRUSTED status on unvalidated self-assessment. Calibrated trust profiles are scoped to model, spec, cohort/domain, risk and evaluation identity.
4. Implement typed outcomes: continue, review, unknown, request-state, human, retry, fallback and block as actually supported. Retry/fallback must respond to operational failure, not silently reinterpret it as novelty. No trust disposition grants execution permission.
5. Define independently reviewed known, withheld, ambiguous, missing/stale-state and adversarial-input partitions before tuning. Fit any thresholds on a calibration split; freeze a separate held-out test split and retain all failed attempts.
6. Evaluate selective risk/coverage, trusted error rate, UNKNOWN precision/recall, operational completion and calibration where mathematically supported. Include confidence intervals/sample counts and separate completed-only semantic metrics from full-cohort operational yield.
7. Expose policy controls, explicit reasons and review queues in the UI. Show score kind and calibration status instead of marketing every number as probability.
8. Add sampling of apparently trusted decisions and drift/expiry invalidation. Unvalidated provider/spec changes revert to review; a threshold tuned on one tenant cannot silently authorize another tenant's high-risk workflow.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

SupervisionPolicyVersion, ScoreProvenance, TrustProfile, NoveltyAssessment, SupervisionDecision and ReviewTask. Persist reason codes and the exact inputs/policy version, not only a TRUSTED string.
Events: supervision.assessed, review.requested, trust_profile.invalidated and state.requested. Preserve current public enums or provide explicit compatible mappings.
Proposal target for a low-risk pilot: independently checked trusted error rate ≤1% with the upper 95% uncertainty bound also below the signed risk limit. This is a proposed gate, not an achieved result; tighter business thresholds require separate evidence.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- A deliberately wrong high-confidence uncalibrated answer is routed to review and cannot authorize an action.
- Missing/stale state, unavailable UNKNOWN signal and provider outage produce different deterministic reasons.
- A frozen test measures risk and coverage against a predeclared business gate; thresholds are not retuned on the held-out data to manufacture a pass.
- Known, novel and ambiguous real cases are retained and human/reference provenance is visible. Insufficient labels/sample size fails the trust claim rather than relaxing its limit.
- UI explains why a run was trusted/reviewed and displays operational failures separately from UNKNOWN.
- Policy changes are immutable drafts for Phase 7/8; existing run assessments remain unchanged.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Zero false trust on a tiny sample is not proof of safety. It is acceptable to finish conservative supervision implementation with no certified automatic fast path yet; record that quality gate as blocked and keep business actions human-approved.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
