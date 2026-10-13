# Phase 10 — Discovery & Canonicalization

- **Depends on:** Phase 09
- **Traceability:** SPEC §§6–17 (DiscoveryProvider, canonicalization, six proposal types), §§58–66 (ADD/ALIAS/REJECT); OC-006

## 1. Goal

Turn clusters into inactive candidate proposals with evidence, canonical names, alias/existing-concept checks — never active behavior.

## 2. Non-goals

- No evaluation, review approval, or promotion (Phases 11–14). No per-unknown LLM calls.

## 3. Constraints

- Providers cannot write ontology. All six types handled: `NEW_CLASS, EXISTING_CLASS, ALIAS, INSUFFICIENT_EVIDENCE, OUT_OF_DOMAIN, SCHEMA_ISSUE`.
- Canonicalization resolves synonyms before new-class suggestion (e.g. “cancel plan” vs “close subscription”).
- Cluster summaries sent externally are minimal + redacted. No automatic activation button exists anywhere.

## 4. Tasks

### Engine

1. `DiscoveryRequest { cluster_id, member_texts (capped, redacted), existing_classes, ontology_version }`, `DiscoveryResult { type, canonical_name?, display_name?, definition?, aliases[], existing_match?, confidence, reason }`.
2. Adapters: `mock` (deterministic), `openai-compatible`, `ollama`; structured output validation; timeouts/telemetry like Phase 07.
3. Canonicalizer: normalize (lower, trim, synonym map), compare aliases/existing (exact + embedding similarity), decide NEW vs ALIAS vs EXISTING.
4. `POST /projects/:id/clusters/:cid/discover` → creates `candidate` (status `candidate`) + `candidate_evidence` links; emits `candidate.created`. No ontology write.

### Portal

Routes: `/projects/:id/discoveries` (candidate cards: type chip, confidence, evidence count, status), `/projects/:id/discoveries/:cid` (definition, aliases, existing-match check, evidence list, provenance). Actions here are read-only; mutations live in Phase 11.

## 5. Data & migrations

`candidates (id, project_id, type, canonical_name, display_name, definition, confidence, status, created_at)`, `candidate_evidence (candidate_id, unknown_event_id)`. Alembic.

## 6. API

- `POST /api/v1/projects/:id/clusters/:cid/discover`
- `GET /api/v1/projects/:id/candidates`, `GET .../candidates/:cid`

## 7. Portal routes

| Route                            | Expected                                                  |
| -------------------------------- | --------------------------------------------------------- |
| `/projects/:id/discoveries`      | “cancel_request” candidate (or alias) with evidence count |
| `/projects/:id/discoveries/:cid` | Shows INSUFFICIENT_EVIDENCE for tiny clusters correctly   |

## 8. Seeder + credentials

`pnpm seed:portal-phase-10`: runs discovery on Phase 09 clusters; expects cancel → `NEW_CLASS` or `ALIAS` (if cancel exists) + one `INSUFFICIENT_EVIDENCE`. Owner runs; reviewer views.

## 9. Manual browser tests

| #   | Action                                              | Expected                                             |
| --- | --------------------------------------------------- | ---------------------------------------------------- |
| 1   | Discover cancel cluster                             | Candidate with definition + aliases, status inactive |
| 2   | Discover singleton cluster                          | `INSUFFICIENT_EVIDENCE`, no candidate promotion path |
| 3   | Check synonyms “cancel plan” / “close subscription” | Canonicalized to one proposal, not two classes       |

## 10. Automated tests

Unit: synonym merge, alias detection, six-type handling. Contract: malformed discovery JSON rejected; oversized rationale rejected. Integration: candidate references all member observations.

## 11. Acceptance

- [ ] Candidates inactive; no ontology change.
- [ ] Synonyms cannot bypass canonicalization.

## 12. Risks

LLM hallucinated names → constrain with existing-class list + low-confidence → INSUFFICIENT_EVIDENCE.
