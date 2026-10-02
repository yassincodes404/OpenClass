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

| Route | Expected result |
| --- | --- |
| `http://127.0.0.1:5173/` | Genesis landing screen and **Open demo workspace** action. |
| `http://127.0.0.1:5173/projects` | Simulated Acme Support project is visible. |
| `http://127.0.0.1:5173/projects/acme-support-phase-01-demo` | Project navigation lists all planned portal sections; only Phase 1 foundation messaging is claimed. |
| `http://127.0.0.1:7400/control/health` | `{ "status": "ready", "service": "openclass-control-plane" }`. |
