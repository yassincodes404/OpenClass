import { test, expect } from "@playwright/test";

const projectResponse = {
  id: "00000000-0000-0000-0000-000000000001",
  slug: "gymholic-intelligence",
  name: "GymHolic Intelligence",
  description: "Customer intelligence platform",
  status: "active",
  owner_id: null,
  created_at: "2026-04-18T10:00:00Z",
  updated_at: "2026-04-18T10:00:00Z",
};

test("integrations page displays metrics, connects new MCP server, and shows unsupported connectivity checks", async ({
  page,
}) => {
  let integrationsList: Array<{
    id: string;
    project_id: string;
    name: string;
    type: string;
    status: string;
    endpoint: string | null;
    secret_ref: string | null;
    capabilities: string[];
    latency_ms: number | null;
    last_health_check: string | null;
    error_message: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  }> = [];

  await page.route("**/api/v1/projects/gymholic-intelligence", (route) =>
    route.fulfill({ json: projectResponse }),
  );

  await page.route("**/api/v1/projects/gymholic-intelligence/integrations", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: integrationsList });
    }
    if (route.request().method() === "POST") {
      const data = route.request().postDataJSON();
      const created = {
        id: "int-1111",
        project_id: projectResponse.id,
        name: data.name,
        type: data.type,
        status: "pending",
        endpoint: data.endpoint || null,
        secret_ref: data.secret_ref || null,
        capabilities: data.capabilities || [],
        latency_ms: null,
        last_health_check: null,
        error_message: null,
        metadata: data.metadata || {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      integrationsList.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    return route.fulfill({ status: 404 });
  });

  await page.route(
    "**/api/v1/projects/gymholic-intelligence/integrations/int-1111/test",
    (route) => {
      if (integrationsList.length > 0) {
        integrationsList[0].status = "pending";
        integrationsList[0].latency_ms = 18.5;
      }
      return route.fulfill({
        json: {
          integration_id: "int-1111",
          status: "pending",
          latency_ms: 18.5,
          capabilities: [],
          error_message: "Connectivity checks for this integration type are not implemented",
        },
      });
    },
  );

  // 1. Visit integrations page
  await page.goto("/projects/gymholic-intelligence/integrations");
  await expect(
    page.getByRole("heading", { name: "Integrations & External Capabilities" }),
  ).toBeVisible();
  await expect(page.getByText("Connected Integrations", { exact: true })).toBeVisible();
  await expect(page.getByText("MCP Servers", { exact: true })).toBeVisible();
  await expect(page.getByText("Inbound Webhooks", { exact: true })).toBeVisible();

  // 2. Click "+ Connect Integration"
  await page.getByRole("button", { name: "+ Connect Integration" }).click();
  await expect(page.getByRole("heading", { name: "Connect New Integration" })).toBeVisible();

  // 3. Fill and submit modal
  await page.getByPlaceholder("e.g. DevOps MCP Server, Stripe Webhook").fill("DevOps MCP Server");
  await page
    .getByPlaceholder("https://mcp.internal.domain.com or https://api.service.com")
    .fill("https://mcp.internal.dev");
  await page
    .getByPlaceholder("e.g. read_logs, query_metrics, event_ingestion")
    .fill("read_logs, query_metrics");
  await page.getByRole("button", { name: "Connect", exact: true }).click();

  // 4. Verify integration appears in table
  await expect(page.getByText("DevOps MCP Server")).toBeVisible();
  await expect(page.getByText("read_logs")).toBeVisible();

  // 5. Test connection
  await page.getByRole("button", { name: "⚡ Ping Test" }).click({ force: true });
  await expect(page.getByText("Live Connectivity Test Result")).toBeVisible();
  await expect(page.getByText("18.5 ms").first()).toBeVisible();

  // 6. Verify webhook instructions snippet
  await expect(page.getByRole("heading", { name: "Inbound Webhook Specification" })).toBeVisible();
});
