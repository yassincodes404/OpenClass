# Genesis verification record

Validated locally on 2026-09-23. This is implementation evidence, not a public release certification.

## OC-016 — Supervisor review foundation

Validated locally on 2026-09-23 on branch `oc-016-supervisor-review-foundation`,
on top of the Genesis results below.

| Check                                          | Result                                                                                                                                  |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Python lint, formatting and strict mypy        | Passed (25 source files)                                                                                                                |
| Python unit / contract / integration / E2E     | 59 passed on SQLite; 61 passed including PostgreSQL                                                                                     |
| Confidence bounds, closed enums, text limits   | Passed (`tests/unit/test_review_models.py`)                                                                                             |
| Mock supervisor contract                       | Passed, deterministic and marked simulated                                                                                              |
| Review lifecycle, isolation, safe 502, OpenAPI | Passed (`tests/integration/test_reviews.py`)                                                                                            |
| Append-only review rows (SQLite + PostgreSQL)  | UPDATE/DELETE rejected with append-only errors                                                                                          |
| Confident-misclassification stays advisory     | Passed (`tests/e2e/test_supervisor.py`): run remains `phone`, review says `possible_misclassification`, ontology v1 unchanged           |
| Reviews survive restart                        | Passed (E2E restart and live Compose restart)                                                                                           |
| TypeScript SDK contracts                       | 4 passed, including review route/trigger assertions                                                                                     |
| Desktop/mobile browser review panel            | 6 passed (3 tests × 2 projects)                                                                                                         |
| Next.js production build                       | Passed                                                                                                                                  |
| Five wheels plus source distributions          | Built; workspace version/license consistency passed                                                                                     |
| Compose migration to `0002_supervisor_reviews` | Passed; readiness reports the new revision                                                                                              |
| Live CLI review flow                           | known → `no_issue`; unknown → `possible_missing_class`; reviews persisted across `docker compose restart server`, ontology v1 unchanged |

The same environment qualifications as Genesis applied: image builds needed a
temporary `build.network: host` Compose override, host-to-container published
ports still time out (readiness and CLI checks run inside the container), and
PostgreSQL-marked tests ran against a disposable host-networked pgvector
container at `localhost:5432`. Browser tests used the local Chromium through
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

## Genesis

| Check                                       | Result                                        |
| ------------------------------------------- | --------------------------------------------- |
| Python lint, formatting and strict mypy     | Passed                                        |
| TypeScript checks and repository Prettier   | Passed                                        |
| Python unit / contract / integration / E2E  | 37 passed, including real PostgreSQL/pgvector |
| TypeScript SDK contracts                    | 2 passed                                      |
| Desktop/mobile browser behavior             | 4 passed                                      |
| Next.js production build                    | Passed                                        |
| Five Python wheels and source distributions | Built; each wheel includes AGPL text          |
| Workspace version/license consistency       | Passed                                        |
| Python dependency audit                     | No known vulnerabilities reported             |
| npm dependency audit during installation    | No vulnerabilities reported                   |
| Compose migrations and server readiness     | Passed                                        |
| CLI known/unknown flow                      | billing and persistent UNKNOWN confirmed      |

## Reproduce

Follow [development.md](development.md). `make check`, `make test`,
`npm run test:web`, `npm run build`, `uv build --all-packages`, and the optional
Compose test profile cover these checks. CI repeats the portable checks; a remote
GitHub Actions run has not been performed by this local implementation session.

## Local environment qualifications

Docker bridge downloads and host-to-container database connections timed out on
this machine. Images were built using an external temporary Compose override with
`build.network: host`; runtime services used the normal repository Compose network.
PostgreSQL tests ran inside the dedicated Compose test container and passed.
No host firewall or system configuration was changed. Plain bridge-based image
downloads remain unverified on this machine.

The managed Playwright browser download timed out. Browser tests instead used
an existing local Chromium through `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.
CI installs Playwright's managed Chromium. Screenshots were visually inspected
at desktop and mobile sizes. Browser tests use protocol fixtures; Python E2E and
CLI smoke checks exercise actual storage and API services.

One upstream Starlette TestClient deprecation warning remains (httpx transport).
It does not affect the passing tests or the runtime SDK.

Discovery, evaluation, human-reviewed promotion, TUI and real model adapters remain
future milestones. The full v0.1 learning-loop gate has not been implemented or claimed.
