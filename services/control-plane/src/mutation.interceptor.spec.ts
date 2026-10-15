import "reflect-metadata";
import type { ExecutionContext } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import type { Pool } from "pg";
import { lastValueFrom, of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import type { IdempotencyService, RequestIdentity, StoredResponse } from "./idempotency.service.js";
import { requestHash } from "./idempotency.service.js";
import { MutationInterceptor } from "./mutation.interceptor.js";
import { ProjectController } from "./project.controller.js";
import { requestContext } from "./request-context.js";
import { KeycloakGuard } from "./auth.js";
import { ProjectService } from "./project.service.js";
import { SafeExceptionFilter } from "./safe-exception.filter.js";

function fixture(
  path = "/control/workspaces/w/projects/p/events",
  handler: Function = ProjectController.prototype.create,
) {
  const request = {
    method: "POST",
    originalUrl: path,
    body: { content: "ordinary fixture" },
    params: { workspaceId: "w", projectId: "p" },
    principal: { subject: "api-key:p" },
    headers: { "idempotency-key": "shared-key" },
    keyId: "first-key",
    keyProjectId: "p",
    keyScopes: ["ingest"],
    keyRequiredScope: "ingest",
  };
  let row = {
    id: "first-key",
    workspace_id: "w",
    project_id: "p",
    scopes: ["ingest"],
    revoked_at: null as Date | null,
  };
  const query = vi.fn(async (_sql: string, _params: unknown[]) => ({ rows: [row], rowCount: 1 }));
  const identities: RequestIdentity[] = [];
  const downstream: Array<string | undefined> = [];
  const execute = vi.fn(
    async (
      _scope: string,
      _key: string | undefined,
      resolve: () => Promise<RequestIdentity>,
      operation: (hash?: string) => Promise<StoredResponse<unknown>>,
    ) => {
      const identity = await resolve();
      identities.push(identity);
      return operation(requestHash(identity));
    },
  );
  const next = {
    handle: vi.fn(() => {
      downstream.push(requestContext.getStore()?.idempotencyKey);
      return of({ accepted: true });
    }),
  };
  const response = { statusCode: 201, status: vi.fn() };
  const context = {
    getHandler: () => handler,
    getClass: () => ProjectController,
    switchToHttp: () => ({ getRequest: () => request, getResponse: () => response }),
  } as unknown as ExecutionContext;
  const interceptor = new MutationInterceptor(
    { query } as unknown as Pool,
    { execute } as unknown as IdempotencyService,
  );
  return {
    request,
    query,
    next,
    identities,
    downstream,
    execute,
    setRow(value: typeof row) {
      row = value;
    },
    run: () => lastValueFrom(interceptor.intercept(context, next)),
  };
}

describe("trusted mutation identity", () => {
  it("blocks actual Express case-insensitive secret routes without database access or key creation", async () => {
    const createKey = vi.fn();
    const execute = vi.fn();
    const query = vi.fn();
    Reflect.defineMetadata("design:paramtypes", [ProjectService], ProjectController);
    const module = await Test.createTestingModule({
      controllers: [ProjectController],
      providers: [{ provide: ProjectService, useValue: { createKey } }],
    })
      .overrideGuard(KeycloakGuard)
      .useValue({
        canActivate(context: ExecutionContext) {
          context.switchToHttp().getRequest().principal = {
            subject: "simulated-authenticated-user",
          };
          return true;
        },
      })
      .compile();
    const app = module.createNestApplication({ logger: false });
    app.useGlobalInterceptors(
      new MutationInterceptor(
        { query } as unknown as Pool,
        { execute } as unknown as IdempotencyService,
      ),
    );
    app.useGlobalFilters(new SafeExceptionFilter());
    try {
      await app.listen(0, "127.0.0.1");
      const base = await app.getUrl();
      for (const spelling of ["keys", "KEYS", "KeYs"]) {
        const response = await fetch(`${base}/control/workspaces/w/projects/p/${spelling}`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": `case-${spelling}` },
          body: JSON.stringify({ scopes: ["read"] }),
        });
        expect(response.status).toBe(400);
      }
      expect(createKey).not.toHaveBeenCalled();
      expect(execute).not.toHaveBeenCalled();
      expect(query).not.toHaveBeenCalled();
    } finally {
      await app.close();
    }
  });

  it.each(["keys", "KEYS", "KeYs"])(
    "rejects secret handler caching for %s before reservation or creation",
    async (spelling) => {
      const test = fixture(
        `/control/workspaces/w/projects/p/${spelling}`,
        ProjectController.prototype.createKey,
      );
      await expect(test.run()).rejects.toMatchObject({ status: 400 });
      expect(test.execute).not.toHaveBeenCalled();
      expect(test.query).not.toHaveBeenCalled();
      expect(test.next.handle).not.toHaveBeenCalled();
    },
  );

  it("uses the exact current key row ID in request identity and downstream keys", async () => {
    const test = fixture();
    await test.run();
    test.request.keyId = "second-key";
    test.setRow({
      id: "second-key",
      workspace_id: "w",
      project_id: "p",
      scopes: ["ingest"],
      revoked_at: null,
    });
    await test.run();
    expect(test.identities.map((identity) => identity.authorization)).toEqual([
      { subject: "api-key:p", keyId: "first-key", project: "p", scopes: ["ingest"] },
      { subject: "api-key:p", keyId: "second-key", project: "p", scopes: ["ingest"] },
    ]);
    expect(test.downstream[0]).not.toBe(test.downstream[1]);
    expect(test.query.mock.calls[0][1]).toEqual(["first-key"]);
    expect(test.query.mock.calls[0][0]).toContain("FOR SHARE OF k");
    expect(JSON.stringify(test.identities)).not.toContain("oc_dev_");
  });

  it.each(["revoked", "scope-removed", "wrong-workspace", "wrong-project"])(
    "rechecks %s from the database after guard admission",
    async (state) => {
      const test = fixture();
      test.setRow({
        id: "first-key",
        workspace_id: state === "wrong-workspace" ? "other" : "w",
        project_id: state === "wrong-project" ? "other" : "p",
        scopes: state === "scope-removed" ? ["read"] : ["ingest"],
        revoked_at: state === "revoked" ? new Date() : null,
      });
      await expect(test.run()).rejects.toMatchObject({
        status: state.startsWith("wrong") ? 404 : 403,
      });
      expect(test.next.handle).not.toHaveBeenCalled();
      expect(test.downstream).toEqual([]);
    },
  );
});
