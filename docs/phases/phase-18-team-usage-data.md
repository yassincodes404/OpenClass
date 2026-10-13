# Phase 18 — SaaS Workspace Operations

- **Depends on:** Phases 02–03
- **Traceability:** Product vision §§29–30 (Team & Access, production readiness: retention/deletion/export)

## 1. Goal

Operate workspaces as SaaS: team roles/invites, API-key management, usage metering, exports, retention/deletion requests — all auditable and scoped.

## 2. Non-goals

- No billing charges (Phase 19). No SSO/SCIM/IP allow-list (Enterprise later; stub honestly).

## 3. Constraints

- Matrix: Owner (billing/deletion/all), Admin (team/integrations/classifiers), Reviewer (unknowns/evidence/proposals), Analyst (reports/exports), Developer (API keys/tech), Viewer (read-only). Enforced server-side.
- Exports/deletion scoped to workspace; deletion is request + approval + audit, not instant silent wipe (retention policy).
- No PII in audit logs beyond subject id.

## 4. Tasks

### Control-plane

1. Invites: `POST .../invites { email, role }` → token (hashed), `POST .../invites/:token/accept` (Keycloak link on accept in dev: map email to sub).
2. Keys: list/revoke (from Phase 03) + scopes editor + last-used.
3. Usage: `GET .../usage?from&to` (classifications, retained obs, active classifiers, seats, discovery/eval runs, API requests, exports, provider cost).
4. Data: `POST .../data/export` (CSV/JSON job + download), `POST .../data/deletion` (request with reason → pending → admin approve → scoped purge, audit).

### Portal

Routes: `/projects/:id/team` (members, invites, role editor), `/projects/:id/usage` (meters + quotas), `/projects/:id/settings/data` (export/deletion). Role-gated UI + server 403 fallback messages.

## 5. Data & migrations

`invites`, `usage_events`, `export_jobs`, `deletion_requests`; control-plane SQL.

## 6. API

- `GET/POST .../members`, `POST .../invites`, `POST .../invites/:token/accept`
- `GET .../usage`, `POST .../data/export`, `POST .../data/deletion`

## 7. Portal routes

| Route                         | Expected                                                    |
| ----------------------------- | ----------------------------------------------------------- |
| `/projects/:id/team`          | Owner invites reviewer; reviewer cannot manage billing/keys |
| `/projects/:id/usage`         | Meters match seeded runs                                    |
| `/projects/:id/settings/data` | Export downloads; deletion request auditable                |

## 8. Seeder + credentials

`pnpm seed:portal-phase-18`: invites reviewer (pending), usage fixtures, one export job. Owner manages; reviewer cannot invite admins.

## 9. Manual browser tests

| #   | Action                      | Expected                                 |
| --- | --------------------------- | ---------------------------------------- |
| 1   | Invite analyst              | Email stub logged (dev); accept works    |
| 2   | Reviewer opens billing/keys | 403 + read-only message                  |
| 3   | Export observations         | CSV downloads; job logged                |
| 4   | Request deletion            | Pending → approve → scoped purge + audit |

## 10. Automated tests

Unit: role matrix; scope checks. Integration: cross-workspace export blocked; deletion scoped.

## 11. Acceptance

- [ ] Least-privilege holds; all ops audited.

## 12. Risks

Invite abuse → expiry + single-use tokens + rate limits.
