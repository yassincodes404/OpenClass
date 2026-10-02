# OpenClass — 20-Phase Delivery Plan (Deployable Slices)

> Superseded sequencing: the founder-authorized 2026-10-02
> [application proof program](../architecture/application-proof-program.md) and its
> [ten-phase roadmap](../implementation-phases/README.md) set the current development
> priority and order of work. This plan remains the portal/control-plane architecture
> reference for slices it already delivered (phases 1–10 of 20); new numbered phases
> are governed by `docs/implementation-phases/` and OC-034–039.

> Source vision: Product, Business & Technical Vision (UNKNOWN → Evidence → Discovery → Evaluation → Human Review → Versioned Improvement).
> Architecture authority: `docs/architecture/SPECIFICATION.md`, `docs/architecture/genesis.md`, `docs/contributing/tickets.md`.
> This is a Genesis foundation (`v0.0.1`), not a completed `v0.1` release. Do not label any phase `v0.1` until all §58 gates pass.

## Architecture split (applies to all phases)

```text
apps/portal (React + Vite + TypeScript)
  → services/control-plane (NestJS + TypeScript, SaaS workflows only)
  → packages/server (Python FastAPI, canonical decision engine)
  → PostgreSQL + pgvector
```

Rules:

- Core owns domain rules and ports; it must never import server, adapters, SDKs, or UI.
- Providers implement core ports; providers never get writable ontology access.
- SDKs speak HTTP only. Portal uses TypeScript SDK / control-plane HTTP. CLI may launch server.
- UNKNOWN is permanent. Unknown is never proof of a new class.
- Predictions never become ground truth. No automatic promotion.
- Ontology snapshots and audit history are append-only. Aliases are versioned.
- Persistence changes require explicit Alembic migrations (engine) or versioned SQL migrations (control-plane). Never `create_all` at startup.
- All new behavior needs typed boundaries, errors, meaningful tests, API docs, and events.
- Mock output is always marked `simulated: true`. No invented benchmarks.
- No secrets in source, logs, provider errors, fixtures, or events.
- pnpm is the main JS package manager. Python uses `uv`.
- Portal visual identity is shared across all phases (Genesis):
  `bg #101411`, `surface #171d18`, `border #303a31`, `text #eef0e8`, `muted #a6b0a6`, `accent #c4f48a`.

## Local ports (default)

| Service                | URL                                                  |
| ---------------------- | ---------------------------------------------------- |
| Portal (Vite)          | `http://127.0.0.1:5173`                              |
| Control plane (NestJS) | `http://127.0.0.1:7400`                              |
| Engine (FastAPI)       | `http://127.0.0.1:7331`                              |
| Keycloak (Phase 2+)    | `http://127.0.0.1:8080`                              |
| Postgres               | `127.0.0.1:5432` (or isolated `55432` when occupied) |

## Local-only test credentials (Phase 2+)

These are deterministic **simulated development accounts only**. Never ship or use in production.

| Role     | Username                       | Password                        |
| -------- | ------------------------------ | ------------------------------- |
| Owner    | `owner@acme.openclass.test`    | `OpenClass-Local-Owner-2026`    |
| Reviewer | `reviewer@acme.openclass.test` | `OpenClass-Local-Reviewer-2026` |

Print them with:

```bash
pnpm seed:portal-phase-02
# Phase 1 only (no login):
uv run python scripts/seed_portal_phase_01.py
```

## Phase index

| Phase | File                                     | Deployable outcome                                                           |
| ----- | ---------------------------------------- | ---------------------------------------------------------------------------- |
| 01    | `phase-01-portal-foundation.md`          | Separate portal + NestJS skeleton, shared design system, full project navbar |
| 02    | `phase-02-identity-workspaces.md`        | Keycloak auth, orgs/workspaces, roles, tenant isolation                      |
| 03    | `phase-03-projects-classifiers.md`       | Project/classifier CRUD, initial versioned ontology, scoped API keys         |
| 04    | `phase-04-secure-boundaries.md`          | Secrets, redaction, rate limits, audit log, pagination/idempotency           |
| 05    | `phase-05-observation-ingestion.md`      | Text/JSON/CSV ingest, dedup, observation history                             |
| 06    | `phase-06-decision-services-runs.md`     | Decision services, permanent UNKNOWN, persisted runs                         |
| 07    | `phase-07-provider-protocol-costs.md`    | Jev/Ollama/OpenAI-compatible protocol, retries, usage/cost                   |
| 08    | `phase-08-unknown-workspace.md`          | UNKNOWN trends, filters, triage, assignment                                  |
| 09    | `phase-09-embeddings-clustering.md`      | pgvector embeddings, similarity grouping, cluster provenance                 |
| 10    | `phase-10-discovery-canonicalization.md` | Discovery provider, candidates, duplicate/alias detection                    |
| 11    | `phase-11-candidate-review.md`           | Candidate lifecycle, human review, append-only decisions                     |
| 12    | `phase-12-evaluation-datasets.md`        | Verified datasets, label provenance, immutable sets                          |
| 13    | `phase-13-replay-regression.md`          | Baseline vs candidate replay, metrics, regression gates                      |
| 14    | `phase-14-ontology-promotion.md`         | Guarded promotion, immutable versions, diff, rollback-as-new-version         |
| 15    | `phase-15-operations-dashboard.md`       | Overview metrics, alerts, SSE, quality/cost reporting                        |
| 16    | `phase-16-support-integrations.md`       | Webhooks + Zendesk/Intercom, safe routing, escalation                        |
| 17    | `phase-17-feedback-kb-faq.md`            | Agent feedback, KB linking, FAQ routing, safe LLM drafting                   |
| 18    | `phase-18-team-usage-data.md`            | Roles/invites, API keys, usage metering, export/deletion                     |
| 19    | `phase-19-billing-deployops.md`          | Stripe test-mode, plans, email, backups, tracing, CI/CD                      |
| 20    | `phase-20-release-candidate.md`          | Security review, load/failure tests, docs, pilot, release gates              |

Each phase file contains: goal, non-goals, tasks, data/migrations, API, portal routes, seeder/credentials, manual browser tests, automated tests, acceptance criteria, risks, and traceability.
