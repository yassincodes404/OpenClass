import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { AuditService } from "./audit.service.js";
import { IdempotencyService } from "./idempotency.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import { redactText } from "./redaction.js";

type Row = Record<string, unknown>;

function fakePool(
  script: (text: string, params?: unknown[]) => Promise<{ rows: Row[]; rowCount: number }>,
): Pool {
  return { query: vi.fn(script) } as unknown as Pool;
}

describe("AuditService", () => {
  it("records actor/action/target without secrets", async () => {
    const calls: { text: string; params?: unknown[] }[] = [];
    const pool = fakePool(async (text, params) => {
      calls.push({ text, params });
      return { rows: [], rowCount: 0 };
    });
    await new AuditService(pool).record({
      workspaceId: "w1",
      projectId: "p1",
      actor: "subject-1",
      action: "api_key.created",
      target: "key:oc_dev_abc…",
    });
    const insert = calls.find((c) => c.text.startsWith("INSERT INTO control_audit_events"));
    expect(insert?.params).toEqual(["w1", "p1", "subject-1", "api_key.created", "key:oc_dev_abc…"]);
    expect(JSON.stringify(insert?.params)).not.toMatch(/oc_dev_[0-9a-f]{20,}/);
  });

  it("pages newest-first with a cursor and caps limit at 100", async () => {
    const calls: { text: string; params?: unknown[] }[] = [];
    const iso = new Date("2026-10-02T10:00:00Z");
    const pool = fakePool(async (text, params) => {
      calls.push({ text, params });
      const rows = Array.from({ length: 3 }, (_, i) => ({
        id: `e${i}`,
        workspace_id: "w1",
        project_id: null,
        actor: "a",
        action: "project.created",
        target: "project:x",
        created_at: new Date(iso.getTime() - i * 1000),
      }));
      return { rows, rowCount: rows.length };
    });
    const page = await new AuditService(pool).list("w1", {
      limit: 3,
      cursor: "2026-10-02T11:00:00.000Z",
    });
    expect(page.items).toHaveLength(3);
    expect(page.next_cursor).toBe(page.items[2].created_at.toISOString());
    const select = calls[0];
    expect(select.text).toContain("ORDER BY created_at DESC");
    expect(select.text).toContain("created_at <");
    await expect(new AuditService(pool).list("w1", { limit: 500 })).resolves.toBeDefined();
    const capped = calls[calls.length - 1];
    expect(capped.params?.[1]).toBe(100);
  });

  it("exposes no update or delete path (append-only by construction)", () => {
    const service = new AuditService(fakePool(async () => ({ rows: [], rowCount: 0 })));
    expect(Object.getOwnPropertyNames(Object.getPrototypeOf(service)).sort()).toEqual([
      "constructor",
      "list",
      "record",
    ]);
  });
});

describe("RateLimitService", () => {
  it("allows up to capacity then 429s with retry-after", () => {
    const limiter = new RateLimitService();
    const t0 = 1_000_000;
    const first = limiter.check("key-1", "ingest", t0);
    expect(first.allowed).toBe(true);
    // Drain the bucket (default ingest capacity 60).
    let drained = false;
    for (let i = 1; i <= 60; i += 1) {
      const decision = limiter.check("key-1", "ingest", t0 + i);
      drained = !decision.allowed;
      if (drained) break;
    }
    expect(drained).toBe(true);
    const blocked = limiter.check("key-1", "ingest", t0 + 100);
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfterSeconds).toBeGreaterThanOrEqual(1);
    expect(blocked.limit).toBe(60);
  });

  it("isolates identities and classes", () => {
    const limiter = new RateLimitService();
    const t0 = 2_000_000;
    for (let i = 0; i < 60; i += 1) limiter.check("a", "ingest", t0 + i);
    expect(limiter.check("a", "ingest", t0 + 100).allowed).toBe(false);
    expect(limiter.check("b", "ingest", t0 + 100).allowed).toBe(true);
    expect(limiter.check("a", "classify", t0 + 100).allowed).toBe(true);
  });
});

describe("IdempotencyService", () => {
  it("replays a stored response for a repeated key", async () => {
    const pool = fakePool(async () => ({
      rows: [{ response: { id: "p1", slug: "acme" } }],
      rowCount: 1,
    }));
    const replayed = await new IdempotencyService(pool).replay<{ id: string }>("w1", "key-42");
    expect(replayed).toEqual({ id: "p1", slug: "acme" });
  });

  it("stores the response hash, never executes the mutation twice at the caller level", async () => {
    const calls: { text: string; params?: unknown[] }[] = [];
    const pool = fakePool(async (text, params) => {
      calls.push({ text, params });
      return { rows: [], rowCount: 0 };
    });
    await new IdempotencyService(pool).remember("w1", "key-42", { id: "p1" });
    const insert = calls[0];
    expect(insert.text).toContain("ON CONFLICT (key, workspace_id) DO NOTHING");
    expect(insert.params?.[2]).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("redaction", () => {
  it("strips emails, cards, tokens, and blocklist terms", () => {
    const redacted = redactText(
      "Mail a@b.co card 4111111111111111 key oc_dev_0123456789abcdef0123456789abcdef secret-project",
      ["secret-project"],
    );
    expect(redacted).not.toContain("a@b.co");
    expect(redacted).not.toContain("4111111111111111");
    expect(redacted).not.toContain("oc_dev_0123");
    expect(redacted).not.toContain("secret-project");
    expect(redacted).toContain("[redacted]");
  });

  it("leaves ordinary support text intact", () => {
    expect(redactText("I was charged twice for my subscription")).toBe(
      "I was charged twice for my subscription",
    );
  });
});
