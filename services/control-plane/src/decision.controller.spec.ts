import { BadRequestException, NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { AuditService } from "./audit.service.js";
import { DecisionController } from "./decision.controller.js";
import { EngineClient } from "./engine.js";
import { RateLimitService } from "./rate-limit.service.js";

type Row = Record<string, unknown>;
type FakeResult = { rows: Row[]; rowCount: number };

const principal = { subject: "owner-sub" };
const statusStub = { status: () => statusStub } as unknown as Parameters<
  DecisionController["run"]
>[5];
const REVIEWER = { subject: "reviewer-sub" };

function memberPool(role: string | null): Pool {
  return {
    query: vi.fn(async (text: string): Promise<FakeResult> => {
      if (text.startsWith("SELECT role FROM control_workspace_memberships")) {
        return role ? { rows: [{ role }], rowCount: 1 } : { rows: [], rowCount: 0 };
      }
      if (text.startsWith("SELECT id, workspace_id, engine_project_id")) {
        return { rows: [{ id: "p1", workspace_id: "w1", engine_project_id: "e1" }], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    }),
  } as unknown as Pool;
}

function fakeEngine(overrides: Partial<EngineClient> = {}): EngineClient {
  return {
    listDecisionServices: vi.fn(async () => [{ id: "s1", slug: "support-router", nodes: [] }]),
    createDecisionService: vi.fn(async () => ({
      id: "s1",
      slug: "support-router",
      nodes: [{ choices: [{ key: "BILLING" }, { key: "UNKNOWN" }] }],
    })),
    getDecisionService: vi.fn(async () => ({ id: "s1", slug: "support-router", nodes: [] })),
    runDecisions: vi.fn(async () => [
      {
        id: "r1",
        selected_choice: "BILLING",
        supervision_outcome: "TRUSTED",
        probabilities: { BILLING: 0.8, UNKNOWN: 0.2 },
        provider: "mock",
      },
    ]),
    listRuns: vi.fn(async () => []),
    getRun: vi.fn(),
    ...overrides,
  } as unknown as EngineClient;
}

function controllerWith(pool: Pool, engine: EngineClient) {
  const audit = { record: vi.fn(async () => undefined) } as unknown as AuditService;
  return {
    controller: new DecisionController(pool, engine, new RateLimitService(), audit),
    engine,
    audit,
  };
}

const validService = {
  name: "Support router",
  instructions: "Route each message to the best intent.",
  choices: [{ key: "BILLING", label: "Billing" }],
};

describe("DecisionController", () => {
  it("creates a service and records audit (UNKNOWN auto-appended by the engine)", async () => {
    const { controller, engine, audit } = controllerWith(memberPool("owner"), fakeEngine());
    const created = await controller.createService({ principal }, "w1", "p1", validService);
    expect(created.nodes[0].choices.map((c) => c.key)).toContain("UNKNOWN");
    expect(engine.createDecisionService).toHaveBeenCalled();
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({ action: "decision_service.created" }),
    );
  });

  it("rejects a service that sends UNKNOWN as a choice (400)", async () => {
    const { controller, engine } = controllerWith(memberPool("owner"), fakeEngine());
    await expect(
      controller.createService({ principal }, "w1", "p1", {
        ...validService,
        choices: [...validService.choices, { key: "UNKNOWN", label: "Unknown" }],
      }),
    ).rejects.toThrow(BadRequestException);
    expect(engine.createDecisionService).not.toHaveBeenCalled();
  });

  it("rejects lowercase choice keys (400)", async () => {
    const { controller } = controllerWith(memberPool("owner"), fakeEngine());
    await expect(
      controller.createService({ principal }, "w1", "p1", {
        ...validService,
        choices: [{ key: "billing", label: "B" }],
      }),
    ).rejects.toThrow(BadRequestException);
  });

  it("reviewer cannot create services (403) but can run", async () => {
    const { controller, engine } = controllerWith(memberPool("reviewer"), fakeEngine());
    await expect(
      controller.createService({ principal: REVIEWER }, "w1", "p1", validService),
    ).rejects.toMatchObject({
      getStatus: expect.any(Function),
    });
    const runs = await controller.run(
      { principal: REVIEWER },
      "w1",
      "p1",
      "s1",
      { content: "charged twice" },
      statusStub,
    );
    expect(runs).toHaveLength(1);
    expect(engine.runDecisions).toHaveBeenCalled();
  });

  it("runs require content or event ids (400)", async () => {
    const { controller } = controllerWith(memberPool("owner"), fakeEngine());
    await expect(controller.run({ principal }, "w1", "p1", "s1", {}, statusStub)).rejects.toThrow(
      BadRequestException,
    );
  });

  it("non-member gets 404 (no enumeration)", async () => {
    const { controller } = controllerWith(memberPool(null), fakeEngine());
    await expect(controller.listServices({ principal }, "w1", "p1")).rejects.toThrow(
      new NotFoundException("Workspace not found"),
    );
  });

  it("run results are audited with selected choice", async () => {
    const { controller, audit } = controllerWith(memberPool("owner"), fakeEngine());
    await controller.run({ principal }, "w1", "p1", "s1", { content: "x" }, statusStub);
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "decision_run.executed",
        target: expect.stringContaining("BILLING"),
      }),
    );
  });

  it("allows scoped API key with classify scope to run decisions without workspace membership", async () => {
    const { controller, engine } = controllerWith(memberPool(null), fakeEngine());
    const runs = await controller.run(
      {
        principal: { subject: "api-key:p1" },
        keyPrefix: "oc_dev_secrets",
        keyProjectId: "p1",
        keyScopes: ["classify"],
      },
      "w1",
      "p1",
      "s1",
      { content: "charged twice" },
      statusStub,
    );
    expect(runs).toHaveLength(1);
    expect(engine.runDecisions).toHaveBeenCalled();

    await expect(
      controller.run(
        {
          principal: { subject: "api-key:p9" },
          keyPrefix: "oc_dev_secrets",
          keyProjectId: "p9",
          keyScopes: ["classify"],
        },
        "w1",
        "p1",
        "s1",
        { content: "charged twice" },
        statusStub,
      ),
    ).rejects.toThrow(NotFoundException);
  });
});
