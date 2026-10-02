# OpenClass — implementation phases for a real business SaaS

Date: 2026-10-02. Status: **implementation roadmap; no phase certified complete**.

This folder turns the founder's ten-phase direction into bounded execution briefs for future agents. Deliver the central adaptive loop before expanding integrations or polishing disconnected experimental surfaces:

**Create → Connect → Decide → Observe → Investigate → Propose → Evaluate → Approve → Version → Act/Verify → Measure.**

A class, endpoint, provider card or screenshot is not a completed feature. Completion requires persisted domain behavior → public API → SDK → actual UI → user action → durable result → restart/reconstruction, with permissions, failures and measured evidence.

## Read and execute in this order

| Order | Implementation brief | Main gate | Status |
|---|---|---|---|
| 01 | [Project, data and persistence](01-real-project-data-foundation.md) | Isolated authenticated projects; restart-safe real ingestion/state | Planned |
| 02 | [Canonical decision runtime](02-canonical-decision-runtime.md) | Enforced real provider bindings and historical spec identity | Planned |
| 03 | [Trust, UNKNOWN and supervision](03-trust-unknown-supervision.md) | Conservative deterministic gating; independent risk/coverage evidence | Planned |
| 04 | [Runs, traces and audit](04-runs-traces-audit.md) | Reconstructable success/failure/version history and honest usage | Planned |
| 05 | [Evidence, cohorts and discovery](05-evidence-cohorts-discovery.md) | Frozen distinct-source cohorts; non-destructive cluster history | Planned |
| 06 | [Supervisor and typed proposals](06-supervisor-typed-proposals.md) | Real evidence-linked advisory changes, with no mutation authority | Planned |
| 07 | [Evaluation, replay and shadow](07-evaluation-replay-shadow.md) | Complete independent baseline/candidate comparison and regression gates | Planned |
| 08 | [Approval and immutable activation](08-approval-immutable-activation.md) | Reviewed vN → vN+1, atomic activation and rollback-as-new-version | Planned |
| 09 | [Controlled actions and integrations](09-controlled-actions-integrations.md) | Authorized external effect plus independent verification/recovery | Planned |
| 10 | [Product and SaaS operations](10-saas-product-operations.md) | Whole lifecycle plus tenant security, quotas, recovery and business pilot | Planned |

Read [AGENT-HANDOFF](AGENT-HANDOFF.md) before any phase. Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) after each implementation. Work serially on numbered gates; independently executable tasks within a phase may be batched, but later phases cannot bypass prerequisites.

## Authority and existing plans

- [Canonical specification](../architecture/SPECIFICATION.md), [Genesis](../architecture/genesis.md), [ticket backlog](../contributing/tickets.md) and [RFC template](../contributing/rfc-template.md) remain authoritative for architecture/invariants and stable ticket IDs.
- [Product experience target](../OpenClass_Product_Experience_Platform_Spec.md) defines the intended user journey; it is not an implementation audit.
- [Application proof program](../architecture/application-proof-program.md) supplies real execution, integration and metric requirements. Its prior immediate ordering emphasized execution earlier. The founder's newer request supplies this ten-phase sequence; preserve OC-034–039 and reuse their scope rather than duplicating their services. Read-only capability/API feasibility work may happen earlier, but external action certification is Phase 09.
- The old specification excludes hosted SaaS/billing from v0.1. Phase 10 is a later founder-requested productization target with new scoped tickets/RFCs. It does not rename Genesis, relax Discovery release gates or authorize public deployment/publication.
- Automatic promotion remains deferred. Initial business deployment uses human-reviewed activation and conservative action approvals. A future guarded-autonomy phase requires separate evidence and scope.

## Baseline and facts versus targets

There are at least two relevant baselines: the current project checkout and the isolated `origin/feat/portal-phase-10` checkout used for the real challenge. The latter started at `d539862` and received an unmerged local real-provider patch. Branch-only portal/control-plane files are not assumed present in the current checkout. Every agent must capture its own branch/commit/dirty state and audit actual wiring before claiming reuse or completion.

The [retained challenge report](../../artifacts/application-proofs/scikit-learn-2026-10-02/REPORT.md) and [results](../../artifacts/application-proofs/scikit-learn-2026-10-02/results.json) describe 60 real GitHub issues per provider attempt: GPT completed 56, Gemini 38. Trusted-reference disagreements were 12/51 and 7/36. These are small curated source-label comparisons with incomplete coverage, not certified business accuracy or a fair provider ranking. The patch/artifacts must be inspected before reuse; no secret is part of this roadmap.

Reported implementation gaps include provider-card binding, service instruction transport, uncalibrated trust, core audit decoding, latest-N evidence selection, destructive reclustering, missing replay and unproven activation/external verification. Some are reproduced runtime failures; others are code-inspected or unimplemented gates. Keep those distinctions in future evidence. Inactive or insufficient-evidence proposals are valid safety outcomes, not proof that discovery needs to invent a new class.

Any threshold, SLO or improvement target in these briefs is **proposed acceptance**, never a measured result. Existing implementation status documents can be stale; fresh evidence is required. No percentage-complete estimates are supplied.

## Shared business pilot

Choose one actual support/developer issue-routing operation with an operator who can authorize data and resources. Start with public issues for development; acquire authorized real business tickets before claiming business usefulness. Keep domain configuration/adapters outside Core.

1. Define 5–10 meaningful known choices, at least one withheld concept, ambiguous/out-of-domain items, missing-state inputs and historical retained cases. Choose counts from the statistical/business risk gate; do not fabricate rows to satisfy a quota.
2. Freeze input hashes, provenance, label-review process, discovery/calibration/test splits, failure accounting, risk limits and operational success criteria **before** provider runs. Selection/truncation rules and title cues must be disclosed.
3. Before evaluation, route all unvalidated predictions through review. Preserve incorrect confident decisions and failed requests. No production write follows confidence alone.
4. Build a candidate only from sufficient independent evidence. Evaluate it against the same retained independent-reference dataset before human approval; failed evaluation remains blocked.
5. After approved v2, measure later real reuse and known-case retention, with exact versions and usage. Calling an LLM on every event again does not prove an avoided-Teacher fast path. If no fast provider meets risk/latency gates, report that blocker honestly.
6. Phase 09 adds one authorized low-risk external routing action and independent destination readback. Phase 10 adds isolated tenants, operational recovery and a named business pilot over a declared period.

Do not cherry-pick a new dataset after failures and report only that success. A failed improvement proposal may pass safety tests while the business improvement claim remains unproven.

## Gates, sequencing and exceptions

- Phase 0, before Phase 01: choose the target branch, inventory existing changes, identify canonical app/API, reproduce baseline checks and preserve unrelated work. No migration or implementation starts against an ambiguous target.
- Security is incremental: authentication and project/tenant isolation begin in Phase 01, provider secrets in Phase 02, review authority in Phase 08 and execution grants in Phase 09. Phase 10 hardens hosted operations; it is not the first security phase.
- Engineering completion and live-quality/business certification are separate. Fixtures can prove failure handling but cannot certify real model quality, real payment handling or real external effects.
- A blocked quality gate may allow clearly labeled review-only development, but cannot authorize a later production activation/action or mark the dependent business gate complete.
- Existing failed checks must be reproduced and resolved on the actual target branch. If an unrelated blocker prevents completion, record it explicitly rather than silently exempting the gate.
- Architectural/public API/schema changes follow the existing RFC/design-review process. This roadmap authorizes preparation of concrete implementation plans; do not invent an extra permission flow for routine reversible work. Deployment, publishing, live billing and third-party writes require their actual scoped authorization.

## Delivery shape

Each phase produces small runnable PRs, explicit migrations, contract/API docs, public typed SDKs, product UI, meaningful negative-path tests and a completed evidence record. Use a phase-local RFC when needed and map work to existing OC tickets; only create new SaaS tickets for genuinely new scope.

A paying-customer launch additionally requires all Phase 10 gates, declared support/SLO ownership and a reviewed deploy/rollback plan. No marketplace, multi-region cluster or enterprise feature catalog is needed to prove the first business use case.
