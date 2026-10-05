# Phase 14 — Guarded Ontology Promotion

- **Depends on:** Phases 11 + 13
- **Traceability:** SPEC §§54–66, 75–79 (promotion guards, immutable versions, diff, rollback-as-new-version, events); OC-009 (RFC-0002)

## 1. Goal

Activate only validated candidates through explicit human approval into new immutable ontology versions, with diff and rollback-as-new-version.

## 2. Non-goals

- No autonomous promotion (deferred to OC-015, beyond v0.1). No MERGE/SPLIT/REPARENT/DEPRECATE beyond ADD/ALIAS/REJECT in v0.1.

## 3. Constraints

- Guards (all required): minimum distinct evidence + genuinely-new canonicalization + current successful evaluation + explicit human review. Stale/concurrent promotions conflict atomically.
- vN never changes; rollback creates vN+1 derived from older snapshot; history replays snapshots.
- Events identify actor/proposal/evaluation/from/to versions.

## 4. Tasks

### Engine

1. `POST .../candidates/:cid/promote { evaluation_id, reviewer, rationale }` → checks guards → creates `ontology_version vN+1` + `ontology_events (ClassAdded/AliasAdded)` → marks candidate `active`. Failures: 409 (stale/guard).
2. `GET .../ontology`, `GET .../ontology/versions`, `GET .../ontology/versions/:vid`, `GET .../ontology/diff?from=v2&to=v3` (added/modified/removed).
3. `POST .../ontology/rollback { from_version, rationale }` → new version derived from older (never edits history).

### Portal

Routes: `/projects/:id/ontology` (version timeline + diff viewer), `/projects/:id/ontology/versions/:vid` (class table), `/projects/:id/discoveries/:cid` (Promote button enabled only when eval passed + reviewer + evidence ok; otherwise disabled with reason tooltip).

## 5. Data & migrations

Normalize `ontology_classes`, `class_aliases`, `ontology_versions`, `ontology_events` as needed; triggers reject UPDATE/DELETE on versions/events (Genesis pattern).

## 6. API

- `POST /api/v1/projects/:id/candidates/:cid/promote`
- `GET /api/v1/projects/:id/ontology*`, `POST .../ontology/rollback`

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/ontology` | v1 → v2 diff shows `account_compromise` added (seeded) |
| `/projects/:id/discoveries/:cid` | Promote succeeds only with passing eval + approval |

## 8. Seeder + credentials

`pnpm seed:portal-phase-14`: approved + evaluated cancel candidate → promotes to v2; verifies same observation now classifies `known`. Owner/admin promote; reviewer cannot self-approve own request (403 if same actor, configurable).

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Promote without eval | 409 blocked |
| 2 | Promote with passing eval + approval | v2 created; v1 unchanged; diff correct |
| 3 | Reclassify previously UNKNOWN | Now `known` with v2 |
| 4 | Rollback v2 | v3 derived from v1; history intact; runs still reproducible |

## 10. Automated tests

Unit: guard logic, diff. Integration: concurrent promote conflict; failed eval blocks; replay reconstructs snapshots.

## 11. Acceptance

- [ ] Only guarded human promotion activates; vN immutable; rollback-as-new-version works.

## 12. Risks

Concurrent edits → optimistic locking on `current_version_id`.
