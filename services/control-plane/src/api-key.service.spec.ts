import { ForbiddenException, NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { ApiKeyService, hashKey } from "./api-key.service.js";

type Row = Record<string, unknown>;

function fakePool(script: (text: string, params?: unknown[]) => Promise<{ rows: Row[]; rowCount: number }>): Pool {
  return { query: vi.fn(script) } as unknown as Pool;
}

describe("ApiKeyService", () => {
  it("creates a key, stores only the hash, and returns the raw value once", async () => {
    let inserted: { key_hash: string; prefix: string; scopes: string[] } | undefined;
    const pool = fakePool(async (_text, params) => {
      inserted = { key_hash: params![2] as string, prefix: params![3] as string, scopes: params![4] as string[] };
      return { rows: [{ id: "k1", workspace_id: "w1", project_id: "p1", prefix: params![3], scopes: params![4], created_at: new Date(), revoked_at: null }], rowCount: 1 };
    });
    const { key, row } = await new ApiKeyService(pool).create("w1", "p1", ["ingest", "read"]);
    expect(key).toMatch(/^oc_dev_[0-9a-f]{48}$/);
    expect(key.startsWith(row.prefix)).toBe(true);
    expect(inserted!.key_hash).toBe(hashKey(key));
    expect(inserted!.key_hash).not.toContain(key);
    expect(row.scopes).toEqual(["ingest", "read"]);
  });

  it("verifies an active key with the required scope", async () => {
    const pool = fakePool(async () => ({
      rows: [{ workspace_id: "w1", project_id: "p1", scopes: ["ingest", "read"], revoked_at: null }],
      rowCount: 1,
    }));
    const verified = await new ApiKeyService(pool).verify("oc_dev_x", "ingest");
    expect(verified).toEqual({ workspaceId: "w1", projectId: "p1", scopes: ["ingest", "read"] });
  });

  it("rejects a key that lacks the required scope", async () => {
    const pool = fakePool(async () => ({
      rows: [{ workspace_id: "w1", project_id: "p1", scopes: ["read"], revoked_at: null }],
      rowCount: 1,
    }));
    await expect(new ApiKeyService(pool).verify("oc_dev_x", "ingest")).rejects.toThrow(ForbiddenException);
  });

  it("rejects an unknown or revoked key (revoke blocks use)", async () => {
    const missing = fakePool(async () => ({ rows: [], rowCount: 0 }));
    await expect(new ApiKeyService(missing).verify("nope")).rejects.toThrow(ForbiddenException);
    const revoked = fakePool(async () => ({
      rows: [{ workspace_id: "w1", project_id: "p1", scopes: ["read"], revoked_at: new Date() }],
      rowCount: 1,
    }));
    await expect(new ApiKeyService(revoked).verify("oc_dev_x")).rejects.toThrow(ForbiddenException);
  });

  it("revoke is idempotent-safe: missing key → 404", async () => {
    const pool = fakePool(async () => ({ rows: [], rowCount: 0 }));
    await expect(new ApiKeyService(pool).revoke("p1", "missing")).rejects.toThrow(NotFoundException);
  });

  it("hashKey is deterministic and hex sha256", () => {
    expect(hashKey("abc")).toBe(hashKey("abc"));
    expect(hashKey("abc")).toMatch(/^[0-9a-f]{64}$/);
  });
});
