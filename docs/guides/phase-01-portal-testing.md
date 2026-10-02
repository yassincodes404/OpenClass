# Phase 1 portal testing

Phase 1 establishes the navigation shell for the existing local web portal. It
does not introduce authentication, billing, hosted tenancy, or production
deployment claims. All seeded data is explicitly simulated.

## Start and seed

Start a migrated local API, then the web app:

```bash
uv run alembic upgrade head
uv run openclass serve
npm ci
npm run dev
```

In another terminal, seed the deterministic local project:

```bash
OPENCLASS_SERVER_URL=http://127.0.0.1:7331 uv run python scripts/seed_phase_01.py
```

The command is idempotent and prints the seeded project slug. **No login is
required in Phase 1.** Authentication begins in Phase 2.

## Browser routes and expected results

| Route | Expected result |
| --- | --- |
| `http://127.0.0.1:3000/` | The global header offers **Workspace** and **Projects**; Workspace is active. |
| `http://127.0.0.1:3000/projects` | The global header remains visible and the simulated **Acme Support — Phase 1 demo** project is listed. |
| `http://127.0.0.1:3000/projects/<seeded-slug>` | The project shell exposes Overview, Data, Decisions, Knowledge, Evolution, Integrations, Analytics, Runs, and Settings. Existing sections render; unimplemented sections state that they are unavailable rather than implying capability. |

The portal intentionally uses the existing Genesis visual identity defined in
[`design.json`](../../design.json): dark #101411 background, restrained green
#c4f48a accent, evidence-oriented monospace labels, and low-radius bordered
surfaces.
