import assert from "node:assert/strict";
import test from "node:test";
import { OpenClass, OpenClassError } from "./index.ts";

test("classification uses public protocol and escapes identifiers", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, "http://local/api/v1/classifiers/a%2Fb/classify");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(init?.body as string), { observation: "hello" });
    return Response.json({ selected_class: null });
  };
  const client = new OpenClass("http://local/", fetcher);
  assert.equal(
    (await client.classify({ classifier: "a/b", observation: "hello" })).selected_class,
    null,
  );
});

test("non-success responses reject without exposing response bodies", async () => {
  const client = new OpenClass(
    "http://local",
    async () => new Response("private", { status: 503 }),
  );
  await assert.rejects(
    client.health(),
    (error: unknown) => error instanceof OpenClassError && error.status === 503,
  );
});
