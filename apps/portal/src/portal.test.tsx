import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { Portal } from "./portal";

const { keycloak } = vi.hoisted(() => ({
  keycloak: {
    init: vi.fn<() => Promise<boolean>>(),
    login: vi.fn(),
    logout: vi.fn<() => Promise<void>>(),
    token: "local-test-token",
  },
}));

vi.mock("keycloak-js", () => ({ default: function MockKeycloak() { return keycloak; } }));

const workspaces = [
  { id: "w-1", slug: "acme-support", name: "Acme Support", role: "owner" },
];

function stubFetch(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderPortal(route = "/projects") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={[route]}>
          <Portal />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.stubGlobal("fetch", stubFetch(200, workspaces));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("portal auth gate", () => {
  it("shows the sign-in gate for anonymous visitors with no workspace data leak", async () => {
    const fetchMock = stubFetch(200, workspaces);
    vi.stubGlobal("fetch", fetchMock);
    keycloak.init.mockResolvedValue(false);
    renderPortal();
    expect(await screen.findByText("Sign in to your workspace.")).toBeTruthy();
    expect(screen.getByText("Continue with Keycloak ↗")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the checking state before Keycloak resolves", () => {
    keycloak.init.mockReturnValue(new Promise(() => {}));
    renderPortal();
    expect(screen.getByText("Checking secure session…")).toBeTruthy();
  });

  it("lists workspaces with bearer token once authenticated", async () => {
    const fetchMock = stubFetch(200, workspaces);
    vi.stubGlobal("fetch", fetchMock);
    keycloak.init.mockResolvedValue(true);
    renderPortal();
    expect(await screen.findByText("Acme Support")).toBeTruthy();
    expect(screen.getByText("Sign out")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/control/workspaces", { headers: { Authorization: "Bearer local-test-token" } });
  });

  it("returns to the gate after sign out", async () => {
    keycloak.init.mockResolvedValue(true);
    keycloak.logout.mockResolvedValue();
    renderPortal();
    await screen.findByText("Acme Support");
    fireEvent.click(screen.getByText("Sign out"));
    expect(await screen.findByText("Sign in to your workspace.")).toBeTruthy();
    expect(keycloak.logout).toHaveBeenCalled();
  });

  it("recovers to the gate without crashing when the session 401s", async () => {
    vi.stubGlobal("fetch", stubFetch(401, { message: "Authentication required" }));
    keycloak.init.mockResolvedValue(true);
    renderPortal();
    expect(await screen.findByText("Sign in to your workspace.", {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.queryByText("Sign out")).toBeNull();
  });
});
