import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  NotFoundException,
} from "@nestjs/common";
import type { Pool } from "pg";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiKeyService } from "./api-key.service.js";
import type { AuditService } from "./audit.service.js";
import { EngineClient } from "./engine.js";
import { ProjectController } from "./project.controller.js";
import { ProjectService, type ControlClassifier } from "./project.service.js";

// Real controller, service and HTTP engine adapter; only SQL/HTTP storage is simulated.
// This is NOT genuine PostgreSQL -> engine acceptance.
const owner = { subject: "owner" };
const projects = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    workspace_id: "w1",
    engine_project_id: "engine-p1",
    slug: "first",
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    workspace_id: "w1",
    engine_project_id: "engine-p2",
    slug: "second",
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    workspace_id: "w2",
    engine_project_id: "engine-p3",
    slug: "private",
  },
];
const body = {
  name: "Support intent",
  slug: "support-intent",
  unknown_fallback: true,
  classes: [{ canonical_name: "billing", display_name: "Billing" }],
};

afterEach(() => vi.unstubAllGlobals());

function harness() {
  const mappings: ControlClassifier[] = [];
  const engineRows = new Map<string, { id: string; slug: string }>();
  const attempts: string[] = [];
  let failInsert = false;
  const fetcher = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    if (path === "/api/v1/classifiers" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body)) as { slug: string };
      attempts.push(payload.slug);
      // Actual engine CreateClassifier/Classifer pattern and global SQL uniqueness.
      if (!/^[a-z][a-z0-9-]{0,79}$/.test(payload.slug))
        return Response.json({ detail: "invalid slug" }, { status: 422 });
      if (engineRows.has(payload.slug))
        return Response.json({ detail: "globally duplicate slug" }, { status: 409 });
      const row = { ...payload, id: `engine-c${engineRows.size + 1}` };
      engineRows.set(row.slug, row);
      return Response.json(
        { ...row, active_ontology_version_id: `ontology-${row.id}` },
        { status: 201 },
      );
    }
    const ontology = /^\/api\/v1\/classifiers\/([^/]+)\/ontology$/.exec(path);
    if (ontology && [...engineRows.values()].some((row) => row.id === ontology[1]))
      return Response.json({ id: `ontology-${ontology[1]}`, classes: body.classes });
    throw new Error(`Unexpected engine route ${path}`);
  });
  vi.stubGlobal("fetch", fetcher);
  const db = {
    query: vi.fn(async (sql: string, params: string[]) => {
      const result = (rows: unknown[]) => ({ rows, rowCount: rows.length });
      if (sql.startsWith("SELECT role"))
        return result(
          params[0] === "w1" && ["owner", "viewer"].includes(params[1]!)
            ? [{ role: params[1] }]
            : [],
        );
      if (sql.startsWith("SELECT id, workspace_id"))
        return result(
          projects.filter(
            (p) =>
              p.workspace_id === params[1] &&
              [p.id, p.engine_project_id, p.slug].includes(params[0]!),
          ),
        );
      if (sql.startsWith("SELECT 1 FROM control_classifiers"))
        return result(mappings.filter((m) => m.project_id === params[0] && m.slug === params[1]));
      if (sql.startsWith("INSERT INTO control_classifiers")) {
        if (failInsert) throw new Error("simulated local insert failure");
        const row = {
          id: `control-c${mappings.length + 1}`,
          project_id: params[0]!,
          engine_classifier_id: params[1]!,
          slug: params[2]!,
          name: params[3]!,
          created_at: new Date(),
        };
        mappings.push(row);
        return result([row]);
      }
      if (sql.includes("FROM control_classifiers WHERE id ="))
        return result(mappings.filter((m) => m.id === params[0] && m.project_id === params[1]));
      throw new Error("Unexpected SQL boundary");
    }),
  } as unknown as Pool;
  const service = new ProjectService(
    db,
    new EngineClient(),
    {} as ApiKeyService,
    {
      record: vi.fn(async () => {}),
    } as unknown as AuditService,
  );
  return {
    controller: new ProjectController(service),
    mappings,
    engineRows,
    attempts,
    fetcher,
    failLocalInsert: () => {
      failInsert = true;
    },
  };
}

describe("project-local public classifier slugs across the engine boundary", () => {
  it("creates distinct deterministic engine identities for the same public slug in two projects", async () => {
    const first = harness();
    const a = await first.controller.createClassifier(
      { principal: owner },
      "w1",
      projects[0]!.id,
      body,
    );
    const b = await first.controller.createClassifier(
      { principal: owner },
      "w1",
      projects[1]!.id,
      body,
    );
    expect([a.slug, b.slug]).toEqual(["support-intent", "support-intent"]);
    expect(a.engine_classifier_id).not.toBe(b.engine_classifier_id);
    expect(first.mappings.map((m) => m.project_id)).toEqual(projects.slice(0, 2).map((p) => p.id));
    expect(new Set(first.attempts).size).toBe(2);
    for (const slug of first.attempts) expect(slug).toMatch(/^ocp-[a-f0-9]{64}$/);
    const second = harness();
    // Canonical project identity, not the caller's deep-link alias.
    await second.controller.createClassifier(
      { principal: owner },
      "w1",
      projects[0]!.engine_project_id,
      body,
    );
    await second.controller.createClassifier({ principal: owner }, "w1", projects[1]!.slug, body);
    expect(second.attempts).toEqual(first.attempts);
  });

  it("hashes the full 80-character public slug without truncating shared prefixes", async () => {
    const h = harness();
    for (const slug of [`a${"b".repeat(78)}c`, `a${"b".repeat(78)}d`, "a"])
      await h.controller.createClassifier({ principal: owner }, "w1", projects[0]!.id, {
        ...body,
        slug,
      });
    expect(new Set(h.attempts).size).toBe(3);
    for (const slug of h.attempts) expect(slug).toMatch(/^ocp-[a-f0-9]{64}$/);
    expect(h.mappings[0]!.slug).toHaveLength(80);
  });

  it("rejects same-project duplicate retries before engine I/O, including project aliases", async () => {
    const h = harness();
    await h.controller.createClassifier({ principal: owner }, "w1", projects[0]!.id, body);
    for (const project of [projects[0]!.id, projects[0]!.slug, projects[0]!.engine_project_id])
      await expect(
        h.controller.createClassifier({ principal: owner }, "w1", project, body),
      ).rejects.toThrow(BadRequestException);
    expect(h.attempts).toHaveLength(1);
    expect(h.mappings).toHaveLength(1);
  });

  it("does not adopt or randomly rename a remote creation after local mapping failure", async () => {
    const h = harness();
    h.failLocalInsert();
    await expect(
      h.controller.createClassifier({ principal: owner }, "w1", projects[0]!.id, body),
    ).rejects.toThrow("simulated local insert failure");
    await expect(
      h.controller.createClassifier({ principal: owner }, "w1", projects[0]!.id, body),
    ).rejects.toThrow(ConflictException);
    expect(h.attempts).toHaveLength(2);
    expect(h.attempts[0]).toBe(h.attempts[1]);
    expect(h.engineRows.size).toBe(1);
    expect(h.mappings).toHaveLength(0);
  });

  it.each(["Support-intent", "../intent", "a/b", "étiquette", "a".repeat(81)])(
    "rejects malformed public slug %s before engine I/O",
    (slug) => {
      const h = harness();
      expect(() =>
        h.controller.createClassifier({ principal: owner }, "w1", projects[0]!.id, {
          ...body,
          slug,
        }),
      ).toThrow(BadRequestException);
      expect(h.fetcher).not.toHaveBeenCalled();
    },
  );

  it("preserves role, cross-workspace and malformed project identifier gates", async () => {
    const h = harness();
    await expect(
      h.controller.createClassifier(
        { principal: { subject: "viewer" } },
        "w1",
        projects[0]!.id,
        body,
      ),
    ).rejects.toThrow(ForbiddenException);
    for (const [workspace, project] of [
      ["w2", projects[2]!.id],
      ["w1", projects[2]!.id],
      ["w1", "../invalid"],
    ])
      await expect(
        h.controller.createClassifier({ principal: owner }, workspace!, project!, body),
      ).rejects.toThrow(NotFoundException);
    expect(h.fetcher).not.toHaveBeenCalled();
  });

  it("reads legacy classifiers by the saved engine ID, never a recomputed namespaced slug", async () => {
    const h = harness();
    h.engineRows.set("support-intent", { id: "legacy-engine-id", slug: "support-intent" });
    h.mappings.push({
      id: "legacy-control-id",
      project_id: projects[0]!.id,
      engine_classifier_id: "legacy-engine-id",
      slug: "support-intent",
      name: "Support intent",
      created_at: new Date(),
    });
    const result = await h.controller.getClassifier(
      { principal: owner },
      "w1",
      projects[0]!.id,
      "legacy-control-id",
    );
    expect(result).toMatchObject({
      slug: "support-intent",
      engine_classifier_id: "legacy-engine-id",
      active_ontology_version_id: "ontology-legacy-engine-id",
    });
    expect(h.attempts).toHaveLength(0);
    expect(h.fetcher).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/classifiers/legacy-engine-id/ontology"),
      expect.anything(),
    );
  });
});
