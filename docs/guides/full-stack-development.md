# Full-stack local development and browser QA

This is a local Genesis stack, not a production deployment or a claim of model
quality. Inference uses the explicitly **simulated mock provider**. Authentication,
HTTP calls, explicit migrations and PostgreSQL persistence are real.

## Reproducible disposable verification

Prerequisites: Docker Compose v2, Node 22+, and the pinned pnpm package manager.
Run from the checkout root:

```sh
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:web:live
```

The runner builds locked images sequentially, creates a fresh `openclass-live-<id>`
project and fresh PostgreSQL volume, imports the existing local Keycloak realm
with exact test-origin redirect URIs, waits for dependencies, and runs only the
`live-backend` Playwright project. It never uses the checkout `.env`, existing
databases, default Compose project, or another test project's resources.
Requested loopback ports are checked together; occupied ports get unused ports.
A concurrent bind race fails startup rather than displacing any listener.

| Surface                | Preferred host URL / port |
| ---------------------- | ------------------------- |
| PostgreSQL / pgvector  | `127.0.0.1:55436`         |
| Auth-required engine   | `http://127.0.0.1:17332`  |
| Control plane          | `http://127.0.0.1:17333`  |
| Portal (browser entry) | `http://127.0.0.1:17334`  |
| Next.js web            | `http://127.0.0.1:17335`  |
| Local Keycloak         | `http://127.0.0.1:18081`  |

The runner prints the actual non-secret URL/port manifest in the operating
system's temporary directory. Generated database/admin/internal credentials stay
in child-process environment, not in that manifest or browser assets.
The realm's two checked-in test users/passwords are intentionally public local
fixtures, never suitable for an exposed deployment. Ports bind **only loopback**.

`pnpm test:web:live -- --keep` retains only that fresh project for diagnosis.
The runner prints its manifest path. Shut down its containers and disposable
volume with:

```sh
node scripts/live_stack/down.mjs "/absolute/temp/openclass-live-.../manifest.json"
```

Cleanup refuses non-generated project names. Normal SIGINT/Ctrl-C and SIGTERM
cancel the active owned child process tree, wait for it to stop, then clean up
exactly once (unless `--keep` was explicit). Exit codes remain 130/143. Cleanup
has a 30-second timeout plus bounded child termination. SIGKILL or a machine
failure may require the explicit cleanup command. Temporary manifests contain no application credentials; retained
database volumes do contain test observations.

Only the **public local realm fixture** is mode 0644 with a 0755 bind-mount
directory, so the Keycloak container UID can read it on Linux even with a
restrictive host umask. The surrounding temporary directory remains private;
environment/manifest files are created mode 0600. Private generated credentials
are not written to the public fixture.

`node scripts/live_stack/run.mjs --build-only` proves image builds independently;
it does **not** certify migration, readiness, authentication, or browser gates.
`node scripts/live_stack/run.mjs --engine-only` runs just the independent
database/engine/web/identity smoke plus standalone-web browser check. It does
**not** certify the authenticated control-plane lifecycle. Both modes still
build from this checkout; neither silently reuses another project's images.

## Services, migrations and identity boundaries

The original loopback-only, no-key/mock quickstart remains:

```sh
docker compose --env-file .env.example up --build -d --wait
docker compose exec -T server openclass init examples/support-intents/classifier.json
docker compose exec -T server openclass classify "Cancel my plan"
```

This base demo is **not an authenticated workspace deployment**. Use a separate
Compose project/database for it; do not run existing private workspace volumes
under anonymous base configuration.

The runner always loads the explicit full-stack override. For manual workspace use,
set a strong `OPENCLASS_INTERNAL_TOKEN` in the environment, then:

```sh
docker compose -f docker-compose.yml -f docker/full-stack.compose.yml \
  --profile full-stack up --build -d --wait
```

The override defaults to project `openclass-workspace`, with a separate
`openclass-workspace_postgres-data` volume rather than the base demo's
`openclass_postgres-data`. Keep project names distinct if using `--project-name`
or `COMPOSE_PROJECT_NAME`. The default host ports overlap, so stop one stack
before starting the other; do not reuse the workspace database for the anonymous
demo.

This override adds control-plane, portal and web, forces engine authentication
even if `OPENCLASS_AUTH_REQUIRED=false` is inherited, and rejects an absent token
**during configuration, before any containers start**. A profile alone cannot
enable workspace services from the base file. Never place the private token in
`VITE_*`, `NEXT_PUBLIC_*`, browser storage,
request-content logs, or committed files. The base stack has no model-key
requirement and forwards no ambient provider credentials.

The engine runs `alembic upgrade head` as a separate one-shot service. After that,
`control-migrate` runs the agreed
`pnpm --filter @openclass/control-plane migrate` interface on the same database.
The application starts only after successful migration and engine/identity
readiness. No startup `create_all` or schema reset is used. Control-plane tests
use the independent `test:postgres` command and
`CONTROL_PLANE_TEST_DATABASE_URL`, always against a disposable database.

The container-only control-plane transport bootstrap imports the existing
`AppModule`, binds an unprivileged container port and exposes dependency readiness
at `/health/ready`, including migration filenames/checksums, engine and identity.
It preserves correlation middleware and uses AppModule's shared transactional
pool, mutation interceptor and safe exception filter. It does not replace guards
or domain services. Because the
current guard derives JWKS from the public issuer URL, a container-local TCP
bridge maps that issuer's loopback port to the real Keycloak service. Issuer,
audience and signature verification remain enabled. This avoids host networking,
wildcard redirect URIs and machine-specific hosts-file changes.

Portal nginx serves the built Vite bundle and forwards `/control/` without
injecting authentication. The browser uses Keycloak authorization code + PKCE.
The engine internal token is held only by the engine/control-plane containers.
Next.js runs standalone with bounded build concurrency and contains no private
token; direct unauthenticated `/api/v1/` access through it returns 401, by design.
Authenticated workspace UI is the portal. These containers do not claim that the
legacy web entry point has authenticated feature parity.

For manual Compose use at a portal port other than 5173, import a local realm copy
whose exact `redirectUris`/`webOrigins` match the chosen origin, and point
`OPENCLASS_KEYCLOAK_REALM_DIR` to it. The runner does this automatically.
Changing the public identity port requires rebuilding portal assets, as Vite
configuration is compiled into the bundle.

## What the browser gate covers

Existing route-mocked desktop/mobile tests remain available as `pnpm test:web`.
The separate live project uses no business API route interception:

- genuine signed Keycloak identity plus interactive portal sign-in;
- workspace-owned project creation through the UI and control-plane → engine;
- UI observation ingestion, service creation, simulated run and persisted IDs;
- another identity/workspace denied reads and writes, including mismatched IDs;
- unauthenticated engine and legacy-web boundaries fail closed;
- PostgreSQL/engine/control-plane restart followed by persisted run/event
  readback and browser reload.

Successful screenshots live under `test-results/` (owned run, restart readback,
cross-workspace denial). Live traces and storage-state recording are disabled so
authentication material is not published as a CI artifact. The CI `live-backend`
job runs this gate separately from mocked UI tests. The
dedicated `.github/workflows/control-plane-postgres.yml` workflow runs the other
OC-BG-033 persistence gate; this browser
slice alone must not be described as full OC-BG-033 completion.

## Original OC-BG-034 clean-clone criteria

The original acceptance is broader than containers. Inspect, then execute:

```sh
uv run python -m scripts.jev_contract.audit
docker compose --profile test run --build --rm test
uv run mypy
uv run python scripts/release.py
```

The runtime image now includes `benchmarks`, `examples`, and the benchmark
runner's `scripts`, and runs as a non-root user. Existing `pyproject.toml` includes
the GLM package; existing release validation enumerates `services/*/package.json`.
The audit is an **integrity audit**, not a measured classifier benchmark:
`verify_inputs` still conditionally skips missing historical `build/` evidence
unless strict verification is requested, and `historical_files_preserved: 0`
must not be represented as preserved evidence. Frozen-evidence completeness and
measured benchmark behavior are separate scope. Image success or audit exit 0
does not establish those claims.
