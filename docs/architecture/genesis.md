# Genesis implementation decisions

This is an executable foundation for the founding specification's §§37, 45, 56, 57.
It includes Phase 0, the classification kernel, and initial novelty persistence.
It is not the Discovery milestone.

1. **uv workspace, hatchling packages.** Each Python component has its own installable
   distribution. One lockfile resolves the workspace. The root is virtual. See
   [uv workspace documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/).
2. **Thin clients.** Python/TypeScript SDKs use HTTP, CLI uses the Python SDK, and
   Next.js uses the TypeScript SDK through same-origin rewrites. Next.js follows its
   [App Router setup](https://nextjs.org/docs/app/getting-started/installation).
3. **Versioned snapshots first.** Seven relational tables hold JSON domain snapshots.
   These preserve evidence and stable IDs without speculative empty tables. Classifier
   active-version and run payloads duplicate indexed identities; service writes keep
   them consistent. Fully normalized classes, projects, aliases, usage and evaluation
   tables are follow-up migrations. Ontology tuples and frozen models prevent in-process
   mutation; database triggers reject updates/deletes of versions and events.
4. **Atomic history.** Creation and classification use transaction contexts, following
   [SQLAlchemy transaction guidance](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).
   Provider execution precedes the write. A failed call produces no completed run.
5. **No hidden activation path.** No promote/alias/merge endpoint exists before evidence,
   canonicalization, evaluation and review guards. A frozen snapshot is not yet a full
   replayable semantic event-sourcing engine. Full events/diff/rollback are ticketed.
6. **PostgreSQL is primary.** pgvector is installed by migration, but no fabricated
   embeddings are stored. SQLite is a fast development/test convenience, not a promise
   of identical concurrency semantics or a production replacement.
7. **No remote inference.** Only the deterministic mock is registered. Its dictionary
   matching is useful for contracts and developer examples, not accuracy claims.
   Only choice is defined now; boolean/score and discovery/embedding ports land with
   implementations and contract tests.
8. **Explicit configuration.** Novelty settings are environment configurable through
   nested Pydantic settings. Project YAML, encrypted credential storage and redaction
   will land before remote integrations. Genesis persists raw text locally.
9. **Audit polling first.** Ordered, cursor-based event history is available over JSON.
   Durable resumable SSE and provider-failure telemetry are still planned.
10. **No public deployment by default.** Compose binds host services to 127.0.0.1.
    Actor is `local-user`, not authenticated identity. No auth/RBAC claims are made.
11. **Reviews are advisory evidence (OC-016).** A `SupervisorProvider` re-examines a
    persisted run with the ontology version that run actually used and returns a
    bounded, structured finding. Reviews persist append-only beside the run they
    reviewed; they never rewrite runs, ontology, or the unknown pool, and no
    apply/promote route exists. Only the deterministic mock supervisor is registered.

## Known limits

No discovery, clustering, promotion, evaluation, rollback, TUI, Jev/remote providers,
installer, package publication, or benchmark results. Supervisor reviews are
manual-trigger only with the simulated mock; no reasoning model, automatic
sampling, or batch audit exists yet (OC-018/OC-020). Lists of classifiers/versions
are unpaginated for the initial local workspace; run, review, unknown and event
history are bounded. Python SDK responses are typed dictionaries of JSON values;
fully generated SDK models and protocol compatibility checks are planned. No
automatic schema creation occurs.

## Invariants

- A known result references a class in the captured ontology; unknown selects no class.
- Probabilities include UNKNOWN, are finite, and sum to 1 within tolerance.
- Distribution keys must exactly match the version used for inference.
- Duplicate slugs conflict and never overwrite a classifier.
- Unknown observations, runs and events commit atomically.
- Existing ontology versions and audit records cannot be updated or deleted by SQL DML.
- A supervisor review never modifies the run, ontology, or unknown pool it examined;
  reviews are append-only and a provider finding is never ground truth.
- No model output becomes ground truth, and no new class is automatically activated.
