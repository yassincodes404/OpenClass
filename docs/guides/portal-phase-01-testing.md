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

## Phase 4 secure boundaries testing

Apply `services/control-plane/migrations/0003_security.sql` to the control-plane
database and run `uv run alembic upgrade head` for the engine (revision
`0011_idempotency_keys`). Then `pnpm seed:portal-phase-4` (strict redaction +
rate-limit test key, printed once).

Manual checks:

| # | Action | Expected |
| --- | --- | --- |
| 1 | Save settings on `/projects/:id/settings` | Redaction toggle + retention persist; secrets are never displayed |
| 2 | POST a project twice with the same `Idempotency-Key` | Second call replays the original project (same id, no second write) |
| 3 | POST engine `/events` twice with the same `Idempotency-Key` | 200 replay with `Idempotency-Replayed: true`; no duplicate rows |
| 4 | Exceed the ingest rate limit (engine) | `429` + `Retry-After` + `X-RateLimit-*` headers |
| 5 | Open `/projects/:id/audit` | New actions appear with actor/timestamp; cursor pagination works |

Engine env: `OPENCLASS_RATE_LIMITS_ENABLED`, `OPENCLASS_RATE_LIMIT_INGEST_PER_MIN`
(default 60), `OPENCLASS_RATE_LIMIT_CLASSIFY_PER_MIN` (default 300),
`OPENCLASS_REDACTION_BLOCKLIST` (comma-separated terms). Request-content logging
stays off; audit records never contain observation content or key values.

## Phase 5 observation ingestion testing

Engine migration `0012_raw_event_content_hash` (content-hash dedup; run
`uv run alembic upgrade head`). Seeder: `pnpm seed:portal-phase-5` — 25
deterministic support texts (billing/refund/delivery/cancel/account_access plus
unknowns); re-running reports all 25 as deduped.

Manual checks:

| # | Action | Expected |
| --- | --- | --- |
| 1 | Ingest text from `/projects/:id/data` | Saved toast with event id; appears first in Observations |
| 2 | Re-send identical content (same or no key) | `200 deduped: true`, same id, count unchanged |
| 3 | Batch with one blank row | `207` per-item statuses (201/400/413) |
| 4 | Search "refund" in Observations | Only matching rows |
| 5 | Open detail drawer | Original content + metadata (members only) |
| 6 | Ingest with an `oc_dev_` key scoped to another project | `404` |

Programmatic ingestion accepts either a member JWT or a scoped API key
(`Authorization: Bearer oc_dev_…`, requires the `ingest` scope). Engine limits:
content 1–10,000 chars (blank 400/422, oversize 413), batch ≤ 500. The control
plane enforces per-caller token buckets, a 10k/workspace/month simulated quota,
and redacted list previews per project settings.
