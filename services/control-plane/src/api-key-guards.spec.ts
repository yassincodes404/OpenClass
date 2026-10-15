import "reflect-metadata";
import type { ExecutionContext } from "@nestjs/common";
import { describe, expect, it, vi } from "vitest";
import type { ApiKeyService } from "./api-key.service.js";
import type { KeycloakGuard } from "./auth.js";
import { DecisionGuard } from "./decision.controller.js";
import { IngestionGuard } from "./ingestion.service.js";

describe.each([
  ["ingestion", IngestionGuard, "ingest"],
  ["decision", DecisionGuard, "classify"],
] as const)("%s API key guard", (_name, Guard, mutationScope) => {
  it.each(["GET", "POST"])(
    "propagates non-secret row identity and required scope for %s",
    async (method) => {
      const requiredScope = method === "GET" ? "read" : mutationScope;
      const verified = {
        keyId: "key-row-id",
        workspaceId: "workspace",
        projectId: "project",
        scopes: [requiredScope],
      };
      const verify = vi.fn(async () => verified);
      const request = {
        method,
        headers: { authorization: "Bearer oc_dev_simulated_guard_fixture" },
      };
      const context = {
        switchToHttp: () => ({ getRequest: () => request }),
      } as unknown as ExecutionContext;
      const guard = new Guard({} as KeycloakGuard, { verify } as unknown as ApiKeyService);
      expect(await guard.canActivate(context)).toBe(true);
      expect(verify).toHaveBeenCalledWith("oc_dev_simulated_guard_fixture", requiredScope);
      expect(request).toMatchObject({
        keyId: "key-row-id",
        keyProjectId: "project",
        keyScopes: [requiredScope],
        keyRequiredScope: requiredScope,
      });
    },
  );
});
