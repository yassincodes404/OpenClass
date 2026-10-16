import { BadRequestException, ForbiddenException, NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "./engine.js";
import type { ProjectService } from "./project.service.js";
import { IngestionService } from "./ingestion.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import type { AuditService } from "./audit.service.js";
import { WorkflowController } from "./workflow.controller.js";

const principal = { subject: "user-1" };
const UUID = "123e4567-e89b-42d3-a456-426614174000";

function memberPool(role: string | null): Pool {
  return {
    query: vi.fn(async (text: string) => {
      if (text.startsWith("SELECT role FROM control_workspace_memberships")) {
        return role ? { rows: [{ role }], rowCount: 1 } : { rows: [], rowCount: 0 };
      }
      if (text.startsWith("SELECT engine_project_id"))
        return { rows: [{ engine_project_id: "e1" }], rowCount: 1 };
      if (text.startsWith("SELECT id, workspace_id, engine_project_id"))
        return { rows: [{ id: "p1", workspace_id: "w1", engine_project_id: "e1" }], rowCount: 1 };
      return { rows: [], rowCount: 0 };
    }),
  } as unknown as Pool;
}

function controllerWith(role: string | null, engineResult: unknown = { ok: true }) {
  const engine = {
    request: vi.fn(async () => engineResult),
    ingestEvent: vi.fn(async () => ({ status: 201, body: engineResult })),
    ingestEventsBatch: vi.fn(async () => ({ status: 207, body: engineResult })),
    projectSummary: vi.fn(async () => ({ events: 0 })),
  } as unknown as EngineClient;
  const projects = {
    get: vi.fn(async () => ({ id: "p1", workspace_id: "w1", engine_project_id: "e1" })),
  } as unknown as ProjectService;
  const response = { status: vi.fn() };
  const pool = memberPool(role);
  const rateLimits = new RateLimitService();
  const ingestion = new IngestionService(pool, engine, rateLimits, {
    record: vi.fn(),
  } as unknown as AuditService);
  const controller = new WorkflowController(pool, projects, engine, ingestion, rateLimits);
  return { controller, engine, projects, response, rateLimits };
}

describe("WorkflowController", () => {
  it("provides bounded provider metadata after project membership without exposing connection details", async () => {
    const { controller, engine, response } = controllerWith("viewer", {
      default_provider: "laya",
      laya: {
        status: "ready",
        mode: "local_engine",
        daemon_status: "ready",
        endpoint: "https://user:sentinel-secret@private.example/?token=sentinel-secret",
        model: "laya-model",
        default: true,
        api_key: "sentinel-secret",
      },
      jev: { status: "not_configured", model: "jev", configured: false, default: false },
      internal_token: "sentinel-secret",
    });
    const result = await controller.handle(
      { principal, method: "GET" },
      "w1",
      "p1",
      ["provider-status"],
      {},
      undefined,
      response,
    );
    expect(engine.request).toHaveBeenCalledWith("GET", "/api/v1/providers/status", undefined, 200, {
      workspaceId: "w1",
      actor: principal.subject,
    });
    expect(result).toMatchObject({
      default_provider: "laya",
      laya: { model: "laya-model", endpoint: "" },
    });
    expect(JSON.stringify(result)).not.toContain("sentinel-secret");
    expect(response.status).toHaveBeenCalledWith(200);
  });

  it("hides provider metadata from non-members before engine access", async () => {
    const { controller, engine, response } = controllerWith(null);
    await expect(
      controller.handle(
        { principal, method: "GET" },
        "w1",
        "p1",
        ["provider-status"],
        {},
        undefined,
        response,
      ),
    ).rejects.toThrow(NotFoundException);
    expect(engine.request).not.toHaveBeenCalled();
  });

  it.each(["events", "events/batch"])(
    "enforces the existing workspace quota before workflow %s mutation",
    async (path) => {
      const { controller, engine, response } = controllerWith("developer");
      vi.mocked(engine.projectSummary).mockResolvedValue({ events: 1_000_000_000 });
      await expect(
        controller.handle(
          { principal, method: "POST" },
          "w1",
          "p1",
          path.split("/"),
          {},
          path === "events"
            ? { content: "quota bypass" }
            : { items: [{ content: "quota bypass" }] },
          response,
        ),
      ).rejects.toMatchObject({ status: 429 });
      expect(engine.ingestEvent).not.toHaveBeenCalled();
      expect(engine.ingestEventsBatch).not.toHaveBeenCalled();
    },
  );

  it.each(["events", "events/batch"])(
    "enforces the existing principal throttle before workflow %s mutation",
    async (path) => {
      const { controller, engine, response, rateLimits } = controllerWith("developer");
      vi.spyOn(rateLimits, "check").mockReturnValue({
        allowed: false,
        retryAfterSeconds: 30,
        limit: 60,
        remaining: 0,
      });
      await expect(
        controller.handle(
          { principal, method: "POST" },
          "w1",
          "p1",
          path.split("/"),
          {},
          path === "events"
            ? { content: "throttle bypass" }
            : { items: [{ content: "throttle bypass" }] },
          response,
        ),
      ).rejects.toMatchObject({ status: 429 });
      expect(engine.ingestEvent).not.toHaveBeenCalled();
      expect(engine.ingestEventsBatch).not.toHaveBeenCalled();
    },
  );

  it("shares the existing classify throttle for workflow decision runs", async () => {
    const { controller, engine, response, rateLimits } = controllerWith("developer");
    vi.spyOn(rateLimits, "check").mockReturnValue({
      allowed: false,
      retryAfterSeconds: 30,
      limit: 300,
      remaining: 0,
    });
    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["decision-services", UUID, "runs"],
        {},
        { content: "must not bypass classify throttle" },
        response,
      ),
    ).rejects.toMatchObject({ status: 429 });
    expect(rateLimits.check).toHaveBeenCalledWith(principal.subject, "classify");
    expect(engine.request).not.toHaveBeenCalled();
  });

  it.each(["__proto__", "constructor", "unknown"])("denies unrecognized role %s", async (role) => {
    const { controller, engine } = controllerWith(role);
    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["events"],
        {},
        { content: "x" },
        { status: vi.fn() },
      ),
    ).rejects.toThrow(ForbiddenException);
    expect(engine.request).not.toHaveBeenCalled();
  });

  it("never reaches the engine when the project is outside the authorized workspace", async () => {
    const { controller, projects, engine } = controllerWith("owner");
    vi.mocked(projects.get).mockRejectedValue(new NotFoundException("Project not found"));
    await expect(
      controller.handle(
        { principal, method: "GET" },
        "other-workspace",
        "p1",
        ["evidence"],
        {},
        undefined,
        { status: vi.fn() },
      ),
    ).rejects.toThrow(NotFoundException);
    expect(engine.request).not.toHaveBeenCalled();
  });

  it("resolves membership before engine I/O and forwards viewer reads", async () => {
    const { controller, engine, response } = controllerWith("viewer", { id: "e1" });
    const result = await controller.handle(
      { principal, method: "GET" },
      "w1",
      "p1",
      undefined,
      {},
      undefined,
      response,
    );
    expect(result).toEqual({ id: "e1" });
    expect(engine.request).toHaveBeenCalledWith("GET", "/api/v1/projects/e1", undefined, 200, {
      workspaceId: "w1",
      actor: "user-1",
    });
    expect(response.status).toHaveBeenCalledWith(200);
  });

  it("forwards validated list filters as engine query strings", async () => {
    const { controller, engine } = controllerWith("viewer", []);
    await controller.handle(
      { principal, method: "GET" },
      "w1",
      "p1",
      ["evidence"],
      { status: "pending", limit: "25" },
      undefined,
      { status: vi.fn() },
    );
    expect(engine.request).toHaveBeenCalledWith(
      "GET",
      "/api/v1/projects/e1/evidence?limit=25&status=pending",
      undefined,
      200,
      expect.objectContaining({ workspaceId: "w1" }),
    );
  });

  it("forwards validated mutation bodies with the contract status", async () => {
    const { controller, engine, response } = controllerWith("developer", { id: "evt-1" });
    await controller.handle(
      { principal, method: "POST" },
      "w1",
      "p1",
      ["events"],
      {},
      { content: "charged twice", source_type: "text" },
      response,
    );
    expect(engine.ingestEvent).toHaveBeenCalledWith(
      "e1",
      { content: "charged twice", source_type: "text" },
      expect.objectContaining({ actor: "user-1" }),
    );
    expect(response.status).toHaveBeenCalledWith(201);
  });

  it.each([
    { path: "events", status: 200, adapter: "ingestEvent", payload: { content: "same event" } },
    { path: "events", status: 201, adapter: "ingestEvent", payload: { content: "new event" } },
    {
      path: "events/batch",
      status: 200,
      adapter: "ingestEventsBatch",
      payload: { items: [{ content: "same event" }] },
    },
    {
      path: "events/batch",
      status: 207,
      adapter: "ingestEventsBatch",
      payload: { items: [{ content: "new event" }] },
    },
  ] as const)(
    "preserves $path success status $status",
    async ({ path, status, adapter, payload }) => {
      const body = { id: "evt-1", deduped: status === 200 };
      const { controller, engine, response } = controllerWith("developer", body);
      vi.mocked(engine[adapter]).mockResolvedValue({ status, body });
      const result = await controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        path.split("/"),
        {},
        payload,
        response,
      );
      expect(result).toEqual(body);
      expect(response.status).toHaveBeenCalledWith(status);
      expect(engine[adapter]).toHaveBeenCalledWith("e1", payload, {
        workspaceId: "w1",
        actor: principal.subject,
      });
      expect(engine.request).not.toHaveBeenCalled();
    },
  );

  it("lets reviewers triage evidence but not create decision services", async () => {
    const { controller, engine } = controllerWith("reviewer");
    await controller.handle(
      { principal, method: "PATCH" },
      "w1",
      "p1",
      ["evidence", UUID, "triage"],
      {},
      { diagnosis: "decision_space", rationale: "Missing intent" },
      { status: vi.fn() },
    );
    expect(engine.request).toHaveBeenCalledWith(
      "PATCH",
      `/api/v1/projects/e1/evidence/${UUID}/triage`,
      { diagnosis: "decision_space", rationale: "Missing intent" },
      200,
      expect.objectContaining({ workspaceId: "w1" }),
    );

    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["decision-services"],
        {},
        { name: "Router", instructions: "Route", choices: [{ key: "BILLING", label: "B" }] },
        { status: vi.fn() },
      ),
    ).rejects.toThrow(ForbiddenException);
  });

  it("hides the workspace from non-members (404) and never calls the engine", async () => {
    const { controller, engine } = controllerWith(null);
    await expect(
      controller.handle({ principal, method: "GET" }, "w1", "p1", undefined, {}, undefined, {
        status: vi.fn(),
      }),
    ).rejects.toThrow(NotFoundException);
    expect(engine.request).not.toHaveBeenCalled();
  });

  it("rejects insufficient roles before engine I/O (403)", async () => {
    const { controller, engine } = controllerWith("viewer");
    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["events"],
        {},
        { content: "x" },
        { status: vi.fn() },
      ),
    ).rejects.toThrow(ForbiddenException);
    expect(engine.request).not.toHaveBeenCalled();
  });

  it("rejects unallowlisted routes before touching membership or the engine (404)", async () => {
    const { controller, engine, projects } = controllerWith("admin");
    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["discovery-candidates", UUID, "promote"],
        {},
        {},
        { status: vi.fn() },
      ),
    ).rejects.toThrow(NotFoundException);
    expect(projects.get).not.toHaveBeenCalled();
    expect(engine.request).not.toHaveBeenCalled();
  });

  it("rejects invalid bodies and query strings (400) without engine I/O", async () => {
    const { controller, engine } = controllerWith("admin");
    await expect(
      controller.handle(
        { principal, method: "POST" },
        "w1",
        "p1",
        ["events"],
        {},
        { content: "" },
        { status: vi.fn() },
      ),
    ).rejects.toThrow(BadRequestException);
    await expect(
      controller.handle(
        { principal, method: "GET" },
        "w1",
        "p1",
        ["runs"],
        { debug: "1" },
        undefined,
        {
          status: vi.fn(),
        },
      ),
    ).rejects.toThrow(BadRequestException);
    expect(engine.request).not.toHaveBeenCalled();
  });
});
