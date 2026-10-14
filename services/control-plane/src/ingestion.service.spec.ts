import {
  BadRequestException,
  ForbiddenException,
  NotFoundException,
  PayloadTooLargeException,
} from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { ApiKeyService } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import { EngineClient } from "./engine.js";
import { IngestionController, callerOf } from "./ingestion.controller.js";
import { IngestionGuard, IngestionService, type Caller } from "./ingestion.service.js";
import { KeycloakGuard } from "./auth.js";
import { RateLimitService } from "./rate-limit.service.js";

type Row = Record<string, unknown>;
type FakeResult = { rows: Row[]; rowCount: number };

const owner = { subject: "owner-sub" };
const memberCaller: Caller = { principal: owner, rateIdentity: "owner-sub" };
const WORKSPACE = "w1";
const PROJECT = "p1";

function memberPool(redactionEnabled = true): Pool {
  const script = async (text: string): Promise<FakeResult> => {
    if (text.startsWith("SELECT role FROM control_workspace_memberships"))
      return { rows: [{ role: "owner" }], rowCount: 1 };
    if (text.startsWith("SELECT engine_project_id FROM control_projects"))
      return { rows: [{ engine_project_id: "e1" }], rowCount: 1 };
    if (text.startsWith("SELECT id, workspace_id, engine_project_id")) {
      return {
        rows: [
          {
            id: PROJECT,
            workspace_id: WORKSPACE,
            engine_project_id: "e1",
            slug: "acme",
            name: "Acme",
            redaction_enabled: redactionEnabled,
          },
        ],
        rowCount: 1,
      };
    }
    return { rows: [], rowCount: 0 };
  };
  return { query: vi.fn(script) } as unknown as Pool;
}

function fakeEngine(overrides: Partial<EngineClient> = {}): EngineClient {
  return {
    ingestEvent: vi.fn(async () => ({ status: 201, body: { id: "evt-1", deduped: false } })),
    ingestEventsBatch: vi.fn(async () => ({
      status: 207,
      body: { items: [{ index: 0, status: 201, event: { id: "evt-1" }, deduped: false }] },
    })),
    listEvents: vi.fn(async () => [
      {
        id: "e1",
        project_id: "p",
        source_type: "text",
        content: "Email me at a@b.co please",
        created_at: "2026-10-02T00:00:00Z",
      },
      {
        id: "e2",
        project_id: "p",
        source_type: "csv",
        content: "I want a refund",
        created_at: "2026-10-02T00:00:01Z",
      },
    ]),
    getEvent: vi.fn(async () => ({
      id: "e1",
      project_id: "p",
      source_type: "text",
      content: "Email a@b.co",
      created_at: "2026-10-02T00:00:00Z",
    })),
    projectSummary: vi.fn(async () => ({ events: 3 })),
    ...overrides,
  } as unknown as EngineClient;
}

function serviceWith(pool: Pool, engine: EngineClient, rateLimits = new RateLimitService()) {
  const audit = { record: vi.fn(async () => undefined) } as unknown as AuditService;
  return { service: new IngestionService(pool, engine, rateLimits, audit), audit };
}

describe("IngestionService", () => {
  it("ingests through the engine and audits without content", async () => {
    const engine = fakeEngine();
    const { service, audit } = serviceWith(memberPool(), engine);
    const result = await service.ingest(
      memberCaller,
      WORKSPACE,
      PROJECT,
      { content: "I was charged twice" },
      "key-1",
    );
    expect(result.status).toBe(201);
    expect(engine.ingestEvent).toHaveBeenCalledWith(
      "e1",
      expect.objectContaining({ content: "I was charged twice" }),
      "key-1",
    );
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({ action: "observation.ingested", target: "event:evt-1" }),
    );
    const auditCall = vi.mocked(audit.record).mock.calls[0][0];
    expect(JSON.stringify(auditCall)).not.toContain("charged twice");
  });

  it("rejects blank and oversized content (400/413)", async () => {
    const { service } = serviceWith(memberPool(), fakeEngine());
    await expect(
      service.ingest(memberCaller, WORKSPACE, PROJECT, { content: "   " }),
    ).rejects.toThrow(BadRequestException);
    await expect(
      service.ingest(memberCaller, WORKSPACE, PROJECT, { content: "x".repeat(10_001) }),
    ).rejects.toThrow(PayloadTooLargeException);
  });

  it("rate limits per caller with 429", async () => {
    const engine = fakeEngine();
    const { service } = serviceWith(memberPool(), engine);
    for (let i = 0; i < 60; i += 1) {
      engine.ingestEvent = vi.fn(async () => ({
        status: 201,
        body: { id: `evt-${i}`, deduped: false },
      }));
      await service.ingest({ principal: owner, rateIdentity: "owner-sub" }, WORKSPACE, PROJECT, {
        content: `msg ${i}`,
      });
    }
    await expect(
      service.ingest(memberCaller, WORKSPACE, PROJECT, { content: "one more" }),
    ).rejects.toThrow(expect.objectContaining({ getStatus: expect.any(Function) }));
  });

  it("maps batch entries per item and returns 207 shape", async () => {
    const engine = fakeEngine({
      ingestEventsBatch: vi.fn(async () => ({
        status: 207,
        body: { items: [{ index: 0, status: 201, event: { id: "ok-1" }, deduped: false }] },
      })),
    });
    const { service } = serviceWith(memberPool(), engine);
    const result = await service.ingestBatch(
      memberCaller,
      WORKSPACE,
      PROJECT,
      [{ content: "good" }, { content: "  " }, { content: "y".repeat(10_001) }],
      "text",
    );
    expect(result.items.map((e) => e.status)).toEqual([201, 400, 413]);
    expect(result.items[0].event).toMatchObject({ id: "ok-1" });
  });

  it("list redacts previews when the project enables redaction", async () => {
    const { service } = serviceWith(memberPool(true), fakeEngine());
    const page = await service.list(memberCaller, WORKSPACE, PROJECT, {});
    expect(page.items[0].preview).not.toContain("a@b.co");
    expect(page.items[0].preview).toContain("[redacted]");
  });

  it("list search filters by substring", async () => {
    const { service } = serviceWith(memberPool(false), fakeEngine());
    const page = await service.list(memberCaller, WORKSPACE, PROJECT, { q: "refund" });
    expect(page.items).toHaveLength(1);
    expect(page.items[0].preview).toContain("refund");
  });

  it("non-member gets 404 (no enumeration)", async () => {
    const pool = {
      query: vi.fn(async (text: string): Promise<FakeResult> => {
        if (text.startsWith("SELECT role")) return { rows: [], rowCount: 0 };
        return { rows: [], rowCount: 0 };
      }),
    } as unknown as Pool;
    await expect(
      serviceWith(pool, fakeEngine()).service.list(
        { principal: owner, rateIdentity: "x" },
        WORKSPACE,
        PROJECT,
        {},
      ),
    ).rejects.toThrow(NotFoundException);
  });

  it("api-key caller scoped to another project gets 404", async () => {
    const keyCaller: Caller = {
      principal: { subject: "api-key:p9" },
      keyProjectId: "p9",
      rateIdentity: "key-x",
    };
    await expect(
      serviceWith(memberPool(), fakeEngine()).service.list(keyCaller, WORKSPACE, PROJECT, {}),
    ).rejects.toThrow(NotFoundException);
  });

  it("viewer role can list observations but cannot ingest (403)", async () => {
    const viewerPool = {
      query: vi.fn(async (text: string): Promise<FakeResult> => {
        if (text.startsWith("SELECT role FROM control_workspace_memberships"))
          return { rows: [{ role: "viewer" }], rowCount: 1 };
        if (text.startsWith("SELECT id, workspace_id, engine_project_id")) {
          return {
            rows: [
              {
                id: PROJECT,
                workspace_id: WORKSPACE,
                engine_project_id: "e1",
                slug: "acme",
                name: "Acme",
                redaction_enabled: true,
              },
            ],
            rowCount: 1,
          };
        }
        return { rows: [], rowCount: 0 };
      }),
    } as unknown as Pool;
    const { service } = serviceWith(viewerPool, fakeEngine());
    const page = await service.list(memberCaller, WORKSPACE, PROJECT, {});
    expect(page.items).toHaveLength(2);
    await expect(
      service.ingest(memberCaller, WORKSPACE, PROJECT, { content: "viewer write" }),
    ).rejects.toThrow(ForbiddenException);
  });

  it("callerOf propagates keyProjectId and keyScopes through IngestionController", async () => {
    const apiKeyPool = {
      query: vi.fn(async (text: string): Promise<FakeResult> => {
        if (text.startsWith("SELECT role FROM control_workspace_memberships"))
          return { rows: [], rowCount: 0 };
        if (text.startsWith("SELECT engine_project_id FROM control_projects"))
          return { rows: [{ engine_project_id: "e1" }], rowCount: 1 };
        if (text.startsWith("SELECT id, workspace_id, engine_project_id")) {
          return {
            rows: [
              {
                id: PROJECT,
                workspace_id: WORKSPACE,
                engine_project_id: "e1",
                slug: "acme",
                name: "Acme",
                redaction_enabled: true,
              },
            ],
            rowCount: 1,
          };
        }
        return { rows: [], rowCount: 0 };
      }),
    } as unknown as Pool;
    const { service } = serviceWith(apiKeyPool, fakeEngine());
    const controller = new IngestionController(service);
    const req = {
      principal: { subject: `api-key:${PROJECT}` },
      keyPrefix: "oc_dev_secrets",
      keyProjectId: PROJECT,
      keyScopes: ["ingest"] as const,
    };
    expect(callerOf({ ...req, keyScopes: ["ingest"] })).toMatchObject({
      keyProjectId: PROJECT,
      keyScopes: ["ingest"],
    });
    const resStub = { status: () => resStub };
    const created = await controller.ingest(
      { ...req, keyScopes: ["ingest"] },
      WORKSPACE,
      PROJECT,
      { content: "api key observation" },
      undefined,
      resStub,
    );
    expect(created).toMatchObject({ id: "evt-1" });
    await expect(
      controller.list({ ...req, keyScopes: ["ingest"] }, WORKSPACE, PROJECT),
    ).rejects.toThrow(ForbiddenException);
  });
});

describe("IngestionGuard", () => {
  function contextWith(headers: Record<string, string | undefined>, method = "POST") {
    const request = {
      method,
      headers,
      principal: undefined,
      keyPrefix: undefined,
      keyProjectId: undefined,
      keyScopes: undefined,
    };
    return {
      request,
      context: { switchToHttp: () => ({ getRequest: () => request }) } as never,
    };
  }

  it("routes oc_dev_ keys through API key verification with method-specific scope", async () => {
    const verify = vi.fn(async (_raw: string, scope?: string) => ({
      workspaceId: WORKSPACE,
      projectId: PROJECT,
      scopes: [scope ?? "ingest"],
    }));
    const apiKeys = { verify } as unknown as ApiKeyService;
    const keycloak = { canActivate: vi.fn(async () => true) } as unknown as KeycloakGuard;
    const guard = new IngestionGuard(keycloak, apiKeys);
    const { request, context } = contextWith(
      { authorization: "Bearer oc_dev_secretsecretsecret" },
      "POST",
    );
    expect(await guard.canActivate(context)).toBe(true);
    expect(verify).toHaveBeenCalledWith("oc_dev_secretsecretsecret", "ingest");
    expect(request.keyPrefix).toBe("oc_dev_secrets");
    expect(request.keyProjectId).toBe(PROJECT);
    expect(request.keyScopes).toEqual(["ingest"]);
    expect(keycloak.canActivate).not.toHaveBeenCalled();

    const getCtx = contextWith({ authorization: "Bearer oc_dev_secretsecretsecret" }, "GET");
    expect(await guard.canActivate(getCtx.context)).toBe(true);
    expect(verify).toHaveBeenCalledWith("oc_dev_secretsecretsecret", "read");
  });

  it("revoked keys are rejected", async () => {
    const apiKeys = {
      verify: vi.fn(async () => {
        throw new ForbiddenException("API key is invalid or revoked");
      }),
    } as unknown as ApiKeyService;
    const keycloak = { canActivate: vi.fn(async () => true) } as unknown as KeycloakGuard;
    const guard = new IngestionGuard(keycloak, apiKeys);
    const { context } = contextWith({ authorization: "Bearer oc_dev_revoked" });
    await expect(guard.canActivate(context)).rejects.toThrow(ForbiddenException);
  });

  it("JWT bearers fall through to Keycloak", async () => {
    const apiKeys = { verify: vi.fn() } as unknown as ApiKeyService;
    const keycloak = { canActivate: vi.fn(async () => true) } as unknown as KeycloakGuard;
    const guard = new IngestionGuard(keycloak, apiKeys);
    const { context } = contextWith({ authorization: "Bearer eyJhbGciOi..." });
    expect(await guard.canActivate(context)).toBe(true);
    expect(apiKeys.verify).not.toHaveBeenCalled();
    expect(keycloak.canActivate).toHaveBeenCalled();
  });
});
