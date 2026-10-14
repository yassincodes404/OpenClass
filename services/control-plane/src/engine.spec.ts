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
      new NotFoundException("Project not found in engine"),
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
    ).rejects.toThrow(
      new ConflictException("Candidate promotion requires verified replay evaluation"),
    );

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
      new BadRequestException("Invalid engine payload: field required"),
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
});
