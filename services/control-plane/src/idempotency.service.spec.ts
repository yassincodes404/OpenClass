import { BadRequestException, ConflictException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { canonicalJson, IdempotencyService, requestHash } from "./idempotency.service.js";

const identity = {
  method: "POST",
  path: "/control/projects",
  body: { name: "Example" },
  authorization: { subject: "user", role: "owner" },
};

function database(rows: unknown[] = []) {
  const query = vi.fn(async (sql: string) => ({
    rows: sql.startsWith("SELECT request_hash") ? rows : [],
    rowCount: sql.startsWith("SELECT request_hash") ? rows.length : 0,
  }));
  const release = vi.fn();
  return { query, release, pool: { connect: async () => ({ query, release }) } as unknown as Pool };
}

describe("transactional idempotency", () => {
  it("canonicalizes object keys but preserves array order and body/path/method/caller identity", () => {
    expect(canonicalJson({ b: [1, 2], a: { z: null, x: true } })).toBe(
      canonicalJson({ a: { x: true, z: null }, b: [1, 2] }),
    );
    for (const changed of [
      { body: { name: "Changed" } },
      { method: "PATCH" },
      { path: "/control/other" },
      { authorization: { subject: "another" } },
      { body: [2, 1] },
    ])
      expect(requestHash({ ...identity, ...changed })).not.toBe(requestHash(identity));
    expect(canonicalJson({})).not.toBe(canonicalJson({ a: null }));
  });

  it("replays status and body without invoking mutation", async () => {
    const db = database([
      { request_hash: requestHash(identity), response: { id: "p1" }, response_status: 201 },
    ]);
    const operation = vi.fn();
    expect(
      await new IdempotencyService(db.pool).execute("workspace:w1", "key", identity, operation),
    ).toEqual({ status: 201, body: { id: "p1" } });
    expect(operation).not.toHaveBeenCalled();
    expect(db.query.mock.calls.map(([sql]) => sql)).toContain("COMMIT");
    expect(db.release).toHaveBeenCalledOnce();
  });

  it("rejects mismatched and legacy identities and rolls back", async () => {
    for (const hash of ["different", null]) {
      const db = database([{ request_hash: hash }]);
      const operation = vi.fn();
      await expect(
        new IdempotencyService(db.pool).execute("w", "key", identity, operation),
      ).rejects.toBeInstanceOf(ConflictException);
      expect(operation).not.toHaveBeenCalled();
      expect(db.query.mock.calls.map(([sql]) => sql)).toContain("ROLLBACK");
    }
  });

  it("resolves current authorization after the reservation lock, even on replay", async () => {
    const db = database([
      { request_hash: requestHash(identity), response: { id: "p1" }, response_status: 201 },
    ]);
    const resolve = vi.fn(async () => {
      expect(
        db.query.mock.calls.some(([sql]) => sql.startsWith("SELECT pg_advisory_xact_lock")),
      ).toBe(true);
      return { ...identity, authorization: { subject: "user", role: "viewer" } };
    });
    const operation = vi.fn();
    await expect(
      new IdempotencyService(db.pool).execute("workspace:w1", "key", resolve, operation),
    ).rejects.toBeInstanceOf(ConflictException);
    expect(resolve).toHaveBeenCalledOnce();
    expect(operation).not.toHaveBeenCalled();
  });

  it("reserves before execution and rolls back failures without recording a response", async () => {
    const db = database();
    const operation = vi.fn(async () => {
      expect(
        db.query.mock.calls.some(([sql]) => sql.startsWith("INSERT INTO control_idempotency_keys")),
      ).toBe(true);
      throw new Error("simulated failure");
    });
    await expect(
      new IdempotencyService(db.pool).execute("w", "key", identity, operation),
    ).rejects.toThrow("simulated failure");
    expect(
      db.query.mock.calls.some(([sql]) => sql.startsWith("UPDATE control_idempotency_keys")),
    ).toBe(false);
    expect(db.query.mock.calls.map(([sql]) => sql)).toContain("ROLLBACK");
  });

  it("rejects malformed keys rather than truncating colliding identities", async () => {
    const db = database();
    for (const key of ["", " ", "x".repeat(201), "line\nbreak"]) {
      await expect(
        new IdempotencyService(db.pool).execute("w", key, identity, vi.fn()),
      ).rejects.toBeInstanceOf(BadRequestException);
    }
    expect(db.query).not.toHaveBeenCalled();
  });

  it("commits mutations without keys and does not cache them", async () => {
    const db = database();
    const result = await new IdempotencyService(db.pool).execute(
      "w",
      undefined,
      identity,
      async () => ({ status: 200, body: null }),
    );
    expect(result).toEqual({ status: 200, body: null });
    expect(db.query.mock.calls.map(([sql]) => sql)).toEqual(["BEGIN", "COMMIT"]);
  });
});
