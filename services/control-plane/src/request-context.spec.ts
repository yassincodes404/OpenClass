import { Logger } from "@nestjs/common";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineClient } from "./engine.js";
import { correlationId, correlationMiddleware, requestContext } from "./request-context.js";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("correlation and secret-safe engine failures", () => {
  it("accepts bounded opaque IDs and replaces invalid/repeated header values", () => {
    expect(correlationId("incoming-123:child")).toBe("incoming-123:child");
    for (const value of ["bad\nheader", ["one", "two"], "x".repeat(129), "", undefined]) {
      expect(correlationId(value)).toMatch(/^[0-9a-f-]{36}$/);
    }
  });

  it("echoes and forwards incoming context for ordinary and ingestion HTTP paths", async () => {
    const fetchMock = vi.fn(
      async (_url: unknown, init?: RequestInit) =>
        new Response(
          JSON.stringify(init?.method === "GET" ? [] : { id: "event", deduped: false }),
          { status: init?.method === "GET" ? 200 : 201 },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const setHeader = vi.fn();
    await new Promise<void>((resolve, reject) => {
      correlationMiddleware(
        { headers: { "x-correlation-id": "incoming-123" } },
        { setHeader },
        () => {
          (async () => {
            const client = new EngineClient();
            await client.providers({ workspaceId: "workspace" });
            await client.ingestEvent("project", { content: "ordinary content" });
            resolve();
          })().catch(reject);
        },
      );
    });
    expect(setHeader).toHaveBeenCalledWith("X-Correlation-ID", "incoming-123");
    for (const [, init] of fetchMock.mock.calls) {
      expect((init?.headers as Record<string, string>)["X-Correlation-ID"]).toBe("incoming-123");
    }
    expect(requestContext.getStore()).toBeUndefined();
  });

  it("forwards explicit correlation options and isolates simultaneous request contexts", async () => {
    const seen: Array<Record<string, string>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url, init) => {
        await new Promise((resolve) => setTimeout(resolve, 2));
        seen.push(init.headers);
        return new Response("[]", { status: 200 });
      }),
    );
    const client = new EngineClient();
    await Promise.all(
      ["first", "second"].map((id) =>
        requestContext.run({ correlationId: id }, () => client.providers()),
      ),
    );
    await client.providers({ correlationId: "explicit" });
    expect(seen.map((headers) => headers["X-Correlation-ID"]).sort()).toEqual([
      "explicit",
      "first",
      "second",
    ]);
  });

  it("never exposes upstream strings through exceptions or structured logs", async () => {
    const sentinel = "simulated-private-upstream-detail";
    const log = vi.spyOn(Logger.prototype, "warn").mockImplementation(() => undefined);
    const client = new EngineClient();
    for (const status of [400, 404, 409, 500]) {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => new Response(JSON.stringify({ detail: sentinel }), { status })),
      );
      for (const operation of [
        () => client.providers({ correlationId: "failure-123" }),
        () =>
          client.ingestEvent("project", { content: "ordinary" }, { correlationId: "failure-123" }),
      ]) {
        await expect(operation()).rejects.not.toThrow(sentinel);
      }
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(sentinel);
      }),
    );
    await expect(client.providers({ correlationId: "failure-123" })).rejects.not.toThrow(sentinel);
    expect(JSON.stringify(log.mock.calls)).not.toContain(sentinel);
    expect(log.mock.calls[0][0]).toMatchObject({
      event: "control.engine_request_failed",
      correlation_id: "failure-123",
    });
  });
});
