import assert from "node:assert/strict";
import test from "node:test";
import {
  ControlApiError,
  OpenClass,
  OpenClassClient,
  OpenClassControlClient,
  OpenClassError,
} from "./index.ts";

test("webhook retries retain external event identity and send credentials only in headers", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, "http://local/api/v1/projects/a%2Fb/integrations/i%2Fd/webhook");
    assert.equal(init?.method, "POST");
    assert.equal(new Headers(init?.headers).get("X-OpenClass-Token"), "test-token");
    assert.equal(JSON.parse(init?.body as string).event_key, "ticket:revision:1");
    assert.ok(!(init?.body as string).includes("test-token"));
    return Response.json({ status: "duplicate", event_id: "original-event" });
  };
  const client = new OpenClass("http://local", fetcher);
  const result = await client.ingestIntegrationWebhook({
    project: "a/b",
    integrationId: "i/d",
    eventKey: "ticket:revision:1",
    content: "Customer message",
    token: "test-token",
  });
  assert.equal(result.status, "duplicate");
});

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

test("candidate rejection uses the scoped public route", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, "http://local/api/v1/classifiers/a%2Fb/candidates/candidate-1/reject");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(init?.body as string), { reason: "Wrong concept" });
    return Response.json({ id: "candidate-1", status: "rejected" });
  };
  const client = new OpenClass("http://local", fetcher);
  const result = await client.rejectCandidate({
    classifier: "a/b",
    candidateId: "candidate-1",
    reason: "Wrong concept",
  });
  assert.equal(result.status, "rejected");
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

test("projects create posts the public contract and reads back by slug", async () => {
  const requests: Array<{ url: string; method?: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    if (method === "POST" && String(url).endsWith("/projects")) {
      requests.push({ url: String(url), method, body });
      return Response.json({
        id: "p1",
        slug: "gymholic-intelligence",
        name: body.name,
        description: body.description,
        status: "active",
        owner_id: null,
        created_at: "2026-09-25T00:00:00Z",
        updated_at: "2026-09-25T00:00:00Z",
      });
    }
    return Response.json([
      { id: "p1", slug: "gymholic-intelligence", name: "GymHolic Intelligence" },
    ]);
  };
  const client = new OpenClass("http://local/", fetcher);
  const created = await client.createProject({
    name: "GymHolic Intelligence",
    description: "Customer intelligence experiment",
  });
  assert.equal(created.slug, "gymholic-intelligence");
  const listed = await client.projects();
  assert.equal(listed.length, 1);
  assert.equal(requests[0]?.url, "http://local/api/v1/projects");
});

test("project update issues PATCH with only the changed fields", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(init?.method, "PATCH");
    assert.deepEqual(JSON.parse(init?.body as string), { description: "updated" });
    return Response.json({
      id: "p1",
      slug: "p",
      name: "P",
      description: "updated",
      status: "active",
    });
  };
  const client = new OpenClass("http://local/", fetcher);
  const updated = await client.updateProject("p", { description: "updated" });
  assert.equal(updated.description, "updated");
});

test("raw events ingestion and retrieval work through public routes", async () => {
  const seen: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    seen.push({ url: String(url), method, body });
    if (String(url).endsWith("/events") && method === "POST") {
      return Response.json({ id: "evt-1", ...body });
    }
    if (String(url).endsWith("/events/batch") && method === "POST") {
      return Response.json(
        {
          items: [
            { index: 0, status: 201, event: { id: "evt-2", content: "a" }, deduped: false },
            { index: 1, status: 201, event: { id: "evt-3", content: "b" }, deduped: false },
          ],
        },
        { status: 207 },
      );
    }
    if (String(url).includes("/events?") || String(url).endsWith("/events")) {
      return Response.json([{ id: "evt-1" }]);
    }
    if (String(url).endsWith("/events/evt-1")) {
      return Response.json({ id: "evt-1", content: "hello" });
    }
    if (String(url).endsWith("/providers/status")) {
      return Response.json({ default_provider: "laya", laya: { status: "ready" } });
    }
    return Response.json({});
  };
  const client = new OpenClass("http://local/", fetcher);
  const single = await client.createEvent({ project: "proj-1", content: "test event" });
  assert.equal(single.id, "evt-1");
  const batch = await client.createEventsBatch({
    project: "proj-1",
    items: [{ content: "a" }, { content: "b" }],
  });
  assert.equal(batch.length, 2);
  assert.equal(batch[0]?.id, "evt-2");
  assert.equal(batch[1]?.id, "evt-3");
  const list = await client.events("proj-1", { limit: 10, offset: 0 });
  assert.equal(list.length, 1);
  const fetched = await client.event({ project: "proj-1", eventId: "evt-1" });
  assert.equal(fetched.content, "hello");
  const status = await client.providerStatus();
  assert.equal(status.default_provider, "laya");
});

test("decision services and decision runs work through public routes", async () => {
  const seen: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    seen.push({ url: String(url), method, body });
    if (String(url).endsWith("/decision-services") && method === "POST") {
      return Response.json({
        id: "svc-1",
        project_id: "p1",
        slug: "lead-routing",
        name: (body as any).name,
        description: (body as any).description,
        instructions: (body as any).instructions,
        nodes: [{ id: "n1", name: "default", choices: (body as any).choices }],
        status: "active",
        provider_override: null,
        created_at: "2026-09-26T00:00:00Z",
        updated_at: "2026-09-26T00:00:00Z",
      });
    }
    if (String(url).endsWith("/decision-services") && method === "GET") {
      return Response.json([{ id: "svc-1", name: "Lead Routing" }]);
    }
    if (String(url).endsWith("/decision-services/svc-1") && method === "GET") {
      return Response.json({ id: "svc-1", name: "Lead Routing" });
    }
    if (String(url).endsWith("/decision-services/svc-1") && method === "PATCH") {
      return Response.json({ id: "svc-1", name: "Lead Routing Updated" });
    }
    if (String(url).endsWith("/runs") && method === "POST") {
      return Response.json([
        {
          id: "run-1",
          project_id: "p1",
          raw_event_id: "evt-1",
          decision_service_id: "svc-1",
          provider: "laya",
          selected_choice: "ENTERPRISE",
          supervision_outcome: "REVIEW",
        },
      ]);
    }
    if (String(url).includes("/runs?") || String(url).endsWith("/runs")) {
      return Response.json([{ id: "run-1", selected_choice: "ENTERPRISE" }]);
    }
    if (String(url).endsWith("/runs/run-1")) {
      return Response.json({ id: "run-1", selected_choice: "ENTERPRISE" });
    }
    return Response.json({});
  };
  const client = new OpenClass("http://local/", fetcher);
  const svc = await client.createDecisionService({
    project: "p1",
    name: "Lead Routing",
    instructions: "Route incoming lead",
    choices: [
      { key: "ENTERPRISE", label: "Enterprise" },
      { key: "SMB", label: "SMB" },
    ],
  });
  assert.equal(svc.id, "svc-1");
  const list = await client.decisionServices("p1");
  assert.equal(list.length, 1);
  const single = await client.decisionService({ project: "p1", serviceId: "svc-1" });
  assert.equal(single.id, "svc-1");
  const updated = await client.updateDecisionService({
    project: "p1",
    serviceId: "svc-1",
    changes: { name: "Lead Routing Updated" },
  });
  assert.equal(updated.name, "Lead Routing Updated");
  const runs = await client.executeDecisionRuns({
    project: "p1",
    serviceId: "svc-1",
    rawEventIds: ["evt-1"],
  });
  assert.equal(runs[0]?.selected_choice, "ENTERPRISE");
  assert.equal(runs[0]?.supervision_outcome, "REVIEW");
  const runList = await client.decisionRuns("p1", { limit: 10 });
  assert.equal(runList.length, 1);
  const run = await client.decisionRun({ project: "p1", runId: "run-1" });
  assert.equal(run.id, "run-1");
});

test("evidence and evolution client routes communicate over public HTTP contract", async () => {
  const requests: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const urlStr = String(url);
    requests.push({ url: urlStr, method, body });

    if ((urlStr.includes("/evidence?") || urlStr.endsWith("/evidence")) && method === "GET") {
      return Response.json([{ id: "ev-1", status: "pending" }]);
    }
    if (urlStr.endsWith("/evidence/ev-1") && method === "GET") {
      return Response.json({ id: "ev-1", status: "pending" });
    }
    if (urlStr.endsWith("/evidence/ev-1/triage") && method === "PATCH") {
      return Response.json({ id: "ev-1", status: "triaged", ...body });
    }
    if (urlStr.endsWith("/evidence/ev-1/transition") && method === "POST") {
      return Response.json({ id: "ev-1", status: body.target_status });
    }
    if (urlStr.endsWith("/evidence/ev-1/ai-diagnose") && method === "POST") {
      return Response.json({
        diagnosis: "decision_space",
        rationale: "Missing enterprise option",
        confidence: 0.95,
        recommended_action: "Add choice",
        provider: "gemini",
        model: "gemini-2.5-flash",
        simulated: false,
      });
    }
    if (urlStr.endsWith("/runs/run-1/feedback") && method === "POST") {
      return Response.json({ id: "fb-1", ...body });
    }
    if (urlStr.endsWith("/runs/run-1/feedback") && method === "GET") {
      return Response.json([{ id: "fb-1", action: "confirm" }]);
    }
    if (urlStr.endsWith("/evidence-cases") && method === "POST") {
      return Response.json({ id: "case-1", ...body });
    }
    if (
      (urlStr.includes("/evidence-cases?") || urlStr.endsWith("/evidence-cases")) &&
      method === "GET"
    ) {
      return Response.json([{ id: "case-1", title: "Enterprise Gaps" }]);
    }
    if (urlStr.endsWith("/evidence-cases/case-1") && method === "GET") {
      return Response.json({ id: "case-1", title: "Enterprise Gaps" });
    }
    if (urlStr.endsWith("/evidence-cases/case-1/evidence") && method === "GET") {
      return Response.json([{ id: "ev-1", status: "ready_for_evolution" }]);
    }
    if (urlStr.endsWith("/evidence-cases/case-1/evidence") && method === "POST") {
      return Response.json({ id: "case-1", title: "Enterprise Gaps" });
    }
    if (urlStr.endsWith("/evolution/summary") && method === "GET") {
      return Response.json({
        project_id: "p1",
        pending_evidence: 1,
        triaged_evidence: 0,
        ready_for_evolution: 1,
        resolved_evidence: 0,
        dismissed_evidence: 0,
        total_evidence: 2,
        open_cases: 1,
        total_cases: 1,
      });
    }
    return Response.json({});
  };

  const client = new OpenClass("http://local/", fetcher);

  const evList = await client.evidence("p1", { status: "pending" });
  assert.equal(evList.length, 1);
  assert.equal(evList[0]?.id, "ev-1");

  const evItem = await client.evidenceItem({ project: "p1", evidenceId: "ev-1" });
  assert.equal(evItem.id, "ev-1");

  const triaged = await client.triageEvidence({
    project: "p1",
    evidenceId: "ev-1",
    diagnosis: "decision_space",
    rationale: "Need enterprise tier",
  });
  assert.equal(triaged.status, "triaged");

  const transitioned = await client.transitionEvidence({
    project: "p1",
    evidenceId: "ev-1",
    targetStatus: "ready_for_evolution",
    note: "Ready for Teacher synthesis",
  });
  assert.equal(transitioned.status, "ready_for_evolution");

  const aiDiag = await client.aiDiagnoseEvidence({ project: "p1", evidenceId: "ev-1" });
  assert.equal(aiDiag.diagnosis, "decision_space");
  assert.equal(aiDiag.confidence, 0.95);

  const fb = await client.submitRunFeedback({
    project: "p1",
    runId: "run-1",
    action: "confirm",
  });
  assert.equal(fb.id, "fb-1");

  const fbList = await client.runFeedback({ project: "p1", runId: "run-1" });
  assert.equal(fbList.length, 1);

  const c = await client.createEvidenceCase({
    project: "p1",
    title: "Enterprise Gaps",
    evidenceIds: ["ev-1"],
  });
  assert.equal(c.id, "case-1");

  const attached = await client.addEvidenceToCase({
    project: "p1",
    caseId: "case-1",
    evidenceId: "ev-1",
  });
  assert.equal(attached.id, "case-1");

  const cList = await client.evidenceCases("p1");
  assert.equal(cList.length, 1);

  const singleC = await client.evidenceCase({ project: "p1", caseId: "case-1" });
  assert.equal(singleC.id, "case-1");

  const cEv = await client.caseEvidence({ project: "p1", caseId: "case-1" });
  assert.equal(cEv.length, 1);

  const summary = await client.evolutionSummary("p1");
  assert.equal(summary.ready_for_evolution, 1);
  assert.equal(summary.open_cases, 1);
});

test("candidate evolution, evaluation replay, and promotion work over public HTTP contract", async () => {
  const requests: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const urlStr = String(url);
    requests.push({ url: urlStr, method, body });

    if (urlStr.endsWith("/candidates") && method === "GET") {
      return Response.json([{ id: "cand-1", status: "candidate" }]);
    }
    if (urlStr.endsWith("/candidates/cand-1") && method === "GET") {
      return Response.json({ id: "cand-1", status: "candidate" });
    }
    if (urlStr.endsWith("/decision-services/svc-1/candidates") && method === "POST") {
      return Response.json({
        id: "cand-1",
        status: "candidate",
        evidence_run_ids: body.run_ids,
      });
    }
    if (urlStr.endsWith("/evolution/propose") && method === "POST") {
      return Response.json({
        id: "cand-2",
        status: "candidate",
        proposal: { kind: "new_choice", key: "ENTERPRISE", label: "Enterprise" },
      });
    }
    if (urlStr.endsWith("/candidates/cand-1/evaluate") && method === "POST") {
      return Response.json({
        candidate_id: "cand-1",
        decision_service_id: "svc-1",
        passed: true,
        accuracy_on_knowns: 1.0,
        disambiguation_rate: 1.0,
        regressions: [],
      });
    }
    if (urlStr.endsWith("/candidates/cand-1/promote") && method === "POST") {
      return Response.json({
        candidate: { id: "cand-1", status: "promoted" },
        decision_service: { id: "svc-1", status: "active" },
      });
    }
    if (urlStr.endsWith("/candidates/cand-1/reject") && method === "POST") {
      return Response.json({
        id: "cand-1",
        status: "rejected",
        rejection_reason: body.reason,
      });
    }
    return new Response(null, { status: 404 });
  };

  const client = new OpenClass("http://localhost:7331", fetcher);

  const cands = await client.projectCandidates("p1");
  assert.equal(cands.length, 1);

  const cand = await client.projectCandidate({ project: "p1", candidateId: "cand-1" });
  assert.equal(cand.id, "cand-1");

  const proposed = await client.proposeProjectChoice({
    project: "p1",
    serviceId: "svc-1",
    runIds: ["r1", "r2", "r3"],
  });
  assert.equal(proposed.id, "cand-1");

  const fromEvidence = await client.proposeFromEvidence({
    project: "p1",
    serviceId: "svc-1",
    evidenceIds: ["ev-1", "ev-2", "ev-3"],
  });
  assert.equal(fromEvidence.id, "cand-2");

  const evalResult = await client.evaluateProjectCandidate({
    project: "p1",
    candidateId: "cand-1",
  });
  assert.equal(evalResult.passed, true);
  assert.equal(evalResult.accuracy_on_knowns, 1.0);

  const promoted = await client.promoteProjectCandidate({
    project: "p1",
    candidateId: "cand-1",
    note: "Approved by lead architect",
  });
  assert.equal(promoted.candidate.status, "promoted");
  assert.equal(promoted.decision_service.status, "active");

  const rejected = await client.rejectProjectChoice({
    project: "p1",
    candidateId: "cand-1",
    reason: "Not viable",
  });
  assert.equal(rejected.status, "rejected");
});

test("project integrations and system health operate over public HTTP contract", async () => {
  const requests: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const urlStr = String(url);
    requests.push({ url: urlStr, method, body });

    if (urlStr.endsWith("/api/v1/system/health")) {
      return Response.json({
        status: "healthy",
        database: { connected: true, latency_ms: 1.2 },
        decision_provider: "laya",
        discovery_provider: "mock",
        version: "0.1.0",
      });
    }
    if (urlStr.endsWith("/integrations") && method === "GET") {
      return Response.json([
        {
          id: "int-1",
          name: "Stripe Webhook",
          type: "webhook",
          status: "connected",
          capabilities: ["event_ingestion"],
        },
      ]);
    }
    if (urlStr.endsWith("/integrations") && method === "POST") {
      return Response.json({ id: "int-1", status: "pending", ...body }, { status: 201 });
    }
    if (urlStr.endsWith("/integrations/int-1") && method === "GET") {
      return Response.json({
        id: "int-1",
        name: "Stripe Webhook",
        type: "webhook",
        status: "connected",
        capabilities: ["event_ingestion"],
      });
    }
    if (urlStr.endsWith("/integrations/int-1") && method === "PATCH") {
      return Response.json({ id: "int-1", ...body });
    }
    if (urlStr.endsWith("/integrations/int-1") && method === "DELETE") {
      return new Response(null, { status: 204 });
    }
    if (urlStr.endsWith("/integrations/int-1/test") && method === "POST") {
      return Response.json({
        integration_id: "int-1",
        status: "connected",
        latency_ms: 15.4,
        capabilities: ["event_ingestion"],
        error_message: null,
      });
    }

    return new Response("Not found", { status: 404 });
  };

  const client = new OpenClass("http://example.internal", fetcher);

  const health = await client.systemHealth();
  assert.equal(health.status, "healthy");
  assert.equal(health.database.connected, true);

  const created = await client.createProjectIntegration({
    project: "p1",
    name: "Stripe Webhook",
    type: "webhook",
    capabilities: ["event_ingestion"],
  });
  assert.equal(created.id, "int-1");

  const list = await client.projectIntegrations("p1");
  assert.equal(list.length, 1);
  assert.equal(list[0].name, "Stripe Webhook");

  const detail = await client.projectIntegration({ project: "p1", integrationId: "int-1" });
  assert.equal(detail.id, "int-1");

  const updated = await client.updateProjectIntegration({
    project: "p1",
    integrationId: "int-1",
    changes: { name: "Updated Webhook" },
  });
  assert.equal(updated.name, "Updated Webhook");

  const tested = await client.testProjectIntegration({ project: "p1", integrationId: "int-1" });
  assert.equal(tested.status, "connected");
  assert.equal(tested.latency_ms, 15.4);

  await client.deleteProjectIntegration({ project: "p1", integrationId: "int-1" });
  assert.equal(
    requests.some((r) => r.method === "DELETE"),
    true,
  );
});

test("phase 05-16 unknown clustering, discovery, evaluation, ontology, and ops endpoints work over HTTP", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const urlStr = String(url);
    if (urlStr.includes("/unknowns?") && method === "GET") {
      return Response.json({ items: [{ run_id: "r1" }], total: 1 });
    }
    if (urlStr.endsWith("/unknowns/r1/triage") && method === "POST") {
      return Response.json({ run_id: "r1", category: "candidate_new_class" });
    }
    if (urlStr.endsWith("/unknowns/cluster") && method === "POST") {
      return Response.json({ cluster_count: 1, cluster_ids: ["c1"] });
    }
    if (urlStr.endsWith("/clusters/c1/discover") && method === "POST") {
      return Response.json({ id: "dc-1", status: "proposed" }, { status: 201 });
    }
    if (urlStr.endsWith("/eval-datasets") && method === "POST") {
      return Response.json({ id: "ds-1", name: "Holdout" }, { status: 201 });
    }
    if (urlStr.endsWith("/evaluations") && method === "POST") {
      return Response.json({ id: "eval-1", overall_passed: true }, { status: 201 });
    }
    if (urlStr.endsWith("/discovery-candidates/dc-1/promote") && method === "POST") {
      return Response.json({ version_number: 2, status: "promoted" });
    }
    if (urlStr.endsWith("/ontology") && method === "GET") {
      return Response.json({ current_version: 2 });
    }
    if (urlStr.endsWith("/analytics/summary") && method === "GET") {
      return Response.json({ total_runs: 42 });
    }
    return new Response("Not found", { status: 404 });
  };

  const client = new OpenClass("http://example.internal", fetcher);
  const unknowns = await client.projectUnknowns("p1", { state: "needs_evidence" });
  assert.equal(unknowns.total, 1);

  const triaged = await client.triageProjectUnknown({
    project: "p1",
    runId: "r1",
    category: "candidate_new_class",
  });
  assert.equal(triaged.category, "candidate_new_class");

  const clustered = await client.clusterUnknowns({ project: "p1", threshold: 0.82 });
  assert.equal(clustered.cluster_count, 1);

  const discovered = await client.discoverCluster({ project: "p1", clusterId: "c1" });
  assert.equal(discovered.id, "dc-1");

  const dataset = await client.createEvalDataset({ project: "p1", name: "Holdout" });
  assert.equal(dataset.id, "ds-1");

  const evalRun = await client.runEvaluation({
    project: "p1",
    datasetId: "ds-1",
    candidateId: "dc-1",
  });
  assert.equal(evalRun.overall_passed, true);

  const promoted = await client.promoteDiscoveryCandidate({
    project: "p1",
    candidateId: "dc-1",
    evaluationId: "eval-1",
    reviewer: "lead",
    rationale: "Passed holdout",
  });
  assert.equal(promoted.version_number, 2);

  const ontology = await client.projectOntology("p1");
  assert.equal(ontology.current_version, 2);

  const ops = await client.operationsSummary("p1");
  assert.equal(ops.total_runs, 42);
});

test("OpenClassClient resumeDecisionRun and cancelDecisionRun post checkpoint governance payloads", async () => {
  const seen: Array<{ url: string; method: string; body: unknown }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    seen.push({ url: String(url), method, body });
    if (String(url).endsWith("/runs/run-42/resume")) {
      return Response.json({
        run_id: "run-42",
        status: "completed",
        selected_choice: "BILLING",
        resumed_by: "ops-lead",
      });
    }
    if (String(url).endsWith("/runs/run-42/cancel")) {
      return Response.json({
        run_id: "run-42",
        status: "cancelled",
        cancelled_by: "ops-lead",
        reason: "Duplicate ticket",
      });
    }
    return new Response("Not found", { status: 404 });
  };

  const client = new OpenClassClient("http://example.internal", fetcher);
  const resumed = await client.resumeDecisionRun({
    project: "acme-support",
    runId: "run-42",
    approvedChoice: "BILLING",
    operator: "ops-lead",
    rationale: "Confirmed billing escalation",
    strictVersionCheck: true,
    usePinnedVersion: true,
    expectedCheckpointRevision: 3,
    expectedNodeKey: "billing-review",
    forceRecoverStaleClaim: false,
  });
  assert.equal(resumed.status, "completed");
  assert.equal(resumed.selected_choice, "BILLING");

  const cancelled = await client.cancelDecisionRun("acme-support", "run-42", {
    operator: "ops-lead",
    reason: "Duplicate ticket",
  });
  assert.equal(cancelled.status, "cancelled");
  assert.equal(cancelled.reason, "Duplicate ticket");

  assert.deepEqual(seen, [
    {
      url: "http://example.internal/api/v1/projects/acme-support/runs/run-42/resume",
      method: "POST",
      body: {
        approved_choice: "BILLING",
        operator: "ops-lead",
        rationale: "Confirmed billing escalation",
        strict_version_check: true,
        use_pinned_version: true,
        expected_checkpoint_revision: 3,
        expected_node_key: "billing-review",
        force_recover_stale_claim: false,
      },
    },
    {
      url: "http://example.internal/api/v1/projects/acme-support/runs/run-42/cancel",
      method: "POST",
      body: {
        operator: "ops-lead",
        reason: "Duplicate ticket",
      },
    },
  ]);
});

test("OpenClassControlClient attaches Bearer token, Idempotency-Key, handles 204, and throws ControlApiError on 4xx/5xx", async () => {
  const requests: Array<{
    url: string;
    method?: string;
    headers: Record<string, string>;
    body?: string;
  }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((value, key) => {
      headers[key.toLowerCase()] = value;
    });
    requests.push({
      url: String(url),
      method: init?.method,
      headers,
      body: init?.body as string | undefined,
    });

    const urlStr = String(url);
    if (urlStr.endsWith("/control/projects") && init?.method === "POST") {
      return Response.json(
        {
          id: "cp-1",
          workspace_id: "ws-1",
          engine_project_id: "ep-1",
          slug: "acme",
          name: "Acme",
          created_at: "2026-10-14T00:00:00Z",
        },
        { status: 201 },
      );
    }
    if (urlStr.endsWith("/control/no-content")) {
      return new Response(null, { status: 204 });
    }
    if (urlStr.endsWith("/control/conflict")) {
      return new Response(JSON.stringify({ detail: "Decision run has already been resumed" }), {
        status: 409,
        headers: { "content-type": "application/json" },
      });
    }
    if (urlStr.endsWith("/control/gateway-error")) {
      return new Response(JSON.stringify({ message: "Engine is temporarily unavailable" }), {
        status: 502,
        headers: { "content-type": "application/json" },
      });
    }
    return Response.json([]);
  };

  const control = new OpenClassControlClient({ baseUrl: "/control", fetcher });

  const created = await control.createProject(
    { name: "Acme", description: "Support workspace" },
    { token: "jwt-token-123", idempotencyKey: "idem-abc-1" },
  );
  assert.equal(created.id, "cp-1");
  assert.equal(requests[0]?.url, "/control/projects");
  assert.equal(requests[0]?.headers.authorization, "Bearer jwt-token-123");
  assert.equal(requests[0]?.headers["idempotency-key"], "idem-abc-1");
  assert.equal(requests[0]?.headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(requests[0]?.body ?? "{}"), {
    name: "Acme",
    description: "Support workspace",
  });

  const empty = await control.request<void>("/no-content", {
    method: "DELETE",
    token: "jwt-token-123",
  });
  assert.equal(empty, undefined);

  await assert.rejects(
    control.request("/conflict", { token: "jwt-token-123" }),
    (err: unknown) =>
      err instanceof ControlApiError &&
      err.status === 409 &&
      err.detail === "Decision run has already been resumed",
  );

  await assert.rejects(
    control.request("/gateway-error", { token: "jwt-token-123" }),
    (err: unknown) =>
      err instanceof ControlApiError &&
      err.status === 502 &&
      err.detail === "Engine is temporarily unavailable",
  );
});

test("OpenClassControlClient typed project, decision, unknown, evaluation, and ops convenience methods", async () => {
  const seen: string[] = [];
  const fetcher: typeof fetch = async (url, init) => {
    const method = init?.method ?? "GET";
    seen.push(`${method} ${url}`);
    const urlStr = String(url);
    if (urlStr.endsWith("/summary") && !urlStr.includes("/analytics/summary")) {
      return Response.json({
        events: 10,
        decision_runs: 8,
        unknowns: 2,
        pending_evidence: 2,
        active_policy: "default",
        pending_candidates: 1,
        audit_events: 12,
      });
    }
    if (urlStr.endsWith("/runs/r-1/resume")) {
      return Response.json({ run_id: "r-1", status: "completed" });
    }
    if (urlStr.endsWith("/runs/r-1/cancel")) {
      return Response.json({ run_id: "r-1", status: "cancelled" });
    }
    if (urlStr.endsWith("/runs/r-1")) {
      return Response.json({ id: "r-1", selected_choice: "BILLING" });
    }
    if (urlStr.includes("/unknowns?")) {
      return Response.json({ items: [], total: 0 });
    }
    if (urlStr.endsWith("/unknowns/cluster")) {
      return Response.json({ cluster_count: 1 });
    }
    if (urlStr.endsWith("/ontology")) {
      return Response.json({ versions: [] });
    }
    if (urlStr.endsWith("/analytics/summary")) {
      return Response.json({ window_days: 7, unknown_rate: 0.1 });
    }
    if (urlStr.endsWith("/projects/p-1")) {
      return Response.json({
        id: "p-1",
        workspace_id: "ws-1",
        engine_project_id: "ep-1",
        slug: "acme",
        name: "Acme",
        created_at: "2026-10-14T00:00:00Z",
      });
    }
    return Response.json([]);
  };

  const control = new OpenClassControlClient({
    baseUrl: "/control",
    token: "session-jwt",
    fetcher,
  });

  await control.listProjects("ws-1");
  await control.getProject("p-1");
  const summary = await control.getProjectSummary("ws-1", "p-1");
  assert.equal(summary.events, 10);
  await control.listEvents("ws-1", "p-1", { limit: 10 });
  await control.ingestEvent("ws-1", "p-1", { content: "Charge twice" }, { idempotencyKey: "k-1" });
  await control.listDecisionServices("ws-1", "p-1");
  const run = await control.getDecisionRun("ws-1", "p-1", "r-1");
  assert.equal(run.id, "r-1");
  const resumed = await control.resumeDecisionRun("ws-1", "p-1", "r-1", {
    approved_choice: "BILLING",
    operator: "alice",
  });
  assert.equal(resumed.status, "completed");
  const cancelled = await control.cancelDecisionRun("ws-1", "p-1", "r-1", {
    operator: "alice",
    reason: "Aborted",
  });
  assert.equal(cancelled.status, "cancelled");
  await control.listUnknowns("ws-1", "p-1", { state: "needs_evidence" });
  await control.clusterUnknowns("ws-1", "p-1", { threshold: 0.6 });
  await control.listClusters("ws-1", "p-1");
  await control.listDiscoveryCandidates("ws-1", "p-1");
  await control.listEvaluationDatasets("ws-1", "p-1");
  await control.listEvaluations("ws-1", "p-1");
  await control.listServiceVersions("ws-1", "p-1");
  await control.getAnalyticsSummary("ws-1", "p-1");
  await control.listIntegrations("ws-1", "p-1");
  await control.listApiKeys("ws-1", "p-1");

  assert.ok(seen.includes("GET /control/workspaces/ws-1/projects"));
  assert.ok(seen.includes("GET /control/projects/p-1"));
  assert.ok(seen.includes("POST /control/workspaces/ws-1/projects/p-1/runs/r-1/resume"));
  assert.ok(seen.includes("POST /control/workspaces/ws-1/projects/p-1/runs/r-1/cancel"));
});

test("OpenClassClient forwards X-OpenClass-Workspace-Id header and supports workspace_id on Project", async () => {
  const seenHeaders: Array<{ url: string; workspaceId: string | null }> = [];
  const fetcher: typeof fetch = async (url, init) => {
    const h = new Headers(init?.headers);
    seenHeaders.push({
      url: String(url),
      workspaceId: h.get("X-OpenClass-Workspace-Id"),
    });
    if (String(url).endsWith("/projects") && init?.method === "POST") {
      return Response.json({
        id: "p-ws-1",
        slug: "acme",
        name: "Acme",
        description: "",
        status: "active",
        owner_id: null,
        workspace_id: h.get("X-OpenClass-Workspace-Id"),
        created_at: "2026-10-15T00:00:00Z",
        updated_at: "2026-10-15T00:00:00Z",
      });
    }
    if (String(url).endsWith("/claim") && init?.method === "POST") {
      return Response.json({
        id: "p-ws-1",
        slug: "acme",
        name: "Acme",
        description: "",
        status: "active",
        owner_id: null,
        workspace_id: h.get("X-OpenClass-Workspace-Id"),
        created_at: "2026-10-15T00:00:00Z",
        updated_at: "2026-10-15T00:00:00Z",
      });
    }
    return Response.json([]);
  };

  const client = new OpenClassClient({
    baseURL: "http://example.internal",
    workspaceId: "ws-default",
    fetcher,
  });

  await client.projects();
  const created = await client.createProject({ name: "Acme" }, { workspaceId: "ws-override" });
  assert.equal(created.workspace_id, "ws-override");

  const claimed = await client.claimProject("acme", { workspaceId: "ws-claimed" });
  assert.equal(claimed.workspace_id, "ws-claimed");

  assert.deepEqual(seenHeaders, [
    { url: "http://example.internal/api/v1/projects", workspaceId: "ws-default" },
    { url: "http://example.internal/api/v1/projects", workspaceId: "ws-override" },
    { url: "http://example.internal/api/v1/projects/acme/claim", workspaceId: "ws-claimed" },
  ]);
});
