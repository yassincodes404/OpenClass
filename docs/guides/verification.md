# Genesis verification record

Validated locally on 2026-09-23. This is implementation evidence, not a public release certification.

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
