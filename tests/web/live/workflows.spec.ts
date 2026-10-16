import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Page,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { OpenClass } from "../../../packages/sdk-typescript/src/index";

// Genuine HTTP/browser acceptance. No route interception, fabricated candidate
// rows, browser token injection, trace capture, or storage-state files.
test.skip(process.env.OPENCLASS_LIVE_BACKEND !== "1", "Requires the isolated live-stack runner");
test.setTimeout(240_000);

const owner = "owner@acme.openclass.test";
const outsider = "reviewer@acme.openclass.test";
const portal = process.env.OPENCLASS_LIVE_BASE_URL!;
const web = process.env.OPENCLASS_LIVE_WEB_URL!;
const control = process.env.OPENCLASS_LIVE_CONTROL_URL!;
const engine = process.env.OPENCLASS_LIVE_ENGINE_URL!;
type Mapping = { id: string; workspace_id: string; engine_project_id: string; slug: string };

async function accessToken(request: APIRequestContext, username: string) {
  const response = await request.post(
    `${process.env.OPENCLASS_LIVE_IDENTITY_URL}/realms/openclass-local/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: "openclass-portal",
        username,
        password:
          username === owner ? "OpenClass-Local-Owner-2026" : "OpenClass-Local-Reviewer-2026",
      },
    },
  );
  expect(response.status(), "Genuine local Keycloak token grant").toBe(200);
  return (await response.json()).access_token as string;
}

async function signedIn(page: Page, origin: string, username = owner) {
  await page.goto(`${origin}/projects`);
  // check-sso may restore an existing real IdP session without showing a form.
  await expect(
    page.getByRole("heading", {
      name: /^(Projects|Sign in to your workspace\.)$/,
      exact: true,
      level: 1,
    }),
  ).toBeVisible({ timeout: 30_000 });
  if (await page.getByRole("heading", { name: "Sign in to your workspace." }).isVisible()) {
    await page.getByRole("button", { name: /^Continue with Keycloak/ }).click();
    await page.locator("#username").fill(username);
    await page
      .locator("#password")
      .fill(username === owner ? "OpenClass-Local-Owner-2026" : "OpenClass-Local-Reviewer-2026");
    await page.locator("#kc-login").click();
  }
  await expect(
    page.getByRole("heading", { name: "Projects", exact: true, level: 1 }),
  ).toBeVisible();
}

async function json(response: Pick<APIResponse, "status" | "url" | "json">, status = 200) {
  // Do not include request headers or token-grant payloads in failure messages.
  expect(response.status(), `${response.url()} HTTP status`).toBe(status);
  return response.json();
}

function mutation(page: Page, method: string, suffix: string) {
  return page.waitForResponse(
    (response) =>
      response.request().method() === method && new URL(response.url()).pathname.endsWith(suffix),
  );
}

async function workspace(
  request: APIRequestContext,
  headers: Record<string, string>,
  name: string,
) {
  return json(
    await request.post(`${control}/control/workspaces`, { headers, data: { name } }),
    201,
  );
}

function restartBackends() {
  const project = process.env.OPENCLASS_LIVE_COMPOSE_PROJECT!;
  expect(project).toMatch(/^openclass-live-[a-f0-9]{12}$/);
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
      project,
      "--profile",
      "full-stack",
      "restart",
      "db",
      "server",
      "control-plane",
    ],
    { timeout: 60_000, stdio: "pipe" },
  );
}

test("real frontends share owned projects, scoped classifiers, evidence, graph and sealed replay", async ({
  page,
  context,
  request,
  browser,
}, testInfo) => {
  const bearer = await accessToken(request, owner);
  const otherBearer = await accessToken(request, outsider);
  const headers = { authorization: `Bearer ${bearer}` };
  const otherHeaders = { authorization: `Bearer ${otherBearer}` };
  const name = `Parity ${randomUUID().slice(0, 8)}`;
  const ws = await workspace(request, headers, name);
  const ws2 = await workspace(request, headers, `${name} second`);
  const internal = process.env.OPENCLASS_INTERNAL_TOKEN!;
  expect(Boolean(internal), "Only the trusted Node harness receives the engine credential").toBe(
    true,
  );
  const engineHeaders = {
    "X-OpenClass-Internal-Token": internal,
    "X-OpenClass-Workspace-Id": ws.id,
  };
  const sdk = new OpenClass({
    baseURL: engine,
    workspaceId: ws.id,
    fetcher: (input, init) =>
      fetch(input, {
        ...init,
        headers: { ...init?.headers, "X-OpenClass-Internal-Token": internal },
      }),
  });
  const external = await sdk.createProject({ name, description: "Created outside both browsers" });
  const mappings: Mapping[] = await json(
    await request.get(`${control}/control/workspaces/${ws.id}/projects`, { headers }),
  );
  const project = mappings.find((entry) => entry.engine_project_id === external.id)!;
  expect(
    project,
    "Owned external SDK project must reconcile into the control registry",
  ).toBeTruthy();
  expect(project.workspace_id).toBe(ws.id);
  const prefix = `/control/workspaces/${ws.id}/projects/${project.id}`;
  const workflow = `${prefix}/workflow`;

  // Observe only a boolean, never capture or print browser credentials.
  // headers() is synchronous at issue time, so navigation aborts cannot
  // interrupt an inspection; the counter proves traffic was actually observed.
  let browserBoundaryLeak = false;
  let observedRequests = 0;
  const observe = (current: Page) =>
    current.on("request", (req) => {
      observedRequests += 1;
      const values = req.headers();
      if (
        Object.keys(values).some((key) => key.toLowerCase() === "x-openclass-internal-token") ||
        Object.values(values).some((value) => value.includes(internal)) ||
        req.url().includes(internal) ||
        (req.postData() ?? "").includes(internal)
      )
        browserBoundaryLeak = true;
    });
  observe(page);
  await signedIn(page, portal);
  await expect(page.getByRole("heading", { name, exact: true, level: 3 })).toBeVisible();
  const next = await context.newPage();
  observe(next);
  await signedIn(next, web);
  await expect(next.getByRole("link").filter({ hasText: name })).toBeVisible();
  await next.reload();
  await expect(next.getByRole("link").filter({ hasText: name })).toBeVisible();
  for (const identifier of [project.id, project.engine_project_id]) {
    expect(
      await json(await request.get(`${control}/control/projects/${identifier}`, { headers })),
    ).toMatchObject({ id: project.id, engine_project_id: external.id, workspace_id: ws.id });
  }

  // Create through Next, inspect through portal, then create through portal and
  // inspect through Next. Selecting a real membership is mandatory.
  await next.getByLabel("Workspace for new projects").selectOption(ws.id);
  await next.getByLabel("Name", { exact: true }).fill(`${name} Next`);
  const nextCreation = mutation(next, "POST", `/workspaces/${ws.id}/projects`);
  await next.getByRole("button", { name: "Create project", exact: true }).click();
  const nextProject = await json(await nextCreation, 201);
  await page.reload();
  await expect(page.getByRole("heading", { name: `${name} Next`, exact: true })).toBeVisible();
  const block = page.locator("section.workspace-block").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
  await block.getByRole("button", { name: "+ New project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create project", exact: true });
  await dialog.getByLabel("Name", { exact: true }).fill(`${name} Portal`);
  const portalCreation = mutation(page, "POST", `/workspaces/${ws.id}/projects`);
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await json(await portalCreation, 201);
  await next.reload();
  await expect(next.getByRole("link").filter({ hasText: `${name} Portal` })).toBeVisible();
  expect(nextProject.engine_project_id).not.toBe(project.engine_project_id);

  // Identical public project slugs in different accessible workspaces must not
  // resolve arbitrarily, even though the engine assigns a globally unique slug.
  const second: Mapping = await json(
    await request.post(`${control}/control/workspaces/${ws2.id}/projects`, {
      headers,
      data: { name },
    }),
    201,
  );
  expect(second.slug).toBe(project.slug);
  expect(
    (await request.get(`${control}/control/projects/${project.slug}`, { headers })).status(),
  ).toBe(400);
  expect(
    await json(await request.get(`${control}/control/projects/${second.id}`, { headers })),
  ).toMatchObject({ id: second.id, workspace_id: ws2.id });

  // Exercise the actual portal form twice, not an equivalent decision service.
  const classifierMappings: Array<{ id: string; engine_classifier_id: string }> = [];
  for (const [mapping, workspaceId] of [
    [project, ws.id],
    [second, ws2.id],
  ] as const) {
    await page.goto(`${portal}/projects/${mapping.id}/classifiers`);
    await page.getByRole("button", { name: "+ New classifier", exact: true }).click();
    const form = page.getByRole("dialog", { name: "Create classifier", exact: true });
    await form.getByLabel("Name", { exact: true }).fill("Support intent");
    await form.getByLabel(/^Classes/).fill("billing");
    const created = mutation(page, "POST", `/projects/${mapping.id}/classifiers`);
    await form.getByRole("button", { name: "Create classifier", exact: true }).click();
    const classifier = await json(await created, 201);
    classifierMappings.push(classifier);
    expect(classifier.slug).toBe("support-intent");
    const engineClassifier = await json(
      await request.get(`${engine}/api/v1/classifiers/${classifier.engine_classifier_id}`, {
        headers: { ...engineHeaders, "X-OpenClass-Workspace-Id": workspaceId },
      }),
    );
    expect(engineClassifier.slug).toBe(
      `ocp-${createHash("sha256")
        .update(JSON.stringify(["openclass.control.classifier.v1", mapping.id, "support-intent"]))
        .digest("hex")}`,
    );
    const ontology = await json(
      await request.get(
        `${engine}/api/v1/classifiers/${classifier.engine_classifier_id}/ontology`,
        {
          headers: { ...engineHeaders, "X-OpenClass-Workspace-Id": workspaceId },
        },
      ),
    );
    expect(
      ontology.classes.map((entry: { canonical_name: string }) => entry.canonical_name),
    ).toEqual(["billing"]);
    await page.getByRole("link", { name: "Open classifier", exact: false }).click();
    await expect(page.getByRole("heading", { name: "Support intent", exact: true })).toBeVisible();
    await expect(page.getByText("support-intent", { exact: true })).toBeVisible();
    await expect(page.getByText("UNKNOWN", { exact: true })).toBeVisible();
  }
  expect(classifierMappings[0]!.engine_classifier_id).not.toBe(
    classifierMappings[1]!.engine_classifier_id,
  );
  const classifierInput = {
    name: "Support intent",
    slug: "support-intent",
    unknown_fallback: true,
    classes: [{ canonical_name: "billing", display_name: "Billing" }],
  };
  const before = await json(
    await request.get(`${engine}/api/v1/classifiers`, { headers: engineHeaders }),
  );
  expect(
    (
      await request.post(`${control}${prefix}/classifiers`, { headers, data: classifierInput })
    ).status(),
  ).toBe(400);
  expect(
    (await json(await request.get(`${engine}/api/v1/classifiers`, { headers: engineHeaders })))
      .length,
  ).toBe(before.length);
  const longIds: string[] = [];
  for (const slug of [`a${"b".repeat(78)}c`, `a${"b".repeat(78)}d`]) {
    const classifier = await json(
      await request.post(`${control}${prefix}/classifiers`, {
        headers,
        data: { ...classifierInput, slug },
      }),
      201,
    );
    longIds.push(classifier.engine_classifier_id);
    expect(classifier.slug).toBe(slug);
  }
  expect(new Set(longIds).size).toBe(2);
  expect(
    (
      await request.post(`${control}${prefix}/classifiers`, {
        headers,
        data: { ...classifierInput, slug: "../invalid" },
      })
    ).status(),
  ).toBe(400);
  const legacy = await json(
    await request.post(`${engine}/api/v1/classifiers`, {
      headers: engineHeaders,
      data: {
        name: classifierInput.name,
        classes: classifierInput.classes,
        slug: `legacy-${randomUUID().slice(0, 8)}`,
      },
    }),
    201,
  );
  expect(
    await json(
      await request.get(`${engine}/api/v1/classifiers/${legacy.id}`, {
        headers: engineHeaders,
      }),
    ),
  ).toMatchObject({ id: legacy.id, slug: legacy.slug });
  expect(
    (
      await request.get(`${engine}/api/v1/classifiers/${legacy.id}/ontology`, {
        headers: engineHeaders,
      })
    ).status(),
  ).toBe(200);

  const service = await json(
    await request.post(`${control}${workflow}/decision-services`, {
      headers,
      data: {
        name: "Parity router",
        instructions: "Route billing requests. Abstain from unsupported requests.",
        choices: [{ key: "BILLING", label: "Billing", description: "Billing questions" }],
      },
    }),
    201,
  );
  let pinnedRun: { id: string; decision_service_version_id: string } | undefined;
  for (const text of [
    "Cancel my plan immediately",
    "Cancel my plan today please",
    "Cancel my plan once and for all",
    "Cancel my subscription plan now",
    "Cancel plan next month",
  ]) {
    const runs = await json(
      await request.post(`${control}${workflow}/decision-services/${service.id}/runs`, {
        headers,
        data: { content: text },
      }),
      201,
    );
    expect(runs[0].selected_choice).toBe("UNKNOWN");
    expect(runs[0].provider).toBe("mock");
    pinnedRun ??= runs[0];
  }
  const engineProject = `${engine}/api/v1/projects/${external.id}`;
  const clustered = await json(
    await request.post(`${engineProject}/unknowns/cluster`, {
      headers: engineHeaders,
      data: { threshold: 0.2 },
    }),
  );
  expect(clustered.cluster_count).toBeGreaterThan(0);
  const clusters = await json(
    await request.get(`${engineProject}/unknowns/clusters`, { headers: engineHeaders }),
  );
  const biggest = clusters.sort((a: { size: number }, b: { size: number }) => b.size - a.size)[0];
  const candidate = await json(
    await request.post(`${engineProject}/clusters/${biggest.id}/discover`, {
      headers: engineHeaders,
      data: {},
    }),
    201,
  );
  expect(candidate.type).toBe("NEW_CLASS");
  expect(candidate.canonical_name.trim().length).toBeGreaterThan(0);
  const evidence = await json(await request.get(`${control}${workflow}/evidence`, { headers }));
  const item = evidence.find(
    (entry: { decision_run_id: string }) => entry.decision_run_id === pinnedRun!.id,
  );
  expect(item).toBeTruthy();

  await page.goto(`${portal}/projects/${project.id}/evidence`);
  await page.getByRole("button", { name: new RegExp(item.id.slice(0, 8)) }).click();
  const detail = page.getByRole("region", { name: "Evidence detail" });
  const diagnosis = mutation(page, "POST", `/evidence/${item.id}/ai-diagnose`);
  await detail.getByRole("button", { name: "Request advisory diagnosis" }).click();
  expect((await json(await diagnosis)).simulated).toBe(true);
  const advised = await json(
    await request.get(`${control}${workflow}/evidence/${item.id}`, { headers }),
  );
  expect(advised.diagnosis).toBe(item.diagnosis);
  expect(advised.status).toBe(item.status);
  await detail
    .getByLabel("Human rationale")
    .fill("Human reviewed: unsupported cancellation intent.");
  const triaged = mutation(page, "PATCH", `/evidence/${item.id}/triage`);
  await detail.getByRole("button", { name: "Save human triage" }).click();
  expect((await json(await triaged)).diagnosis_rationale).toContain("Human reviewed");
  await next.goto(`${web}/projects/${external.id}/evolution`);
  await next.getByRole("button", { name: "Inspect & Triage" }).first().click();
  const nextDetail = next.getByRole("region", { name: "Evidence detail" });
  const nextDiagnosis = mutation(next, "POST", "/ai-diagnose");
  await nextDetail.getByRole("button", { name: /Diagnose with Provider/ }).click();
  expect((await json(await nextDiagnosis)).simulated).toBe(true);
  await nextDetail
    .getByLabel("Triage Rationale & Notes")
    .fill("Independent human review through Next.");
  const nextTriage = mutation(next, "PATCH", "/triage");
  await nextDetail.getByRole("button", { name: "Save Triage", exact: true }).click();
  const updatedEvidence = await json(await nextTriage);
  expect(
    (
      await json(
        await request.get(`${control}${workflow}/evidence/${updatedEvidence.id}`, { headers }),
      )
    ).diagnosis_rationale,
  ).toBe("Independent human review through Next.");
  await next.screenshot({ path: testInfo.outputPath("real-next-evidence.png"), fullPage: true });

  // Keep Next's old draft open while portal appends a real immutable version.
  await next.goto(`${web}/projects/${external.id}/decisions`);
  await next.getByRole("button", { name: "Edit graph for Parity router" }).click();
  await page.goto(`${portal}/projects/${project.id}/decisions/${service.id}`);
  const graph = page.getByRole("form", { name: "Decision graph editor" });
  await graph.getByRole("button", { name: "Add node", exact: true }).focus();
  await page.keyboard.press("Enter");
  await graph.getByLabel("Node name", { exact: true }).nth(1).fill("Human review");
  await graph
    .getByRole("combobox", { name: "Next node", exact: true })
    .first()
    .selectOption({ label: "Human review" });
  await graph.getByLabel("Human approval before this transition").check();
  const saved = mutation(page, "PATCH", `/decision-services/${service.id}`);
  await graph.getByRole("button", { name: "Save new graph version" }).click();
  const version2 = await json(await saved);
  expect(version2.version_number).toBe(service.version_number + 1);
  expect(version2.nodes).toHaveLength(2);
  expect(version2.transitions[0].require_approval).toBe(true);
  for (const node of version2.nodes)
    expect(node.choices.map((choice: { key: string }) => choice.key)).toContain("UNKNOWN");
  let stalePatch = false;
  next.on("request", (req) => {
    if (req.method() === "PATCH" && req.url().endsWith(`/decision-services/${service.id}`))
      stalePatch = true;
  });
  await next.getByRole("button", { name: "Save new graph version" }).click();
  await expect(next.getByText(/Service changed since loading/)).toBeVisible();
  expect(stalePatch).toBe(false);
  await next.reload();
  await next.getByRole("button", { name: "Edit graph for Parity router" }).click();
  await next
    .getByRole("textbox", { name: "Node instructions", exact: true })
    .nth(1)
    .fill("Human review is required.");
  const nextSaved = mutation(next, "PATCH", `/decision-services/${service.id}`);
  await next.getByRole("button", { name: "Save new graph version" }).click();
  const version3 = await json(await nextSaved);
  expect(version3.version_number).toBe(version2.version_number + 1);
  expect(
    (await json(await request.get(`${control}${workflow}/runs/${pinnedRun!.id}`, { headers })))
      .decision_service_version_id,
  ).toBe(pinnedRun!.decision_service_version_id);
  expect(pinnedRun!.decision_service_version_id).toBe(service.active_version_id);
  await next.screenshot({ path: testInfo.outputPath("real-next-graph.png"), fullPage: true });

  await page.goto(`${portal}/projects/${project.id}/evaluations`);
  const replay = page.getByRole("region", { name: "Replay evaluation workspace" });
  await replay.getByLabel("New dataset name").fill("Independent human holdout");
  const datasetCreation = mutation(page, "POST", "/eval-datasets");
  await replay.getByRole("button", { name: "Create verified dataset" }).click();
  const dataset = await json(await datasetCreation, 201);
  // These manually specified labels are fixture ground truth, never copied
  // from a model prediction. Holdout text is disjoint from discovery evidence.
  for (const [text, label, split] of [
    [
      "Please end this membership after the prepaid month",
      candidate.canonical_name.toUpperCase(),
      "holdout",
    ],
    ["A question about billing", "BILLING", "regression"],
    ["Unrelated volcanic mineral sample", "UNKNOWN", "holdout"],
  ]) {
    await replay.getByLabel("Observation text").fill(text!);
    await replay.getByLabel("Verified label (or UNKNOWN)", { exact: true }).fill(label!);
    await replay.getByLabel("Annotator / verified source identity").fill("live-human-fixture");
    await replay
      .getByLabel("Label rationale")
      .fill("Independent synthetic annotation for workflow verification only.");
    await replay.getByRole("combobox", { name: "Dataset split", exact: true }).selectOption(split!);
    const example = mutation(page, "POST", `/eval-datasets/${dataset.id}/examples`);
    await replay.getByRole("button", { name: "Add verified example", exact: true }).click();
    await json(await example, 201);
    await expect(replay.getByRole("status")).toContainText("Verified example added.");
  }
  await replay.getByLabel(/I reviewed provenance and disjoint splits/).check();
  const sealed = mutation(page, "POST", `/eval-datasets/${dataset.id}/seal`);
  await replay.getByRole("button", { name: "Seal verified dataset" }).click();
  const seal = await json(await sealed);
  expect(seal.dataset_hash).toBeTruthy();
  const readDataset = await json(
    await request.get(`${engineProject}/eval-datasets/${dataset.id}`, { headers: engineHeaders }),
  );
  expect(readDataset.examples).toHaveLength(3);
  expect(readDataset.dataset_hash).toBe(seal.dataset_hash);
  expect(readDataset.examples.every((entry: { source: string }) => entry.source === "human")).toBe(
    true,
  );
  expect(
    (
      await request.post(`${control}${workflow}/eval-datasets/${dataset.id}/examples`, {
        headers,
        data: {
          text: "Too late",
          label: "UNKNOWN",
          source: "human",
          annotator: "human-fixture",
          slice_tag: "historical",
          source_type: "verified_holdout",
          split: "holdout",
        },
      })
    ).status(),
  ).toBe(409);
  await replay
    .getByRole("combobox", { name: "Inactive candidate", exact: true })
    .selectOption(candidate.id);
  await replay
    .getByRole("combobox", { name: "Decision service", exact: true })
    .selectOption(service.id);
  const evaluation = mutation(page, "POST", "/evaluations");
  await replay.getByRole("button", { name: "Run sealed replay" }).click();
  const evaluated = await json(await evaluation, 201);
  expect(evaluated.is_simulated).toBe(true);
  expect(evaluated.gates.length).toBeGreaterThan(0);
  const result = page.getByRole("region", { name: "Replay result" });
  await expect(
    result.getByText("Simulated replay — not evidence of real model quality."),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("real-portal-replay.png"), fullPage: true });
  expect(
    (
      await json(
        await request.get(`${engineProject}/discovery-candidates/${candidate.id}`, {
          headers: engineHeaders,
        }),
      )
    ).status,
  ).toBe("candidate");
  expect(
    (
      await json(
        await request.get(`${control}${workflow}/decision-services/${service.id}`, { headers }),
      )
    ).version_number,
  ).toBe(version3.version_number);

  // Before membership is granted, neither frontend may reveal either project ID.
  const otherContext = await browser.newContext();
  try {
    const otherPage = await otherContext.newPage();
    observe(otherPage);
    for (const origin of [portal, web]) {
      await signedIn(otherPage, origin, outsider);
      for (const identifier of [project.id, external.id]) {
        const denied = mutation(otherPage, "GET", `/control/projects/${identifier}`);
        await otherPage.goto(`${origin}/projects/${identifier}/evaluations`);
        expect((await denied).status()).toBe(404);
        await expect(
          otherPage.getByRole("heading", { name: "Verified replay evaluations" }),
        ).toHaveCount(0);
      }
    }
    const subject = JSON.parse(Buffer.from(otherBearer.split(".")[1]!, "base64url").toString()).sub;
    await json(
      await request.post(`${control}/control/workspaces/${ws.id}/members`, {
        headers,
        data: { subject, role: "viewer" },
      }),
    );
    for (const [method, suffix, data] of [
      [
        "PATCH",
        `/evidence/${item.id}/triage`,
        { diagnosis: "procedure", rationale: "Viewer must not write" },
      ],
      ["PATCH", `/decision-services/${service.id}`, { instructions: "Viewer must not write" }],
      [
        "POST",
        "/evaluations",
        { dataset_id: dataset.id, candidate_id: candidate.id, service_id: service.id },
      ],
    ] as const) {
      expect(
        (
          await request.fetch(`${control}${workflow}${suffix}`, {
            method,
            headers: otherHeaders,
            data,
          })
        ).status(),
      ).toBe(403);
    }
    expect(
      (
        await request.post(`${control}${prefix}/classifiers`, {
          headers: otherHeaders,
          data: classifierInput,
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await request.get(
          `${control}/control/workspaces/${ws2.id}/projects/${project.id}/workflow`,
          { headers },
        )
      ).status(),
    ).toBe(404);
  } finally {
    await otherContext.close();
  }

  restartBackends();
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
  for (const [current, origin, identifier] of [
    [page, portal, project.id],
    [next, web, external.id],
  ] as const) {
    await current.goto(`${origin}/projects/${identifier}/evaluations`);
    await current.getByRole("button", { name: new RegExp(evaluated.id) }).click();
    await expect(current.getByRole("region", { name: "Replay result" })).toContainText(
      evaluated.id,
    );
    await expect(current.getByRole("region", { name: "Replay result" })).toContainText(
      "Simulated replay",
    );
    await current.screenshot({
      path: testInfo.outputPath(
        origin === portal ? "real-portal-restart.png" : "real-next-restart.png",
      ),
      fullPage: true,
    });
  }
  expect(
    await json(await request.get(`${control}${workflow}/evaluations/${evaluated.id}`, { headers })),
  ).toMatchObject({
    id: evaluated.id,
    dataset_id: dataset.id,
    metrics: evaluated.metrics,
    gates: evaluated.gates,
  });
  expect(
    (
      await json(
        await request.get(`${control}${workflow}/decision-services/${service.id}`, { headers }),
      )
    ).version_number,
  ).toBe(version3.version_number);
  for (const current of [page, next]) {
    expect(
      await current.evaluate(() =>
        [...Object.values(localStorage), ...Object.values(sessionStorage)].some((value) =>
          /access_token|refresh_token|Bearer /i.test(value),
        ),
      ),
    ).toBe(false);
    expect((await current.locator("body").innerText()).includes(internal)).toBe(false);
  }
  expect(observedRequests, "Browser traffic must actually be observed").toBeGreaterThan(0);
  expect(browserBoundaryLeak, "Internal credentials must never cross into browser HTTP").toBe(
    false,
  );
});
