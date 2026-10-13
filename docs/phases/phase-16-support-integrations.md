# Phase 16 — Support Integrations

- **Depends on:** Phases 05–06, 15
- **Traceability:** SPEC product vision §§28–29 (Zendesk/Intercom/Freshdesk/Salesforce/Slack/Webhook/CSV); OC-033 (webhook receipts, scoped identity)

## 1. Goal

Connect support workflows: webhooks + Zendesk/Intercom first, with safe routing (known → tag/route; UNKNOWN → human triage, never auto-reply).

## 2. Non-goals

- No Salesforce/Slack in this slice (stubs with honest “not implemented” if shown). No KB/FAQ (Phase 17).

## 3. Constraints

- Webhook auth via env-backed tokens; scoped event identity; atomic observation/audit/receipt persistence (OC-033 pattern).
- Unsupported adapters cannot invent capabilities — UI shows “connectivity checks … not implemented” honestly.
- UNKNOWN never triggers auto-reply or auto-routing.

## 4. Tasks

### Engine

1. Generic webhook: `POST /api/v1/projects/:id/webhooks/:source` (HMAC/bearer per adapter), idempotent receipts (`0010` pattern), source→event mapping.
2. Adapters: `zendesk`, `intercom` (isolated modules): `connect (validate creds ref)`, `route (add tag, assign queue)`, `escalate (triage queue + needs-review tag)`.
3. Routing rules: `POST .../integrations/routes { when: known_choice==X → action }`; UNKNOWN path fixed to escalate.

### Control-plane

`GET/POST /control/.../integrations`, `POST .../integrations/:id/connect`, `GET .../health` (honest status per adapter).

### Portal

Routes: `/projects/:id/integrations` (adapter cards + connect), `/projects/:id/integrations/:source` (route rules, test delivery, receipt log).

## 5. Data & migrations

`integrations`, `integration_routes`, `webhook_receipts` (reuse `0010`); Alembic.

## 6. API

- `POST /api/v1/projects/:id/webhooks/:source`
- `GET/POST /api/v1/projects/:id/integrations*`

## 7. Portal routes

| Route                                | Expected                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------ |
| `/projects/:id/integrations`         | Zendesk/Intercom connect; others show honest stub                        |
| `/projects/:id/integrations/zendesk` | Known billing → adds “billing” tag; UNKNOWN → triage item, no auto-reply |

## 8. Seeder + credentials

`pnpm seed:portal-phase-16`: mock Zendesk connection (simulated), 2 routing rules, 3 receipt fixtures. Owner connects; reviewer tests delivery.

## 9. Manual browser tests

| #   | Action                       | Expected                                  |
| --- | ---------------------------- | ----------------------------------------- |
| 1   | Deliver known billing ticket | Tagged + routed correctly; receipt logged |
| 2   | Deliver UNKNOWN ticket       | Triage queue item; no auto-reply sent     |
| 3   | Bad webhook secret           | 401, no ingestion                         |

## 10. Automated tests

Unit: HMAC verify, rule matching. Integration: concurrent identical webhook → 1 event; changed payload conflicts; retries survive restart.

## 11. Acceptance

- [ ] Safe routing verified; UNKNOWN path never auto-acts.

## 12. Risks

Vendor API drift → adapter version pin + contract fixtures.
