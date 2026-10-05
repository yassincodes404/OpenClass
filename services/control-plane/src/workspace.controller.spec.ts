import { BadRequestException } from "@nestjs/common";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";

const principal = { subject: "owner-sub" };

function controllerWith(overrides: Partial<WorkspaceService> = {}) {
  const service = {
    mine: vi.fn(async () => [{ id: "w1", slug: "acme", name: "Acme", role: "owner" }]),
    create: vi.fn(async () => ({ id: "w1", slug: "acme", name: "Acme", role: "owner" })),
    members: vi.fn(async () => [{ subject: "owner-sub", role: "owner", created_at: new Date() }]),
    invite: vi.fn(async () => ({ subject: "reviewer-sub", role: "reviewer" })),
    ...overrides,
  } as unknown as WorkspaceService;
  return { controller: new WorkspaceController(service), service };
}

describe("WorkspaceController", () => {
  it("GET / returns the caller's workspaces", async () => {
    const { controller, service } = controllerWith();
    const rows = await controller.mine({ principal });
    expect(rows).toHaveLength(1);
    expect(service.mine).toHaveBeenCalledWith(principal);
  });

  it("POST / rejects names shorter than 2 characters (400)", async () => {
    const { controller, service } = controllerWith();
    expect(() => controller.create({ principal }, { name: "x" })).toThrow(BadRequestException);
    expect(service.create).not.toHaveBeenCalled();
  });

  it("POST / rejects names over 200 characters (400)", async () => {
    const { controller } = controllerWith();
    expect(() => controller.create({ principal }, { name: "x".repeat(201) })).toThrow(BadRequestException);
  });

  it("POST / accepts a valid name and delegates to the service", async () => {
    const { controller, service } = controllerWith();
    const created = await controller.create({ principal }, { name: "  Acme Support  " });
    expect(created).toMatchObject({ slug: "acme", role: "owner" });
    expect(service.create).toHaveBeenCalledWith(principal, "Acme Support");
  });

  it("POST /:id/members rejects an invalid role (400)", async () => {
    const { controller, service } = controllerWith();
    expect(() => controller.invite({ principal }, "w1", { subject: "new-sub", role: "superuser" })).toThrow(
      BadRequestException,
    );
    expect(service.invite).not.toHaveBeenCalled();
  });

  it("POST /:id/members rejects an empty subject (400)", async () => {
    const { controller } = controllerWith();
    expect(() => controller.invite({ principal }, "w1", { subject: "", role: "viewer" })).toThrow(BadRequestException);
  });

  it("POST /:id/members delegates a valid member payload", async () => {
    const { controller, service } = controllerWith();
    const member = await controller.invite({ principal }, "w1", { subject: "new-sub", role: "reviewer" });
    expect(member).toEqual({ subject: "reviewer-sub", role: "reviewer" });
    expect(service.invite).toHaveBeenCalledWith(principal, "w1", "new-sub", "reviewer");
  });
});
