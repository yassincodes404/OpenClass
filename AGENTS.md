# Working on OpenClass

Read `docs/architecture/SPECIFICATION.md`, `docs/architecture/genesis.md`, and
`docs/contributing/tickets.md` before changing architecture. This is a Genesis
foundation, not a completed v0.1 release.

- Core owns domain rules and ports; it must not import server, adapters, SDKs, or UI.
- Providers implement core ports; never give providers writable ontology access.
- SDKs speak HTTP only. UI and CLI use SDKs (CLI may launch the server).
- UNKNOWN is permanent. An unknown observation is not proof of a new class.
- Never turn predictions into ground truth or skip evidence/evaluation/review.
- Ontology snapshots and audit history are append-only. Aliases are versioned too.
- Add explicit Alembic migrations for persistence changes. Never use create_all at startup.
- All new behavior needs typed boundaries, errors, meaningful tests, API docs, and events.
- Keep mock output clearly marked as simulated. No invented benchmark or capability claims.
- No secrets in source, logs, provider errors, fixtures, or events.
- Follow the issue/RFC scope; do not add infrastructure or heavy ML dependencies speculatively.

Validation: `make check`, `make test`, `npm run build`, `uv build --all-packages`.
PostgreSQL checks require a disposable migrated database; see the development guide.
Do not publish packages, releases, or images merely to validate a change.
