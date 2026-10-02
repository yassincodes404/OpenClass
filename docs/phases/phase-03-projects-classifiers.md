# Phase 03 — Project & Classifier Management

- **Depends on:** Phase 02
- **Traceability:** SPEC §§24–27 (target tables: projects, classifiers, ontology_versions...), §57 steps 01–18; OC-001 (workspace), OC-009 (partial: version creation, no promotion yet)

## 1. Goal

Let workspaces create and manage projects and classifiers with an initial immutable ontology version, scoped API keys, and workspace isolation end-to-end (portal → control-plane → engine).

## 2. Non-goals

- No ingestion/runs/discovery/evaluation/promotion (Phases 05–14).
- No billing/usage (Phase 19). No support integrations (Phase 16).
- No ontology editing beyond initial creation (Phase 14 owns evolution).

## 3. Constraints

- Engine `Project`/`Classifier` creation stays in core/service with atomic audit events. Control-plane maps `control_workspace_id ↔ engine project_id` (mapping table, no engine auth change yet beyond `owner_id` already present).
- UNKNOWN fallback is mandatory in every classifier’s initial ontology. Classifier without UNKNOWN is rejected (400).
- API keys are scoped to workspace/project, shown once, stored as hashes. Never log keys.
- Append-only ontology: v1 immutable; edits create new versions only in Phase 14.

## 4. Tasks

### Engine (FastAPI/core)

1. Ensure `POST /api/v1/projects`, `GET /api/v1/projects`, `GET /:id`, `PATCH /:id` enforce workspace mapping via control-plane context (or documented local bypass when control-plane disabled).
2. Classifier create/list/get with `active_ontology_version_id`; initial version snapshot includes supplied classes + `UNKNOWN`.
3. Alembic migration if new columns needed (e.g. `workspace_ref`, `api_key_hash` tables). Never `create_all`.

### Control plane

1. Tables: `control_projects (id, workspace_id fk, engine_project_id unique, slug, name, created_at)`, `control_api_keys (id, workspace_id, project_id, key_hash, prefix, scopes, created_at, revoked_at)`.
2. Endpoints: `POST /control/workspaces/:id/projects` (proxy engine create + mapping), `GET .../projects`, `POST .../projects/:pid/keys` (return key once), `GET .../keys`, `POST .../keys/:kid/revoke`.
3. Zod validation; owner/admin create, reviewer+ read; key creation logged (without key value).

### Portal

1. Routes: `/projects` (create modal: Name 2–200 + Description, React Hook Form + Zod), `/projects/:id`, `/projects/:id/classifiers` (list + create), `/projects/:id/classifiers/:cid` (detail: classes, UNKNOWN badge, version id).
2. API-key UX: “Show once” panel, copy button, prefix/scopes display, revoke confirmation.
3. Empty/loading/error states; pagination for lists.

## 5. Data & migrations

Engine Alembic + control-plane SQL, both forward-only with down scripts for dev. Seed mapping for demo workspace.

## 6. API contracts (summary)

- `POST /control/workspaces/:id/projects { name, description }` → 201 `{ controlId, engineId, slug }`
- `POST /api/v1/classifiers { project_id/slug, name, classes[] }` (via control-plane auth) → 201 with `ontology_version_id`; 400 if UNKNOWN missing
- `POST /control/.../keys { scopes[] }` → 201 `{ key (once), prefix, scopes }`; `GET` lists without hashes; `POST .../revoke` → 200

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects` | Create button; new project appears; validation errors inline |
| `/projects/:id` | Overview with project counts (still 0 until Phase 05+) |
| `/projects/:id/classifiers` | List with UNKNOWN badge; create flow |
| `/projects/:id/classifiers/:cid` | Class table + version id + API key section |

## 8. Seeder + credentials

`pnpm seed:portal-phase-03` (to be added): creates workspace `acme-support`, project `acme-support`, classifier `support-intent` with classes `billing, refund, delivery, cancel_subscription, account_access + UNKNOWN`, one scoped dev key (printed once, simulated).

Login: owner credentials (Phase 02 table). Reviewer can view, cannot create/revoke (403).

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Owner creates project “Acme Support 2” | Appears in list; slug unique; audit event exists |
| 2 | Create classifier without UNKNOWN | 400 “UNKNOWN fallback is required” |
| 3 | Create valid classifier | Detail shows all classes + UNKNOWN locked badge |
| 4 | Create API key | Full key shown once; reload hides it; prefix remains |
| 5 | Reviewer tries create/revoke | 403 + friendly message |
| 6 | Non-member opens project id | 404 |

## 10. Automated tests

Unit: slug collision suffix; UNKNOWN-required validator; key hash/verify; scope check. Integration: create→get→list isolation per workspace; key shown-once; revoke blocks use. Contract: OpenAPI matches SDK. E2E central loop not yet (starts Phase 13).

## 11. Acceptance

- [ ] Workspace isolation holds for projects/classifiers/keys.
- [ ] Every classifier has permanent UNKNOWN.
- [ ] Keys never logged; revocation effective immediately.
- [ ] Migrations explicit; typecheck/build pass.

## 12. Risks

Key sprawl → prefix + scopes + revocation + audit. Slug collisions → numeric suffix + unique constraint.
