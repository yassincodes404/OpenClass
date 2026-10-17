import {
  captureBaseline,
  captureProductBaseline,
  expect,
  expectNoHorizontalOverflow,
  mockKeycloak,
  PROJECT_ID,
  test,
  VISUAL_TOKEN,
} from "./support";

function isMobile(projectName: string) {
  return projectName === "mobile";
}

test("public landing captures the page and exercises scenario controls", async ({
  page,
}, testInfo) => {
  const keycloak = await mockKeycloak(page, false);
  await page.goto("/");

  await expect(
    page.getByRole("heading", { level: 1, name: /Make room for the unknown/i }),
  ).toBeVisible();
  await expect(page.getByText("SIMULATED WALKTHROUGH · NO PROVIDER CALLS")).toBeVisible();
  expect(keycloak.requestCount()).toBeGreaterThan(0);
  await expectNoHorizontalOverflow(page);
  await captureBaseline(page, testInfo, "landing");

  const knownScenario = page.getByRole("tab", { name: /01 \/ Known Intent/i });
  await knownScenario.click();
  await expect(knownScenario).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Ingest raw observation with idempotent provenance." }),
  ).toBeVisible();

  const commitStep = isMobile(testInfo.project.name)
    ? page.getByRole("button", { name: "Go to Fast Commit" })
    : page.getByRole("button", { name: /04 \/ COMMIT/i });
  await commitStep.click();
  await expect(
    page.getByRole("heading", {
      name: "Route to supported workflow on the synchronous fast path.",
    }),
  ).toBeVisible();

  const closedWorldBtn = page.getByRole("button", { name: "Closed-world guess" });
  await closedWorldBtn.click();
  await expect(closedWorldBtn).toHaveAttribute("aria-pressed", "true");
  const openWorldBtn = page.getByRole("button", { name: "Open-world" });
  await openWorldBtn.click();
  await expect(openWorldBtn).toHaveAttribute("aria-pressed", "true");
  await expectNoHorizontalOverflow(page);
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("public landing disables playback while retaining manual steps", async ({
    page,
  }, testInfo) => {
    await mockKeycloak(page, false);
    await page.goto("/");

    await expect(page.getByRole("button", { name: "Play walkthrough" })).toBeDisabled();
    await expect(page.getByText(/Reduced motion is on/)).toBeVisible();

    const governStep = isMobile(testInfo.project.name)
      ? page.getByRole("button", { name: "Go to Replay & Review Gate" })
      : page.getByRole("button", { name: /05 \/ GOVERN/i });
    await governStep.click();
    await expect(
      page.getByRole("heading", {
        name: "Gated by Verified Replay Evaluation (OC-008) & Human Approval (OC-009).",
      }),
    ).toBeVisible();
    await expect(page.locator("#open-world-loop")).toHaveAttribute("data-motion", "instant");
    await expectNoHorizontalOverflow(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await captureBaseline(page, testInfo, "landing-reduced-motion");
  });
});

test("route-mocked authenticated product journey covers dialogs and navigation", async ({
  page,
  control,
}, testInfo) => {
  const keycloak = await mockKeycloak(page, true);
  await page.goto("/projects");

  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Northwind Support/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Support Intent Router" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  expect(keycloak.requestCount()).toBeGreaterThan(0);
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "projects");

  const newProjectBtn = page.getByRole("button", { name: "+ New project" });
  await newProjectBtn.click();
  const createDialog = page.getByRole("dialog", { name: "Create project" });
  await expect(createDialog).toBeVisible();
  await expect(createDialog.getByLabel("Name", { exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(createDialog).toBeHidden();
  await expect(newProjectBtn).toBeFocused();

  await newProjectBtn.click();
  await expect(createDialog).toBeVisible();
  await createDialog.getByLabel("Name", { exact: true }).fill("Returns Triage");
  await createDialog
    .getByLabel(/Description/)
    .fill("Review return requests with explicit unknowns");
  await captureProductBaseline(page, testInfo, "project-create-dialog");
  await createDialog.getByRole("button", { name: "Create project" }).click();
  await expect(createDialog).toBeHidden();
  await expect(page.getByRole("heading", { name: "Returns Triage" })).toBeVisible();
  expect(control.createdProjectNames).toEqual(["Returns Triage"]);

  await page
    .locator("article.project-card")
    .filter({ hasText: "Support Intent Router" })
    .getByRole("link", { name: "Open project →" })
    .click();
  await expect(page).toHaveURL(`/projects/${PROJECT_ID}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "The decision system, in focus." }),
  ).toBeVisible();
  await expect(page.getByText("12.4%", { exact: true })).toBeVisible();
  await expect(page.getByText("oc_visual_fixture…", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "project-overview");

  const projectNav = page.getByRole("navigation", { name: "Project navigation" });
  await projectNav.getByRole("link", { name: "Classifiers", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${PROJECT_ID}/classifiers`);
  await expect(page.getByRole("heading", { level: 1, name: "Classifiers" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Support intent" })).toBeVisible();
  await expect(page.getByText("UNKNOWN — locked", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "classifiers");

  await projectNav.getByRole("link", { name: "Unknowns", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${PROJECT_ID}/unknowns`);
  await expect(page.getByRole("heading", { level: 1, name: "Unknowns" })).toBeVisible();
  await expect(page.locator(".metrics")).toContainText("17");
  await expect(page.getByText("Can I export last year's invoices?", { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "unknowns");

  const unknownRow = page
    .getByRole("row")
    .filter({ hasText: "Can I export last year's invoices?" });
  await unknownRow.focus();
  await page.keyboard.press("Enter");
  const unknownDialog = page.getByRole("dialog", { name: "UNKNOWN detail" });
  await expect(unknownDialog).toBeVisible();
  await expect(unknownDialog.getByText(/reason: strong_unknown_probability/)).toBeVisible();
  await expect(unknownDialog.getByLabel("Bounded probability readout")).toBeVisible();
  await captureProductBaseline(page, testInfo, "unknown-detail-dialog");
  await page.keyboard.press("Escape");
  await expect(unknownDialog).toBeHidden();
  await expect(unknownRow).toBeFocused();

  await projectNav.getByRole("link", { name: "Analytics", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${PROJECT_ID}/analytics`);
  await expect(page.getByRole("heading", { level: 1, name: "Analytics" })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "Is the system healthy?" }),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "analytics");

  await projectNav.getByRole("link", { name: "Ontology", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${PROJECT_ID}/ontology`);
  await expect(page.getByRole("heading", { level: 1, name: "Ontology" })).toBeVisible();
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "vN never changes; rollback creates a new version.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: "Ontology version lineage" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await captureProductBaseline(page, testInfo, "ontology");

  expect(control.requests.length).toBeGreaterThan(0);
  expect(
    control.requests.every((request) => request.authorization === `Bearer ${VISUAL_TOKEN}`),
  ).toBe(true);
});
