# Development

Python 3.12+ (the repository pins 3.12), uv, Node.js 22+, npm, and Docker Compose.

```bash
uv sync --all-packages --locked
npm ci
docker compose up -d db
uv run alembic upgrade head
uv run openclass serve
# Another terminal:
npm run dev
```

The server reads `OPENCLASS_DATABASE_URL` from the environment. Defaults use the
local Compose database. Compose reads `.env`; native Python commands do not load it.
Override the URL explicitly if you change credentials/ports. Passwords embedded in
URLs must be percent-encoded. Never commit `.env` or live credentials.

```bash
export OPENCLASS_DATABASE_URL='postgresql+asyncpg://openclass:openclass@localhost:5432/openclass'
export OPENCLASS_NOVELTY__MINIMUM_TOP_MARGIN=0.2
uv run openclass doctor
```

`doctor` checks API readiness, migration revision, and PostgreSQL's vector extension.
It does not yet test remote providers or filesystem permissions.

## Verification

```bash
make check
make test
npm run build
npx playwright install chromium
npm run test:web
uv build --all-packages
```

Fast tests migrate temporary SQLite files through Alembic; they never call create_all.
PostgreSQL integration tests are opt-in locally and mandatory in CI. They create
unique classifier slugs and append data; use a disposable database, never production.

```bash
OPENCLASS_TEST_DATABASE_URL="$OPENCLASS_DATABASE_URL" uv run pytest -m postgres
uv run alembic check
```

Or run the entire test suite inside Compose (including PostgreSQL):

```bash
docker compose --profile test run --build --rm test
```

Migrations are explicit, reviewed and immutable after release. To add one:

```bash
uv run alembic revision --autogenerate -m 'describe schema change'
# Review both directions before running:
uv run alembic upgrade head
```

For a database-free fast start:

```bash
export OPENCLASS_DATABASE_URL=sqlite+aiosqlite:///./openclass.db
uv run alembic upgrade head
uv run openclass serve
```

SQLite is a development adapter, not the production storage target. To reset it,
stop the server and explicitly remove your own development file. Never automatically
reset a database on startup or after a migration error.

For an existing local Chromium installation, set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. CI installs the browser
version managed by Playwright. Browser checks cover desktop/mobile observation,
unknown, empty and error states using public-API fixtures; Python E2E checks cover
real persistence through the HTTP API.

## Public boundaries

`packages/core` contains no HTTP/database code. Server persistence implements core
repository ports. Mock and future real providers implement choice. SDKs must not
import the server or core. CLI's only direct server dependency is process lifecycle.
Use `/docs` and `/openapi.json` to inspect the API. Request validation returns 422,
missing resources 404, duplicate slugs 409, provider errors 502, database failures 503.
Classification POSTs create new observations; retries are not currently idempotent.

## Packaging and deployment

Compose performs migration as a separate one-shot service before starting the API.
The server runs as an unprivileged container user. The web workspace is a separate
local developer process in Genesis; a web image is a follow-up delivery task.
`docker compose down` preserves observations. Removing the volume is destructive.

CI builds wheels and the web application and exercises Compose. Release publication
is not enabled; the manually invoked artifact workflow builds reviewable artifacts.
