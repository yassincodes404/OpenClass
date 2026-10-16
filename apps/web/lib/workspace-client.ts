import { OpenClassControlClient, OpenClassWorkspaceClient } from "@openclass/sdk";

// Memory only. Identity and roles are always verified by the control plane.
let token: string | undefined;
let workspaceId: string | undefined;
export function setWorkspaceSession(value?: string, workspace?: string) {
  token = value;
  workspaceId = workspace;
}
export const workspaceClient = new OpenClassWorkspaceClient(
  new OpenClassControlClient("/control"),
  () => token,
  () => workspaceId,
);

// Route-mocked browser checks only (tests/web/project-workflows.spec.ts).
// This never grants real access: the control plane validates the bearer token
// on every request. It only lets Playwright render the authenticated shell
// without a live identity provider. Never set outside route-mocked tests.
export function routeMockedSession(): { token: string; workspace?: string } | undefined {
  if (typeof window === "undefined") return undefined;
  return (
    window as unknown as {
      __OPENCLASS_ROUTE_MOCKED_SESSION__?: { token: string; workspace?: string };
    }
  ).__OPENCLASS_ROUTE_MOCKED_SESSION__;
}
