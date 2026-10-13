# Phase 15 — Live Operations & Quality Dashboard

- **Depends on:** Phases 06–14 (reads their data; no new decision logic)
- **Traceability:** SPEC §§113–120 (events, telemetry); product vision §21 (Overview Dashboard)

## 1. Goal

Answer “Is my classification system healthy?” with live metrics, UNKNOWN-rate alerts, recurring-unknown alerts, and SSE updates.

## 2. Non-goals

- No new classification/discovery logic. No billing (Phase 19).

## 3. Constraints

- All numbers are measured persisted values, never samples or invented benchmarks.
- SSE is initial live transport (resumable by cursor); WebSocket later.
- Alerts are configurable thresholds, not hard-coded.

## 4. Tasks

### Engine/control-plane

1. Aggregations: `GET .../analytics/summary?from&to` (total, known/uncertain/novel rates, top classes, UNKNOWN trend, provider cost, pending reviews, recent versions, quality alerts).
2. Alert rules: `POST .../alerts/rules { metric: unknown_rate|recurring_unknowns|latency|cost, threshold, window }`; evaluation on ingest/run; `quality.alert` event.
3. SSE: `GET /api/v1/projects/:id/events?cursor=` (resumable, ordered); portal subscribes for runs/unknowns/candidates/evaluations.

### Portal

Routes: `/projects/:id` (overview KPIs + UNKNOWN-rate delta card), `/projects/:id/analytics` (trend charts, top classes, cost, pending reviews, recent versions, alert config). Charts: lightweight SVG first; no heavy dep until needed. Storybook stories for KPI cards.

## 5. Data & migrations

`alert_rules`, `alert_events`; materialized counters or indexed rollups (avoid full scans).

## 6. API

- `GET /api/v1/projects/:id/analytics/summary`
- `GET/POST /api/v1/projects/:id/alerts/rules`
- `GET /api/v1/projects/:id/events?cursor=` (SSE/JSON polling fallback)

## 7. Portal routes

| Route                     | Expected                                                            |
| ------------------------- | ------------------------------------------------------------------- |
| `/projects/:id`           | KPIs reflect seeded runs; UNKNOWN spike alert visible when breached |
| `/projects/:id/analytics` | Trends + cost + pending reviews; alert rule CRUD                    |

## 8. Seeder + credentials

`pnpm seed:portal-phase-15`: 7 days of runs with UNKNOWN spike (4%→14%), 83 recurring unknowns fixture, one alert rule breached. Any authenticated role views; admin configures alerts.

## 9. Manual browser tests

| #   | Action                          | Expected                                                                          |
| --- | ------------------------------- | --------------------------------------------------------------------------------- |
| 1   | Open overview                   | “Last week 4%, this week 14%” style card + “83 recurring unknowns require review” |
| 2   | Create alert rule threshold 10% | Alert fires on spike; event logged                                                |
| 3   | New classification arrives      | Dashboard updates via SSE without reload                                          |

## 10. Automated tests

Unit: aggregation math, alert threshold evaluation. Integration: SSE resume by cursor; disconnect/backpressure documented. UI: KPI stories + Playwright dashboard load.

## 11. Acceptance

- [ ] All metrics measured; alerts configurable and observable.

## 12. Risks

SSE scaling → cursor pagination + fallback polling; document limits.
