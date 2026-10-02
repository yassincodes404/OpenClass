# Phase 09 — Embeddings & Clustering

- **Depends on:** Phase 08
- **Traceability:** SPEC §§6–17 (embedding → similarity grouping), §90 (pgvector, no heavy ML until needed); OC-005 (full)

## 1. Goal

Group recurring UNKNOWNs into evidence-backed clusters with provenance (algorithm/model versions), without inventing labels.

## 2. Non-goals

- No discovery LLM calls per unknown (batch summaries only, Phase 10). No candidate creation.

## 3. Constraints

- `EmbeddingProvider` port in core; local `sentence-transformers` adapter only when needed; no fabricated embeddings; pgvector is primary, SQLite dev only.
- No cross-classifier/project leakage; retries never duplicate evidence.
- Clusters are observations-groupings, not classes. Cluster names (if any) are display-only.

## 4. Tasks

### Engine

1. Port: `embed(texts[]) → vectors[]` with model version. Adapter: local sentence-transformers (lazy load, batch).
2. Migration: `embeddings (unknown_event_id fk, vector pgvector, model, created_at)`, `unknown_clusters (id, project_id, algorithm, model, threshold, created_at)`, `cluster_members (cluster_id, unknown_event_id)`. Install pgvector extension via migration (already in Genesis — reuse).
3. Job: `POST /projects/:id/unknowns/cluster { threshold?, limit? }` → deterministic grouping (cosine ≥ threshold, e.g. 0.82), persists clusters + `cluster.updated` event; idempotent reruns.
4. `GET .../unknowns/clusters`, `GET .../clusters/:cid` (members, centroid stats, provenance).

### Portal

Route `/projects/:id/unknowns/clusters`: cluster cards (size, top phrases, threshold/model badge), member list, provenance footer (`model vX, threshold 0.82, algorithm`). “Run clustering” button with progress; empty state when <2 unknowns.

## 5. Data & migrations

Alembic migration for tables above + ivfflat/hnsw index per pgvector docs (small data: exact search acceptable initially). Store no vectors in logs.

## 6. API

- `POST /api/v1/projects/:id/unknowns/cluster`
- `GET /api/v1/projects/:id/unknowns/clusters`, `GET .../clusters/:cid`

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/unknowns/clusters` | Seeded cancel cluster together; account-compromise separate |

## 8. Seeder + credentials

`pnpm seed:portal-phase-09`: embeds seeded unknowns then clusters; expects ≥1 cancel cluster (size ≥5) and ≥1 separate cluster. Owner runs clustering; reviewer views.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Run clustering | New cluster run id; cancel texts grouped |
| 2 | Open cluster | Members + provenance visible |
| 3 | Re-run same threshold | No duplicate clusters (idempotent) |

## 10. Automated tests

Unit: cosine grouping deterministic fixture; threshold edge cases. Integration: no cross-project leakage; restart-safe; `cluster.updated` emitted. Contract: embedding dim matches model version.

## 11. Acceptance

- [ ] Recurring unknowns group; unrelated stay separate.
- [ ] Provenance recorded; no label invention.

## 12. Risks

Heavy deps → gate sentence-transformers behind optional extra; document CPU fallback. Large data → batch + limit.
