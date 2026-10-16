import assert from "node:assert/strict";
import test from "node:test";
import { POST } from "../app/control/[...path]/route";
import { readRelayBody } from "./relay-body";

function streamed(chunks = 12) {
  let pulled = 0;
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      pulled += 1;
      if (pulled > chunks) controller.close();
      else controller.enqueue(new Uint8Array(1024 * 1024));
    },
    cancel() {
      cancelled = true;
    },
  });
  const request = new Request("http://relay/control/workspaces", {
    method: "POST",
    headers: { authorization: "Bearer invalid" },
    body,
    duplex: "half",
  } as RequestInit & { duplex: string });
  return { request, pulled: () => pulled, cancelled: () => cancelled };
}

test("relay rejects a chunked oversized body without consuming the remaining stream", async () => {
  const source = streamed();
  const response = await POST(source.request, {
    params: Promise.resolve({ path: ["workspaces"] }),
  });
  assert.equal(response.status, 413);
  assert.equal(source.cancelled(), true);
  assert.ok(source.pulled() < 12, "Must stop before buffering the entire attacker-controlled body");
});

test("declared oversized bodies are cancelled without draining them", async () => {
  const source = streamed();
  source.request.headers.set("content-length", String(12 * 1024 * 1024));
  await assert.rejects(readRelayBody(source.request), { status: 413 });
  assert.equal(source.cancelled(), true);
  assert.ok(source.pulled() < 12);
});

test("relay body deadline cancels a stalled incoming stream", async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    pull() {
      return new Promise<void>(() => {});
    },
    cancel() {
      cancelled = true;
    },
  });
  const request = new Request("http://relay/control/workspaces", {
    method: "POST",
    body,
    duplex: "half",
  } as RequestInit & { duplex: string });
  await assert.rejects(readRelayBody(request, { timeoutMs: 20 }), { status: 408 });
  assert.equal(cancelled, true);
});

test("bounded body decoding preserves Unicode split across byte chunks", async () => {
  const bytes = new TextEncoder().encode('{"text":"é 🐈"}');
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
  const request = new Request("http://relay/control/workspaces", {
    method: "POST",
    body,
    duplex: "half",
  } as RequestInit & { duplex: string });
  assert.equal(await readRelayBody(request, { maxBytes: bytes.length }), '{"text":"é 🐈"}');
});

test("the actual relay preserves upstream 200/201/207/204 success statuses", async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [200, 201, 207, 204]) {
      globalThis.fetch = async () =>
        status === 204
          ? new Response(null, { status })
          : Response.json({ accepted: true }, { status });
      const result = await POST(
        new Request("http://relay/control/workspaces", {
          method: "POST",
          headers: { authorization: "Bearer simulated-local-token" },
          body: JSON.stringify({ name: "Status probe" }),
        }),
        { params: Promise.resolve({ path: ["workspaces"] }) },
      );
      assert.equal(result.status, status);
      if (status === 204) assert.equal(await result.text(), "");
      else assert.deepEqual(await result.json(), { accepted: true });
    }
  } finally {
    globalThis.fetch = original;
  }
});
