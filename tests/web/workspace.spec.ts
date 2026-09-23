import { test, expect } from "@playwright/test";

test("shows actual API decisions, unknown explanations and recoverable errors", async ({
  page,
}, testInfo) => {
  await page.route("**/health/ready", (route) => route.fulfill({ json: { status: "ready" } }));
  await page.route("**/api/v1/classifiers", (route) =>
    route.fulfill({ json: [{ id: "fixture", slug: "support-intent", name: "Support intent" }] }),
  );
  let calls = 0;
  await page.route("**/api/v1/classifiers/support-intent/classify", async (route) => {
    calls++;
    const observation = route.request().postDataJSON().observation;
    if (calls === 3)
      return route.fulfill({ status: 503, json: { detail: "Database unavailable" } });
    const known = observation === "I was charged twice";
    await route.fulfill({
      json: {
        id: "run",
        ontology_version_id: "v1",
        selected_class: known ? "billing" : null,
        decision: {
          provider: "mock",
          model: "lexical-demo-v1",
          probabilities: {},
          unknown_probability: known ? 0.05 : 0.95,
        },
        novelty: {
          state: known ? "known" : "likely_novel",
          score: known ? 0.05 : 0.95,
          reasons: [known ? "known_class_supported" : "strong_unknown_probability"],
        },
      },
    });
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Server ready");
  await page.getByRole("button", { name: "Classify observation" }).click();
  await expect(page.getByRole("heading", { name: "billing", exact: true })).toBeVisible();
  await page.getByLabel("Observation", { exact: true }).fill("Cancel my plan");
  await page.getByRole("button", { name: "Classify observation" }).click();
  await expect(page.getByRole("heading", { name: "UNKNOWN", exact: true })).toBeVisible();
  await expect(page.getByText("strong unknown probability", { exact: true })).toBeVisible();
  await expect(page.getByText(/not yet a new-class proposal/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("workspace.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole("button", { name: "Classify observation" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("503");
  await expect(page.getByRole("button", { name: "Classify observation" })).toBeEnabled();
});

test("empty workspace explains setup and cannot submit", async ({ page }) => {
  await page.route("**/health/ready", (route) => route.fulfill({ json: { status: "ready" } }));
  await page.route("**/api/v1/classifiers", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Server ready");
  await expect(page.getByText(/Create your first classifier/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Classify observation" })).toBeDisabled();
});

test("supervisor review stays advisory and recoverable", async ({ page }) => {
  await page.route("**/health/ready", (route) => route.fulfill({ json: { status: "ready" } }));
  await page.route("**/api/v1/classifiers", (route) =>
    route.fulfill({ json: [{ id: "fixture", slug: "support-intent", name: "Support intent" }] }),
  );
  await page.route("**/api/v1/classifiers/support-intent/classify", (route) =>
    route.fulfill({
      json: {
        id: "run-1",
        ontology_version_id: "v1",
        selected_class: null,
        decision: {
          provider: "mock",
          model: "lexical-demo-v1",
          probabilities: {},
          unknown_probability: 0.95,
        },
        novelty: { state: "likely_novel", score: 0.95, reasons: ["strong_unknown_probability"] },
      },
    }),
  );
  let reviews = 0;
  await page.route("**/api/v1/classifiers/support-intent/runs/run-1/reviews", async (route) => {
    reviews++;
    if (reviews === 2)
      return route.fulfill({ status: 502, json: { detail: "Supervisor provider failed" } });
    await new Promise((resolve) => setTimeout(resolve, 300));
    return route.fulfill({
      json: {
        id: "review-1",
        classifier_id: "fixture",
        classification_run_id: "run-1",
        ontology_version_id: "v1",
        trigger: "manual",
        created_at: "2026-01-01T00:00:00Z",
        result: {
          provider: "mock-supervisor",
          model: "advisory-demo-v1",
          finding: "possible_missing_class",
          confidence: 0.82,
          recommendation: "collect_more_evidence",
          rationale: "Simulated advisory review: the run selected no class.",
          suspected_class: null,
          proposed_class: null,
          proposed_instruction: null,
          provider_metadata: { simulated: true },
        },
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Classify observation" }).click();
  await expect(page.getByRole("heading", { name: "UNKNOWN", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review with Supervisor" }).click();
  await expect(page.getByRole("button", { name: "Reviewing…" })).toBeDisabled();
  await expect(page.getByText("possible missing class", { exact: true })).toBeVisible();
  await expect(page.getByText("collect more evidence", { exact: true })).toBeVisible();
  await expect(page.getByText(/never changes the classification/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "UNKNOWN", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review with Supervisor" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("502");
  await expect(page.getByRole("button", { name: "Review with Supervisor" })).toBeEnabled();
});

for (const simulated of [true, false]) {
  test(`delayed review locks its run and labels simulation=${simulated}`, async ({ page }) => {
    await page.route("**/health/ready", (route) => route.fulfill({ json: { status: "ready" } }));
    await page.route("**/api/v1/classifiers", (route) =>
      route.fulfill({
        json: [
          { id: "fixture", slug: "support-intent", name: "Support intent" },
          { id: "other", slug: "other", name: "Other" },
        ],
      }),
    );
    let runs = 0;
    await page.route("**/classify", (route) =>
      route.fulfill({
        json: {
          id: `run-${++runs}`,
          ontology_version_id: "v1",
          selected_class: "billing",
          decision: { provider: "mock" },
          novelty: { state: "known", score: 0.05, reasons: [] },
        },
      }),
    );
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/runs/run-1/reviews", async (route) => {
      await gate;
      await route.fulfill({
        json: {
          id: "review-1",
          classification_run_id: "run-1",
          result: {
            provider: "test-supervisor",
            finding: "no_issue",
            confidence: 0.8,
            recommendation: "none",
            rationale: "Review for run A",
            provider_metadata: { simulated },
          },
        },
      });
    });
    await page.goto("/");
    const classify = page.getByRole("button", { name: "Classify observation" });
    await classify.click();
    await page.getByRole("button", { name: "Review with Supervisor" }).click();
    await expect(page.getByRole("button", { name: "Reviewing…" })).toBeDisabled();
    await expect(page.getByLabel("Classifier", { exact: true })).toBeDisabled();
    await expect(page.getByLabel("Observation", { exact: true })).toBeDisabled();
    await expect(classify).toBeDisabled();
    release();
    await expect(page.getByText("Review for run A")).toBeVisible();
    await expect(
      page.getByText(
        simulated
          ? "Simulated advisory finding · a review never changes the classification"
          : "Advisory finding · a review never changes the classification",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByLabel("Observation", { exact: true }).fill("second observation");
    await classify.click();
    await expect(page.getByRole("button", { name: "Review with Supervisor" })).toBeEnabled();
    await expect(page.getByText("Review for run A")).toHaveCount(0);
    // Even an incorrectly associated response must not appear under run B.
    await page.route("**/runs/run-2/reviews", (route) =>
      route.fulfill({
        json: {
          classification_run_id: "run-1",
          result: { rationale: "Stale finding" },
        },
      }),
    );
    await page.getByRole("button", { name: "Review with Supervisor" }).click();
    await expect(page.getByRole("button", { name: "Review with Supervisor" })).toBeEnabled();
    await expect(page.getByText("Stale finding")).toHaveCount(0);
    let releaseLate!: () => void;
    const lateGate = new Promise<void>((resolve) => {
      releaseLate = resolve;
    });
    await page.route("**/runs/run-2/reviews", async (route) => {
      await lateGate;
      await route.fulfill({
        json: {
          classification_run_id: "run-2",
          result: {
            finding: "no_issue",
            confidence: 0.8,
            recommendation: "none",
            rationale: "Late run B finding",
            provider_metadata: { simulated },
          },
        },
      });
    });
    await page.getByRole("button", { name: "Review with Supervisor" }).click();
    await expect(page.getByRole("button", { name: "Reviewing…" })).toBeDisabled();
    // Bypass the interaction lock to exercise stale-response protection independently.
    const selector = page.getByLabel("Classifier", { exact: true });
    await selector.evaluate((element: HTMLSelectElement) => {
      element.disabled = false;
    });
    await selector.selectOption("other");
    releaseLate();
    await expect(classify).toBeEnabled();
    await classify.click();
    await expect(page.getByRole("button", { name: "Review with Supervisor" })).toBeEnabled();
    await expect(page.getByText("Late run B finding")).toHaveCount(0);
  });
}
