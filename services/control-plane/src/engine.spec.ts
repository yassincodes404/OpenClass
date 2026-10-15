import {
  BadGatewayException,
  BadRequestException,
  ConflictException,
  NotFoundException,
} from "@nestjs/common";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineClient } from "./engine.js";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("EngineClient", () => {
  const originalInternalToken = process.env.OPENCLASS_INTERNAL_TOKEN;
  const originalBaseUrl = process.env.ENGINE_BASE_URL;

  beforeEach(() => {
    vi.unstubAllGlobals();
    delete process.env.OPENCLASS_INTERNAL_TOKEN;
    delete process.env.ENGINE_BASE_URL;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    if (originalInternalToken === undefined) {
      delete process.env.OPENCLASS_INTERNAL_TOKEN;
    } else {
      process.env.OPENCLASS_INTERNAL_TOKEN = originalInternalToken;
    }
    if (originalBaseUrl === undefined) {
      delete process.env.ENGINE_BASE_URL;
    } else {
      process.env.ENGINE_BASE_URL = originalBaseUrl;
    }
  });

  it("forwards X-OpenClass-Internal-Token when OPENCLASS_INTERNAL_TOKEN is set", async () => {
    process.env.OPENCLASS_INTERNAL_TOKEN = "  internal-secret-token-123  ";
    const fetchMock = vi.fn(async () => jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    const client = new EngineClient();
    await client.listClassifiers();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:7331/api/v1/classifiers", {
      method: "GET",
      headers: {
        "X-OpenClass-Internal-Token": "internal-secret-token-123",
      },
      body: undefined,
    });
  });

  it("omits X-OpenClass-Internal-Token when OPENCLASS_INTERNAL_TOKEN is not set", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    const client = new EngineClient();
    await client.listClassifiers();

    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:7331/api/v1/classifiers", {
      method: "GET",
      headers: {},
      body: undefined,
    });
  });

  it("forwards X-OpenClass-Workspace-Id, X-OpenClass-Actor, and Idempotency-Key headers across request and ingestEvent", async () => {
    process.env.OPENCLASS_INTERNAL_TOKEN = "internal-token-xyz";
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return jsonResponse(201, { id: "evt-1", deduped: false });
      }
      return jsonResponse(200, { id: "proj-1", slug: "acme", name: "Acme", description: "" });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new EngineClient();

    await client.request("GET", "/api/v1/projects/proj-1", undefined, 200, {
      workspaceId: "ws-acme-01",
      actor: "user:alice@acme.io",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:7331/api/v1/projects/proj-1", {
      method: "GET",
      headers: {
        "X-OpenClass-Internal-Token": "internal-token-xyz",
        "X-OpenClass-Workspace-Id": "ws-acme-01",
        "X-OpenClass-Actor": "user:alice@acme.io",
      },
      body: undefined,
    });

    const ingestResult = await client.ingestEvent(
      "proj-1",
      { content: "I was charged twice", source_type: "text" },
      "idem-key-999",
    );

    expect(ingestResult).toEqual({
      status: 201,
      body: { id: "evt-1", deduped: false },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:7331/api/v1/projects/proj-1/events",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-OpenClass-Internal-Token": "internal-token-xyz",
          "Idempotency-Key": "idem-key-999",
        },
        body: JSON.stringify({ content: "I was charged twice", source_type: "text" }),
      },
    );
  });

  it("maps HTTP 404 to NotFoundException, 409 to ConflictException, and 429 to BadGatewayException", async () => {
    const client = new EngineClient();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(404, { detail: "Project not found in engine" })),
    );
    await expect(client.getProject("missing-proj")).rejects.toThrow(
      new NotFoundException("Engine rejected the request"),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(409, { detail: "Candidate promotion requires verified replay evaluation" }),
      ),
    );
    await expect(
      client.promoteCandidate("proj-1", "cand-1", {
        evaluation_id: "eval-1",
        reviewer: "alice",
        rationale: "ready",
      }),
    ).rejects.toThrow(new ConflictException("Engine rejected the request"));

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(429, { detail: "Rate limit exceeded" })),
    );
    await expect(
      client.ingestEvent("proj-1", { content: "Cancel my plan" }, "idem-429"),
    ).rejects.toThrow(new BadGatewayException("Engine rate limit reached; retry shortly"));
  });

  it("maps validation 400 errors to BadRequestException and network failures to BadGatewayException", async () => {
    const client = new EngineClient();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(422, { detail: [{ msg: "field required" }] })),
    );
    await expect(client.createProject("", "")).rejects.toThrow(
      new BadRequestException("Engine rejected the request"),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );
    await expect(client.providers()).rejects.toThrow(
      new BadGatewayException("Engine is temporarily unavailable"),
    );
  });

  it("claims legacy unassigned projects and forwards workspaceId, actor, and idempotencyKey across EngineClient methods", async () => {
    process.env.OPENCLASS_INTERNAL_TOKEN = "internal-token-xyz";
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/claim")) {
        return jsonResponse(200, {
          id: "proj-1",
          slug: "acme",
          name: "Acme",
          description: "",
          workspace_id: "ws-acme-01",
        });
      }
      if (url.endsWith("/projects") && init?.method === "POST") {
        return jsonResponse(201, {
          id: "proj-1",
          slug: "acme",
          name: "Acme",
          description: "desc",
          workspace_id: "ws-acme-01",
        });
      }
      if (url.endsWith("/decision-services") && init?.method === "POST") {
        return jsonResponse(201, {
          id: "svc-1",
          project_id: "proj-1",
          slug: "triage",
          name: "Triage",
          instructions: "Route",
          status: "active",
          nodes: [],
        });
      }
      if (url.endsWith("/runs") && init?.method === "POST") {
        return jsonResponse(201, []);
      }
      if (url.endsWith("/discover") && init?.method === "POST") {
        return jsonResponse(201, { id: "cand-1" });
      }
      return jsonResponse(200, []);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new EngineClient();
    const opts = {
      workspaceId: "ws-acme-01",
      actor: "user:alice@acme.io",
      idempotencyKey: "idem-op-1",
    };

    const claimed = await client.claimProject("acme", opts);
    expect(claimed.workspace_id).toBe("ws-acme-01");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:7331/api/v1/projects/acme/claim",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-OpenClass-Internal-Token": "internal-token-xyz",
          "Idempotency-Key": "idem-op-1",
          "X-OpenClass-Workspace-Id": "ws-acme-01",
          "X-OpenClass-Actor": "user:alice@acme.io",
        },
        body: JSON.stringify({}),
      },
    );

    await client.createProject("Acme", "desc", opts);
    await client.listProjects(opts);
    await client.getProject("proj-1", opts);
    await client.createDecisionService(
      "proj-1",
      { name: "Triage", instructions: "Route", choices: [{ key: "BILLING", label: "Billing" }] },
      opts,
    );
    await client.listDecisionServices("proj-1", opts);
    await client.runDecisions("proj-1", "svc-1", { content: "help" }, opts);
    await client.listUnknowns("proj-1", { state: "needs_evidence" }, opts);
    await client.clusterUnknowns("proj-1", 0.8, opts);
    await client.proposeCandidate("proj-1", "cluster-1", opts);

    for (const [, init] of fetchMock.mock.calls) {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers["X-OpenClass-Workspace-Id"]).toBe("ws-acme-01");
      expect(headers["X-OpenClass-Actor"]).toBe("user:alice@acme.io");
      expect(headers["Idempotency-Key"]).toBe("idem-op-1");
    }
  });
});
