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

vi.mock("keycloak-js", () => ({
  default: function MockKeycloak() {
    return keycloak;
  },
}));

const workspaces = [{ id: "w-1", slug: "acme-support", name: "Acme Support", role: "owner" }];

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(status: number, body: unknown) {
  return vi.fn(async () => jsonResponse(status, body));
}

/** Control-plane stub: workspaces → given payload; nested project lists → empty. */
function stubControl(workspacesBody: unknown, status = 200) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("/projects")) return jsonResponse(status === 200 ? 200 : status, []);
    return jsonResponse(status, workspacesBody);
  });
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
  vi.stubGlobal("fetch", stubControl(workspaces));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("portal auth gate", () => {
  it("shows the sign-in gate for anonymous visitors with no workspace data leak", async () => {
    const fetchMock = stubControl(workspaces);
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
    const fetchMock = stubControl(workspaces);
    vi.stubGlobal("fetch", fetchMock);
    keycloak.init.mockResolvedValue(true);
    renderPortal();
    expect(await screen.findByText("Acme Support")).toBeTruthy();
    expect(screen.getByText("Sign out")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/control/workspaces", {
      headers: { Authorization: "Bearer local-test-token" },
    });
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
    vi.stubGlobal("fetch", stubControl({ message: "Authentication required" }, 401));
    keycloak.init.mockResolvedValue(true);
    renderPortal();
    expect(
      await screen.findByText("Sign in to your workspace.", {}, { timeout: 3000 }),
    ).toBeTruthy();
    expect(screen.queryByText("Sign out")).toBeNull();
  });

  it("renders authenticated navigation with user email workspace context and Sign out button", async () => {
    vi.stubGlobal(
      "fetch",
      stubControl([
        {
          id: "w-1",
          slug: "acme-support",
          name: "Acme Support (ops@acme.io)",
          role: "owner",
        },
      ]),
    );
    keycloak.init.mockResolvedValue(true);
    renderPortal("/projects");

    expect(await screen.findByText("Acme Support (ops@acme.io)")).toBeTruthy();
    expect(screen.getByText(/ops@acme\.io/i)).toBeTruthy();
    const signOutBtn = screen.getByRole("button", { name: "Sign out" });
    expect(signOutBtn).toBeTruthy();
    expect(screen.getByRole("link", { name: "Home" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Projects" })).toBeTruthy();
  });
});

describe("portal landing page (Precision Observatory)", () => {
  it("renders the open-world hero, comparison trace, and interactive loop stage at '/'", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");
    expect(screen.getByText(/Start with what you know\./i)).toBeTruthy();
    expect(screen.getByText("Open workspace ↗")).toBeTruthy();
    expect(screen.getByText("Selects UNKNOWN (0.950) → Evidence Pool")).toBeTruthy();
    expect(
      screen.getByRole("region", {
        name: /Interactive open-world decision and governed discovery architecture/i,
      }),
    ).toBeTruthy();
  });

  it("allows switching interactive observation presets and scrubbing lifecycle steps", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");

    // Default preset is 02 / Novel Concept ("Cancel my plan")
    expect(
      screen.getByText("Unfamiliar request enters Ontology v1 (billing, technical, sales)."),
    ).toBeTruthy();

    // Scrub directly to Step 05 (Replay & Review Gate)
    fireEvent.click(screen.getByRole("button", { name: /05 \/ GOVERN/i }));
    expect(
      screen.getByText("Gated by Verified Replay Evaluation (OC-008) & Human Approval (OC-009)."),
    ).toBeTruthy();

    // Switch to Preset 01: Known Intent ("I was charged twice for my monthly invoice")
    fireEvent.click(screen.getByRole("tab", { name: /01 \/ Known Intent/i }));
    expect(screen.getByText("Ingest raw observation with idempotent provenance.")).toBeTruthy();

    // Switch to Preset 04: Provider Outage ("Upstream 502 Bad Gateway / Inference Timeout")
    fireEvent.click(screen.getByRole("tab", { name: /04 \/ Provider Outage/i }));
    expect(
      screen.getByText("Observation enters pipeline during an upstream model outage."),
    ).toBeTruthy();
  });

  it("renders all 4 observation presets in OpenWorldLoopStage, switches presets when clicked, and updates active stage telemetry", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");

    const presetChargedTwice = screen.getByRole("tab", { name: /I was charged twice/i });
    const presetCancelPlan = screen.getByRole("tab", { name: /Cancel my plan/i });
    const presetComplianceAudit = screen.getByRole("tab", {
      name: /Export compliance packet for EU.*audit/i,
    });
    const presetUpstream502 = screen.getByRole("tab", { name: /Upstream 502.*Timeout/i });

    expect(presetChargedTwice).toBeTruthy();
    expect(presetCancelPlan).toBeTruthy();
    expect(presetComplianceAudit).toBeTruthy();
    expect(presetUpstream502).toBeTruthy();

    // Default active preset is "Cancel my plan"
    expect(presetCancelPlan.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("OBSERVED → CHECKING COVERAGE")).toBeTruthy();
    expect(screen.getByText("likely novel")).toBeTruthy();

    // Click Preset 1 ("I was charged twice") and verify telemetry updates
    fireEvent.click(presetChargedTwice);
    expect(presetChargedTwice.getAttribute("aria-selected")).toBe("true");
    expect(presetCancelPlan.getAttribute("aria-selected")).toBe("false");
    expect(screen.getByText("INGESTED → PINNED TO v1")).toBeTruthy();
    expect(
      screen.getByText("Raw source event is immutable; predictions never overwrite input."),
    ).toBeTruthy();

    // Click Preset 3 ("Export compliance packet for EU invoice audit") and verify telemetry updates
    fireEvent.click(presetComplianceAudit);
    expect(presetComplianceAudit.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("OBSERVED → BOUNDARY TEST")).toBeTruthy();
    expect(screen.getByText("ambiguous review")).toBeTruthy();
    expect(
      screen.getByText("Supervision policy monitors top-2 class margin on every run."),
    ).toBeTruthy();

    // Click Preset 4 ("Upstream 502 Bad Gateway / Inference Timeout") and verify telemetry updates
    fireEvent.click(presetUpstream502);
    expect(presetUpstream502.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("DISPATCHING TO PROVIDER")).toBeTruthy();
    expect(screen.getByText("provider error")).toBeTruthy();
    expect(screen.getByText("∑ P = N/A (FAULT)")).toBeTruthy();
  });

  it("toggles Play/Pause aria-pressed state and switches all 5 stage scrubber buttons", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");

    const playPauseButton = screen.getByRole("button", { name: /Pause trace|Auto-trace/i });
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("true");

    // Click to pause
    fireEvent.click(playPauseButton);
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("false");
    expect(playPauseButton.textContent).toContain("Auto-trace");

    // Click to resume playing
    fireEvent.click(playPauseButton);
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("true");
    expect(playPauseButton.textContent).toContain("Pause trace");

    // Verify all 5 stage scrubber buttons switch steps and update telemetry
    const stepButtons = [
      {
        pattern: /01 \/ OBSERVE/i,
        badge: "OBSERVED → CHECKING COVERAGE",
      },
      {
        pattern: /02 \/ SCORE/i,
        badge: "ABSTAINED → PERMANENT UNKNOWN",
      },
      {
        pattern: /03 \/ EVIDENCE/i,
        badge: "STORED IN EVIDENCE POOL",
      },
      {
        pattern: /04 \/ TEACHER/i,
        badge: "CANDIDATE PROPOSED (INACTIVE)",
      },
      {
        pattern: /05 \/ GOVERN/i,
        badge: "HELD AT REPLAY & HUMAN GATE",
      },
    ];

    for (const [idx, stepSpec] of stepButtons.entries()) {
      const btn = screen.getByRole("button", { name: stepSpec.pattern });
      fireEvent.click(btn);
      expect(btn.getAttribute("aria-pressed")).toBe("true");
      expect(playPauseButton.getAttribute("aria-pressed")).toBe("false");
      expect(screen.getByText(stepSpec.badge)).toBeTruthy();
      expect(screen.getByText(new RegExp(`STEP ${idx + 1} \\/ 5`, "i"))).toBeTruthy();
    }
  });

  it("switches grounded proof scenarios and developer quickstart tabs", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");

    // Switch proof scenario tab to DevOps Port-Conflict Recovery Macro
    fireEvent.click(screen.getByRole("tab", { name: /02 \/ DEVOPS RECOVERY MACRO/i }));
    expect(screen.getByText("Bounded Macro Synthesis")).toBeTruthy();

    // Switch quickstart tab to TypeScript SDK
    fireEvent.click(screen.getByRole("tab", { name: /TypeScript SDK/i }));
    expect(screen.getByText(/Trigger an advisory Supervisor review/i)).toBeTruthy();
  });
});

