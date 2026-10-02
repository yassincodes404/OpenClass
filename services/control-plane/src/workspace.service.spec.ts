import { ForbiddenException, NotFoundException } from "@nestjs/common";
import type { Pool, PoolClient } from "pg";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceService, type Role } from "./workspace.service.js";

type Row = Record<string, unknown>;
type FakeResult = { rows: Row[]; rowCount: number };

function resultOf(rows: Row[]): FakeResult {
  return { rows, rowCount: rows.length };
}

function fakeClient(script: (text: string, params?: unknown[]) => Promise<FakeResult>): PoolClient {
  return {
    query: vi.fn(script),
    release: vi.fn(),
  } as unknown as PoolClient;
}

function fakePool(script: (text: string, params?: unknown[]) => Promise<FakeResult>): Pool {
  return {
    query: vi.fn(script),
    connect: vi.fn(async () => fakeClient(script)),
  } as unknown as Pool;
}

const owner = { subject: "owner-sub" };
const reviewer = { subject: "reviewer-sub" };
const workspaceId = "00000000-0000-4000-8000-000000000001";

describe("WorkspaceService", () => {
  it("mine returns the caller's workspaces with roles", async () => {
    const pool = fakePool(async () =>
      resultOf([{ id: workspaceId, slug: "acme", name: "Acme", role: "owner" }]),
    );
    const workspaces = await new WorkspaceService(pool).mine(owner);
    expect(workspaces).toEqual([{ id: workspaceId, slug: "acme", name: "Acme", role: "owner" }]);
  });

  it("create inserts workspace plus owner membership in one transaction", async () => {
    const statements: string[] = [];
    const pool = fakePool(async (text) => {
      statements.push(text);
      if (text.startsWith("SELECT slug")) return resultOf([]);
      if (text.startsWith("INSERT INTO control_workspaces")) {
        return resultOf([{ id: workspaceId, slug: "acme-support", name: "Acme Support" }]);
      }
      return resultOf([]);
    });
    const created = await new WorkspaceService(pool).create(owner, "Acme Support");
    expect(created).toMatchObject({ slug: "acme-support", role: "owner" });
    expect(statements.some((s) => s === "BEGIN")).toBe(true);
    expect(statements.some((s) => s === "COMMIT")).toBe(true);
    expect(statements.some((s) => s.includes("role) VALUES ($1, $2, 'owner')"))).toBe(true);
  });

  it("create appends a numeric suffix when the slug collides", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT slug")) return resultOf([{ slug: "acme" }, { slug: "acme-2" }]);
      if (text.startsWith("INSERT INTO control_workspaces")) {
        return resultOf([{ id: workspaceId, slug: "acme-3", name: "Acme" }]);
      }
      return resultOf([]);
    });
    const created = await new WorkspaceService(pool).create(owner, "Acme");
    expect(created.slug).toBe("acme-3");
  });

  it("members of an unknown workspace → 404 without enumeration", async () => {
    const pool = fakePool(async () => resultOf([]));
    await expect(new WorkspaceService(pool).members(owner, workspaceId)).rejects.toThrow(
      new NotFoundException("Workspace not found"),
    );
  });

  it("members of a joined workspace are listed for any member", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("SELECT role FROM control_workspace_memberships WHERE workspace_id")) {
        return resultOf([{ role: "viewer" }]);
      }
      return resultOf([{ subject: "owner-sub", role: "owner", created_at: new Date("2026-10-02T00:00:00Z") }]);
    });
    const members = await new WorkspaceService(pool).members({ subject: "viewer-sub" }, workspaceId);
    expect(members).toHaveLength(1);
    expect(members[0].role).toBe("owner");
  });

  it("invite by a reviewer → 403", async () => {
    const pool = fakePool(async () => resultOf([{ role: "reviewer" }]));
    await expect(new WorkspaceService(pool).invite(reviewer, workspaceId, "new-sub", "viewer" as Role)).rejects.toThrow(
      new ForbiddenException("Workspace role cannot manage members"),
    );
  });

  it("invite by an admin upserts the membership", async () => {
    const pool = fakePool(async (text) => {
      if (text.startsWith("INSERT INTO control_workspace_memberships")) {
        return resultOf([{ subject: "new-sub", role: "reviewer" }]);
      }
      return resultOf([{ role: "admin" }]);
    });
    const member = await new WorkspaceService(pool).invite({ subject: "admin-sub" }, workspaceId, "new-sub", "reviewer");
    expect(member).toEqual({ subject: "new-sub", role: "reviewer" });
  });
});
