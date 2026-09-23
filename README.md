<div align="center">

# OpenClass

**The open-world classification engine.**

Start with what you know. Discover what you don't.

[Quick start](#quick-start) · [Architecture](docs/architecture/SPECIFICATION.md) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md)

`UNKNOWN → EVIDENCE → DISCOVERY → EVALUATION → HUMAN REVIEW → EVOLUTION`

</div>

OpenClass treats a classifier’s label space as versioned system knowledge.
It gives observations a persistent UNKNOWN state, so missing concepts can become
researchable evidence instead of forced, incorrect labels.

**Status: v0.0.1 — Genesis foundation.** This repository implements classification,
unknown detection, persistence, and the client/server boundary. Discovery,
clustering, evaluation, and human-reviewed promotion are planned, not implemented.
There is no public release or installer yet.

Unreleased: supervisor reviews can independently inspect
persisted classification runs and produce advisory findings, including disagreement
with a confident known result. Reviews do not change classifications or ontology
state; only the deterministic mock supervisor is registered.

## Quick start

Requires Docker with Compose. No model account or API key is needed.

```bash
git clone https://github.com/yassincodes404/OpenClass.git
cd OpenClass
docker compose up --build -d --wait
curl http://localhost:7331/health/ready

docker compose exec server openclass init examples/support-intents/classifier.json
docker compose exec server openclass classify "I was charged twice"
docker compose exec server openclass classify "Cancel my plan"
docker compose exec server openclass unknowns --classifier support-intent
```

The first observation matches `billing`. The second is stored as UNKNOWN with
its novelty assessment, provider distribution, and ontology version. The bundled
mock provider uses lexical rules: its scores are fixtures, not calibrated confidence.
Creating the same classifier twice returns a conflict rather than replacing history.

API documentation: [localhost:7331/docs](http://localhost:7331/docs).
Compose starts PostgreSQL with pgvector, runs migrations, and starts the API.
Data lives in the `postgres-data` volume. `docker compose down` preserves it.
The unauthenticated development services bind to loopback only.

## Web workspace

With the server running, install Node.js 22+ and run:

```bash
npm ci
npm run dev
```

Open [localhost:3000](http://localhost:3000). The initial observation workspace
lists classifiers and displays real API results; it does not simulate discoveries.

## Python development

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync --all-packages --locked
docker compose up -d db
uv run alembic upgrade head
uv run openclass serve
```

In another terminal:

```bash
uv run openclass init examples/support-intents/classifier.json
uv run openclass classify "I was charged twice"
uv run openclass doctor
make check
make test
```

`openclass` currently prints help. The interactive TUI is a later milestone.
See the [development guide](docs/guides/development.md) for database configuration,
SQLite tests, PostgreSQL tests, migrations, and builds. See the
[verification record](docs/guides/verification.md) for results and local environment qualifications.

## Foundation included

- Provider-neutral typed domain models, a choice protocol, and mock adapter.
- Configurable novelty policy with unknown probability, confidence, margin, and reasons.
- PostgreSQL persistence with atomic classification history and an unknown pool.
- Immutable ontology snapshots, stable class IDs, and append-only audit events.
- FastAPI API, Python/TypeScript HTTP clients, CLI, and Next.js observation workspace.
- Alembic migrations, pgvector infrastructure, CI, tests, governance, and development tickets.

## Repository map

| Path                                             | Responsibility                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| `packages/core`                                  | Domain models, provider/repository ports, classification and novelty |
| `packages/server`                                | HTTP API, SQLAlchemy persistence, migrations                         |
| `packages/cli`                                   | HTTP commands and local server lifecycle                             |
| `packages/sdk-python`, `packages/sdk-typescript` | Public HTTP clients                                                  |
| `packages/tui`, `apps/web`                       | Planned TUI and initial web workspace                                |
| `providers`                                      | Isolated provider adapters; only mock is implemented                 |
| `benchmarks`, `examples`                         | Reproducible scenarios and classifier configurations                 |
| `docs`                                           | Architecture, concepts, guides, research, and scoped tickets         |
| `tests`                                          | Unit, provider contract, integration, and end-to-end checks          |

Dependencies flow inward: clients → public HTTP protocol → server → core.
Providers implement core interfaces. No UI owns classification or learning rules.

For real-provider readiness and the first measured experiment, see the
[live-testing guide](docs/guides/live-testing.md).

## Toward Discovery

The defining next loop is recurring unknowns → candidate → replay evaluation →
human approval → ontology v2 → improved classification. See the
[canonical implementation specification](docs/architecture/SPECIFICATION.md),
[Genesis decisions](docs/architecture/genesis.md), and
[first development tickets](docs/contributing/tickets.md).

Source: [AGPL-3.0-only](LICENSE). Project identity: [trademark policy](TRADEMARKS.md).
Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). No contributor agreement is required.
