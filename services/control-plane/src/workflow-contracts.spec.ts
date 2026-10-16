import { BadRequestException, NotFoundException } from "@nestjs/common";
import { describe, expect, it } from "vitest";
import { workflowContract, workflowQuery } from "./workflow-contracts.js";

const UUID = "123e4567-e89b-42d3-a456-426614174000";

describe("workflowContract", () => {
  it("allows a bare project read for viewers", () => {
    const contract = workflowContract("GET", "", undefined);
    expect(contract.role).toBe("viewer");
    expect(contract.status).toBe(200);
    expect(contract.body).toBeUndefined();
  });

  it("assigns mutation roles and statuses", () => {
    expect(workflowContract("POST", "events", { content: "charged twice" })).toMatchObject({
      role: "developer",
      status: 201,
    });
    expect(
      workflowContract("POST", "decision-services", {
        name: "Router",
        instructions: "Route requests",
        choices: [{ key: "BILLING", label: "Billing" }],
      }),
    ).toMatchObject({ role: "admin", status: 201 });
    expect(
      workflowContract("PATCH", `evidence/${UUID}/triage`, {
        diagnosis: "decision_space",
        rationale: "Missing billing intent",
      }),
    ).toMatchObject({ role: "reviewer", status: 200 });
    expect(workflowContract("POST", `eval-datasets/${UUID}/seal`, {})).toMatchObject({
      role: "admin",
    });
  });

  it("rejects unknown routes and verbs (404, closed allowlist)", () => {
    expect(() => workflowContract("GET", "ontology", undefined)).toThrow(NotFoundException);
    expect(() => workflowContract("DELETE", "ontology/rollback", undefined)).toThrow(
      NotFoundException,
    );
    expect(() => workflowContract("DELETE", `evidence/${UUID}`, undefined)).toThrow(
      NotFoundException,
    );
    expect(() => workflowContract("PUT", "events", { content: "x" })).toThrow(NotFoundException);
  });

  it("never proxies compatibility promotion or replay-shortcut routes", () => {
    // These engine routes cannot bind a verified dataset and explicit human
    // approval, so they must stay unproxied.
    expect(() => workflowContract("POST", `discovery-candidates/${UUID}/promote`, {})).toThrow(
      NotFoundException,
    );
    expect(() => workflowContract("POST", `evaluations/${UUID}/promote`, {})).toThrow(
      NotFoundException,
    );
    expect(() => workflowContract("POST", "evaluations/compat", {})).toThrow(NotFoundException);
  });

  it("rejects invalid bodies (400) and strips nothing silently", () => {
    expect(() => workflowContract("POST", "events", {})).toThrow(BadRequestException);
    expect(() => workflowContract("POST", "events", { content: "" })).toThrow(BadRequestException);
    expect(() =>
      workflowContract("POST", "decision-services", {
        name: "Router",
        instructions: "Route requests",
        choices: [{ key: "billing", label: "Billing" }],
      }),
    ).toThrow(BadRequestException);
    // Strict schemas reject unexpected keys instead of passing them to the engine.
    expect(() =>
      workflowContract("POST", "events", { content: "x", internal_token: "secret" }),
    ).toThrow(BadRequestException);
  });

  it("requires evidence transitions to name a known target status", () => {
    expect(() =>
      workflowContract("POST", `evidence/${UUID}/transition`, { target_status: "promoted" }),
    ).toThrow(BadRequestException);
    expect(
      workflowContract("POST", `evidence/${UUID}/transition`, { target_status: "resolved" }),
    ).toMatchObject({ role: "reviewer" });
  });

  it("requires proposal requests to bind a case or at least three evidence ids", () => {
    expect(() => workflowContract("POST", "evolution/propose", {})).toThrow(BadRequestException);
    expect(() =>
      workflowContract("POST", "evolution/propose", {
        service_id: UUID,
        evidence_ids: [UUID, UUID],
      }),
    ).toThrow(BadRequestException);
    expect(workflowContract("POST", "evolution/propose", { evidence_case_id: UUID })).toMatchObject(
      { role: "reviewer", status: 201 },
    );
  });
});

describe("workflowQuery", () => {
  it("serializes known filters and coerces pagination", () => {
    expect(workflowQuery({ status: "pending", limit: "25", offset: "50" })).toBe(
      "?limit=25&offset=50&status=pending",
    );
    expect(workflowQuery({})).toBe("");
  });

  it("rejects unknown keys and out-of-range pagination (400)", () => {
    expect(() => workflowQuery({ admin: "true" })).toThrow(BadRequestException);
    expect(() => workflowQuery({ limit: "201" })).toThrow(BadRequestException);
    expect(() => workflowQuery({ offset: "-1" })).toThrow(BadRequestException);
    expect(() => workflowQuery({ status: "promoted" })).toThrow(BadRequestException);
  });
});
