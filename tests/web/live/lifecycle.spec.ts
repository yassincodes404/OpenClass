import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

test.skip(process.env.OPENCLASS_LIVE_BACKEND !== "1", "Run pnpm test:web:live for a fresh stack");

test("standalone web renders while its real engine boundary rejects unauthenticated access", async ({
  page,
  request,
}, testInfo) => {
  const web = process.env.OPENCLASS_LIVE_WEB_URL!;
  await page.goto(web);
  await expect(page.locator("main")).toBeVisible();
  expect((await request.get(`${web}/health/ready`)).status()).toBe(200);
  expect((await request.get(`${web}/api/v1/projects`)).status()).toBe(401);
  await page.screenshot({ path: testInfo.outputPath("standalone-web.png"), fullPage: true });
});

// Public, deliberately synthetic credentials from the checked-in LOCAL realm.
const owner = "owner@acme.openclass.test";
const outsider = "reviewer@acme.openclass.test";
const password = (username: string) =>
  username === owner ? "OpenClass-Local-Owner-2026" : "OpenClass-Local-Reviewer-2026";

async function token(request: APIRequestContext, username: string) {
  const response = await request.post(
    `${process.env.OPENCLASS_LIVE_IDENTITY_URL}/realms/openclass-local/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: "openclass-portal",
        username,
        password: password(username),
      },
    },
  );
  expect(response.status(), "Keycloak must issue a genuine signed access token").toBe(200);
  const body = await response.json();
  expect(typeof body.access_token).toBe("string");
  return body.access_token as string;
}

async function login(page: Page, username: string) {
  await page.goto("/projects");
  await page.getByRole("button", { name: "Continue with Keycloak" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password(username));
  await page.locator("#kc-login").click();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
}

test("authenticated owned lifecycle persists after backend restart and denies another workspace", async ({
  page,
  request,
  browser,
}, testInfo) => {
  const ownerToken = await token(request, owner);
  const outsiderToken = await token(request, outsider);
  const control = process.env.OPENCLASS_LIVE_CONTROL_URL!;
  const headers = { authorization: `Bearer ${ownerToken}` };
  const otherHeaders = { authorization: `Bearer ${outsiderToken}` };
  const name = `Live owned ${randomUUID().slice(0, 8)}`;
  const createdWorkspace = await request.post(`${control}/control/workspaces`, {
    headers,
    data: { name },
  });
  expect(createdWorkspace.status()).toBe(201);
  const workspace = await createdWorkspace.json();
  const otherWorkspace = await request.post(`${control}/control/workspaces`, {
    headers: otherHeaders,
    data: { name: `Other ${randomUUID().slice(0, 8)}` },
  });
  expect(otherWorkspace.status()).toBe(201);
  const other = await otherWorkspace.json();

  await login(page, owner);
  await page.getByRole("button", { name: "+ New project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create project", exact: true });
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill(name);
  const projectResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/workspaces/${workspace.id}/projects`),
  );
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  const projectCreated = await projectResponse;
  expect(projectCreated.status()).toBe(201);
  const project = await projectCreated.json();
  expect(project.workspace_id).toBe(workspace.id);
  expect(project.engine_project_id).toBeTruthy();
  await page.getByRole("link", { name: "Open project" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${project.id}$`));

  await page.getByRole("link", { name: "Data", exact: true }).click();
  const content = `Billing invoice charged twice ${randomUUID()}`;
  await page.getByPlaceholder("I was charged twice for my subscription").fill(content);
  const eventResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/events"),
  );
  await page.getByRole("button", { name: "Ingest observation", exact: true }).click();
  const eventCreated = await eventResponse;
  expect(eventCreated.status()).toBe(201);
  const event = await eventCreated.json();
  await expect(page.getByRole("status")).toContainText("Saved observation");

  await page.getByRole("link", { name: "Decisions", exact: true }).click();
  await page.getByRole("button", { name: "+ New decision service", exact: true }).click();
  const serviceDialog = page.getByRole("dialog", { name: "Create decision service", exact: true });
  await serviceDialog.getByRole("textbox", { name: "Name", exact: true }).fill("Simulated router");
  await serviceDialog
    .getByRole("textbox", { name: "Instructions" })
    .fill("Route billing messages. Abstain for anything outside billing.");
  await serviceDialog.getByRole("textbox", { name: "Choices" }).fill("BILLING");
  const serviceResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/decision-services"),
  );
  await serviceDialog.getByRole("button", { name: "Create service", exact: true }).click();
  const serviceCreated = await serviceResponse;
  expect(serviceCreated.status()).toBe(201);
  const service = await serviceCreated.json();
  await page.getByRole("link", { name: "Open service" }).click();
  await page.getByPlaceholder('Try "I was charged twice"').fill(content);
  const runResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/decision-services/${service.id}/runs`),
  );
  await page.getByRole("button", { name: "Run decision", exact: true }).click();
  const runCreated = await runResponse;
  expect(runCreated.status()).toBe(201);
  const [run] = await runCreated.json();
  expect(run.provider).toBe("mock");
  expect(run.raw_event_id).toBe(event.id);
  expect(run.probabilities).toHaveProperty("UNKNOWN");
  await expect(page.getByText("simulated", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("owned-simulated-run.png"), fullPage: true });

  const prefix = `/control/workspaces/${workspace.id}/projects/${project.id}`;
  for (const resource of ["", "/events", "/runs", `/decision-services/${service.id}`]) {
    const denied = await request.get(`${control}${prefix}${resource}`, { headers: otherHeaders });
    expect(denied.status(), `Outsider must not read ${resource || "project"}`).toBe(404);
  }
  const mismatchedWorkspace = await request.get(
    `${control}/control/workspaces/${other.id}/projects/${project.id}/events`,
    { headers: otherHeaders },
  );
  expect(mismatchedWorkspace.status()).toBe(404);
  const deniedWrite = await request.post(`${control}${prefix}/events`, {
    headers: otherHeaders,
    data: { content: "must never be persisted" },
  });
  expect(deniedWrite.status()).toBe(404);
  const unauthenticated = await request.get(`${control}${prefix}`);
  expect(unauthenticated.status()).toBe(401);
  const directEngine = await request.get(
    `${process.env.OPENCLASS_LIVE_ENGINE_URL}/api/v1/projects/${project.engine_project_id}`,
  );
  expect(directEngine.status()).toBe(401);
  const untrustedWeb = await request.get(`${process.env.OPENCLASS_LIVE_WEB_URL}/api/v1/projects`);
  expect(untrustedWeb.status()).toBe(401);

  // No route interception: real Keycloak + CP HTTP + engine HTTP + migrated PG.
  const composeProject = process.env.OPENCLASS_LIVE_COMPOSE_PROJECT!;
  expect(composeProject).toMatch(/^openclass-live-[a-f0-9]{12}$/);
  execFileSync(
    "docker",
    [
      "compose",
      "--project-directory",
      process.env.OPENCLASS_LIVE_COMPOSE_ROOT!,
      "--file",
      process.env.OPENCLASS_LIVE_COMPOSE_FILE!,
      "--file",
      process.env.OPENCLASS_LIVE_COMPOSE_OVERLAY!,
      "--env-file",
      process.env.OPENCLASS_LIVE_COMPOSE_ENV_FILE!,
      "--project-name",
      composeProject,
      "--profile",
      "full-stack",
      "restart",
      "db",
      "server",
      "control-plane",
    ],
    { timeout: 60_000, stdio: "pipe" },
  );
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${control}/health/ready`)).status();
        } catch {
          return 0;
        }
      },
      { timeout: 45_000 },
    )
    .toBe(200);
  const persisted = await request.get(`${control}${prefix}/runs/${run.id}`, { headers });
  expect(persisted.status()).toBe(200);
  expect(await persisted.json()).toMatchObject({
    id: run.id,
    raw_event_id: event.id,
    selected_choice: run.selected_choice,
  });
  const persistedEvent = await request.get(`${control}${prefix}/events/${event.id}`, { headers });
  expect(persistedEvent.status()).toBe(200);
  expect(await persistedEvent.json()).toMatchObject({ id: event.id, content });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Simulated router", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByText(run.id.slice(0, 8), { exact: false })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("restart-persisted-runs.png"),
    fullPage: true,
  });

  const outsiderContext = await browser.newContext({
    baseURL: process.env.OPENCLASS_LIVE_BASE_URL,
  });
  try {
    const otherPage = await outsiderContext.newPage();
    await otherPage.goto(process.env.OPENCLASS_LIVE_BASE_URL!);
    await login(otherPage, outsider);
    await expect(otherPage.getByRole("heading", { name: other.name, exact: true })).toBeVisible();
    await expect(otherPage.getByRole("heading", { name, exact: true })).toHaveCount(0);
    const deniedResolve = otherPage.waitForResponse((response) =>
      response.url().endsWith(`/control/projects/${project.id}`),
    );
    await otherPage.goto(`${process.env.OPENCLASS_LIVE_BASE_URL}/projects/${project.id}/runs`);
    expect((await deniedResolve).status()).toBe(404);
    await expect(otherPage.getByText("Project unavailable.", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await otherPage.screenshot({
      path: testInfo.outputPath("cross-workspace-denied.png"),
      fullPage: true,
    });
  } finally {
    await outsiderContext.close();
  }
});
