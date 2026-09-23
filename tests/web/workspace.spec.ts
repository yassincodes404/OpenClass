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
