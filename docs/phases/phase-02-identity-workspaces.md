# Phase 02 — Identity, Organizations & Workspaces

- **Status:** deployable slice (auth enforced for control-plane; engine stays local-only until Phase 04 hardens it)
- **Depends on:** Phase 01
- **Milestone:** Secure portal access
- **Traceability:** SPEC §§24–27, 39–41 (config/privacy, partial); OC-033 (ingest auth pattern); future SSO groundwork

## 1. Goal

Make portal access safe for real users: Keycloak-backed login, organizations/workspaces, base roles, and tenant isolation in the NestJS control plane. After this phase, anonymous users cannot list workspaces or members.

## 2. Non-goals

- No classifier/ontology/discovery/evaluation logic (Phases 03, 06–14).
- No billing, invitations via email, SSO/SAML/SCIM (Phases 18–19).
- No engine-level auth migration yet (engine stays `local-user` + `127.0.0.1` binding; hardened in Phase 04). Control plane is the auth boundary.
- No production Keycloak realm; local dev realm only.

## 3. Architecture constraints

- Identity authority is Keycloak. OpenClass stores only Keycloak `sub` + workspace role, never passwords.
- NestJS verifies JWT: issuer, audience (`openclass-portal`), JWKS signature, expiry, `sub` presence. Missing/invalid → `401`. Non-member workspace access → `404` (no enumeration). Forbidden role → `403`.
- Control-plane owns `control_workspaces` + `control_workspace_memberships`. Engine tables untouched.
- Portal uses `keycloak-js` PKCE (`check-sso`, `S256`, no iframe), React Router guards, TanStack Query with bearer token.
- Roles: `owner`, `admin`, `reviewer`, `analyst`, `developer`, `viewer`. Minimum matrix enforced server-side (client hiding is UX only).
- No secrets in repo. Realm JSON contains only local dev users/passwords marked simulated.

## 4. Tasks

### 4.1 Infrastructure

1. Add `keycloak` service to `docker-compose.yml` under profile `portal-identity`, image `quay.io/keycloak/keycloak:26.1`, `start-dev --import-realm`, port `127.0.0.1:8080`, volume `./services/control-plane/keycloak:/opt/keycloak/data/import:ro`.
2. Add realm `services/control-plane/keycloak/openclass-local-realm.json`: realm `openclass-local`, public client `openclass-portal` (standard flow + direct grants for tests, redirect `http://127.0.0.1:5173/*`), audience mapper to `openclass-portal`, two users with first/last names (avoids VERIFY_PROFILE block).
3. Document Keycloak env: `KEYCLOAK_ISSUER_URL=http://127.0.0.1:8080/realms/openclass-local`, `KEYCLOAK_AUDIENCE=openclass-portal`, `CONTROL_PLANE_DATABASE_URL`.

### 4.2 Control plane (NestJS)

1. Deps: `jose`, `pg`, `zod`, `@types/pg`. Add `KeycloakGuard` (`src/auth.ts`) with JWKS verification.
2. Migration `services/control-plane/migrations/0001_identity.sql`:
   - `pgcrypto` extension, `control_workspaces (id uuid pk, slug unique, name, created_at)`, `control_workspace_memberships (workspace_id fk cascade, subject, role check, created_at, pk(workspace_id, subject))`.
   - Provide apply script/docs: `psql $CONTROL_PLANE_DATABASE_URL -f services/control-plane/migrations/0001_identity.sql`.
3. `WorkspaceService`: `mine`, `create` (slugify + owner membership in transaction), `members` (require viewer+), `invite` (require admin+, upsert role).
4. `WorkspaceController` (`/control/workspaces`, `@UseGuards(KeycloakGuard)`):
   - `GET /` → caller’s workspaces; `POST /` (Zod name 2–200) → create + owner; `GET /:id/members`; `POST /:id/members` (Zod subject/role).
5. Error mapping: Zod failure → `400`, unauth → `401`, non-member → `404`, reviewer mutate → `403`.

### 4.3 Portal (`apps/portal`)

1. `src/auth.tsx`: Keycloak init, `ready/authenticated/login/logout/token`, context + `useAuth`.
2. Wrap app in `AuthProvider` (inside QueryClient, outside Router).
3. `/projects`: if `!ready` → “Checking secure session…”; if anonymous → Genesis-styled `access-gate` with “Sign in to your workspace.” + “Continue with Keycloak ↗”; if authenticated → workspace list.
4. `Header`: show Sign out only when authenticated.
5. Attach bearer token to control-plane queries; on `401` clear session and return to gate (no crash).
6. Styles: `.sign-out`, `.access-gate` in Genesis tokens; mobile-safe.

### 4.4 Seeder/docs

1. `scripts/seed_portal_phase_02.py` prints local-only credentials JSON. Add `pnpm seed:portal-phase-02`.
2. Update `docs/guides/portal-phase-01-testing.md` (or new Phase 02 guide section) with Keycloak startup + login steps.

## 5. Data model & migrations

Control-plane Postgres only (see 4.2). Engine Alembic untouched. Down migration drops memberships then workspaces (dev only).

## 6. API contracts

| Method & path | Auth | Body | Success | Errors |
|---|---|---|---|---|
| `GET /control/health` | none | — | 200 ready | — |
| `GET /control/workspaces` | Bearer Keycloak | — | 200 `[{id,slug,name,role}]` | 401 |
| `POST /control/workspaces` | Bearer | `{ name }` | 201 workspace | 400/401 |
| `GET /control/workspaces/:id/members` | Bearer + member | — | 200 `[{subject,role,created_at}]` | 401/404 |
| `POST /control/workspaces/:id/members` | Bearer + admin | `{ subject, role }` | 200 member | 400/401/403/404 |

## 7. Portal UI routes & navbar

| Route | Anonymous | Authenticated (owner) |
|---|---|---|
| `/` | Public hero | Public hero |
| `/projects` | Sign-in gate + Keycloak button | Workspace list + project cards + Sign out in header |
| `/projects/:id` | Redirect/gate (no data leak) | Project shell (data still simulated until Phase 03+) |

Navbar unchanged from Phase 01 plus auth state (Sign out). No new section links in this phase.

## 8. Test seeder + credentials

```bash
docker compose --profile portal-identity up -d keycloak
psql "$CONTROL_PLANE_DATABASE_URL" -f services/control-plane/migrations/0001_identity.sql
pnpm dev:control-plane  # env: CONTROL_PLANE_DATABASE_URL, KEYCLOAK_ISSUER_URL, KEYCLOAK_AUDIENCE
pnpm dev:portal
pnpm seed:portal-phase-02
```

| Role | Username | Password |
|---|---|---|
| Owner | `owner@acme.openclass.test` | `OpenClass-Local-Owner-2026` |
| Reviewer | `reviewer@acme.openclass.test` | `OpenClass-Local-Reviewer-2026` |

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Open `/projects` anonymous | “Sign in to your workspace.” + Keycloak button; no workspace data in network tab |
| 2 | Click Continue → Keycloak login as owner | Redirect back to portal; workspace list visible; header shows Sign out |
| 3 | Direct `GET /control/workspaces` without token | `401 { message: Authentication required }` |
| 4 | Owner creates workspace via UI/API | 201, appears in `GET /control/workspaces` with `role: owner` |
| 5 | Reviewer `POST /:id/members` | `403 Workspace role cannot manage members` |
| 6 | Non-member `GET /:id/members` | `404 Workspace not found` (no enumeration) |
| 7 | Logout | Returns to gate; protected queries stop |
| 8 | Expired token | 401 → portal recovers to gate |

## 10. Automated tests

- NestJS Vitest: guard rejects missing/invalid token (401); owner can invite; reviewer invite → 403; non-member → 404; Zod rejects bad name/role (400).
- Portal Vitest: gate renders anonymous; list renders authenticated; logout returns to gate.
- Playwright: anonymous gate snapshot; owner login flow (local Keycloak); auth header present on workspace fetch.
- `pnpm typecheck`, `pnpm build`, `ruff check scripts/seed_portal_phase_02.py`.

## 11. Acceptance criteria

- [ ] Anonymous cannot access workspace/member APIs or UI data.
- [ ] Owner login → list/create workspaces; reviewer restrictions enforced server-side.
- [ ] JWT checks cover issuer/audience/signature/expiry/subject.
- [ ] Migration applies cleanly to disposable DB; rollback documented.
- [ ] Credentials are local-only and clearly labeled simulated.
- [ ] No engine schema change; no SaaS logic in engine.

## 12. Risks

- Keycloak VERIFY_PROFILE friction → seed first/last names; document profile completion if realm re-imported.
- JWKS/network flakiness → cache JWKS, short timeouts, safe 401 without stack traces.
- Token storage XSS → keep in memory where possible; document localStorage trade-off if used; add CSP later (Phase 04).

## 13. Traceability

SPEC privacy/config; OC-033 auth pattern; prepares OC-010 SSE auth and OC-012 workspace scoping.
