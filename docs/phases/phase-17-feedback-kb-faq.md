# Phase 17 — Feedback, Knowledge-Base & FAQ Workflow

- **Depends on:** Phases 06, 11, 16
- **Traceability:** Product vision §§34–35 (FAQ/KB, safe LLM fallback)

## 1. Goal

Close the human-feedback loop and add safe FAQ/KB routing: known FAQ → approved article; UNKNOWN → research queue; LLM drafts only from approved content with human review when required.

## 2. Non-goals

- No open-ended generation. No “ask LLM anything on failure”.

## 3. Constraints

- OpenClass is intent layer, not answer source of truth: `Intent → Approved KB → Retrieval → LLM draft → Human review`.
- Feedback (`correct|missing_concept|note`) creates evidence (like core `submit_run_feedback`) but never auto-labels ground truth.
- All drafts cite KB version; unapproved content never sent.

## 4. Tasks

### Engine

1. Feedback: `POST .../runs/:rid/feedback { action, corrected_choice?, note? }` (reuse core pattern), evidence creation for correct/missing.
2. KB: `POST .../kb/articles { title, body, version }` (immutable versions), `POST .../decision-services/:sid/kb-links { choice → article_id }`.
3. FAQ run: known FAQ choice → retrieve article → optional LLM draft (provider-gated, redacted) → `draft` status; UNKNOWN → research queue item.
4. `GET .../feedback`, `GET .../knowledge` (articles + links + drafts).

### Portal

Routes: `/projects/:id/feedback` (queue: run, predicted, agent correction, actions), `/projects/:id/knowledge` (articles, link editor, draft preview with citations, “needs review” badge).

## 5. Data & migrations

`kb_articles`, `kb_links`, `faq_drafts`, `run_feedback` (reuse core feedback if present); Alembic.

## 6. API

- `POST /api/v1/projects/:id/runs/:rid/feedback`
- `GET/POST .../kb/articles`, `POST .../kb-links`, `POST .../faq-drafts`

## 7. Portal routes

| Route | Expected |
|---|---|
| `/projects/:id/feedback` | Agent corrects billing→refund; evidence created |
| `/projects/:id/knowledge` | Known “delivery time?” retrieves approved article; UNKNOWN enters research queue |

## 8. Seeder + credentials

`pnpm seed:portal-phase-17`: 3 KB articles (v1), 2 links, 5 feedback fixtures, 1 draft. Reviewer gives feedback; owner manages KB.

## 9. Manual browser tests

| # | Action | Expected |
|---|---|---|
| 1 | Submit correction | Feedback saved + evidence triage entry |
| 2 | Ask known FAQ | Approved article + cited draft |
| 3 | Ask UNKNOWN | No draft; research queue item |

## 10. Automated tests

Unit: link resolution, draft citation required. Integration: feedback evidence atomic; unlinked choice → no draft.

## 11. Acceptance

- [ ] No unrestricted generation on failed classification.

## 12. Risks

Stale KB → versioned articles + link health check.
