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

test("review requests the run's review route with a manual trigger", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, "http://local/api/v1/classifiers/a%2Fb/runs/run-1/reviews");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(init?.body as string), { trigger: "manual" });
    return Response.json({
      id: "review",
      classifier_id: "c",
      classification_run_id: "run-1",
      ontology_version_id: "v1",
      trigger: "manual",
      result: { finding: "no_issue", recommendation: "none", rationale: "advisory" },
      created_at: "2026-01-01T00:00:00Z",
    });
  };
  const client = new OpenClass("http://local", fetcher);
  const review = await client.reviewRun({ classifier: "a/b", runId: "run-1" });
  assert.equal(review.result.finding, "no_issue");
  assert.equal(review.classification_run_id, "run-1");
});

test("runs and reviews are read over GET without bodies", async () => {
  const seen: string[] = [];
  const fetcher: typeof fetch = async (url, init) => {
    seen.push(`${init?.method ?? "GET"} ${url}`);
    return Response.json([]);
  };
  const client = new OpenClass("http://local", fetcher);
  await client.runs("support-intent");
  await client.run({ classifier: "support-intent", runId: "run-1" });
  await client.reviews("support-intent");
  assert.deepEqual(seen, [
    "GET http://local/api/v1/classifiers/support-intent/runs",
    "GET http://local/api/v1/classifiers/support-intent/runs/run-1",
    "GET http://local/api/v1/classifiers/support-intent/reviews",
  ]);
});
