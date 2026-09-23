# Contributing to OpenClass

Start with the [development guide](docs/guides/development.md),
[architecture](docs/architecture/SPECIFICATION.md), and
[development tickets](docs/contributing/tickets.md).

Bug fixes, tests, documentation, examples, benchmarks, performance improvements,
and provider adapters are welcome. Before implementing changes to ontology
architecture, novelty algorithms, public APIs, UI architecture, promotion lifecycle,
or database schema, open an issue/RFC for maintainer design review. The founding
architecture authorizes the current Genesis scaffold.

Keep changes independently buildable, scoped to one problem, and accompanied by
meaningful tests. New behavior needs typed models, documented errors/API, domain
events where applicable, and migrations for persistence changes. Do not add a
feature to the roadmap merely to justify scope expansion.

```bash
uv sync --all-packages --locked
npm ci
make check
make test
npm run build
uv build --all-packages
```

PostgreSQL integration checks also run in CI. Explain what changed, why, how it was
verified, and any remaining limitation in your pull request. Mock-provider scores
must not be presented as real model performance. Never include production data or
credentials in tests, logs, examples, or issues.

Use [the RFC template](docs/contributing/rfc-template.md) for significant design
changes. Maintainers review public interfaces and invariants before merging.
Contributions are licensed under the repository's AGPL-3.0-only license. No CLA
is currently in place; any future contributor agreement requires a governance decision.
By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
