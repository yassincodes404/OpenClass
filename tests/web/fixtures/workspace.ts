import { test as base, expect, type Page } from "@playwright/test";
import type { Project } from "@openclass/sdk";

// Simulated HTTP contracts only, not E2E or identity-provider proof.
export const WORKSPACE_ID = "99999999-9999-4999-8999-999999999999";
export const CONTROL_PROJECT_ID = "88888888-8888-4888-8888-888888888888";
export const PROJECTS_ROUTE = `**/control/workspaces/${WORKSPACE_ID}/projects`;
export const WORKFLOW_ROUTE = `${PROJECTS_ROUTE}/${CONTROL_PROJECT_ID}/workflow`;

type ProjectMetadata = Pick<Project, "id" | "slug" | "name" | "created_at">;

export function projectMapping(project: ProjectMetadata) {
  return {
    id: CONTROL_PROJECT_ID,
    workspace_id: WORKSPACE_ID,
    engine_project_id: project.id,
    slug: project.slug,
    name: project.name,
    created_at: project.created_at,
  };
}

export async function mockWorkspaceProject(page: Page, project: ProjectMetadata) {
  const mapping = projectMapping(project);
  await page.route("**/control/projects/*", (route) => {
    const identifier = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").pop()!,
    );
    return [project.id, project.slug, mapping.id].includes(identifier)
      ? route.fulfill({ json: mapping })
      : route.fulfill({ status: 404, json: { message: "Route-mocked project not found" } });
  });
  await page.route(PROJECTS_ROUTE, (route) => route.fulfill({ json: [mapping] }));
  await page.route(WORKFLOW_ROUTE, (route) =>
    route.fulfill({ json: { ...project, workspace_id: WORKSPACE_ID } }),
  );
}

export const test = base.extend<{ routeMockedWorkspace: void }>({
  routeMockedWorkspace: [
    async ({ page }, use) => {
      const unmockedControlRequests: string[] = [];
      const unauthorizedControlRequests: string[] = [];
      page.on("request", (request) => {
        if (
          new URL(request.url()).pathname.startsWith("/control/") &&
          request.headers().authorization !== "Bearer route-mocked-synthetic-session"
        ) {
          unauthorizedControlRequests.push(`${request.method()} ${request.url()}`);
        }
      });
      await page.addInitScript(() => {
        (window as unknown as Record<string, unknown>).__OPENCLASS_ROUTE_MOCKED_SESSION__ = {
          token: "route-mocked-synthetic-session",
        };
      });
      // Fail closed: no unhandled control-plane request contacts a live service.
      await page.route("**/control/**", (route) => {
        unmockedControlRequests.push(`${route.request().method()} ${route.request().url()}`);
        return route.fulfill({ status: 404, json: { message: "Control route not mocked" } });
      });
      await page.route("**/control/workspaces", (route) => {
        expect(route.request().headers().authorization).toBe(
          "Bearer route-mocked-synthetic-session",
        );
        return route.fulfill({
          json: [
            { id: WORKSPACE_ID, name: "Simulated workspace", slug: "simulated", role: "admin" },
          ],
        });
      });
      await use();
      expect(unmockedControlRequests, "Every simulated control request needs a contract").toEqual(
        [],
      );
      expect(unauthorizedControlRequests, "Control requests must use the session bearer").toEqual(
        [],
      );
    },
    { auto: true },
  ],
});

export { expect };
