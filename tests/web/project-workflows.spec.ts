import { test, expect, type Page, type Route } from "@playwright/test";

// ROUTE-MOCKED browser checks for the frontend workflow parity workstream.
// Every control-plane response below is fulfilled in the browser; no engine,
// control plane, database, or identity provider is contacted. These checks
// verify client wiring (SDK-only HTTP, workspace session, allowlist routes,
// honest states). They are NOT end-to-end proof and never close the root
// authenticated cross-child acceptance gate.

const SESSION = { token: "route-mocked-token" };
const WORKSPACE = { id: "ws-1", name: "Acme Ops", slug: "acme-ops", role: "admin" };
const MAPPING = {
  id: "cp-1",
  workspace_id: "ws-1",
  engine_project_id: "ep-1",
  slug: "acme",
  name: "Acme",
  created_at: "2026-10-15T00:00:00Z",
};
const PROJECT = {
  id: "ep-1",
  slug: "acme",
  name: "Acme",
  description: "Support desk",
  status: "active",
  owner_id: null,
  workspace_id: "ws-1",
  created_at: "2026-10-15T00:00:00Z",
  updated_at: "2026-10-15T00:00:00Z",
};
const SERVICE = {
  id: "11111111-1111-4111-8111-111111111111",
  project_id: "ep-1",
  slug: "support-router",
  name: "Support Router",
  description: "Routes support requests",
  instructions: "Route each message to the best intent.",
  status: "active",
  provider_override: null,
  version_number: 1,
  active_version_id: "ver-1",
  nodes: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      name: "Entry",
      instructions: "Route the request",
      choices: [
        { key: "BILLING", label: "Billing", description: "Billing questions" },
        { key: "UNKNOWN", label: "Unknown", description: "Permanent fallback" },
      ],
    },
  ],
  transitions: [],
  created_at: "2026-10-15T00:00:00Z",
  updated_at: "2026-10-15T00:00:00Z",
};

interface MockOptions {
  staleServiceRead?: boolean;
  readyReplay?: boolean;
  draftReplay?: boolean;
  evidenceFailure?: boolean;
}

const EVIDENCE = {
  id: "33333333-3333-4333-8333-333333333333",
  project_id: PROJECT.id,
  decision_service_id: SERVICE.id,
  status: "pending",
  trigger_type: "semantic_unknown",
  selected_choice: "UNKNOWN",
  diagnosis: null,
  diagnosis_rationale: null,
  evidence_case_id: null,
  probabilities_snapshot: { BILLING: 0.1, UNKNOWN: 0.9 },
  unknown_probability: 0.9,
  margin: 0.8,
  created_at: PROJECT.created_at,
};
const DATASET = {
  id: "44444444-4444-4444-8444-444444444444",
  name: "Route-mocked verified holdout",
  sealed_at: PROJECT.created_at,
  dataset_hash: "route-mocked-sealed-identity",
  examples: [],
};
const CANDIDATE = {
  id: "55555555-5555-4555-8555-555555555555",
  decision_service_id: SERVICE.id,
  status: "candidate",
  proposal: { key: "EVIDENCE_ONLY", label: "Evidence proposal", kind: "new_choice" },
};
const DISCOVERY_CANDIDATE = {
  id: "77777777-7777-4777-8777-777777777777",
  cluster_id: "88888888-8888-4888-8888-888888888888",
  type: "NEW_CLASS",
  canonical_name: "refund",
  display_name: "Refund",
  status: "candidate",
  confidence: 0.8,
  provider: "mock",
  simulated: true,
  evidence_count: 5,
  created_at: PROJECT.created_at,
};
const REPLAY = {
  id: "66666666-6666-4666-8666-666666666666",
  dataset_id: DATASET.id,
  candidate_id: DISCOVERY_CANDIDATE.id,
  overall_passed: false,
  is_simulated: true,
  provider: "route-mocked",
  model: "simulated",
  metrics: {
    simulated: true,
    baseline: { accuracy: 0.8 },
    candidate: { accuracy: 0.7 },
  },
  gates: [{ gate: "known_regression", passed: false, reason: "Simulated regression fixture" }],
};

async function mockSession(page: Page, session = SESSION) {
  await page.addInitScript((session) => {
    (window as unknown as Record<string, unknown>).__OPENCLASS_ROUTE_MOCKED_SESSION__ = session;
  }, session);
}

function mockControlPlane(
  page: Page,
  captured: {
    requests: Array<{
      path: string;
      method: string;
      headers: Record<string, string>;
      body: unknown;
    }>;
  },
  options: MockOptions = {},
) {
  let evidence = { ...EVIDENCE };
  let dataset = {
    ...DATASET,
    sealed_at: options.draftReplay ? null : DATASET.sealed_at,
    examples: [] as Array<Record<string, unknown>>,
  };
  return page.route("**/control/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries(request.headers())) headers[key] = value;
    let body: unknown;
    try {
      body = request.postDataJSON();
    } catch {
      body = undefined;
    }
    captured.requests.push({ path, method, headers, body });

    const json = (payload: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });

    if (path === "/control/workspaces" && method === "GET") return json([WORKSPACE]);
    if (path === "/control/workspaces/ws-1/projects" && method === "GET") return json([MAPPING]);
    if (path === "/control/workspaces/ws-1/projects" && method === "POST") {
      const name = (body as { name?: string })?.name ?? "New project";
      return json({ ...MAPPING, id: "cp-2", engine_project_id: "ep-2", slug: "new", name }, 201);
    }
    if (path === "/control/workspaces/ws-1/projects/cp-2/workflow" && method === "GET")
      return json({ ...PROJECT, id: "ep-2", slug: "new", name: "Acme" });
    if (path === "/control/projects/cp-1" && method === "GET") return json(MAPPING);
    const prefix = "/control/workspaces/ws-1/projects/cp-1/workflow";
    if (path === prefix && method === "GET") return json(PROJECT);
    if (path === `${prefix}/decision-services` && method === "GET") return json([SERVICE]);
    if (path === `${prefix}/decision-services/${SERVICE.id}` && method === "GET") {
      return json(
        options.staleServiceRead
          ? { ...SERVICE, active_version_id: "ver-2", version_number: 2, updated_at: "later" }
          : SERVICE,
      );
    }
    if (path === `${prefix}/decision-services/${SERVICE.id}` && method === "PATCH")
      return json({ ...SERVICE, version_number: 2, active_version_id: "ver-2" });
    if (path === `${prefix}/runs` && method === "GET") return json([]);
    if (path === `${prefix}/evolution/summary`)
      return json({ total_evidence: 1, pending_evidence: 1 });
    if (path === `${prefix}/evidence` && method === "GET")
      return options.evidenceFailure
        ? json({ message: "Evidence read denied" }, 403)
        : json([evidence]);
    if (path === `${prefix}/evidence/${EVIDENCE.id}` && method === "GET") return json(evidence);
    if (path === `${prefix}/evidence/${EVIDENCE.id}/ai-diagnose`)
      return json({
        diagnosis: "ambiguous_or_insufficient",
        rationale: "Route-mocked advisory only",
        confidence: 0.5,
        provider: "route-mocked",
        model: "simulated",
        simulated: true,
      });
    if (path === `${prefix}/evidence/${EVIDENCE.id}/triage` && method === "PATCH") {
      evidence = { ...evidence, ...(body as object), status: "triaged" };
      return json(evidence);
    }
    if (path === `${prefix}/evidence-cases`) return json([]);
    if (path === `${prefix}/eval-datasets` && method === "GET")
      return json(options.readyReplay || options.draftReplay ? [dataset] : []);
    if (path === `${prefix}/eval-datasets/${DATASET.id}`) return json(dataset);
    if (path === `${prefix}/eval-datasets/${DATASET.id}/examples` && method === "POST") {
      const example = { ...(body as object), id: "example-1" };
      dataset = { ...dataset, examples: [...dataset.examples, example] };
      return json(example, 201);
    }
    if (path === `${prefix}/eval-datasets/${DATASET.id}/seal` && method === "POST") {
      dataset = { ...dataset, sealed_at: PROJECT.created_at };
      return json(dataset);
    }
    if (path === `${prefix}/candidates` && method === "GET")
      return json(options.readyReplay ? [CANDIDATE] : []);
    if (path === `${prefix}/discovery-candidates` && method === "GET")
      return json(
        options.readyReplay
          ? [
              DISCOVERY_CANDIDATE,
              { ...DISCOVERY_CANDIDATE, id: "99999999-9999-4999-8999-999999999999", type: "ALIAS" },
              {
                ...DISCOVERY_CANDIDATE,
                id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                status: "rejected",
              },
              {
                ...DISCOVERY_CANDIDATE,
                id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                canonical_name: " ",
              },
            ]
          : [],
      );
    if (path === `${prefix}/evaluations` && method === "GET") return json([]);
    if (path === `${prefix}/evaluations` && method === "POST") return json(REPLAY, 201);
    return json({ detail: "not mocked" }, 404);
  });
}

test.describe("frontend workflow parity (route-mocked, not E2E proof)", () => {
  // Serial: the dev server cold-compiles each route once; parallel workers
  // otherwise starve one another past the navigation budget.
  test.describe.configure({ mode: "serial" });
  test.slow();

  const goto = (page: Page, path: string) =>
    page.goto(path, { waitUntil: "domcontentloaded", timeout: 120_000 });

  test("projects require a workspace session before any control-plane call", async ({ page }) => {
    await mockSession(page, { token: "" });
    let controlCalls = 0;
    await page.route("**/control/**", (route) => {
      controlCalls += 1;
      return route.fulfill({ status: 401, json: { detail: "unauthorized" } });
    });
    await goto(page, "/projects");
    await expect(page.getByRole("heading", { name: "Sign in to your workspace." })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("button", { name: "Continue with Keycloak" })).toBeVisible();
    expect(controlCalls).toBe(0);
  });

  test("projects list is built from real workspace memberships over the SDK", async ({ page }) => {
    const captured: {
      requests: Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>;
    } = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured);
    await goto(page, "/projects");
    await expect(page.getByRole("link", { name: /Acme/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: /Acme/ })).toHaveAttribute(
      "href",
      "/projects/ep-1",
    );
    // Every call carried the session bearer and never an internal engine credential.
    expect(captured.requests.length).toBeGreaterThan(0);
    for (const entry of captured.requests) {
      expect(entry.headers.authorization).toBe(`Bearer ${SESSION.token}`);
      expect(entry.headers["x-openclass-internal-token"]).toBeUndefined();
    }
    expect(captured.requests.some((entry) => entry.path.includes("/api/v1/"))).toBe(false);
  });

  test("create project posts to the workspace-scoped control route", async ({ page }) => {
    const captured: {
      requests: Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>;
    } = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured);
    await goto(page, "/projects");
    await page.getByLabel("Name").fill("Acme");
    await page.getByLabel("Description").fill("Support desk");
    await page.getByRole("button", { name: "Create project" }).click();
    await expect(page.getByRole("link", { name: /Acme/ }).first()).toBeVisible();
    const created = captured.requests.find(
      (entry) => entry.method === "POST" && entry.path === "/control/workspaces/ws-1/projects",
    );
    expect(created).toBeDefined();
    expect(created?.body).toEqual({ name: "Acme", description: "Support desk" });
    expect(created?.headers.authorization).toBe(`Bearer ${SESSION.token}`);
  });

  test("graph editor saves a new immutable version through the workflow allowlist", async ({
    page,
  }, testInfo) => {
    const captured: {
      requests: Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>;
    } = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured);
    await goto(page, "/projects/cp-1/decisions");
    await page
      .getByRole("button", { name: "Edit graph for Support Router" })
      .click({ timeout: 60_000 });
    await expect(page.getByRole("heading", { name: "Decision graph" })).toBeVisible();
    await expect(page.getByText(/Saving creates a new immutable version/)).toBeVisible();
    await page.getByRole("button", { name: "Add node", exact: true }).focus();
    await page.keyboard.press("Enter");
    await page.getByLabel("Node name", { exact: true }).nth(1).fill("Review");
    await page
      .getByRole("combobox", { name: "Next node", exact: true })
      .first()
      .selectOption({ label: "Review" });
    await page.getByLabel("Human approval before this transition").check();
    await page.screenshot({ path: testInfo.outputPath("route-mocked-graph.png"), fullPage: true });
    await page.getByRole("button", { name: "Save new graph version" }).click();
    await expect(page.getByText(/New version saved/)).toBeVisible();
    const saved = captured.requests.find(
      (entry) =>
        entry.method === "PATCH" &&
        entry.path ===
          `/control/workspaces/ws-1/projects/cp-1/workflow/decision-services/${SERVICE.id}`,
    );
    expect(saved).toBeDefined();
    const payload = saved?.body as { nodes?: Array<{ choices: Array<{ key: string }> }> };
    expect(payload?.nodes?.[0]?.choices.map((choice) => choice.key)).toContain("UNKNOWN");
    expect(payload.nodes).toHaveLength(2);
    expect((saved?.body as { transitions: unknown[] }).transitions).toEqual([
      expect.objectContaining({ choice_key: "BILLING", require_approval: true }),
    ]);
  });

  test("stale graph edits are blocked before any mutation reaches the control plane", async ({
    page,
  }) => {
    const captured: {
      requests: Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>;
    } = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured, { staleServiceRead: true });
    await goto(page, "/projects/cp-1/decisions");
    await page
      .getByRole("button", { name: "Edit graph for Support Router" })
      .click({ timeout: 60_000 });
    await page.getByRole("button", { name: "Save new graph version" }).click();
    await expect(page.getByText(/Service changed since loading/)).toBeVisible();
    expect(captured.requests.some((entry) => entry.method === "PATCH")).toBe(false);
  });

  test("replay workspace requires sealed verified datasets and never auto-promotes", async ({
    page,
  }) => {
    const captured: {
      requests: Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>;
    } = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured);
    await goto(page, "/projects/cp-1/evaluations");
    await expect(page.getByRole("heading", { name: "Verified replay evaluations" })).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText(/Predictions are not ground truth/)).toBeVisible();
    await expect(page.getByText(/No datasets yet/)).toBeVisible();
    await expect(page.getByText(/No replay evaluations recorded/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Run sealed replay" })).toBeDisabled();
    await expect(
      page.getByText(/No eligible inactive NEW_CLASS discovery candidates are available/),
    ).toBeVisible();
  });

  test("advisory diagnosis requires explicit keyboard-accessible human triage", async ({
    page,
  }, testInfo) => {
    const captured = {
      requests: [] as Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>,
    };
    await mockSession(page);
    await mockControlPlane(page, captured);
    await goto(page, "/projects/cp-1/evolution");
    await page.getByRole("button", { name: "Inspect & Triage" }).focus();
    await page.keyboard.press("Enter");
    const detail = page.getByRole("region", { name: "Evidence detail" });
    await expect(detail).toBeVisible();
    await detail.getByRole("button", { name: /Diagnose with Provider/ }).click();
    await expect(detail.getByText("Route-mocked advisory only", { exact: true })).toBeVisible();
    expect(captured.requests.some((entry) => entry.method === "PATCH")).toBe(false);
    await detail.getByRole("button", { name: /Copy Advisory to Human Triage Form/ }).click();
    await expect(detail.getByLabel("Triage Rationale & Notes")).toHaveValue(
      "Route-mocked advisory only",
    );
    await detail.getByRole("button", { name: "Save Triage", exact: true }).click();
    await expect(detail.getByRole("status")).toContainText("Triage saved");
    await page.screenshot({
      path: testInfo.outputPath("route-mocked-evidence.png"),
      fullPage: true,
    });
    const triage = captured.requests.find((entry) => entry.method === "PATCH");
    expect(triage?.body).toEqual({
      diagnosis: "ambiguous_or_insufficient",
      rationale: "Route-mocked advisory only",
    });
    await detail.getByLabel("Triage Rationale & Notes").focus();
    await page.keyboard.press("Escape");
    await expect(detail).toHaveCount(0);
    expect(captured.requests.some((entry) => /promote|activate/.test(entry.path))).toBe(false);
  });

  test("evidence read failures are not rendered as empty success", async ({ page }) => {
    const captured = { requests: [] };
    await mockSession(page);
    await mockControlPlane(page, captured, { evidenceFailure: true });
    await goto(page, "/projects/cp-1/evolution");
    await expect(page.getByRole("alert").filter({ hasText: "Evidence read denied" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry evidence read" })).toBeVisible();
    await expect(page.getByText("No evidence found")).toHaveCount(0);
  });

  test("sealed replay displays persisted blocked gates without activation", async ({
    page,
  }, testInfo) => {
    const captured = {
      requests: [] as Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>,
    };
    await mockSession(page);
    await mockControlPlane(page, captured, { readyReplay: true });
    await goto(page, "/projects/cp-1/evaluations");
    await page.getByRole("combobox", { name: "Dataset", exact: true }).selectOption(DATASET.id);
    const picker = page.getByRole("combobox", { name: "Inactive candidate" });
    await expect(picker.locator("option")).toHaveCount(2);
    await expect(picker.getByRole("option", { name: /REFUND/ })).toBeAttached();
    await picker.selectOption(DISCOVERY_CANDIDATE.id);
    await expect(page.getByRole("combobox", { name: "Decision service" })).toHaveValue("");
    await expect(page.getByRole("button", { name: "Run sealed replay" })).toBeDisabled();
    await page.getByRole("combobox", { name: "Decision service" }).selectOption(SERVICE.id);
    await page.getByRole("button", { name: "Run sealed replay" }).click();
    const result = page.getByRole("region", { name: "Replay result" });
    await expect(result.getByRole("heading")).toHaveText("Blocked — evaluation did not pass");
    await expect(result.getByText(/Simulated replay/)).toBeVisible();
    await expect(result.getByText(/BLOCKED · known regression/)).toBeVisible();
    expect(captured.requests.find((entry) => entry.method === "POST")?.body).toEqual({
      dataset_id: DATASET.id,
      candidate_id: DISCOVERY_CANDIDATE.id,
      service_id: SERVICE.id,
    });
    expect(
      captured.requests.some(
        (entry) => entry.method === "GET" && entry.path.endsWith("/workflow/discovery-candidates"),
      ),
    ).toBe(true);
    expect(
      captured.requests.some(
        (entry) => entry.method === "GET" && entry.path.endsWith("/workflow/candidates"),
      ),
    ).toBe(false);
    expect(captured.requests.some((entry) => /promote|activate/.test(entry.path))).toBe(false);
    await page.screenshot({ path: testInfo.outputPath("route-mocked-replay.png"), fullPage: true });
  });

  test("Next relay rejects unauthenticated and malformed control requests locally", async ({
    request,
  }) => {
    const anonymous = await request.get("/control/workspaces");
    expect(anonymous.status()).toBe(401);
    const malformed = await request.get("/control/not%3Aallowed", {
      headers: { authorization: `Bearer ${SESSION.token}` },
    });
    expect(malformed.status()).toBe(400);
  });

  test("verified example provenance and explicit sealing are required before replay", async ({
    page,
  }) => {
    const captured = {
      requests: [] as Array<{
        path: string;
        method: string;
        headers: Record<string, string>;
        body: unknown;
      }>,
    };
    await mockSession(page);
    await mockControlPlane(page, captured, { draftReplay: true });
    await goto(page, "/projects/cp-1/evaluations");
    await page.getByRole("combobox", { name: "Dataset", exact: true }).selectOption(DATASET.id);
    await expect(page.getByRole("button", { name: "Run sealed replay" })).toBeDisabled();
    await page.getByLabel("Observation text").fill("An independently reviewed billing request.");
    await page.getByLabel("Verified label (or UNKNOWN)").fill("billing");
    await page.getByLabel("Annotator / verified source identity").fill("Human reviewer fixture");
    await page.getByLabel("Label rationale").fill("Verified independently, not a prediction.");
    await page.getByRole("button", { name: "Add verified example", exact: true }).click();
    await expect(page.getByRole("cell", { name: "BILLING", exact: true })).toBeVisible();
    const added = captured.requests.find(
      (entry) => entry.method === "POST" && entry.path.endsWith("/examples"),
    );
    expect(added?.body).toMatchObject({
      label: "BILLING",
      source: "human",
      annotator: "Human reviewer fixture",
      split: "holdout",
      source_type: "verified_holdout",
    });
    await expect(page.getByRole("button", { name: "Seal verified dataset" })).toBeDisabled();
    await page.getByRole("checkbox", { name: /I reviewed provenance and disjoint splits/ }).check();
    await page.getByRole("button", { name: "Seal verified dataset" }).click();
    await expect(page.getByRole("heading", { name: /sealed — immutable/ })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Add verified example", exact: true }),
    ).toHaveCount(0);
  });
});
