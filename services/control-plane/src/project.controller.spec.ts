import { BadRequestException } from "@nestjs/common";
import { describe, expect, it, vi } from "vitest";
import { ProjectController } from "./project.controller.js";
import type { ProjectService } from "./project.service.js";

const principal = { subject: "owner-sub" };

function controllerWith(overrides: Partial<ProjectService> = {}) {
  const service = {
    list: vi.fn(async () => []),
    create: vi.fn(async () => ({ id: "p1", slug: "acme", name: "Acme" })),
    get: vi.fn(),
    createClassifier: vi.fn(async () => ({ id: "c1", slug: "support-intent" })),
    listClassifiers: vi.fn(async () => []),
    getClassifier: vi.fn(),
    createKey: vi.fn(async () => ({ key: "oc_dev_x", row: { id: "k1", prefix: "oc_dev_" } })),
    listKeys: vi.fn(async () => []),
    revokeKey: vi.fn(),
    ...overrides,
  } as unknown as ProjectService;
  return { controller: new ProjectController(service), service };
}

const validClassifier = {
  name: "Support intent",
  classes: [{ canonical_name: "billing", display_name: "Billing" }],
};

describe("ProjectController", () => {
  it("rejects a project name shorter than 2 chars (400)", () => {
    const { controller } = controllerWith();
    expect(() => controller.create({ principal }, "w1", { name: "x" })).toThrow(BadRequestException);
  });

  it("rejects classifier creation that opts out of UNKNOWN (400)", () => {
    const { controller, service } = controllerWith();
    expect(() => controller.createClassifier({ principal }, "w1", "p1", { ...validClassifier, unknown_fallback: false })).toThrow(BadRequestException);
    expect(service.createClassifier).not.toHaveBeenCalled();
  });

  it("defaults unknown_fallback to true for valid classifier bodies", () => {
    const { controller, service } = controllerWith();
    controller.createClassifier({ principal }, "w1", "p1", validClassifier);
    expect(service.createClassifier).toHaveBeenCalledWith(principal, "w1", "p1", expect.objectContaining({ unknownFallback: true }));
  });

  it("rejects an empty class list (400)", () => {
    const { controller } = controllerWith();
    expect(() => controller.createClassifier({ principal }, "w1", "p1", { ...validClassifier, classes: [] })).toThrow(BadRequestException);
  });

  it("rejects invalid key scopes (400)", () => {
    const { controller } = controllerWith();
    expect(() => controller.createKey({ principal }, "w1", "p1", { scopes: ["root"] })).toThrow(BadRequestException);
  });

  it("delegates valid key creation", () => {
    const { controller, service } = controllerWith();
    controller.createKey({ principal }, "w1", "p1", { scopes: ["ingest", "read"] });
    expect(service.createKey).toHaveBeenCalledWith(principal, "w1", "p1", ["ingest", "read"]);
  });
});
