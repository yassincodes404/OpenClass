import { test, expect } from "@playwright/test";

const project = {
  id: "11111111-1111-4111-8111-111111111111",
  slug: "saas-support",
  name: "SaaS Support",
  description: "Customer support platform",
  status: "active",
  owner_id: null,
  created_at: "2026-09-28T00:00:00Z",
  updated_at: "2026-09-28T00:00:00Z",
};

const service = {
  id: "dddddddd-1111-4111-8111-111111111111",
  project_id: project.id,
  slug: "support-routing",
  name: "Support Routing",
  description: "Routes support inquiries",
  instructions: "Classify incoming tickets into appropriate departments",
  status: "active",
  provider_override: null,
  created_at: "2026-09-28T00:00:00Z",
  updated_at: "2026-09-28T00:00:00Z",
  nodes: [
    {
      id: "eeeeeeee-1111-4111-8111-111111111111",
      name: "Root",
      instructions: "Classify incoming tickets into appropriate departments",
      choices: [
        {
          key: "BILLING",
          label: "Billing Support",
          description: "Payment and invoice questions",
        },
        {
          key: "UNKNOWN",
          label: "Unknown",
          description: "Input cannot be reliably classified",
        },
      ],
    },
  ],
};

const candidate = {
  id: "cand-1111-2222-3333-444444444444",
  project_id: project.id,
  decision_service_id: service.id,
  base_service_hash: "a".repeat(64),
  evidence_run_ids: [
    "run-1111-1111-1111-111111111111",
    "run-2222-2222-2222-222222222222",
    "run-3333-3333-3333-333333333333",
  ],
  proposal: {
    kind: "new_choice",
    key: "SUBSCRIPTION_PAUSE",
    label: "Subscription Pause",
    description: "Requests to temporarily freeze account during vacation",
    rationale: "Cluster of 3 customer tickets mentions pausing during travel",
    provider: "google-gemini",
    model: "gemini-2.5-flash",
    simulated: false,
  },
  status: "candidate",
  rejection_reason: null,
  promoted_at: null,
  created_at: "2026-09-28T01:00:00Z",
};

test("candidate proposals remain inspectable but evaluation and activation are unavailable", async ({
  page,
}) => {
  const currentCandidate = { ...candidate };
  const currentService = { ...service };

  await page.route("**/api/v1/projects/saas-support", (route) => route.fulfill({ json: project }));
  await page.route("**/api/v1/projects/saas-support/evolution/summary", (route) =>
    route.fulfill({
      json: {
        project_id: project.id,
        total_evidence: 3,
        pending_evidence: 0,
        triaged_evidence: 0,
        ready_for_evolution: 3,
        resolved_evidence: 0,
        open_cases: 0,
      },
    }),
  );
  await page.route("**/api/v1/projects/saas-support/evidence*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/projects/saas-support/evidence-cases*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/projects/saas-support/decision-services*", (route) =>
    route.fulfill({ json: [currentService] }),
  );
  await page.route("**/api/v1/projects/saas-support/candidates", (route) =>
    route.fulfill({ json: [currentCandidate] }),
  );
  await page.route(`**/api/v1/projects/saas-support/candidates/${candidate.id}`, (route) =>
    route.fulfill({ json: currentCandidate }),
  );
  let forbiddenRequests = 0;
  await page.route("**/candidates/*/evaluate", (route) => {
    forbiddenRequests += 1;
    return route.fulfill({
      status: 409,
      json: { detail: "Verified replay evaluation is not implemented" },
    });
  });
  await page.route("**/candidates/*/promote", (route) => {
    forbiddenRequests += 1;
    return route.fulfill({
      status: 409,
      json: { detail: "Verified replay evaluation is required before activation" },
    });
  });
  // 1. Visit Evolution page
  await page.goto("/projects/saas-support/evolution");
  await expect(page.locator("h2").first()).toHaveText("Evolution Inbox & Human Triage");

  // 2. Click "Choice Candidates" tab
  const candidatesTab = page.locator("button:has-text('Choice Candidates')");
  await expect(candidatesTab).toBeVisible();
  await candidatesTab.click();

  // 3. Verify candidate card displays synthesized proposal
  await expect(page.locator("text=SUBSCRIPTION_PAUSE")).toBeVisible();
  await expect(page.locator("text=Subscription Pause")).toBeVisible();
  await expect(page.locator("text=PENDING REVIEW")).toBeVisible();
  await expect(
    page.locator("text=Cluster of 3 customer tickets mentions pausing during travel"),
  ).toBeVisible();

  await expect(page.getByText("Proposals remain inactive.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Evaluation Replay" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Promote & Activate Choice" })).toBeDisabled();
  expect(forbiddenRequests).toBe(0);

  await page.route(`**/api/v1/projects/saas-support/candidates/${candidate.id}/reject`, (route) => {
    expect(route.request().postDataJSON().reason).toBe("Insufficient verified evidence");
    Object.assign(currentCandidate, {
      status: "rejected",
      rejection_reason: "Insufficient verified evidence",
    });
    return route.fulfill({ json: currentCandidate });
  });
  page.once("dialog", (dialog) => dialog.accept("Insufficient verified evidence"));
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText("rejected", { exact: true })).toBeVisible();
});
