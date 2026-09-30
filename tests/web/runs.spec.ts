import { test, expect } from "@playwright/test";

const project = {
  id: "11111111-1111-4111-8111-111111111111",
  slug: "support-demo",
  name: "Support Demo",
  description: "",
  status: "active",
  owner_id: null,
  created_at: "2026-09-27T10:00:00Z",
  updated_at: "2026-09-27T10:00:00Z",
};

const run = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: project.id,
  raw_event_id: "33333333-3333-4333-8333-333333333333",
  decision_service_id: "44444444-4444-4444-8444-444444444444",
  decision_node_id: "55555555-5555-4555-8555-555555555555",
  provider: "mock",
  model: "lexical-demo-v1",
  execution_mode: "mock",
  real_inference: false,
  selected_choice: "BILLING",
  probabilities: { BILLING: 0.95, UNKNOWN: 0.05 },
  top_probability: 0.95,
  second_probability: 0.05,
  margin: 0.9,
  unknown_probability: 0.05,
  supervision_outcome: "TRUSTED",
  supervision_reason: "Decision margin threshold satisfied",
  latency_ms: 4.2,
  input_snapshot: { content: "billing help needed" },
  instructions_snapshot: "Route support requests",
  choices_snapshot: [
    { key: "BILLING", label: "Billing", description: "Billing issues" },
    { key: "UNKNOWN", label: "Unknown", description: "Fallback" },
  ],
  provider_metadata: { simulated: true },
  created_at: "2026-09-27T10:01:00Z",
};

test("runs remain inspectable after a reload and filters use loaded history", async ({ page }) => {
  let detailCalls = 0;
  await page.route("**/api/v1/projects/support-demo", (route) => route.fulfill({ json: project }));
  await page.route("**/api/v1/projects/support-demo/runs?*", (route) =>
    route.fulfill({
      json: [
        run,
        {
          ...run,
          id: "66666666-6666-4666-8666-666666666666",
          selected_choice: "UNKNOWN",
          supervision_outcome: "UNKNOWN",
        },
      ],
    }),
  );
  await page.route(`**/api/v1/projects/support-demo/runs/${run.id}`, (route) => {
    detailCalls += 1;
    return route.fulfill({ json: run });
  });

  await page.goto("/projects/support-demo/runs");
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  await page.getByLabel("Choice").selectOption("BILLING");
  await expect(page.getByRole("row")).toHaveCount(2);
  await page.getByRole("button", { name: `Inspect run ${run.id}` }).click();
  await expect(page.getByRole("region", { name: "Run details" })).toContainText(
    "billing help needed",
  );
  await expect(page.getByRole("region", { name: "Run details" })).toContainText("Simulated");
  await expect(page.getByRole("region", { name: "Run details" })).toContainText("95.0%");
  expect(detailCalls).toBe(1);

  await page.reload();
  await expect(page.getByRole("row")).toHaveCount(3);
  await page.getByRole("button", { name: `Inspect run ${run.id}` }).click();
  await expect(page.getByRole("region", { name: "Run details" })).toContainText(run.id);
  expect(detailCalls).toBe(2);
});

test("run history reports API failure and offers retry", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/v1/projects/support-demo", (route) => route.fulfill({ json: project }));
  await page.route("**/api/v1/projects/support-demo/runs?*", (route) => {
    attempts += 1;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
      : route.fulfill({ json: [run] });
  });
  await page.goto("/projects/support-demo/runs");
  await expect(page.locator(".form-error[role=alert]")).toContainText("Could not load runs");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("billing help needed")).toBeVisible();
});
