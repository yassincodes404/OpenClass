# Portal Phase 1 testing

The portal is a separate **React + Vite + TypeScript** application in `apps/portal`.
Its control plane is a separate **NestJS** service in `services/control-plane`.
The FastAPI engine remains the sole source of decision/ontology logic.

## Start

```bash
pnpm install
pnpm dev:control-plane
pnpm dev:portal
uv run python scripts/seed_portal_phase_01.py
```

No login is required in Phase 1.

## Phase 2 access testing

Keycloak backs portal sign-in. Realm import happens at container start; recreate
the container after editing the realm JSON.

```bash
# 1. Postgres (engine schema already required by Phase 1; use port 55432 if 5432 is taken)
docker compose up -d db   # or reuse an existing migrated instance

# 2. Apply the control-plane identity migration (once)
psql "postgresql://openclass:openclass@127.0.0.1:5432/openclass" \
  -f services/control-plane/migrations/0001_identity.sql

# 3. Keycloak with the local dev realm (realm: openclass-local)
docker compose --profile portal-identity up -d --force-recreate keycloak

# 4. Control plane (NestJS) with identity env
KEYCLOAK_ISSUER_URL=http://127.0.0.1:8080/realms/openclass-local \
KEYCLOAK_AUDIENCE=openclass-portal \
CONTROL_PLANE_DATABASE_URL=postgresql://openclass:openclass@127.0.0.1:5432/openclass \
pnpm dev:control-plane

# 5. Portal + local-only credentials manifest
pnpm dev:portal
pnpm seed:portal-phase-02
```

Visit `/projects`: anonymous users see **Sign in to your workspace**. Sign in
with `owner@acme.openclass.test` / `OpenClass-Local-Owner-2026`; expected result
is the authenticated workspace list and a **Sign out** action. These are
local-only simulated credentials.

Manual checks:

| # | Action | Expected |
| --- | --- | --- |
| 1 | `curl http://127.0.0.1:7400/control/workspaces` | `401 { "message": "Authentication required" }` |
| 2 | Sign in as owner | Workspace list renders; header shows Sign out |
| 3 | `POST /control/workspaces { "name": "Acme Support" }` with owner token | `201` with `role: "owner"` |
| 4 | Reviewer token calls `POST /control/workspaces/:id/members` | `403 Workspace role cannot manage members` |
| 5 | Non-member calls `GET /control/workspaces/:id/members` | `404 Workspace not found` |
| 6 | Sign out | Portal returns to the sign-in gate |

Automated checks: `pnpm test` (NestJS guard/service/controller Vitest, portal
gate/list/logout Vitest), `pnpm typecheck`, `pnpm build`, `uv run ruff check scripts/`.

| Route | Expected result |
| --- | --- |
| `http://127.0.0.1:5173/` | Genesis landing screen and **Open demo workspace** action. |
| `http://127.0.0.1:5173/projects` | Anonymous: sign-in gate. Authenticated: workspace list. |
| `http://127.0.0.1:5173/projects/:slug` | Project navigation lists all planned portal sections; only delivered phase messaging is claimed. |
| `http://127.0.0.1:7400/control/health` | `{ "status": "ready", "service": "openclass-control-plane" }`. |

## Phase 3 projects & classifiers testing

Requires the Phase 2 stack plus the engine (`uv run openclass serve`, default
`http://127.0.0.1:7331`, Postgres migrated to head) and migration `0002_projects.sql`
applied to the control-plane database. Start the control plane with
`ENGINE_BASE_URL=http://127.0.0.1:7331`.

```bash
docker exec -i <pg-container> psql -U openclass -d openclass \
  < services/control-plane/migrations/0002_projects.sql
pnpm seed:portal-phase-3   # workspace acme-support → project → classifier → dev key (printed once)
```

Manual checks:

| # | Action | Expected |
| --- | --- | --- |
| 1 | Owner creates project via `/projects` modal | Project card appears with unique slug |
| 2 | `POST .../classifiers` with `unknown_fallback: false` | `400 UNKNOWN fallback is required and permanent` |
| 3 | Valid classifier via UI | Detail lists all classes + locked UNKNOWN row + version id |
| 4 | Create API key | Full key shown once; after reload only the prefix remains |
| 5 | Reviewer creates project/classifier/key | `403 Workspace role cannot manage projects` |
| 6 | Non-member resolves project id | `404 Project not found` |

UNKNOWN is enforced as a permanent fallback state, never a class: requests may
not opt out, and class canonical names `unknown`/`other` are rejected.
