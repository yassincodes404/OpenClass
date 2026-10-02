# Phase 01 — Portal Foundation & Navigation

- **Status:** deployable slice (no auth, no customer data, simulated data only)
- **Depends on:** Genesis `v0.0.1` (OC-001), current `apps/web` project runtime
- **Milestone:** Portal foundation
- **Traceability:** SPEC §§18–23, 28–35, 37, 57 steps 33–35/37; OC-010, OC-012 (partial, shell only)

## 1. Goal

Create the separate deployable portal and control-plane skeleton with the shared Genesis visual identity, and fix the missing navbar problem from the pulled commits: every implemented project area must be reachable from navigation.

Business outcome: a stable visual/technical shell that later phases can fill without re-theming or re-routing.

## 2. Non-goals (explicitly out of scope)

- No authentication, organizations, roles, or tenant isolation (Phase 02).
- No project/classifier CRUD beyond reading existing local engine projects (Phase 03).
- No ingestion, decisions, discovery, evaluation, promotion, billing (Phases 05–19).
- No production deployment claims, no real customer data, no hosted tenancy.
- No duplication of FastAPI decision/ontology logic in NestJS.

## 3. Architecture constraints

- Create `apps/portal` (React + Vite + TypeScript) as a new pnpm workspace package. Do not rebuild portal inside `apps/web` (Next.js workbench stays as-is for Genesis reference).
- Create `services/control-plane` (NestJS + TypeScript) as a new pnpm workspace package. It exposes only portal health/status in this phase.
- Engine remains canonical: `packages/core` → `packages/server` (FastAPI). Portal talks HTTP only (TypeScript SDK / `fetch` to control-plane, which may proxy/authorize engine later).
- pnpm is the main JS manager: `pnpm-workspace.yaml` includes `apps/portal`, `services/control-plane`, `apps/web`, `packages/sdk-typescript`.
- Visual identity is shared and frozen here: dark `#101411`, surface `#171d18`, border `#303a31`, text `#eef0e8`, muted `#a6b0a6`, accent `#c4f48a`; technical mono labels; 4px controls / 10–14px panels; 160ms transitions; `prefers-reduced-motion` respected; responsive at 720px breakpoint.
- Frontend stack installed now (even if lightly used): React, Vite, TypeScript, React Router, TanStack Query, React Hook Form, Zod, keycloak-js (for Phase 02), Playwright, Vitest.

## 4. Tasks

### 4.1 Portal app (`apps/portal`)

1. Scaffold Vite React TS app: `package.json`, `vite.config.ts` (port 5173, `/control` proxy to `127.0.0.1:7400`), `tsconfig.*`, `index.html` + favicon, `src/main.tsx`, `src/styles.css`.
2. Implement shell:
   - `Header`: brand `O↗ OPENCLASS`, nav Home `/`, Projects `/projects`, badge `GENESIS / PORTAL`.
   - `Home /`: hero “Turn uncertainty into evidence.”, lede, CTA to `/projects`.
   - `Projects /projects`: simulated workspace card (Acme Support, explicitly simulated).
   - `Project /projects/:id/:section?`: kicker, section nav with ALL areas: Overview, Classifiers, Observations, Unknowns, Discoveries, Ontology, Evaluations, Integrations, Usage & Billing, Team & Access, Settings; foundation signal panel; zeroed metrics.
3. Use React Router (not ad-hoc state), TanStack Query provider (even if no remote query yet), Zod + React Hook Form available for later forms.
4. Responsive: header wraps, nav scrolls horizontally, metrics stack to 1 column under 720px, hero scales with `clamp()`.

### 4.2 Control plane (`services/control-plane`)

1. Scaffold NestJS: `package.json`, `nest-cli.json`, `tsconfig.json`, `src/main.ts` (listen `127.0.0.1:7400`, CORS for portal origin), `src/app.module.ts`.
2. `PortalController` (`/control`):
   - `GET /control/health` → `{ status: "ready", service: "openclass-control-plane" }`
   - `GET /control/portal-phase` → `{ phase: 1, status: "foundation", simulated: true, capabilities: [...] }`
3. Add `@nestjs/platform-express` driver dependency. No DB, no auth in this phase.

### 4.3 Workspace / docs / seeder

1. Add root scripts: `dev` / `dev:portal` / `dev:control-plane`, `seed:portal-phase-01` (if needed).
2. Add `scripts/seed_portal_phase_01.py`: prints deterministic manifest `{ seed, simulated: true, login_required: false, project, routes }`. Idempotent, no DB writes required (engine seeding optional via existing `seed_phase_01.py`).
3. Add testing guide `docs/guides/portal-phase-01-testing.md`.
4. Ensure `apps/web` still builds (no regression).

## 5. Data model & migrations

None. No new tables. No Alembic migration. No control-plane SQL migration.

## 6. API contracts

| Method & path               | Auth | Response                                              |
| --------------------------- | ---- | ----------------------------------------------------- |
| `GET /control/health`       | none | `{ status, service }`                                 |
| `GET /control/portal-phase` | none | `{ phase: 1, status, simulated: true, capabilities }` |

Typed DTOs in NestJS; Zod schemas in portal for any parsed payload. No engine calls in this phase.

## 7. Portal UI routes & navbar

All routes use the same Genesis theme. Navbar must expose every planned section (fixes “no routes in navbar” from last 2 commits).

| Route                                                                      | Navbar state             | Expected content                                                                               |
| -------------------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------- |
| `/`                                                                        | Home active              | Hero, CTA “Open workspace”                                                                     |
| `/projects`                                                                | Projects active          | Simulated Acme Support card, “Open project →”                                                  |
| `/projects/acme-support-phase-01-demo`                                     | Project tabs visible     | Kicker + 11 section tabs + foundation panel + metrics (0,0,0)                                  |
| `/projects/:id/<section>` (e.g. `/observations`, `/unknowns`, `/ontology`) | Corresponding tab active | Same shell; section title; “staged for its planned phase” message (honest, no fake capability) |

Mobile: tabs scroll horizontally; header wraps; no horizontal page overflow at 390px.

## 8. Test seeder + credentials

No login in Phase 01.

```bash
pnpm install
pnpm dev:control-plane
pnpm dev:portal
uv run python scripts/seed_portal_phase_01.py
```

Expected seeder output: JSON with `simulated: true`, `login_required: false`, project slug and 3 routes. Seeder is idempotent and prints only; it creates no users.

## 9. Manual browser tests

| #   | Route / action                                              | Expected result                                                        |
| --- | ----------------------------------------------------------- | ---------------------------------------------------------------------- |
| 1   | `http://127.0.0.1:5173/`                                    | Hero renders, CTA goes to `/projects`, no console errors (except none) |
| 2   | `http://127.0.0.1:5173/projects`                            | Simulated project card visible, link to demo project works             |
| 3   | `http://127.0.0.1:5173/projects/acme-support-phase-01-demo` | All 11 section links visible and clickable; overview content renders   |
| 4   | Any `/projects/:id/<section>`                               | Title matches section; honest “staged” message; metrics show 0s        |
| 5   | `http://127.0.0.1:7400/control/health`                      | JSON ready status                                                      |
| 6   | Resize to 390px                                             | No broken layout; nav scrolls; cards stack                             |

## 10. Automated tests

- `pnpm typecheck` (portal + control-plane + sdk + web) passes.
- `pnpm build` (portal Vite + control-plane Nest + web Next) passes.
- `uv run ruff check scripts/seed_portal_phase_01.py` passes.
- Portal Vitest: shell renders header/nav/routes (add in Phase 01 if missing).
- Control-plane: health controller test.
- Playwright (portal): anonymous `/projects` loads; project route shows section nav. (Full Playwright matrix starts Phase 02.)

## 11. Acceptance criteria / Definition of Done

- [ ] `apps/portal` and `services/control-plane` exist as pnpm workspaces and build.
- [ ] Navbar exposes all 11 project sections; no implemented route is unreachable.
- [ ] Visual identity matches Genesis palette/typography/spacing; mobile passes 390px check.
- [ ] Seeder prints deterministic manifest; docs explain no-login testing.
- [ ] Control-plane health endpoints return typed JSON.
- [ ] No engine domain logic duplicated; no secrets; mock/simulated labels where applicable.
- [ ] `make check`-relevant JS checks (typecheck/build) pass.

## 12. Risks & mitigations

- Scope creep into auth/data → enforce non-goals; defer to Phase 02+.
- Theming drift between `apps/web` and `apps/portal` → share tokens via `design.json` / CSS variables; review screenshots.
- Vite proxy/CORS breakage → test `/control/health` through Vite proxy and directly.

## 13. Traceability

SPEC §§18–23 (surfaces), §§28–35 (UX), §37/57 (monorepo order); OC-010/OC-012 shell subset. No ontology/evaluation/promotion claims.
