import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { EvidencePage } from "./evidence-page";

vi.mock("./auth", () => ({
  useAuth: () => ({ ready: true, authenticated: true, token: () => "simulated-session" }),
}));
vi.mock("./projects", () => ({
  ProjectShell: ({ children }: { children: ReactNode }) => children,
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const item = {
  id: "e1",
  status: "pending",
  trigger_type: "semantic_unknown",
  selected_choice: "UNKNOWN",
  decision_service_id: "s1",
  diagnosis: null,
  diagnosis_rationale: null,
};
function mount() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={["/projects/p1/evidence"]}>
        <Routes>
          <Route path="/projects/:projectId/evidence" element={<EvidencePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("portal evidence HTTP workflow", () => {
  it("retains simulated advisory after refetch and triages only after human submission", async () => {
    let diagnosed = false;
    const mutations: Array<{ path: string; body: unknown }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const prefix = "/control/workspaces/w1/projects/p1/workflow";
      const json = (data: unknown) => Response.json(data);
      if (init?.method && init.method !== "GET") {
        mutations.push({ path, body: init.body ? JSON.parse(String(init.body)) : undefined });
      }
      if (path === "/control/projects/p1")
        return json({ id: "p1", workspace_id: "w1", engine_project_id: "engine1" });
      if (path === `${prefix}/evidence`) return json([item]);
      if (path.startsWith(`${prefix}/evidence?`)) return json([item]);
      if (path === `${prefix}/evidence/e1`)
        return json({ ...item, human_note: diagnosed ? "Refreshed note" : null });
      if (path === `${prefix}/evidence/e1/ai-diagnose`) {
        diagnosed = true;
        return json({
          diagnosis: "ambiguous_or_insufficient",
          rationale: "Simulated advisory rationale",
          provider: "test",
          model: "simulated",
          confidence: 0.5,
          simulated: true,
        });
      }
      if (path === `${prefix}/evidence/e1/triage`) return json(item);
      return json([]);
    });
    vi.stubGlobal("fetch", fetcher);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /semantic_unknown/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Request advisory diagnosis" }));
    await screen.findByRole("complementary", { name: "Advisory diagnosis" });
    await screen.findByText("Refreshed note");
    expect(screen.getByText("Simulated advisory rationale")).toBeTruthy();
    expect(screen.getByText(/simulated · confidence/)).toBeTruthy();
    expect(mutations).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Use as editable triage draft" }));
    expect(screen.getByLabelText("Human rationale")).toHaveProperty(
      "value",
      "Simulated advisory rationale",
    );
    fireEvent.click(screen.getByRole("button", { name: "Save human triage" }));
    await waitFor(() => expect(mutations).toHaveLength(2));
    expect(mutations[1]).toEqual({
      path: "/control/workspaces/w1/projects/p1/workflow/evidence/e1/triage",
      body: { diagnosis: "ambiguous_or_insufficient", rationale: "Simulated advisory rationale" },
    });
    expect(mutations.some((mutation) => /promote|transition/.test(mutation.path))).toBe(false);
  });

  it("does not query workflow resources after a denied project resolution", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ message: "Project not found" }, { status: 404 }),
    );
    vi.stubGlobal("fetch", fetcher);
    mount();
    expect((await screen.findByRole("alert")).textContent).toBe("Project not found");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
