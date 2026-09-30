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

test("data page shows empty state and decision engine banner", async ({ page }) => {
  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.route("**/api/v1/projects/gymholic-intelligence/events*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/providers/status", (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );

  await page.goto("/projects/gymholic-intelligence/data");

  await expect(page.getByRole("heading", { name: "Ingest Raw Data" })).toBeVisible();
  await expect(page.getByText("Laya (Local ModernBERT)")).toBeVisible();
  await expect(
    page.getByText("No raw events ingested yet. Paste text, JSON, or CSV above to begin."),
  ).toBeVisible();
});

test("ingest text event posts through public SDK route and displays in table", async ({ page }) => {
  const eventsList: any[] = [];

  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.route("**/api/v1/providers/status", (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );
  await page.route("**/api/v1/projects/gymholic-intelligence/events*", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      const newEvt = {
        id: "evt-text-1111",
        project_id: projectResponse.id,
        source_type: body.source_type || "text",
        content: body.content,
        metadata: body.metadata || {},
        created_at: new Date().toISOString(),
      };
      eventsList.unshift(newEvt);
      return route.fulfill({ status: 201, json: newEvt });
    }
    return route.fulfill({ json: eventsList });
  });

  await page.goto("/projects/gymholic-intelligence/data");

  const textarea = page.getByLabel("Event content input");
  await textarea.fill("User reports gym locker PIN reset failure");
  await page.getByRole("button", { name: /Ingest TEXT Event/i }).click();

  await expect(page.getByText("1 event ingested successfully.")).toBeVisible();
  await expect(page.getByText("User reports gym locker PIN reset failure")).toBeVisible();
  await expect(page.getByText("text", { exact: true })).toBeVisible();
});

test("ingest JSON events batch posts and displays multiple rows", async ({ page }) => {
  const eventsList: any[] = [];

  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.route("**/api/v1/providers/status", (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );
  await page.route("**/api/v1/projects/gymholic-intelligence/events/batch", async (route) => {
    const body = route.request().postDataJSON();
    const created = body.items.map((item: any, i: number) => ({
      id: `evt-json-${i + 1}`,
      project_id: projectResponse.id,
      source_type: "json",
      content: item.content,
      metadata: item.metadata || {},
      created_at: new Date().toISOString(),
    }));
    eventsList.push(...created);
    return route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/v1/projects/gymholic-intelligence/events*", (route) =>
    route.fulfill({ json: eventsList }),
  );

  await page.goto("/projects/gymholic-intelligence/data");

  await page.getByRole("tab", { name: "Paste JSON" }).click();
  const textarea = page.getByLabel("Event content input");
  await textarea.fill(
    JSON.stringify([
      { content: "Invoice #1002 payment overdue", metadata: { customer: "c-1" } },
      { content: "Membership upgraded to Platinum", metadata: { customer: "c-2" } },
    ]),
  );

  await page.getByRole("button", { name: /Ingest JSON Events/i }).click();

  await expect(page.getByText("2 events ingested successfully.")).toBeVisible();
  await expect(page.getByText("Invoice #1002 payment overdue")).toBeVisible();
  await expect(page.getByText("Membership upgraded to Platinum")).toBeVisible();
});

test("inspecting an event opens the detail dialog and displays metadata", async ({ page }) => {
  const sampleEvent = {
    id: "evt-inspect-42",
    project_id: projectResponse.id,
    source_type: "text",
    content: "Detailed observation regarding subscription charge anomaly",
    metadata: { environment: "production", error_code: "CHARGE_ERR_42" },
    created_at: "2026-09-26T12:00:00Z",
  };

  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );
  await page.route("**/api/v1/providers/status", (route) =>
    route.fulfill({ json: providerStatusResponse }),
  );
  await page.route("**/api/v1/projects/gymholic-intelligence/events*", (route) =>
    route.fulfill({ json: [sampleEvent] }),
  );

  await page.goto("/projects/gymholic-intelligence/data");

  await expect(
    page.getByText("Detailed observation regarding subscription charge anomaly"),
  ).toBeVisible();
  const inspectBtn = page.getByRole("button", { name: "Inspect" });
  await inspectBtn.scrollIntoViewIfNeeded();
  await inspectBtn.click({ force: true });

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("CHARGE_ERR_42")).toBeVisible();
  await expect(dialog.getByText("evt-inspect-42")).toBeVisible();

  await dialog.getByRole("button", { name: "Close dialog" }).click({ force: true });
  await expect(dialog).not.toBeVisible();
});
