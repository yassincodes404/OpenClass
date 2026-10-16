import { Logger } from "@nestjs/common";
import { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { createControlPool } from "./db.js";

describe("createControlPool", () => {
  it("survives repeated idle connection errors and logs only a stable event", async () => {
    const warn = vi.spyOn(Logger.prototype, "warn").mockImplementation(() => undefined);
    const pool = createControlPool();
    const failure = Object.assign(new Error("private-database-error-detail"), {
      detail: "private-connection-detail",
      code: "57P01",
    });
    try {
      expect(() => pool.emit("error", failure)).not.toThrow();
      expect(() => pool.emit("error", failure)).not.toThrow();
      expect(warn.mock.calls).toEqual([
        [{ event: "control.database_connection_error" }],
        [{ event: "control.database_connection_error" }],
      ]);
    } finally {
      await pool.end();
      warn.mockRestore();
    }
  });

  it("preserves query rejection and permits a later query rather than hiding failure", async () => {
    const failure = new Error("query failed");
    const query = vi
      .spyOn(Pool.prototype, "query")
      .mockImplementationOnce(async () => {
        throw failure;
      })
      .mockImplementationOnce(async () => ({
        command: "SELECT",
        rowCount: 1,
        oid: 0,
        fields: [],
        rows: [{ ready: true }],
      }));
    const pool = createControlPool();
    try {
      await expect(pool.query("SELECT 1")).rejects.toBe(failure);
      await expect(pool.query("SELECT true AS ready")).resolves.toMatchObject({
        rows: [{ ready: true }],
      });
    } finally {
      query.mockRestore();
      await pool.end();
    }
  });
});
