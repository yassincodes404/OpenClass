# Phase 19 — Billing & Deployment Operations

- **Depends on:** Phases 04, 18
- **Traceability:** Product vision §§11–13 (SaaS, usage-based, enterprise), §30 (backups, logging, tracing, CI/CD, migrations, rollback)

## 1. Goal

Monetize and operate safely: Stripe test-mode subscriptions, plan enforcement, metering, email, backups/restore drills, tracing/alerts, CI/CD + rollback procedure. Still no production customer charge — test-mode only.

## 2. Non-goals

- No real charges. No Enterprise SSO/VPC/on-prem (document as roadmap).

## 3. Constraints

- Pricing hypotheses only (Genesis $0, Explorer $29–49, Studio $149–299, Business $750–1500, Enterprise $15k–100k+/yr) — validated with customers later, not hard-coded as “final”.
- Metered units: classifications, retained observations, active classifiers, seats, discovery/eval runs, API requests, exports, provider usage. Platform fee + provider usage shown separately.
- Backups tested by restore drill, not just “backup exists”.

## 4. Tasks

### Control-plane + infra

1. Stripe test-mode: `POST .../billing/checkout` (test key), `POST .../billing/webhook` (verify signature), `GET .../billing/subscription`; plans table; enforcement middleware (402/429 with upgrade message when over quota).
2. Metering job aggregates `usage_events` → `billing_periods`.
3. Email via Resend/Postmark (dev stub logs): invite, quota, eval-ready, UNKNOWN-spike digests.
4. Backups: `pg_dump` cron docs + `scripts/backup.sh`, restore to disposable DB + verify (`scripts/restore_verify.sh`); runbook.
5. Observability: OpenTelemetry traces (portal→control→engine `trace_id`), Sentry (no PII), health/ready probes.
6. CI/CD: GitHub Actions (typecheck/build/test/migrate check), container build, rollback procedure (previous image + migration down plan for dev only; prod uses forward-fix + new version).

### Portal

Routes: `/billing` (plans, current test subscription, usage vs quota), `/projects/:id/usage` (enforcement banners), `/projects/:id/settings` (plan + email prefs).

## 5. Data & migrations

`plans`, `subscriptions`, `billing_periods`, `usage_aggregates`, `email_log`; control-plane SQL.

## 6. API

- `GET /billing/plans`, `POST /billing/checkout`, `POST /billing/webhook`, `GET .../subscription`
- `GET .../usage` (now quota-aware: `{ used, included, overage }`)

## 7. Portal routes

| Route                 | Expected                                                       |
| --------------------- | -------------------------------------------------------------- |
| `/billing`            | Test subscription + usage bars; over-quota shows clear message |
| `/projects/:id/usage` | Enforcement banner when capped                                 |

## 8. Seeder + credentials

`pnpm seed:portal-phase-19`: test subscription (Explorer, 10k included), usage at 80% + one over-quota fixture. Owner manages billing; others read-only/blocked.

## 9. Manual browser tests

| #   | Action              | Expected                                                        |
| --- | ------------------- | --------------------------------------------------------------- |
| 1   | Open billing        | Test-mode badge; no real card required                          |
| 2   | Exceed quota        | Classify → 402/429 with upgrade CTA (recoverable, no data loss) |
| 3   | Trigger alert email | Dev log shows email (no real send)                              |

## 10. Automated tests

Unit: quota math, webhook signature. Integration: over-quota blocked; webhook idempotent. Ops: backup/restore verify script passes on disposable DB.

## 11. Acceptance

- [ ] Test-mode billing + enforcement + backup restore verified; no real charges.

## 12. Risks

Accidental live keys → blocklist `sk_live` in test env; separate env files.
