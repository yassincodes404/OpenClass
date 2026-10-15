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
    listProjects: vi.fn(async () => []),
    getProject: vi.fn(async () => ({
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

function serviceWith(pool: Pool, engine: EngineClient) {
  const apiKeys = new ApiKeyService(pool);
  return {
    service: new ProjectService(pool, engine, apiKeys, auditStub),
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
    expect(engine.createProject).toHaveBeenCalledWith("Acme Support", "desc", {
      workspaceId: "w1",
      actor: "owner-sub",
    });
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

  it("reconciles missing engine projects into control_projects on listProjects", async () => {
    const insertedParams: unknown[][] = [];
    const storedRows: Row[] = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.includes("SELECT id, engine_project_id, slug FROM control_projects")) {
        return { rows: [...storedRows], rowCount: storedRows.length };
      }
      if (text.startsWith("INSERT INTO control_projects")) {
        insertedParams.push(params ?? []);
        const row = {
          id: "cp-reconciled",
          workspace_id: params?.[0],
          engine_project_id: params?.[1],
          slug: params?.[2],
          name: params?.[3],
          created_at: new Date(),
        };
        storedRows.push(row);
        return { rows: [row], rowCount: 1 };
      }
      if (text.includes("FROM control_projects WHERE workspace_id = $1")) {
        return { rows: [...storedRows], rowCount: storedRows.length };
      }
      return { rows: [], rowCount: 0 };
    });

    const engine = fakeEngine({
      listProjects: vi.fn(async () => [
        {
          id: "eng-seed-1",
          slug: "support-triage",
          name: "Support Triage",
          description: "Seeded in engine",
          workspace_id: "w1",
        },
      ]),
    });

    const projects = await serviceWith(pool, engine).service.listProjects("w1", owner);
    expect(engine.listProjects).toHaveBeenCalledWith({
      workspaceId: "w1",
      actor: "owner-sub",
    });
    expect(insertedParams).toHaveLength(1);
    expect(insertedParams[0]).toEqual(["w1", "eng-seed-1", "support-triage", "Support Triage"]);
    expect(projects).toHaveLength(1);
    expect(projects[0]).toMatchObject({
      id: "cp-reconciled",
      workspace_id: "w1",
      engine_project_id: "eng-seed-1",
      slug: "support-triage",
      name: "Support Triage",
    });
  });

  it("refuses to import engine projects belonging to another workspace or legacy unassigned (null workspace_id)", async () => {
    const insertedParams: unknown[][] = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("INSERT INTO control_projects")) {
        insertedParams.push(params ?? []);
        return {
          rows: [
            {
              id: `cp-${insertedParams.length}`,
              workspace_id: params?.[0],
              engine_project_id: params?.[1],
              slug: params?.[2],
              name: params?.[3],
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      return { rows: [], rowCount: 0 };
    });

    const engine = fakeEngine({
      listProjects: vi.fn(async () => [
        {
          id: "eng-own",
          slug: "alpha-project",
          name: "Alpha Project",
          description: "Owned by ws-1",
          workspace_id: "ws-1",
        },
        {
          id: "eng-other",
          slug: "beta-project",
          name: "Beta Project",
          description: "Owned by other-workspace",
          workspace_id: "other-workspace",
        },
        {
          id: "eng-legacy",
          slug: "legacy-project",
          name: "Legacy Project",
          description: "Legacy unassigned",
          workspace_id: null,
        },
        {
          id: "eng-undefined",
          slug: "undefined-project",
          name: "Undefined Project",
          description: "Missing workspace_id",
        },
      ]),
    });

    const projects = await serviceWith(pool, engine).service.list(owner, "ws-1");
    expect(insertedParams).toHaveLength(1);
    expect(insertedParams[0]).toEqual(["ws-1", "eng-own", "alpha-project", "Alpha Project"]);
    expect(projects).toHaveLength(1);
    expect(projects[0]).toMatchObject({
      workspace_id: "ws-1",
      engine_project_id: "eng-own",
      slug: "alpha-project",
    });
  });

  it("isolates two workspaces (ws-alpha and ws-beta) so listing never leaks or imports each other's projects", async () => {
    const controlProjects: Row[] = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (text.startsWith("SELECT workspace_id FROM control_projects WHERE engine_project_id")) {
        const matches = controlProjects.filter(
          (row) => row.engine_project_id === params?.[0] || row.slug === params?.[1],
        );
        return { rows: matches, rowCount: matches.length };
      }
      if (text.includes("FROM control_projects WHERE workspace_id = $1")) {
        const wsRows = controlProjects.filter((row) => row.workspace_id === params?.[0]);
        return { rows: wsRows, rowCount: wsRows.length };
      }
      if (text.startsWith("INSERT INTO control_projects")) {
        const row = {
          id: `cp-${controlProjects.length + 1}`,
          workspace_id: params?.[0],
          engine_project_id: params?.[1],
          slug: params?.[2],
          name: params?.[3],
          created_at: new Date(),
        };
        controlProjects.push(row);
        return { rows: [row], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    });

    const engineStore: Array<{
      id: string;
      slug: string;
      name: string;
      description: string;
      workspace_id: string | null;
    }> = [
      {
        id: "eng-alpha",
        slug: "alpha-ops",
        name: "Alpha Ops",
        description: "",
        workspace_id: "ws-alpha",
      },
      {
        id: "eng-beta",
        slug: "beta-ops",
        name: "Beta Ops",
        description: "",
        workspace_id: "ws-beta",
      },
      {
        id: "eng-unassigned",
        slug: "legacy-seed",
        name: "Legacy Seed",
        description: "",
        workspace_id: null,
      },
    ];

    const engine = fakeEngine({
      listProjects: vi.fn(async () => [...engineStore]),
    });

    const { service } = serviceWith(pool, engine);
    const alphaList = await service.list(owner, "ws-alpha");
    const betaList = await service.list(owner, "ws-beta");

    expect(alphaList.map((p) => p.slug)).toEqual(["alpha-ops"]);
    expect(betaList.map((p) => p.slug)).toEqual(["beta-ops"]);
    expect(alphaList.every((p) => p.workspace_id === "ws-alpha")).toBe(true);
    expect(betaList.every((p) => p.workspace_id === "ws-beta")).toBe(true);
  });

  it("looks up a project by control id, engine_project_id, or slug and lazily syncs null engine_project_id", async () => {
    const updatedParams: unknown[][] = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (
        text.includes("FROM control_projects") &&
        text.includes("(id::text = $1 OR engine_project_id = $1 OR slug = $1)")
      ) {
        return {
          rows: [
            {
              id: "cp-1",
              workspace_id: "w1",
              engine_project_id: null,
              slug: "support-triage",
              name: "Support Triage",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      if (text.startsWith("UPDATE control_projects SET engine_project_id =")) {
        updatedParams.push(params ?? []);
        return { rows: [], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    });

    const engine = fakeEngine({
      getProject: vi.fn(async () => ({
        id: "eng-lazy-1",
        slug: "support-triage",
        name: "Support Triage",
        description: "",
      })),
    });

    const found = await serviceWith(pool, engine).service.getProjectForWorkspace(
      "w1",
      "support-triage",
      owner,
    );
    expect(engine.getProject).toHaveBeenCalledWith("support-triage", {
      workspaceId: "w1",
      actor: "owner-sub",
    });
    expect(updatedParams).toEqual([["cp-1", "w1", "eng-lazy-1"]]);
    expect(found.engine_project_id).toBe("eng-lazy-1");
  });

  it("syncMissingEngineProject does not link another workspace's engine project and tries claimProject on 404 before creating", async () => {
    const updatedParams: unknown[][] = [];
    const pool = fakePool(async (text, params) => {
      if (text.startsWith("SELECT role")) return { rows: [{ role: "owner" }], rowCount: 1 };
      if (
        text.includes("FROM control_projects") &&
        text.includes("(id::text = $1 OR engine_project_id = $1 OR slug = $1)")
      ) {
        return {
          rows: [
            {
              id: "cp-1",
              workspace_id: "ws-alpha",
              engine_project_id: null,
              slug: "shared-slug",
              name: "Shared Slug",
              created_at: new Date(),
            },
          ],
          rowCount: 1,
        };
      }
      if (text.startsWith("UPDATE control_projects SET engine_project_id =")) {
        updatedParams.push(params ?? []);
        return { rows: [], rowCount: 1 };
      }
      return { rows: [], rowCount: 0 };
    });

    const engineOtherWorkspace = fakeEngine({
      getProject: vi.fn(async () => ({
        id: "eng-owned-by-beta",
        slug: "shared-slug",
        name: "Shared Slug",
        description: "",
        workspace_id: "ws-beta",
      })),
      createProject: vi.fn(async () => ({
        id: "eng-fresh-alpha",
        slug: "shared-slug-2",
        name: "Shared Slug",
        description: "",
        workspace_id: "ws-alpha",
      })),
    });

    const syncedFresh = await serviceWith(pool, engineOtherWorkspace).service.get(
      owner,
      "ws-alpha",
      "shared-slug",
    );
    expect(engineOtherWorkspace.createProject).toHaveBeenCalledWith("Shared Slug", "", {
      workspaceId: "ws-alpha",
      actor: "owner-sub",
    });
    expect(syncedFresh.engine_project_id).toBe("eng-fresh-alpha");

    const engineClaimable = fakeEngine({
      getProject: vi.fn(async () => {
        throw new NotFoundException("Project not found");
      }),
      claimProject: vi.fn(async () => ({
        id: "eng-claimed-alpha",
        slug: "shared-slug",
        name: "Shared Slug",
        description: "",
        workspace_id: "ws-alpha",
      })),
    });

    const syncedClaimed = await serviceWith(pool, engineClaimable).service.get(
      owner,
      "ws-alpha",
      "shared-slug",
    );
    expect(engineClaimable.claimProject).toHaveBeenCalledWith("shared-slug", {
      workspaceId: "ws-alpha",
      actor: "owner-sub",
    });
    expect(syncedClaimed.engine_project_id).toBe("eng-claimed-alpha");
  });
});
