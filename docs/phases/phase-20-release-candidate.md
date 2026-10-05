# Phase 20 — Release Candidate & Production Readiness

- **Depends on:** Phases 01–19 (full loop)
- **Traceability:** SPEC §§42–58 (delivery/governance, §58 gates), §§30–31 (readiness checklist); OC-002, OC-013, OC-014

## 1. Goal

Earn the right to be a platform: prove the UNKNOWN loop creates measurable validated improvement, then meet release gates for a deployable candidate (still not `v0.1` until founder signs §58).

## 2. Non-goals

- No new features. Only validation, docs, pilot, and gates.
- No speculative infra (K8s, multi-region, autonomous promotion — explicitly deferred).

## 3. Constraints (SPEC §30 checklist must all be addressed)

Real provider protocol, safe errors, secure credential storage, redaction, logging off by default, rate limiting, auth, tenant isolation, API keys, pagination, idempotency, backups + restore testing, central logging, tracing, alerts, security review, privacy/terms/DPA, deletion/export, CI/CD, migrations, rollback. Mock stays simulated. No invented claims.

## 4. Tasks

### 4.1 Proof of value (MVP experiment)

1. Run `benchmarks/hidden-intents` + support pilot (5–10 design partners): Baseline vs OpenClass; measure UNKNOWN detection, cluster quality, new-intent discovery, validation rate, coverage (e.g. 72%→88% illustrative only — real numbers from runs), triage 28%→12% illustrative, error rate, cost/classification.
2. Record real demo assets + measured report (no flattering constants).

### 4.2 Hardening

Threat model + security review (auth, tenant isolation, secrets, PII, webhook trust, dependency audit `pnpm audit`/`uv`); load test (k6/locust: p95 latency, 429 behavior); failure tests (DB down, provider down, Keycloak down → safe degraded messages); accessibility (keyboard, focus, contrast, reduced motion); privacy/terms/DPA docs.

### 4.3 Release engineering

Version consistency (`scripts/release.py`), CHANGELOG, checksums/SBOMs, GHCR images (non-publishing until authorized), clean-clone verification, deployment runbook (migrate → engine → control-plane → portal → Keycloak → verify), rollback runbook.

## 5. Data & migrations

No new tables unless review finds gaps. Final migration audit: all Alembic heads linear; control-plane SQL versioned; `EXPECTED_SCHEMA_REVISION` matches head.

## 6. API & docs

Freeze OpenAPI for the slice; publish `docs/guides/api.md` deltas, portal testing guide, pilot handbook. No豆腐 public installer URLs until artifacts exist.

## 7. Portal routes (full critical-path browser test)

| Step | Route / action | Expected |
|---|---|---|
| 1 | `/login` → owner login | Authenticated, workspace visible |
| 2 | `/projects` → create/select `acme-support` | Project overview with real counters |
| 3 | `/projects/:id/data` → ingest “Cancel my plan” + “I was charged twice” | Events persisted |
| 4 | `/projects/:id/decisions` → run router | Known → `billing`; unmatched → `UNKNOWN` (not forced) |
| 5 | `/projects/:id/unknowns` → triage | UNKNOWN visible with evidence |
| 6 | `/projects/:id/unknowns/clusters` → cluster | Cancel groups together |
| 7 | `/projects/:id/discoveries/:cid` → review | Evidence threshold + approval |
| 8 | `/projects/:id/evaluations/:eid` | Passing eval, no billing regression |
| 9 | `/projects/:id/ontology` → promote | v1 unchanged, v2 with approved change + diff |
| 10 | Re-run decision | Previously UNKNOWN now `known` with v2 + audit trail intact |

## 8. Seeder + credentials

`pnpm seed:portal-phase-20` (or composed seeds 05–14): full deterministic pilot dataset. Same local-only owner/reviewer credentials. Production requires real IdP + secrets; seeded users never deploy.

## 9. Manual browser tests

Execute §7 table end-to-end on disposable migrated DB; record results in pilot report. Verify no auto-truth/promotion anywhere.

## 10. Automated tests

- `make check`, `make test`, `pnpm build`, `uv build --all-packages` (per AGENTS.md; PG checks on disposable DB).
- Central E2E: known → unknowns → cluster → candidate → evaluate → approve → v2 → same input known (must pass; until then do not fake loop).
- Contract + integration + Playwright full matrix green.

## 11. Acceptance / Release gates (all required)

- [ ] Pain validated with design partners; ROI measured (automation + error reduction).
- [ ] Full governed loop demonstrated with audit history.
- [ ] Security, load, failure, a11y, backup/restore all pass with evidence.
- [ ] Docs: privacy, terms, DPA, runbooks, API docs complete.
- [ ] Founder release review (OC-002/OC-014) signed; version consistency holds.
- [ ] System is deployable candidate; `v0.1 Discovery` label only after §58 sign-off.

## 12. Risks

Biggest risk is business, not technical: customers may see this as internal feature. Mitigation: integrations + evaluation + ontology + versioning + governance + analytics + review + security as complete product (per vision §45), plus measured pilot ROI before SaaS scale-up.

## 13. Final definition

> OpenClass is a governed AI classification platform that identifies what a system does not understand, turns uncertainty into evidence and actionable discoveries, and lets teams safely improve classification through evaluation and human review.
