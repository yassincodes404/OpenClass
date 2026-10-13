import { BadRequestException, ForbiddenException, NotFoundException } from "@nestjs/common";
import type { Pool } from "pg";
import { describe, expect, it, vi } from "vitest";
import { ApiKeyService } from "./api-key.service.js";
import { EngineClient } from "./engine.js";
import { ProjectService } from "./project.service.js";

type Row = Record<string, unknown>;
type FakeResult = { rows: Row[]; rowCount: number };

const owner = { subject: "owner-sub" };
const reviewer = { subject: "reviewer-sub" };

function fakePool(script: (text: string, params?: unknown[]) => Promise<FakeResult>): Pool {
  return { query: vi.fn(script) } as unknown as Pool;
}

function rolePool(role: string | null): Pool {
  return fakePool(async (text) => {
    if (text.startsWith("SELECT role FROM control_workspace_memberships")) {
      return role ? { rows: [{ role }], rowCount: 1 } : { rows: [], rowCount: 0 };
    }
    return { rows: [], rowCount: 0 };
  });
}

function fakeEngine(overrides: Partial<EngineClient> = {}): EngineClient {
  return {
    createProject: vi.fn(async () => ({
      id: "engine-p1",
      slug: "acme",
      name: "Acme",
      description: "",
    })),
    createClassifier: vi.fn(async () => ({
      id: "engine-c1",
      slug: "support-intent",
      name: "Support intent",
      active_ontology_version_id: "v1",
    })),
    getOntology: vi.fn(async () => ({
      id: "v1",
      version_number: 1,
      classes: [{ canonical_name: "billing", display_name: "Billing" }],
    })),
    request: vi.fn(async () => ({})),
    ...overrides,
  } as unknown as EngineClient;
}

const classes = [
  { canonical_name: "billing", display_name: "Billing" },
  { canonical_name: "refund", display_name: "Refund" },
];

const auditStub = {
  record: vi.fn(async () => undefined),
  list: vi.fn(async () => ({ items: [], next_cursor: null })),
} as unknown as import("./audit.service.js").AuditService;
const idempotencyStub = {
  replay: vi.fn(async () => null),
  remember: vi.fn(async () => undefined),
} as unknown as import("./idempotency.service.js").IdempotencyService;

function serviceWith(pool: Pool, engine: EngineClient) {
  const apiKeys = new ApiKeyService(pool);
  return {
    service: new ProjectService(pool, engine, apiKeys, auditStub, idempotencyStub),
    apiKeys,
  };
}

describe("ProjectService", () => {
  it("creates a project via the engine and stores the control mapping", async () => {
    const inserts: Array<unknown[] | undefined> = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT slug FROM control_projects")) return { rows: [], rowCount: 0 };
      if (text.startsWith("INSERT INTO control_projects")) {
        inserts.push(params);
        return {
          rows: [
            {
              id: "cp1",
              workspace_id: "w1",
              engine_project_id: "engine-p1",
              slug: "acme-support",
              name: "Acme Support",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      return { rows: [], rowCount: 0 };
    });
    const engine = fakeEngine();
    const created = await serviceWith(pool, engine).service.create(
      owner,
      "w1",
      "Acme Support",
      "desc",
    );
    expect(created).toMatchObject({ slug: "acme-support", engine_project_id: "engine-p1" });
    expect(engine.createProject).toHaveBeenCalledWith("Acme Support", "desc");
    expect(inserts[0]).toContain("w1");
  });

  it("appends a numeric suffix when the project slug already exists in the workspace", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT slug FROM control_projects")) {
        return { rows: [{ slug: "acme" }, { slug: "acme-2" }], rowCount: 2 };
      }
      if (text.startsWith("INSERT INTO control_projects")) {
        return {
          rows: [
            {
              id: "cp1",
              workspace_id: "w1",
              engine_project_id: "e",
              slug: "acme-3",
              name: "Acme",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      return { rows: [], rowCount: 0 };
    });
    const created = await serviceWith(pool, fakeEngine()).service.create(owner, "w1", "Acme", "");
    expect(created.slug).toBe("acme-3");
  });

  it("reviewer cannot create projects (403)", async () => {
    const service = serviceWith(rolePool("reviewer"), fakeEngine()).service;
    await expect(service.create(reviewer, "w1", "Acme", "")).rejects.toThrow(ForbiddenException);
  });

  it("non-member project access → 404 without enumeration", async () => {
    const service = serviceWith(rolePool(null), fakeEngine()).service;
    await expect(service.list(owner, "w1")).rejects.toThrow(
      new NotFoundException("Workspace not found"),
    );
  });

  it("listing is scoped to the workspace (isolation) and any member role can read", async () => {
    const queries: { text: string; params?: unknown[] }[] = [];
    const pool = fakePool(async (text, params) => {
      queries.push({ text, params });
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      return { rows: [], rowCount: 0 };
    });
    await serviceWith(pool, fakeEngine()).service.list(owner, "w1");
    const listQuery = queries.find((q) => q.text.includes("FROM control_projects"));
    expect(listQuery?.params).toEqual(["w1"]);
    expect(listQuery?.text).toContain("workspace_id = $1");
  });

  it("developer (below admin) cannot create projects (403)", async () => {
    await expect(
      serviceWith(rolePool("developer"), fakeEngine()).service.create(owner, "w1", "Acme", ""),
    ).rejects.toThrow(ForbiddenException);
  });

  it("classifier without UNKNOWN fallback is rejected (400)", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT id, workspace_id"))
        return {
          rows: [
            {
              id: "p1",
              workspace_id: "w1",
              engine_project_id: "e",
              slug: "acme",
              name: "Acme",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      return { rows: [], rowCount: 0 };
    });
    const engine = fakeEngine();
    await expect(
      serviceWith(pool, engine).service.createClassifier(owner, "w1", "p1", {
        name: "Support intent",
        description: "",
        classes,
        unknownFallback: false,
      }),
    ).rejects.toThrow(new BadRequestException("UNKNOWN fallback is required and permanent"));
    expect(engine.createClassifier).not.toHaveBeenCalled();
  });

  it("a class named 'unknown' is rejected — UNKNOWN is a state, not a class", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT id, workspace_id"))
        return {
          rows: [
            {
              id: "p1",
              workspace_id: "w1",
              engine_project_id: "e",
              slug: "acme",
              name: "Acme",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      return { rows: [], rowCount: 0 };
    });
    const engine = fakeEngine();
    await expect(
      serviceWith(pool, engine).service.createClassifier(owner, "w1", "p1", {
        name: "Support intent",
        description: "",
        classes: [...classes, { canonical_name: "unknown", display_name: "Unknown" }],
        unknownFallback: true,
      }),
    ).rejects.toThrow(BadRequestException);
    expect(engine.createClassifier).not.toHaveBeenCalled();
  });

  it("creates a classifier through the engine and records the mapping", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT id, workspace_id"))
        return {
          rows: [
            {
              id: "p1",
              workspace_id: "w1",
              engine_project_id: "e",
              slug: "acme",
              name: "Acme",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      if (text.startsWith("SELECT 1 FROM control_classifiers")) return { rows: [], rowCount: 0 };
      if (text.startsWith("INSERT INTO control_classifiers")) {
        return {
          rows: [
            {
              id: "cc1",
              project_id: "p1",
              engine_classifier_id: "engine-c1",
              slug: "support-intent",
              name: "Support intent",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      return { rows: [], rowCount: 0 };
    });
    const engine = fakeEngine();
    const created = await serviceWith(pool, engine).service.createClassifier(owner, "w1", "p1", {
      name: "Support intent",
      description: "",
      classes,
      unknownFallback: true,
    });
    expect(created).toMatchObject({ slug: "support-intent", engine_classifier_id: "engine-c1" });
    expect(created.classes).toHaveLength(2);
    expect(engine.createClassifier).toHaveBeenCalled();
  });

  it("duplicate classifier slug inside a project → 400", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT id, workspace_id"))
        return {
          rows: [
            {
              id: "p1",
              workspace_id: "w1",
              engine_project_id: "e",
              slug: "acme",
              name: "Acme",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      if (text.startsWith("SELECT 1 FROM control_classifiers"))
        return { rows: [{ ok: 1 }], rowCount: 1 };
      return { rows: [], rowCount: 0 };
    });
    await expect(
      serviceWith(pool, fakeEngine()).service.createClassifier(owner, "w1", "p1", {
        name: "Support intent",
        description: "",
        classes,
        unknownFallback: true,
      }),
    ).rejects.toThrow(BadRequestException);
  });
});
