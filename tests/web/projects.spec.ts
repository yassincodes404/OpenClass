import { test, expect } from "@playwright/test";

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

test("projects list shows an empty state before anything exists", async ({ page }) => {
  await page.route("**/api/v1/projects", (route) => route.fulfill({ json: [] }));
  await page.goto("/projects");
  await expect(page.getByRole("navigation", { name: "Portal navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Workspace" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Projects" })).toHaveClass(/active/);
  await expect(page.getByText("No projects yet.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
});

test("create project posts to the public API and shows the new project", async ({ page }) => {
  let created = false;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "POST") {
      created = true;
      const body = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { ...projectResponse, name: body.name, description: body.description },
      });
    }
    return route.fulfill({ json: created ? [projectResponse] : [] });
  });
  await page.goto("/projects");
  await page.getByLabel("Name").fill("GymHolic Intelligence");
  await page.getByLabel("Description").fill("Customer intelligence experiment");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name: /GymHolic Intelligence/ })).toBeVisible();
  expect(created).toBe(true);
});

test("create project surfaces validation errors without calling the API", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/projects", (route) => {
    calls++;
    return route.fulfill({ json: [] });
  });
  let created = 0;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "POST") {
      created++;
      return route.fulfill({ status: 201, json: {} });
    }
    calls++;
    return route.fulfill({ json: [] });
  });
  await page.goto("/projects");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText("Project name is required")).toBeVisible();
  expect(created).toBe(0); // the create was blocked client-side
});

test("project overview shows persisted metadata and real counters", async ({ page }) => {
  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.route("**/api/v1/projects/gymholic-intelligence/summary", (route) =>
    route.fulfill({
      json: {
        events: 0,
        decision_runs: 0,
        unknowns: 0,
        active_policy: null,
        pending_candidates: 0,
        audit_events: 1,
      },
    }),
  );
  await page.goto("/projects/gymholic-intelligence");
  await expect(page.getByRole("heading", { name: "GymHolic Intelligence" })).toBeVisible();
  await expect(page.getByText("Customer intelligence experiment")).toBeVisible();
  for (const label of ["Events", "Decision runs", "Unknowns", "Pending candidates"]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("—", { exact: true })).toBeVisible();
});

test("shell sections that are not built show an honest unavailable state", async ({ page }) => {
  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.goto("/projects/gymholic-intelligence/workflows");
  await expect(page.getByRole("heading", { name: "workflows" })).toBeVisible();
  await expect(page.getByText("Not available in this build yet.")).toBeVisible();
});

test("settings edit persists through the public API", async ({ page }) => {
  let patched: unknown;
  await page.route("**/api/v1/projects/gymholic-intelligence", async (route) => {
    if (route.request().method() === "PATCH") {
      patched = route.request().postDataJSON();
      return route.fulfill({
        json: { ...projectResponse, description: "updated description" },
      });
    }
    return route.fulfill({ json: projectResponse });
  });
  await page.goto("/projects/gymholic-intelligence/settings");
  await page.getByLabel("Description").fill("updated description");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Saved. Changes are persisted server-side.")).toBeVisible();
  expect(patched).toEqual({
    name: "GymHolic Intelligence",
    description: "updated description",
  });
});

test("server errors are recoverable and reported", async ({ page }) => {
  await page.route("**/api/v1/projects", (route) =>
    route.fulfill({ status: 503, json: { detail: "Database unavailable" } }),
  );
  await page.goto("/projects");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("503");
});
