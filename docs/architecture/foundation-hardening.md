# Foundation hardening

Date: 2026-09-30. Scope: OC-033. Status: implemented locally, unreleased.

The founder requested structural cleanup and real core/integration behavior.
Keep the proven Python core, FastAPI server, Next.js client, HTTP SDKs and
PostgreSQL authority. The master/product documents describe the target runtime;
the Genesis specification still governs invariants and release claims.

## Concrete findings

The starting tree passed `make check` and its fast suite (314 passed, 12 skipped),
but mixed product and prototype behavior:

- `main.py` held more than 1,000 lines of unrelated handlers and integration I/O.
- Project candidate evaluation generated perfect scores from evidence counts and
  predicted choices. It did not replay independently verified cases.
- Project promotion could rewrite a decision service without a persistent
  evaluation, approval record or immutable version chain.
- Integration checks invented capabilities and connected states for unsupported
  adapters. A direct JSON-RPC `tools/list` request was not a complete MCP client.
- Missing webhook secrets fell back to the reference name itself as a token.
- Duplicate webhook deliveries created duplicate observations.
- System health claimed version 0.1.0; provider status confused package installation
  with an HTTP daemon that had actually been probed.

Passing tests mirrored those shortcuts, so correcting the contracts also required
replacing success assertions with checks that invalid activation cannot write state.

## Runtime structure

| Layer                                                                    | Responsibility                                                                                                          |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `packages/core/openclass_core`                                           | Domain models, services, policies and repository/provider ports                                                         |
| `packages/server/openclass_server/main.py`                               | Compose services, register errors, manage lifecycle and mount routes                                                    |
| `packages/server/openclass_server/api`                                   | Route modules for classifiers, projects, decisions, evidence, evolution, providers, integrations and system diagnostics |
| `packages/server/openclass_server/integration_adapters.py`               | Resolve environment secrets, authenticate webhook requests, probe supported HTTP endpoints                              |
| `packages/server/openclass_server/persistence/integration_repository.py` | Scoped integration configuration, health records, atomic webhook ingestion/receipts                                     |
| `packages/server/openclass_server/persistence/mappers.py`                | Shared raw-event and audit snapshot mapping                                                                             |
| `packages/sdk-python`, `packages/sdk-typescript`                         | Public HTTP clients, including external event identity and authentication headers                                       |
| `apps/web`                                                               | Public SDK consumer; shows supported/unsupported behavior accurately                                                    |

Routes depend on typed core services and ports. SQL transactions and HTTP transports
remain outside core. Integration configuration is not permission to execute a capability.
Existing historical artifacts and data are retained; this work does not re-label
earlier prototype activations as valid production approvals.

## Implemented slice

Generic webhook ingestion requires an environment-backed token and an external
`event_key`. The database transaction writes one source observation, one ingestion
audit event and one receipt. A retry with the identical logical payload returns the
original event; key reuse with changed content conflicts. Receipt identity is scoped
to project and integration. Receipt, raw-event and project-audit rows are protected
against UPDATE/DELETE by migration `0010_webhook_receipts`.

REST checks perform a bounded HTTP GET and optionally resolve a bearer credential.
They do not follow redirects, return upstream bodies, or claim unverified actions.
MCP, provider and database connector checks remain explicitly unimplemented.

Both legacy classifier and project evaluation/activation routes fail closed until
verified replay and immutable activation are implemented. Proposals, evidence,
triage, rejection and run inspection remain available. The public endpoints remain
for compatibility and return 409 rather than fabricated passing metrics.

## Next core work

1. OC-008: immutable verified datasets, label provenance, persisted baseline/candidate
   replay, hand-checked metrics, policy/version/dataset hashes and failure records.
2. OC-009/017: immutable decision/spec snapshots, explicit human approval tied to a
   successful evaluation, transactional current-version checks and version diffs.
3. Typed capability execution and independent verification, then transactional
   outbox delivery with retry state. Side effects need durable delivery before
   adding helpdesk write actions.
4. One customer-intelligence adapter (CSV or helpdesk) over generic ingestion and
   state/capability ports, with transport contracts and authorized live validation.

Do not introduce NestJS, migrate Next.js to Vite, or add Redis, object storage,
Kubernetes or a connector marketplace solely because a target document names them.
Durable job orchestration should arrive with the first implemented long-running
operation; its transport is a separate choice. Auth, tenancy, billing and RBAC belong
around the domain, and no current local endpoint claims enterprise authorization.
