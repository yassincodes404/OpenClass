import { NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { AuditService } from "./audit.service.js";
import { EngineClient } from "./engine.js";
import { UnknownController } from "./unknown.controller.js";

type Row = Record<string, unknown>;
type FakeResult = { rows: Row[]; rowCount: number };

const principal = { subject: "user-sub" };

function poolWith(role: string | null): Pool {
  return {
    query: vi.fn(async (text: string): Promise<FakeResult> => {
      if (text.startsWith("SELECT role FROM control_workspace_memberships")) {
        return role ? { rows: [{ role }], rowCount: 1 } : { rows: [], rowCount: 0 };
      }
      if (text.startsWith("SELECT id, engine_project_id")) {
        return { rows: [{ id: "p1", engine_project_id: "e1" }], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    }),
  } as unknown as Pool;
}

function engineWith(overrides: Partial<EngineClient> = {}): EngineClient {
  return {
    listUnknowns: vi.fn(async () => ({ items: [], next_cursor: null })),
    unknownStats: vi.fn(async () => ({ total_unknown: 0, total_runs: 0, unknown_rate: 0 })),
    unknownDetail: vi.fn(),
    triageUnknown: vi.fn(async (_id: string, _run: string, body: { category: string }) => ({ run_id: "r1", category: body.category })),
    transitionUnknown: vi.fn(async () => ({ run_id: "r1", status: "triaged" })),
    ...overrides,
  } as unknown as EngineClient;
}

function controllerWith(pool: Pool, engine: EngineClient) {
  const audit = { record: vi.fn(async () => undefined) } as unknown as AuditService;
  return { controller: new UnknownController(pool, engine, audit), engine, audit };
}

describe("UnknownController", () => {
  it("viewer can read the pool and stats", async () => {
    const { controller, engine } = controllerWith(poolWith("viewer"), engineWith());
    await controller.list({ principal }, "w1", "p1", undefined, undefined, undefined);
    await controller.stats({ principal }, "w1", "p1");
    expect(engine.listUnknowns).toHaveBeenCalledTimes(1);
    expect(engine.unknownStats).toHaveBeenCalledTimes(1);
  });

  it("viewer cannot triage (403)", async () => {
    const { controller } = controllerWith(poolWith("viewer"), engineWith());
    await expect(controller.triage({ principal }, "w1", "p1", "r1", { category: "missing_info" })).rejects.toMatchObject({
      getStatus: expect.any(Function),
    });
  });

  it("reviewer can triage and the action is audited (advisory only)", async () => {
    const { controller, audit } = controllerWith(poolWith("reviewer"), engineWith());
    const result = await controller.triage({ principal }, "w1", "p1", "r1", { category: "truly_novel" });
    expect(result).toMatchObject({ category: "truly_novel" });
    expect(audit.record).toHaveBeenCalledWith(expect.objectContaining({ action: "unknown.triaged" }));
  });

  it("invalid category is rejected (400)", async () => {
    const { controller } = controllerWith(poolWith("reviewer"), engineWith());
    await expect(controller.triage({ principal }, "w1", "p1", "r1", { category: "new_class" })).rejects.toThrow(
      "Invalid request body",
    );
  });

  it("non-member gets 404 (no enumeration)", async () => {
    const { controller } = controllerWith(poolWith(null), engineWith());
    await expect(controller.list({ principal }, "w1", "p1", undefined, undefined, undefined)).rejects.toThrow(
      new NotFoundException("Workspace not found"),
    );
  });
});
