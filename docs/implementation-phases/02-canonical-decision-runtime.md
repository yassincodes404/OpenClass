# Phase 02 — Canonical Decision Model & Real Provider Runtime

Status: **planned, not audited complete**. Sequence: 2/10. Release status: no release or SaaS-readiness claim.

## Outcome and entry gate

Canonical Decision Model & Real Provider Runtime must be a persisted vertical slice that a real business operator can use through the public API, SDK and actual product UI.

**Depends on:** Phase 01 gate evidence accepted; retain every preceding invariant. See README for scoped exception handling.

**Existing ticket mapping:** OC-003, OC-004, OC-017, OC-034. Preserve OC identifiers; draft scoped child tickets rather than renumbering the backlog.

Read [README](README.md) and [agent handoff](AGENT-HANDOFF.md) before implementation. Follow repository AGENTS.md and the canonical specification. This document specifies intended behavior; an agent must verify every current-state claim against its chosen commit.

## Audit first

Inspect core/decision.py, decision_executor.py, providers.py, server/provider_config.py, settings.py, api/decisions.py and providers/{jev,laya,glm}. Trace service instructions to the actual provider request. Inspect adapter registration and the live model identity, not provider cards alone.
The challenge needed local gateway wiring and explicit model overrides; the patch is not automatically part of the target branch. Jev access failed with HTTP 403. A fallback implementation is not evidence that Jev works.

Produce an exists/wired/simulated/broken/missing matrix with file, route, migration and test evidence. Do not spend the phase reimplementing working behavior. Review architectural/API/schema changes using the repository RFC process before landing them.

## Ordered implementation slices

1. Specify immutable DecisionSpecVersion: task instructions, UNKNOWN guidance, state schema, bounded nodes/choices and output schema. Preserve semantic Choice identities independently of provider names and future transitions.
2. Migrate existing mutable service definitions to deterministic initial snapshots. Bind every completed run to the exact spec, ontology, input snapshot, provider profile and binding versions used.
3. Carry the full approved DecisionSpec through the provider-neutral request. Contract-test that task instructions and exclusion rules reach every adapter without vendor fields leaking into Core.
4. Make project/service provider bindings operational. Resolve precedence deterministically, validate supported model capabilities and snapshot nonsecret configuration at execution. Editing a provider card cannot silently change historical runs.
5. Reuse and review the real gateway patch where appropriate. Implement strict bounded structured output, exact choice keys plus UNKNOWN, finite distributions and score provenance. A self-assessed score is not a calibrated probability.
6. Implement bounded timeout, retry budget, cancellation and explicit configured fallback. Unknown provider/model fails closed. Record each attempt and fallback identity; never silently substitute a mock or different model.
7. Support the adapters justified by the application: one real fast provider and one independent real comparison provider. Attempt Jev with authorized access and document availability; unavailable Jev blocks Jev-specific release claims without blocking provider-neutral development.
8. Deliver provider setup/test, service graph/choices and real run details via API/SDK/UI. A connectivity test, credential validity and demonstrated inference readiness are separate statuses.

Each numbered slice includes domain/service, persistence when required, public API, typed SDK, actual UI, errors/events and meaningful verification. Keep intermediate commits runnable. Work in bounded PRs; do not deliver only backend scaffolding and call the phase complete.

## Contracts, persistence and observable behavior

DecisionSpecVersion, DecisionNode, SemanticChoice, ProviderProfileVersion, ProviderBindingVersion, DecisionRequest, DecisionResult and ProviderAttempt need typed boundaries. Include full distribution, selected choice, top/second score, margin, UNKNOWN signal availability, score kind/calibration identity, execution mode, model, usage and safe error.
Provider adapters implement Core ports; transports, credential resolution and SDK dependencies remain outside Core. New spec changes are drafts pending Phase 7/8 activation, not writable runtime shortcuts.
Events: decision.started/completed, provider.attempt_completed/failed, provider.binding_created and decision.spec_created.

Schema changes use explicit Alembic migrations, including upgrades from existing data. Core owns deterministic rules/ports; providers/adapters cannot write ontology. UI/CLI access public HTTP SDKs. Secrets, raw sensitive payloads and upstream credential-bearing errors stay out of source, fixtures, logs and events.

## Business proof and exit criteria

- The same immutable business decision works through two actual available providers without rewriting its choices or state schema.
- Stored instructions can be shown to have reached the inference request through safe contract inspection; no customer prompt/key logging is required.
- Malformed, missing, extra, nonfinite or out-of-range output is rejected without becoming a semantic UNKNOWN.
- Profile changes, fallback and concurrent configuration edits retain the exact binding used by historical runs.
- Wrong-tenant bindings, unknown models, unavailable daemons, 403, 429, timeout and cancellation produce distinct inspectable outcomes; no hidden simulation occurs.
- UI reports the actual selected model and immutable spec identity after restart.

The shared pilot is real business issue/support routing with independently reviewed references, authorized external resources and a deliberately withheld concept. Use the retained scikit-learn cohort as a development probe, not a substitute for customer outcomes. Run the phase through the actual product and retain negative findings as well as success evidence.

## Required checks and evidence

- Run meaningful unit/contract tests for the changed rules and failure paths; run PostgreSQL integration checks against a disposable explicitly migrated database.
- Run `make check`, `make test`, `npm run build` and `uv build --all-packages` on the actual target branch. Document the supported frontend/package-manager setup from its development guide; app-specific builds do not silently substitute for required repository gates.
- Add/run public API + SDK + browser E2E for the acceptance behavior and a reload/API/database restart check where relevant. Opt-in live calls use runtime credentials and measured usage; credential-free CI may use clearly marked fixtures.
- Fill [PHASE-EVIDENCE-TEMPLATE](PHASE-EVIDENCE-TEMPLATE.md) with commit, environment, commands, results, IDs/hashes, source/label authorization, coverage and limitations. Do not retain tokens, customer secrets or unnecessary personal data.
- Mark COMPLETE only when all phase criteria and prerequisite gates pass. A pre-existing failed check is recorded and repaired or remains a named blocker; it is not a passing-release claim. Preserve independent quality/business gates even when engineering tests pass.

## Scope limits and risks

Do not implement every boolean, score or graph operation speculatively. Version the single-choice vertical first. GPT/Gemini quality does not establish fast-path latency; measure the real chosen fast provider.

## Handoff

Provide the reviewed commit/PRs, migrations and rollback instructions, public contract changes, UI routes, persisted proof artifact references, actual check results and remaining blockers. Update phase status in README only with linked evidence; never copy planned/sample figures into measured product metrics.
