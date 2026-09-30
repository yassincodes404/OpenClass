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

const summary = {
  project_id: project.id,
  pending_evidence: 1,
  triaged_evidence: 1,
  ready_for_evolution: 1,
  resolved_evidence: 0,
  dismissed_evidence: 0,
  total_evidence: 3,
  open_cases: 1,
  total_cases: 1,
};

const evidenceItems = [
  {
    id: "aaaaaaaa-1111-4111-8111-111111111111",
    project_id: project.id,
    raw_event_id: "bbbbbbbb-1111-4111-8111-111111111111",
    decision_run_id: "cccccccc-1111-4111-8111-111111111111",
    decision_service_id: "dddddddd-1111-4111-8111-111111111111",
    decision_node_id: "eeeeeeee-1111-4111-8111-111111111111",
    evidence_case_id: null,
    trigger_type: "semantic_unknown",
    status: "pending",
    diagnosis: null,
    diagnosis_rationale: null,
    selected_choice: "UNKNOWN",
    probabilities_snapshot: { SUPPORT: 0.1, UNKNOWN: 0.9 },
    unknown_probability: 0.9,
    margin: 0.8,
    supervision_outcome: "UNKNOWN",
    supervision_reason: "High unknown probability",
    provider: "gemini",
    model: "gemini-2.5-flash",
    execution_mode: "mock",
    source: "automatic",
    human_note: "Can we get shared workspaces for our team?",
    corrected_choice: null,
    created_at: "2026-09-28T00:10:00Z",
    resolved_at: null,
  },
  {
    id: "aaaaaaaa-2222-4222-8222-222222222222",
    project_id: project.id,
    raw_event_id: "bbbbbbbb-2222-4222-8222-222222222222",
    decision_run_id: "cccccccc-2222-4222-8222-222222222222",
    decision_service_id: "dddddddd-1111-4111-8111-111111111111",
    decision_node_id: "eeeeeeee-1111-4111-8111-111111111111",
    evidence_case_id: "ffffffff-1111-4111-8111-111111111111",
    trigger_type: "low_trust",
    status: "triaged",
    diagnosis: "decision_space",
    diagnosis_rationale: "Enterprise SSO feature request",
    selected_choice: "SUPPORT",
    probabilities_snapshot: { SUPPORT: 0.52, UNKNOWN: 0.48 },
    unknown_probability: 0.48,
    margin: 0.04,
    supervision_outcome: "REVIEW",
    supervision_reason: "Low confidence margin",
    provider: "laya",
    model: "local-fast-v1",
    execution_mode: "daemon",
    source: "automatic",
    human_note: "Need SAML SSO for enterprise compliance",
    corrected_choice: null,
    created_at: "2026-09-28T00:15:00Z",
    resolved_at: null,
  },
];

const cases = [
  {
    id: "ffffffff-1111-4111-8111-111111111111",
    project_id: project.id,
    title: "Enterprise Feature Gaps",
    description: "Inquiries regarding SSO and data governance",
    status: "pending",
    decision_service_id: "dddddddd-1111-4111-8111-111111111111",
    created_at: "2026-09-28T00:20:00Z",
    updated_at: "2026-09-28T00:20:00Z",
  },
];

test("evolution inbox displays summary, filters evidence, and enables AI diagnosis and triage", async ({
  page,
}) => {
  await page.route("**/api/v1/projects/saas-support", (route) => route.fulfill({ json: project }));
  await page.route("**/api/v1/projects/saas-support/evolution/summary", (route) =>
    route.fulfill({ json: summary }),
  );
  await page.route("**/api/v1/projects/saas-support/evidence?*", (route) =>
    route.fulfill({ json: evidenceItems }),
  );
  await page.route("**/api/v1/projects/saas-support/evidence", (route) =>
    route.fulfill({ json: evidenceItems }),
  );
  await page.route("**/api/v1/projects/saas-support/evidence-cases*", (route) =>
    route.fulfill({ json: cases }),
  );
  await page.route(`**/api/v1/projects/saas-support/evidence/${evidenceItems[0].id}`, (route) =>
    route.fulfill({ json: evidenceItems[0] }),
  );

  // Mock AI Diagnose endpoint
  await page.route(
    `**/api/v1/projects/saas-support/evidence/${evidenceItems[0].id}/ai-diagnose`,
    (route) =>
      route.fulfill({
        json: {
          diagnosis: "decision_space",
          rationale:
            "Customer requests collaborative workspace capabilities not present in choices.",
          confidence: 0.95,
          recommended_action: "Expand choice set with TEAM_WORKSPACE option.",
          provider: "gemini",
          model: "gemini-2.5-flash",
          simulated: false,
        },
      }),
  );

  // Mock Triage endpoint
  await page.route(
    `**/api/v1/projects/saas-support/evidence/${evidenceItems[0].id}/triage`,
    (route) =>
      route.fulfill({
        json: {
          ...evidenceItems[0],
          status: "triaged",
          diagnosis: "decision_space",
          diagnosis_rationale: "Missing shared workspaces capability",
        },
      }),
  );

  // Mock Transition endpoint
  await page.route(
    `**/api/v1/projects/saas-support/evidence/${evidenceItems[0].id}/transition`,
    (route) =>
      route.fulfill({
        json: {
          ...evidenceItems[0],
          status: "ready_for_evolution",
        },
      }),
  );

  await page.goto("/projects/saas-support/evolution");

  // Verify Heading & Overview
  await expect(page.getByRole("heading", { name: "Evolution Inbox & Human Triage" })).toBeVisible();

  // Verify Metric Counters
  await expect(page.getByText("Total Evidence")).toBeVisible();
  await expect(page.getByText("Pending Triage")).toBeVisible();
  await expect(page.locator(".counter-label", { hasText: "Ready for Evolution" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ready for Evolution" })).toBeVisible();

  // Verify Evidence Item is present
  await expect(page.getByText("Can we get shared workspaces for our team?")).toBeVisible();

  // Inspect the item
  await page.getByRole("button", { name: "Inspect & Triage" }).first().click();

  // Verify Inspection drawer opens
  await expect(page.getByText("Inspection & Human Triage")).toBeVisible();
  await expect(page.getByText("Execution Context")).toBeVisible();
  await expect(page.getByText("Probability Distribution")).toBeVisible();

  // Run AI Failure Diagnosis with Gemini
  const diagnoseBtn = page.getByRole("button", { name: /Diagnose with Provider/ });
  await expect(diagnoseBtn).toBeVisible();
  await diagnoseBtn.click();

  // Verify AI Diagnosis output appears
  await expect(
    page.getByText(
      "Customer requests collaborative workspace capabilities not present in choices.",
    ),
  ).toBeVisible();
  await expect(page.getByText("Confidence: 95%")).toBeVisible();

  // Copy AI Advisory to Human Triage Form
  const copyBtn = page.getByRole("button", { name: "✓ Copy Advisory to Human Triage Form" });
  await expect(copyBtn).toBeVisible();
  await copyBtn.click();

  // Save Triage
  await page.getByRole("button", { name: "Save Triage" }).click();
  await expect(page.getByText("Triage saved successfully!")).toBeVisible();

  // Mark Ready for Evolution
  const evolveBtn = page.getByRole("button", { name: "🚀 Mark Ready for Evolution" });
  await expect(evolveBtn).toBeVisible();
  await evolveBtn.click();

  // Close drawer
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Inspection & Human Triage")).not.toBeVisible();
});
