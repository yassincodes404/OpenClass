import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { DecisionSpecimen } from "./decision-specimen";
import { Dialog } from "./dialog";
import {
  OpenWorldLoopStage,
  PREDEFINED_SCENARIOS,
  deriveScenarioDistribution,
} from "./open-world-stage";
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
  vi.useRealTimers();
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
    expect(
      screen.getByRole("heading", { level: 1, name: /Make room for the unknown/i }),
    ).toBeTruthy();
    const callsToAction = screen.getAllByRole("link", { name: "Open workspace ↗" });
    expect(callsToAction.length).toBe(2);
    expect(callsToAction.every((link) => link.getAttribute("href") === "/projects")).toBe(true);
    expect(
      within(
        screen.getByRole("complementary", { name: "Simulated classification example" }),
      ).getByText("UNKNOWN"),
    ).toBeTruthy();
    expect(screen.getByText("SIMULATED WALKTHROUGH · NO PROVIDER CALLS")).toBeTruthy();
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
      screen.getByRole("heading", {
        name: "Unfamiliar request enters Ontology v1 (billing, technical, sales).",
      }),
    ).toBeTruthy();

    // Scrub directly to Step 05 (Replay & Review Gate)
    fireEvent.click(screen.getByRole("button", { name: /05 \/ GOVERN/i }));
    expect(
      screen.getByRole("heading", {
        name: "Gated by Verified Replay Evaluation (OC-008) & Human Approval (OC-009).",
      }),
    ).toBeTruthy();

    // Switch to Preset 01: Known Intent ("I was charged twice for my monthly invoice")
    fireEvent.click(screen.getByRole("tab", { name: /01 \/ Known Intent/i }));
    expect(
      screen.getByRole("heading", { name: "Ingest raw observation with idempotent provenance." }),
    ).toBeTruthy();

    // Switch to Preset 04: Provider Outage ("Upstream 502 Bad Gateway / Inference Timeout")
    fireEvent.click(screen.getByRole("tab", { name: /04 \/ Provider Outage/i }));
    expect(
      screen.getByRole("heading", {
        name: "Observation enters pipeline during an upstream model outage.",
      }),
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
    expect(screen.getAllByText("OBSERVED → CHECKING COVERAGE").length).toBeGreaterThan(0);
    expect(screen.getByText("likely novel")).toBeTruthy();

    // Click Preset 1 ("I was charged twice") and verify telemetry updates
    fireEvent.click(presetChargedTwice);
    expect(presetChargedTwice.getAttribute("aria-selected")).toBe("true");
    expect(presetCancelPlan.getAttribute("aria-selected")).toBe("false");
    expect(screen.getAllByText("INGESTED → PINNED TO v1").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Raw source event is immutable; predictions never overwrite input."),
    ).toBeTruthy();

    // Click Preset 3 ("Export compliance packet for EU invoice audit") and verify telemetry updates
    fireEvent.click(presetComplianceAudit);
    expect(presetComplianceAudit.getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByText("OBSERVED → BOUNDARY TEST").length).toBeGreaterThan(0);
    expect(screen.getByText("ambiguous review")).toBeTruthy();
    expect(
      screen.getByText("Supervision policy monitors top-2 class margin on every run."),
    ).toBeTruthy();

    // Click Preset 4 ("Upstream 502 Bad Gateway / Inference Timeout") and verify telemetry updates
    fireEvent.click(presetUpstream502);
    expect(presetUpstream502.getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByText("DISPATCHING TO PROVIDER").length).toBeGreaterThan(0);
    expect(screen.getByText("provider error")).toBeTruthy();
    expect(screen.getByText("∑ P = N/A (FAULT)")).toBeTruthy();
  });

  it("toggles Play/Pause aria-pressed state and switches all 5 stage scrubber buttons", () => {
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");

    const playPauseButton = screen.getByRole("button", { name: /Play walkthrough/i });
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("false");

    // Playback requires an explicit choice, rather than running on page load.
    fireEvent.click(playPauseButton);
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("true");
    expect(playPauseButton.textContent).toContain("Pause walkthrough");

    // Pause, then resume.
    fireEvent.click(playPauseButton);
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(playPauseButton);
    expect(playPauseButton.getAttribute("aria-pressed")).toBe("true");
    expect(playPauseButton.textContent).toContain("Pause walkthrough");

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
      expect(screen.getAllByText(stepSpec.badge).length).toBeGreaterThan(0);
      expect(screen.getAllByText(new RegExp(`STEP ${idx + 1} \\/ 5`, "i")).length).toBeGreaterThan(
        0,
      );
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

  it("supports mobile step cards and bounded previous/next navigation", () => {
    render(<OpenWorldLoopStage />);
    const mobile = within(screen.getByRole("list", { name: "Mobile decision loop" }));
    const steps = mobile.getAllByRole("button");
    expect(steps).toHaveLength(5);
    expect(steps[0]!.getAttribute("aria-current")).toBe("step");
    expect(screen.getByRole("button", { name: "Previous" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(steps[4]!);
    expect(steps[4]!.getAttribute("aria-current")).toBe("step");
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(steps[3]!.getAttribute("aria-current")).toBe("step");
    expect(
      screen.getByRole("button", { name: "Play walkthrough" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("advances during explicit playback and stops when a scenario or step is selected", () => {
    vi.useFakeTimers();
    render(<OpenWorldLoopStage />);
    const play = screen.getByRole("button", { name: "Play walkthrough" });
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByRole("button", { name: /01 \/ OBSERVE/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(play);
    act(() => vi.advanceTimersByTime(2800));
    expect(screen.getByRole("button", { name: /02 \/ SCORE/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: /Known Intent/ }));
    expect(play.getAttribute("aria-pressed")).toBe("false");
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByRole("button", { name: /01 \/ OBSERVE/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(play);
    fireEvent.click(screen.getByRole("button", { name: /03 \/ POLICY/ }));
    act(() => vi.advanceTimersByTime(6000));
    expect(play.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: /03 \/ POLICY/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("uses roving keyboard scenario tabs without animating keyboard navigation", () => {
    const { container } = render(<OpenWorldLoopStage />);
    const initial = screen.getByRole("tab", { name: /Novel Concept/ });
    initial.focus();
    fireEvent.keyDown(initial, { key: "ArrowRight" });
    const review = screen.getByRole("tab", { name: /Ambiguous Margin/ });
    expect(document.activeElement).toBe(review);
    expect(review.getAttribute("aria-selected")).toBe("true");
    expect(initial.getAttribute("tabindex")).toBe("-1");
    expect(container.querySelector("[data-motion]")?.getAttribute("data-motion")).toBe("instant");
    fireEvent.keyDown(review, { key: "Home" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: /Known Intent/ }));
  });

  it("finishes playback once and keeps keyboard play, pause and replay instant", () => {
    vi.useFakeTimers();
    const { container } = render(<OpenWorldLoopStage />);
    const play = screen.getByRole("button", { name: "Play walkthrough" });
    fireEvent.click(play, { detail: 0 });
    expect(container.querySelector("[data-motion]")?.getAttribute("data-motion")).toBe("instant");
    for (let tick = 0; tick < 5; tick += 1) act(() => vi.advanceTimersByTime(2800));
    expect(play.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: /05 \/ GOVERN/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(play, { detail: 0 });
    expect(screen.getByRole("button", { name: /01 \/ OBSERVE/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(container.querySelector("[data-motion]")?.getAttribute("data-motion")).toBe("instant");
    fireEvent.click(play, { detail: 0 });
    expect(play.getAttribute("aria-pressed")).toBe("false");
  });

  it("pauses for payload inspection and preserves the disclosure across step changes", () => {
    vi.useFakeTimers();
    render(<OpenWorldLoopStage />);
    const play = screen.getByRole("button", { name: "Play walkthrough" });
    fireEvent.click(play);
    const summary = screen.getByText("Inspect the example payload");
    act(() => summary.focus());
    expect(play.getAttribute("aria-pressed")).toBe("false");
    expect(document.activeElement).toBe(summary);
    const disclosure = summary.closest("details")!;
    disclosure.open = true;
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Inspect the example payload")).toBe(summary);
    expect(disclosure.open).toBe(true);
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByRole("button", { name: /02 \/ SCORE/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("disables automatic playback for reduced motion but keeps every manual step available", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    render(<OpenWorldLoopStage />);
    expect(screen.getByRole("button", { name: "Play walkthrough" }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(screen.getByText(/Reduced motion is on/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /05 \/ GOVERN/ }));
    expect(screen.getByRole("button", { name: /05 \/ GOVERN/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("reports clipboard failures rather than claiming a snippet was copied", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("Denied")) },
    });
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");
    fireEvent.click(screen.getByRole("button", { name: "Copy snippet" }));
    expect(
      await screen.findByText("Clipboard unavailable. Select the code to copy it."),
    ).toBeTruthy();
    expect(screen.queryByText("Snippet copied.")).toBeNull();
  });

  it("ignores pending copy completion after switching snippets", async () => {
    let complete!: () => void;
    const pending = new Promise<void>((resolve) => {
      complete = resolve;
    });
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn(() => pending) } });
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");
    fireEvent.click(screen.getByRole("button", { name: "Copy snippet" }));
    fireEvent.click(screen.getByRole("tab", { name: "TypeScript SDK" }));
    await act(async () => {
      complete();
      await pending;
    });
    expect(screen.queryByText("Snippet copied.")).toBeNull();
    expect(screen.getByRole("button", { name: "Copy snippet" })).toBeTruthy();
  });

  it("ignores an older copy failure after a newer successful request", async () => {
    let fail!: (reason: Error) => void;
    const pending = new Promise<void>((_resolve, reject) => {
      fail = reject;
    });
    const writeText = vi
      .fn()
      .mockImplementationOnce(() => pending)
      .mockResolvedValueOnce(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    keycloak.init.mockResolvedValue(false);
    renderPortal("/");
    const copy = screen.getByRole("button", { name: "Copy snippet" });
    fireEvent.click(copy);
    fireEvent.click(copy);
    expect(await screen.findByText("Snippet copied.")).toBeTruthy();
    await act(async () => {
      fail(new Error("Old request denied"));
    });
    expect(screen.getByText("Snippet copied.")).toBeTruthy();
    expect(screen.queryByText("Clipboard unavailable. Select the code to copy it.")).toBeNull();
  });

  it("does not attribute UNKNOWN probabilities to a candidate or predict unmeasured improvement", () => {
    const unknown = PREDEFINED_SCENARIOS.find((scenario) => scenario.id === "unknown_cancel")!;
    expect(unknown.steps[3].telemetry.topClass).toMatch(/^UNKNOWN \(0\.950\)/);
    expect(unknown.steps[4].telemetry.topClass).toContain("awaiting verified replay");
    expect(unknown.steps[4].telemetry.unknownProb).not.toContain("<0.050");
    expect(unknown.steps[4].telemetry.unknownProbability).toBe(0.95);
  });

  it("enforces probability bar, telemetry readout, and top-2 margin consistency across all 4 scenarios and all 5 steps", () => {
    const knownDist = deriveScenarioDistribution({
      billing: 0.9,
      technical: 0.033,
      sales: 0.017,
      UNKNOWN: 0.05,
    });
    expect(knownDist.topLabel).toBe("billing");
    expect(knownDist.topProbability).toBe(0.9);
    expect(knownDist.topDisplay).toBe("0.900");
    expect(knownDist.unknownProbability).toBe(0.05);
    expect(knownDist.unknownDisplay).toBe("0.050");
    expect(knownDist.topMargin).toBe(0.85);
    expect(knownDist.topMarginDisplay).toBe("0.850");

    expect(PREDEFINED_SCENARIOS.length).toBe(4);
    for (const scenario of PREDEFINED_SCENARIOS) {
      expect(scenario.steps.length).toBe(5);
      for (const step of scenario.steps) {
        const sortedProbs = [...step.probabilities].sort((a, b) => b.value - a.value);
        const topBar = sortedProbs[0]!;
        const secondBar = sortedProbs[1]!;
        const unknownBar = step.probabilities.find((p) => p.isUnknown || p.label === "UNKNOWN")!;

        if (step.telemetry.topProbability !== null) {
          expect(topBar.value.toFixed(3)).toBe(step.telemetry.topProbability.toFixed(3));
          expect(topBar.display).toBe(step.telemetry.topProbability.toFixed(3));
        }

        expect(unknownBar.value.toFixed(3)).toBe(step.telemetry.unknownProbability.toFixed(3));
        if (scenario.id !== "error_timeout") {
          expect(unknownBar.display).toBe(step.telemetry.unknownProbability.toFixed(3));
        }

        const expectedMargin = Number((topBar.value - secondBar.value).toFixed(3));
        expect(step.telemetry.topMargin).toBe(expectedMargin);
      }
    }

    render(<OpenWorldLoopStage />);

    // Verify "I was charged twice" displays 0.900 in both probability bar and telemetry readout across all 5 steps
    fireEvent.click(screen.getByRole("tab", { name: /I was charged twice/i }));
    for (let idx = 0; idx < 5; idx += 1) {
      const stepBtns = screen.getAllByRole("button", { name: /^0[1-5] \//i });
      fireEvent.click(stepBtns[idx]!);
      const matches0900 = screen.getAllByText(/0\.900/);
      expect(matches0900.length).toBeGreaterThanOrEqual(2);
      expect(screen.getAllByText(/0\.850/).length).toBeGreaterThanOrEqual(1);
    }

    // Verify "Export compliance packet for EU audit" displays 0.410 and 0.140 margin consistently across all 5 steps
    fireEvent.click(screen.getByRole("tab", { name: /Export compliance packet for EU.*audit/i }));
    for (let idx = 0; idx < 5; idx += 1) {
      const stepBtns = screen.getAllByRole("button", { name: /^0[1-5] \//i });
      fireEvent.click(stepBtns[idx]!);
      const matches0410 = screen.getAllByText(/0\.410/);
      expect(matches0410.length).toBeGreaterThanOrEqual(2);
      expect(screen.getAllByText(/0\.140/).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("toggles DecisionSpecimen between Open-world abstention and Closed-world forced guess", () => {
    render(<DecisionSpecimen />);
    const openBtn = screen.getByRole("button", { name: "Open-world" });
    const closedBtn = screen.getByRole("button", { name: "Closed-world guess" });
    expect(openBtn.getAttribute("aria-pressed")).toBe("true");
    expect(closedBtn.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText("UNKNOWN")).toBeTruthy();

    fireEvent.click(closedBtn);
    expect(openBtn.getAttribute("aria-pressed")).toBe("false");
    expect(closedBtn.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/billing \(forced\)/i)).toBeTruthy();

    fireEvent.click(openBtn);
    expect(openBtn.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
  });

  it("traps focus, closes on Escape, and restores focus to the trigger when Dialog unmounts", () => {
    const onClose = vi.fn();
    const trigger = document.createElement("button");
    trigger.textContent = "Launch dialog";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render(
      <Dialog label="Test accessible dialog" onClose={onClose}>
        <input aria-label="First field" />
        <button type="button">Second action</button>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog", { name: "Test accessible dialog" });
    const firstInput = within(dialog).getByLabelText("First field");
    const secondBtn = within(dialog).getByRole("button", { name: "Second action" });
    expect(document.activeElement).toBe(firstInput);

    secondBtn.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(firstInput);

    firstInput.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(secondBtn);

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});
