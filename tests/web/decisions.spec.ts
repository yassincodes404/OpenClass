import { test, expect, mockWorkspaceProject, WORKFLOW_ROUTE } from "./fixtures/workspace";

const projectResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  slug: "gymholic-intelligence",
  name: "GymHolic Intelligence",
  description: "Customer intelligence experiment",
  status: "active",
  owner_id: null,
  created_at: "2026-09-25T10:00:00Z",
  updated_at: "2026-09-25T10:00:00Z",
};

const providerStatusResponse = {
  default_provider: "laya",
  laya: {
    status: "ready",
    mode: "local_engine",
    daemon_status: "unavailable",
    endpoint: "http://127.0.0.1:8000",
    model: "laya-modernbert-v1",
    default: true,
  },
  jev: {
    status: "not_configured",
    model: "typesafe-ai/jev",
    configured: false,
    default: false,
  },
};

const sampleService = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: projectResponse.id,
  slug: "support-routing",
  name: "Support Routing",
  description: "Route customer tickets by urgency",
  instructions: "Classify incoming ticket by urgency and type",
  nodes: [
    {
      id: "33333333-3333-4333-8333-333333333333",
      name: "default",
      instructions: "Classify incoming ticket by urgency and type",
      choices: [
        { key: "URGENT", label: "Urgent Support", description: "Equipment failure or safety" },
        { key: "GENERAL", label: "General Inquiry", description: "Hours, membership inquiry" },
        { key: "UNKNOWN", label: "Unknown", description: "Permanent semantic fallback" },
      ],
    },
  ],
  status: "active",
  provider_override: null,
  created_at: "2026-09-26T12:00:00Z",
  updated_at: "2026-09-26T12:00:00Z",
};

const sampleRun = {
  id: "44444444-4444-4444-8444-444444444444",
  project_id: projectResponse.id,
  raw_event_id: "55555555-5555-4555-8555-555555555555",
  decision_service_id: sampleService.id,
  decision_node_id: "33333333-3333-4333-8333-333333333333",
  provider: "laya",
  model: "laya-router",
  execution_mode: "deterministic_test_fallback",
  real_inference: false,
  selected_choice: "URGENT",
  probabilities: {
    URGENT: 0.88,
    GENERAL: 0.07,
    UNKNOWN: 0.05,
  },
  top_probability: 0.88,
  second_probability: 0.07,
  margin: 0.81,
  unknown_probability: 0.05,
  supervision_outcome: "REVIEW",
  supervision_reason:
    "Laya provider operates under research calibration (conservative supervision)",
  latency_ms: 14.2,
  input_snapshot: {
    id: "55555555-5555-4555-8555-555555555555",
    content: "Treadmill 4 belt snapped and stopped abruptly with member on it!",
    metadata: { gym_location: "downtown" },
  },
  instructions_snapshot: "Classify incoming ticket by urgency and type",
  choices_snapshot: [
    { key: "URGENT", label: "Urgent Support", description: "Equipment failure or safety" },
    { key: "GENERAL", label: "General Inquiry", description: "Hours, membership inquiry" },
    { key: "UNKNOWN", label: "Unknown", description: "Permanent semantic fallback" },
  ],
  provider_metadata: { local: true, engine: "laya-fallback" },
  created_at: "2026-09-26T12:05:00Z",
};

test.beforeEach(async ({ page }) => {
  await mockWorkspaceProject(page, projectResponse);
});

test("decisions page renders empty states and provider banner", async ({ page }) => {
  await page.route(`${WORKFLOW_ROUTE}`, (route) => route.fulfill({ json: projectResponse }));
  await page.route(`${WORKFLOW_ROUTE}/decision-services*`, (route) => route.fulfill({ json: [] }));
  await page.route(`${WORKFLOW_ROUTE}/runs*`, (route) => route.fulfill({ json: [] }));
  await page.route(`${WORKFLOW_ROUTE}/provider-status`, (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );

  await page.goto("/projects/gymholic-intelligence/decisions");

  await expect(page.getByRole("heading", { name: "Decision Services" })).toBeVisible();
  await expect(page.getByTestId("provider-banner")).toBeVisible();
  await expect(page.getByTestId("empty-services")).toBeVisible();
  await expect(page.getByTestId("empty-runs")).toBeVisible();
});

test("create decision service modal shows locked UNKNOWN choice and submits", async ({ page }) => {
  const servicesList: any[] = [];

  await page.route(`${WORKFLOW_ROUTE}`, (route) => route.fulfill({ json: projectResponse }));
  await page.route(`${WORKFLOW_ROUTE}/runs*`, (route) => route.fulfill({ json: [] }));
  await page.route(`${WORKFLOW_ROUTE}/provider-status`, (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );
  await page.route(`${WORKFLOW_ROUTE}/decision-services*`, async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      const newService = {
        id: "66666666-6666-4666-8666-666666666666",
        project_id: projectResponse.id,
        slug: "lead-routing",
        name: body.name,
        description: body.description || "",
        instructions: body.instructions,
        nodes: [
          {
            id: "77777777-7777-4777-8777-777777777777",
            name: "default",
            instructions: body.instructions,
            choices: [
              ...body.choices,
              { key: "UNKNOWN", label: "Unknown", description: "Permanent semantic fallback" },
            ],
          },
        ],
        status: "active",
        provider_override: body.provider_override || null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      servicesList.push(newService);
      return route.fulfill({ status: 201, json: newService });
    }
    return route.fulfill({ json: servicesList });
  });

  await page.goto("/projects/gymholic-intelligence/decisions");

  await page.getByTestId("create-service-btn").click();

  // Verify modal is open and permanent UNKNOWN notice is present
  await expect(page.getByRole("heading", { name: "Create Decision Service" })).toBeVisible();
  await expect(page.getByText("UNKNOWN", { exact: true })).toBeVisible();
  await expect(page.getByText("Permanent semantic fallback", { exact: false })).toBeVisible();
  await expect(page.getByText("Locked")).toBeVisible();

  // Fill in service name
  await page.getByLabel("Service Name").fill("Lead Routing");
  await page
    .getByLabel("Instructions / Classification Prompt")
    .fill("Route inquiries to sales or support");
  await page.getByTestId("submit-service-btn").click();

  // Verify service card appears on the page
  await expect(page.getByTestId("service-card-lead-routing")).toBeVisible();
  await expect(
    page
      .getByTestId("service-card-lead-routing")
      .getByRole("heading", { name: "Lead Routing", exact: true }),
  ).toBeVisible();
});

test("decision runs explorer displays runs table and inspect drawer", async ({ page }) => {
  await page.route(`${WORKFLOW_ROUTE}`, (route) => route.fulfill({ json: projectResponse }));
  await page.route(`${WORKFLOW_ROUTE}/decision-services*`, (route) =>
    route.fulfill({ json: [sampleService] }),
  );
  await page.route(`${WORKFLOW_ROUTE}/runs*`, (route) => route.fulfill({ json: [sampleRun] }));
  await page.route(`${WORKFLOW_ROUTE}/provider-status`, (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );

  await page.goto("/projects/gymholic-intelligence/decisions");

  // Verify runs table
  await expect(page.getByTestId("decision-runs-table")).toBeVisible();
  await expect(
    page
      .getByTestId("run-row-44444444-4444-4444-8444-444444444444")
      .getByText("URGENT", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("88.0%")).toBeVisible();
  await expect(page.getByText("+81.0%")).toBeVisible();
  await expect(page.getByText("REVIEW")).toBeVisible();
  await expect(page.getByText("laya · deterministic_test_fallback")).toBeVisible();
  await expect(page.getByText("⚠ Fallback")).toBeVisible();

  // Click Inspect
  await page.getByTestId("inspect-run-44444444-4444-4444-8444-444444444444").click({ force: true });

  // Verify Inspector Drawer content
  await expect(page.getByRole("heading", { name: "Decision Run Details" })).toBeVisible();
  await expect(page.getByText("Run ID: 44444444-4444-4444-8444-444444444444")).toBeVisible();
  await expect(
    page.getByText("Laya provider operates under research calibration (conservative supervision)"),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Probability Distribution" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Input Snapshot (Observation)" })).toBeVisible();
});

test("data page selects raw events and runs intelligence to create decision runs", async ({
  page,
}) => {
  const events = [
    {
      id: "55555555-5555-4555-8555-555555555555",
      project_id: projectResponse.id,
      source_type: "text",
      content: "Treadmill stopped working",
      metadata: {},
      created_at: "2026-09-26T10:00:00Z",
    },
  ];

  await page.route(`${WORKFLOW_ROUTE}`, (route) => route.fulfill({ json: projectResponse }));
  await page.route(`${WORKFLOW_ROUTE}/events*`, (route) => route.fulfill({ json: events }));
  await page.route(`${WORKFLOW_ROUTE}/decision-services*`, (route) =>
    route.fulfill({ json: [sampleService] }),
  );
  await page.route(`${WORKFLOW_ROUTE}/provider-status`, (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );
  await page.route(
    `${WORKFLOW_ROUTE}/decision-services/22222222-2222-4222-8222-222222222222/runs`,
    async (route) => {
      return route.fulfill({ status: 201, json: [sampleRun] });
    },
  );

  await page.goto("/projects/gymholic-intelligence/data");

  // Check the select all checkbox
  await page.getByTestId("select-all-events").check({ force: true });

  // Verify action bar appeared
  await expect(page.getByTestId("run-intelligence-bar")).toBeVisible();
  await expect(page.getByText("1 event selected")).toBeVisible();

  // Click Run Intelligence
  await page.getByTestId("run-intelligence-btn").click({ force: true });

  // Verify success banner and link to Decisions
  await expect(page.getByTestId("intel-success-banner")).toBeVisible();
  await expect(page.getByRole("link", { name: "View Runs in Decisions →" })).toBeVisible();
});
