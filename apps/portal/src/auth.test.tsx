import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";

const { keycloak } = vi.hoisted(() => ({
  keycloak: {
    init: vi.fn<() => Promise<boolean>>(),
    login: vi.fn(),
    logout: vi.fn(),
    token: undefined,
  },
}));

vi.mock("keycloak-js", () => ({
  default: function MockKeycloak() {
    return keycloak;
  },
}));

function Session() {
  const auth = useAuth();
  return (
    <output>{!auth.ready ? "Loading" : auth.authenticated ? "Authenticated" : "Signed out"}</output>
  );
}

function renderAuth() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Session />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.history.replaceState(null, "", "/projects/project-1/runs");
  keycloak.init.mockReset().mockResolvedValue(false);
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("portal SSO initialization", () => {
  it("checks the existing Keycloak session when a fresh page initializes", async () => {
    keycloak.init.mockResolvedValueOnce(true);
    renderAuth();
    await screen.findByText("Authenticated");
    expect(keycloak.init).toHaveBeenCalledWith(
      expect.objectContaining({
        onLoad: "check-sso",
        pkceMethod: "S256",
        checkLoginIframe: false,
      }),
    );
  });

  it("stays signed out when Keycloak finds no existing session", async () => {
    renderAuth();
    await screen.findByText("Signed out");
    expect(screen.queryByText("Authenticated")).toBeNull();
  });

  it("does not start an SSO redirect on the public landing page", async () => {
    window.history.replaceState(null, "", "/");
    renderAuth();
    await screen.findByText("Signed out");
    expect(keycloak.init).toHaveBeenCalledWith(
      expect.objectContaining({ onLoad: undefined, pkceMethod: "S256" }),
    );
  });
});
