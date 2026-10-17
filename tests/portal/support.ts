import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test as base, type Page, type Route, type TestInfo } from "@playwright/test";

export const PROJECT_ID = "project-visual-support";
export const VISUAL_TOKEN = "visual-fixture-token";

const WORKSPACE_ID = "workspace-visual";
const BASELINE_DIR = path.resolve(
  process.env.PORTAL_CAPTURE_DIR ??
    path.join(__dirname, "../../artifacts/portal-visual-experience/final"),
);
const KEYCLOAK_MODULE = /keycloak-js(?:\.js)?(?:\?.*)?$/;

const workspace = {
  id: WORKSPACE_ID,
  slug: "northwind-support",
  name: "Northwind Support (review@example.test)",
  role: "owner",
};

const project = {
  id: PROJECT_ID,
  workspace_id: WORKSPACE_ID,
  engine_project_id: "engine-visual-support",
  slug: "support-intent",
  name: "Support Intent Router",
  created_at: "2026-10-01T09:00:00Z",
};

const classifier = {
  id: "classifier-visual-support",
  project_id: PROJECT_ID,
  engine_classifier_id: "engine-classifier-visual-support",
  slug: "support-intent",
  name: "Support intent",
  active_ontology_version_id: "891dc20d-0000-0000-0000-000000000000",
  classes: [
    { canonical_name: "billing", display_name: "Billing", aliases: ["invoice"] },
    { canonical_name: "technical", display_name: "Technical", aliases: [] },
    { canonical_name: "sales", display_name: "Sales", aliases: [] },
  ],
};

const unknownItem = {
  run_id: "run-visual-unknown-001",
  content: "Can I export last year's invoices?",
  unknown_probability: 0.91,
  supervision_reason: "strong_unknown_probability",
  created_at: "2026-10-15T14:30:00Z",
  recurrence: 4,
  triage: { status: "needs_evidence", category: null, assignee: null, note: null },
};

const summary = {
  window_days: 30,
  unknown_rate: 0.124,
  previous_unknown_rate: 0.145,
  unknown_rate_delta: -0.021,
  latency_avg_ms: 48,
  provider_cost: 0.0412,
  provider_cost_measurement: { status: "complete", amount: 0.0412, declared_cost: 0.0412 },
  recurring_unknowns: 4,
  top_classes: [
    { class: "billing", count: 72 },
    { class: "technical", count: 39 },
  ],
  daily: [
    { date: "2026-10-14", total: 41, unknowns: 5 },
    { date: "2026-10-15", total: 46, unknowns: 6 },
    { date: "2026-10-16", total: 49, unknowns: 6 },
  ],
  pending_reviews: 3,
  recent_versions: [],
  recent_alerts: [],
  simulated: true,
};

const unknownStats = {
  total_unknown: 17,
  total_runs: 136,
  unknown_rate: 0.125,
  by_status: { needs_evidence: 12, triaged: 5 },
  by_category: { missing_info: 5 },
  top_phrases: ["invoice export", "plan cancellation"],
  daily: [
    { date: "2026-10-14", unknowns: 5 },
    { date: "2026-10-15", unknowns: 6 },
    { date: "2026-10-16", unknowns: 6 },
  ],
};

type ControlRequest = {
  method: string;
  path: string;
  authorization: string | undefined;
};

export type ControlMock = {
  requests: ControlRequest[];
  unmocked: ControlRequest[];
  createdProjectNames: string[];
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, json: body });
}

async function installControlMock(page: Page): Promise<ControlMock> {
  const control: ControlMock = { requests: [], unmocked: [], createdProjectNames: [] };
  const projects = [project];

  await page.route("**/control/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const pathname = url.pathname;
    const record = {
      method,
      path: `${pathname}${url.search}`,
      authorization: request.headers().authorization,
    };
    control.requests.push(record);

    const projectPrefix = `/control/workspaces/${WORKSPACE_ID}/projects/${PROJECT_ID}`;

    if (method === "GET" && pathname === "/control/workspaces") {
      return json(route, [workspace]);
    }
    if (method === "GET" && pathname === `/control/workspaces/${WORKSPACE_ID}/projects`) {
      return json(route, projects);
    }
    if (method === "POST" && pathname === `/control/workspaces/${WORKSPACE_ID}/projects`) {
      const body = request.postDataJSON() as { name?: string; description?: string };
      const name = body.name ?? "Untitled visual project";
      const created = {
        ...project,
        id: "project-visual-created",
        engine_project_id: "engine-visual-created",
        slug: "returns-triage",
        name,
      };
      projects.push(created);
      control.createdProjectNames.push(name);
      return json(route, created, 201);
    }
    if (method === "GET" && pathname === `/control/projects/${PROJECT_ID}`) {
      return json(route, project);
    }
    if (method === "GET" && pathname === `${projectPrefix}/analytics/summary`) {
      return json(route, summary);
    }
    if (method === "GET" && pathname === `${projectPrefix}/keys`) {
      return json(route, [
        {
          id: "key-visual-001",
          prefix: "oc_visual_fixture",
          scopes: ["ingest", "read"],
          created_at: "2026-10-02T10:00:00Z",
          revoked_at: null,
        },
      ]);
    }
    if (method === "GET" && pathname === `${projectPrefix}/classifiers`) {
      return json(route, [classifier]);
    }
    if (method === "GET" && pathname === `${projectPrefix}/unknowns/stats`) {
      return json(route, unknownStats);
    }
    if (method === "GET" && pathname === `${projectPrefix}/unknowns`) {
      return json(route, { items: [unknownItem], next_cursor: null });
    }
    if (method === "GET" && pathname === `${projectPrefix}/unknowns/${unknownItem.run_id}`) {
      return json(route, {
        ...unknownItem,
        probabilities: { billing: 0.05, technical: 0.025, sales: 0.015, UNKNOWN: 0.91 },
        raw_event_id: "event-visual-unknown-001",
      });
    }
    if (method === "GET" && pathname === `${projectPrefix}/alerts/rules`) {
      return json(route, [
        {
          id: "rule-visual-001",
          metric: "unknown_rate",
          threshold: 0.2,
          window: "24h",
          enabled: true,
        },
      ]);
    }
    if (method === "GET" && pathname === `${projectPrefix}/ops/events`) {
      return json(route, [
        {
          event: "ontology.version_created",
          actor: "review@example.test",
          created_at: "2026-10-12T11:20:00Z",
        },
      ]);
    }
    if (method === "GET" && pathname === `${projectPrefix}/unknowns/ontology`) {
      return json(route, {
        current_choices: [{ key: "BILLING" }, { key: "TECHNICAL" }, { key: "SALES" }],
        versions: [
          {
            version_number: 2,
            origin: "human_promotion",
            rationale: "Promote INVOICE_EXPORT after verified replay",
            actor: "review@example.test",
            created_at: "2026-10-12T11:20:00Z",
            choices: [
              { key: "BILLING", label: "Billing" },
              { key: "TECHNICAL", label: "Technical" },
              { key: "SALES", label: "Sales" },
              { key: "INVOICE_EXPORT", label: "Invoice export" },
              { key: "UNKNOWN", label: "Unknown" },
            ],
          },
          {
            version_number: 1,
            origin: "initial_seed",
            rationale: "Initial production classes",
            actor: "review@example.test",
            created_at: "2026-10-05T09:15:00Z",
            choices: [
              { key: "BILLING", label: "Billing" },
              { key: "TECHNICAL", label: "Technical" },
              { key: "SALES", label: "Sales" },
              { key: "UNKNOWN", label: "Unknown" },
            ],
          },
        ],
        events: [
          {
            event: "version.promoted",
            actor: "review@example.test",
            from_version: 1,
            to_version: 2,
            detail: { choice: "INVOICE_EXPORT" },
          },
        ],
      });
    }

    control.unmocked.push(record);
    return json(route, { message: `Unmocked control API request: ${method} ${record.path}` }, 501);
  });

  return control;
}

export const test = base.extend<{ control: ControlMock }>({
  control: [
    async ({ page }, use) => {
      const control = await installControlMock(page);
      await use(control);
      expect(
        control.unmocked,
        `unmocked control API calls: ${JSON.stringify(control.unmocked)}`,
      ).toEqual([]);
    },
    { auto: true },
  ],
});

export async function mockKeycloak(page: Page, authenticated: boolean) {
  let requestCount = 0;
  await page.route(KEYCLOAK_MODULE, (route) => {
    requestCount += 1;
    return route.fulfill({
      status: 200,
      contentType: "application/javascript",
      body: `export default class VisualKeycloak {
        constructor() { this.token = ${JSON.stringify(VISUAL_TOKEN)}; }
        init() { return Promise.resolve(${authenticated}); }
        login() { return Promise.resolve(); }
        logout() { return Promise.resolve(); }
        clearToken() { this.token = undefined; }
      }`,
    });
  });
  return { requestCount: () => requestCount };
}

export async function expectNoHorizontalOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    viewportWidth: document.documentElement.clientWidth,
    rootScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }));
  expect(
    metrics.rootScrollWidth,
    `root horizontal overflow: ${JSON.stringify(metrics)}`,
  ).toBeLessThanOrEqual(metrics.viewportWidth);
  expect(
    metrics.bodyScrollWidth,
    `body horizontal overflow: ${JSON.stringify(metrics)}`,
  ).toBeLessThanOrEqual(metrics.viewportWidth);
}

export async function captureBaseline(page: Page, testInfo: TestInfo, name: string) {
  await mkdir(BASELINE_DIR, { recursive: true });
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  const filename = `${name}-${testInfo.project.name}.png`;
  await page.screenshot({
    path: path.join(BASELINE_DIR, filename),
    fullPage: true,
    animations: "disabled",
  });
}

export async function captureProductBaseline(page: Page, testInfo: TestInfo, name: string) {
  await captureBaseline(page, testInfo, `route-mocked-${name}`);
}

export { expect };
