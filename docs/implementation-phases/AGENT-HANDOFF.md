# Agent execution contract

Use this alongside the selected numbered phase. It is an implementation brief, not permission to certify future features from names alone.

## Copyable task

> Implement Phase NN from `docs/implementation-phases/NN-*.md` on the reviewed target branch. First read repository AGENTS.md, canonical architecture, Genesis, tickets, the roadmap README and prerequisite evidence. Trace actual DB → domain/service → API → SDK → UI → persisted outcome. Audit existing, wired, simulated, broken and missing behavior. Produce a bounded implementation/RFC where required, reuse working code, add explicit migrations and meaningful failure-path tests, and complete real UI/restart proof. Preserve independent labels, immutable versions/audit, provider neutrality and secret safety. Never bypass replay/review/activation guards, turn predictions into truth or report simulation as live business evidence. Complete the evidence template and report blockers; a class or endpoint alone does not close the phase.

## Before editing

1. Record branch, HEAD, worktree and dirty files. Preserve unrelated edits; use a separate worktree when needed. Confirm whether the real-provider patch is actually merged and which app is supported.
2. Read `docs/architecture/SPECIFICATION.md`, `genesis.md`, `docs/contributing/tickets.md`, relevant product sections, development/validation guides and applicable nested AGENTS.md.
3. Capture baseline installation/check failures without secrets. Identify a disposable migrated PostgreSQL database for persistence tests; never run destructive tests on the real pilot workspace.
4. Produce the phase audit matrix below, with references to actual source/migrations/routes/tests and a runtime check. Inspect both the engine and any control plane; a secured UI cannot protect an exposed unauthenticated backend.
5. Confirm each prerequisite gate has evidence. Prepare a reviewed RFC for architecture/schema/public-contract changes; reuse stable OC ticket IDs. Do not ask for broad approval of an unspecified implementation.

## Audit matrix

| Requirement | Existing code and migration | Actual API/SDK/UI route | Status | Runtime/test evidence | Planned repair |
|---|---|---|---|---|---|
| Example: provider binding | Fill actual paths | Fill actual routes | Wired / unwired / simulated / broken / missing | Fill command/artifact | Bounded change |

## During implementation

- Keep Core free of server/SDK/UI/vendor imports. Server resolves credentials; providers implement ports and cannot mutate ontology.
- Reuse the canonical service instead of adding parallel candidate, ingress or analytics systems. Public clients use HTTP SDKs.
- Write additive, upgrade-tested migrations. Immutable source/version/audit semantics must survive existing-data upgrades; no startup create_all or destructive reconstruction.
- Implement complete vertical slices in small runnable changes: persistence, domain, API, SDK, UI, errors, events and meaningful tests together.
- Preserve typed semantic UNKNOWN separately from infrastructure/error states. Scores confer neither truth nor permissions.
- Reference human/externally verified labels with provenance. Freeze splits/protocols before tuning; retain failed calls and compare full operational coverage.
- Use only runtime secret references. Never include API tokens, auth cookies, customer payloads or credential-bearing upstream responses in evidence/logs/fixtures.
- For external writes first build concrete payloads, scope, permission checks and verifier. Use existing explicit authorization; obtain missing resource-specific authorization before the write. No unsolicited Slack/email or financial operation.
- Do not deploy, publish packages/images/releases or incur live billing merely to validate code.

## Definition of complete

All numbered acceptance items and prerequisite gates pass, actual UI/public-SDK workflow succeeds, scoped access is tested negatively, persistence survives restart and meaningful checks pass on the reviewed commit. Live-provider/business evidence is identified separately from offline fixtures. Quality/availability/sample-size failures remain blockers even when code tests pass.

Run required `make check`, `make test`, `npm run build`, `uv build --all-packages` and relevant PostgreSQL/E2E checks from the branch's documented setup. Record exact commands and all failures; focused passing tests are not a substitute for a failing release baseline.

## Final agent handoff

Provide: problem/result, target commit and changed files, ticket/RFC mapping, migration/upgrade/rollback, contract compatibility, actual UI paths, proof IDs/artifact hashes, checks passed/failed, real-versus-simulated evidence, quality limitations, privacy/operations risks and next-phase dependency blockers. Link the completed evidence file from README before changing status.

Allowed status values: **PLANNED**, **AUDITED**, **IN_PROGRESS**, **BLOCKED**, **COMPLETE_WITH_EVIDENCE**. Review-only availability is a limitation, not an alternative COMPLETE status. Do not count the documentation itself as implementation completion.
