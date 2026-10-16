import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DecisionService, OpenClass, ReplayEvaluation } from "@openclass/sdk";
import { OpenClassControlClient, OpenClassWorkspaceClient } from "@openclass/sdk";
import { GraphEditor } from "./graph-editor";
import { ReplayResult, ReplayWorkspace } from "./replay-workspace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const service = {
  id: "service",
  instructions: "Route requests",
  version_number: 1,
  nodes: [
    {
      id: "entry",
      name: "Entry",
      instructions: "Route requests",
      choices: [
        { key: "CONTINUE", label: "Continue", description: "", target_node_id: "next" },
        { key: "UNKNOWN", label: "Unknown", description: "" },
      ],
    },
    {
      id: "next",
      name: "Next",
      instructions: "Handle request",
      choices: [
        { key: "DONE", label: "Done", description: "" },
        { key: "UNKNOWN", label: "Unknown", description: "" },
      ],
    },
  ],
  transitions: [],
} as unknown as DecisionService;

describe("shared workflow forms", () => {
  it("uses only compatible discovery inventory over the SDK and requires an explicitly selected service", async () => {
    const prefix = "http://control/control/workspaces/workspace/projects/project/workflow";
    const eligibleId = "11111111-1111-4111-8111-111111111111";
    const datasetId = "22222222-2222-4222-8222-222222222222";
    const serviceId = "33333333-3333-4333-8333-333333333333";
    const proposalId = "44444444-4444-4444-8444-444444444444";
    const discovery = {
      id: eligibleId,
      cluster_id: "cluster",
      type: "NEW_CLASS",
      canonical_name: "refund",
      display_name: "Refund",
      confidence: 0.8,
      status: "candidate",
      provider: "mock",
      simulated: true,
      evidence_count: 5,
      created_at: "2026-10-15T00:00:00Z",
    };
    const dataset = {
      id: datasetId,
      name: "Verified",
      sealed_at: discovery.created_at,
      examples: [],
    };
    const requests: Array<{ url: string; method: string; body: unknown }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input),
        method = init?.method ?? "GET";
      requests.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === "http://control/control/projects/project")
        return Response.json({
          id: "project",
          workspace_id: "workspace",
          engine_project_id: "engine-project",
        });
      if (url === `${prefix}/candidates`)
        return Response.json([
          {
            id: proposalId,
            status: "candidate",
            decision_service_id: serviceId,
            proposal: { key: "UNSUPPORTED_PROPOSAL", label: "Evidence proposal" },
          },
        ]);
      if (url === `${prefix}/discovery-candidates`)
        return Response.json([
          discovery,
          { ...discovery, id: "rejected", status: "rejected" },
          { ...discovery, id: "active", status: "active" },
          { ...discovery, id: "alias", type: "ALIAS" },
          { ...discovery, id: "existing", type: "EXISTING_CLASS" },
          { ...discovery, id: "insufficient", type: "INSUFFICIENT_EVIDENCE" },
          { ...discovery, id: "out-of-domain", type: "OUT_OF_DOMAIN" },
          { ...discovery, id: "schema", type: "SCHEMA_ISSUE" },
          { ...discovery, id: "legacy-compatibility", type: "new_class", cluster_id: null },
          { ...discovery, id: "blank", canonical_name: "   " },
          { ...discovery, id: "null-name", canonical_name: null },
        ]);
      if (url === `${prefix}/decision-services`)
        return Response.json([{ ...service, id: serviceId, name: "Router" }]);
      if (url === `${prefix}/eval-datasets`) return Response.json([dataset]);
      if (url === `${prefix}/eval-datasets/${datasetId}`) return Response.json(dataset);
      if (url === `${prefix}/evaluations` && method === "GET") return Response.json([]);
      if (url === `${prefix}/evaluations` && method === "POST")
        return Response.json(
          {
            id: "evaluation",
            dataset_id: datasetId,
            candidate_id: eligibleId,
            overall_passed: false,
            metrics: { baseline: {}, candidate: {} },
            gates: [],
          },
          { status: 201 },
        );
      throw new Error(`Unexpected SDK request ${method} ${url}`);
    });
    const client = new OpenClassWorkspaceClient(
      new OpenClassControlClient({ baseUrl: "http://control/control", fetcher }),
      () => "simulated-session",
    );
    // Evidence inventory really is populated, but cannot supply modern replay IDs.
    expect((await client.projectCandidates("project"))[0]?.id).toBe(proposalId);
    const callsBeforeMount = requests.length;
    render(<ReplayWorkspace client={client} projectId="project" />);
    await waitFor(() =>
      expect(
        screen.getAllByRole("option").some((o) => o.getAttribute("value") === eligibleId),
      ).toBe(true),
    );
    const picker = screen.getByRole("combobox", { name: "Inactive candidate" });
    const options = Array.from((picker as HTMLSelectElement).options);
    expect(options.map((option) => option.value)).toEqual(["", eligibleId]);
    expect(options[1]!.textContent).toContain("REFUND");
    expect(requests.slice(callsBeforeMount).some((r) => r.url === `${prefix}/candidates`)).toBe(
      false,
    );
    fireEvent.change(screen.getByRole("combobox", { name: /^Dataset$/ }), {
      target: { value: datasetId },
    });
    fireEvent.change(picker, { target: { value: eligibleId } });
    await screen.findByRole("heading", { name: /Verified · sealed/ });
    const run = screen.getByRole("button", { name: "Run sealed replay" });
    expect(run).toHaveProperty("disabled", true);
    const servicePicker = screen.getByRole("combobox", { name: "Decision service" });
    expect(servicePicker).toHaveProperty("value", "");
    fireEvent.change(servicePicker, { target: { value: serviceId } });
    fireEvent.click(run);
    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(requests.filter((r) => r.method === "POST")).toEqual([
      {
        url: `${prefix}/evaluations`,
        method: "POST",
        body: { dataset_id: datasetId, candidate_id: eligibleId, service_id: serviceId },
      },
    ]);
    expect(requests.some((r) => /evaluate$|promote|activate/.test(r.url))).toBe(false);
  });

  it("removes a deleted middle node's outgoing edges but requires repair of its incoming target", async () => {
    const graphService: DecisionService = {
      ...service,
      nodes: [
        { ...service.nodes[0]!, id: "root", name: "Root" },
        { ...service.nodes[1]!, id: "middle", name: "Middle" },
        { ...service.nodes[1]!, id: "final", name: "Final" },
      ],
      transitions: [
        {
          from_node_key: "root",
          choice_key: "CONTINUE",
          to_node_key: "middle",
          require_approval: true,
        },
        {
          from_node_key: "middle",
          choice_key: "DONE",
          to_node_key: "final",
          require_approval: false,
        },
      ],
    };
    const save = vi.fn(async () => {});
    render(<GraphEditor service={graphService} onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove node Middle" }));
    fireEvent.click(screen.getByRole("button", { name: "Save new graph version" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Remove transitions to deleted nodes before saving.",
    );
    expect(save).not.toHaveBeenCalled();
    const rootTarget = screen.getAllByRole("combobox", { name: "Next node" })[0]!;
    expect(rootTarget).toHaveProperty("value", "middle");
    fireEvent.change(rootTarget, { target: { value: "final" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new graph version" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0]).toEqual([
      expect.objectContaining({
        nodes: [expect.objectContaining({ id: "root" }), expect.objectContaining({ id: "final" })],
        transitions: [
          {
            from_node_key: "root",
            choice_key: "CONTINUE",
            to_node_key: "final",
            require_approval: true,
          },
        ],
      }),
    ]);
  });

  it("renders persisted flat legacy metrics without pretending they are a baseline/candidate replay", () => {
    const historical = {
      id: "legacy-evaluation",
      dataset_id: "legacy-dataset",
      candidate_id: "legacy-candidate",
      overall_passed: true,
      is_simulated: true,
      metrics: { accuracy_on_knowns: 0.72, disambiguation_rate: 0.33, simulated: true },
      gates: [],
    } as unknown as ReplayEvaluation;
    render(<ReplayResult result={historical} />);
    expect(screen.getByText("72.0%")).toBeTruthy();
    expect(screen.getByText("33.0%")).toBeTruthy();
    expect(screen.getByText(/Legacy metrics/)).toBeTruthy();
    expect(screen.getByText(/Gate details unavailable/)).toBeTruthy();
    expect(screen.queryByText("Gates passed — human review still required")).toBeNull();
  });

  it.each([
    { baseline: { accuracy: 0.75 } },
    { baseline: null, candidate: "not a nested metric record" },
  ])("renders missing or nonnested historical metric records safely: %j", (metrics) => {
    render(
      <ReplayResult
        result={
          {
            id: "partial-evaluation",
            dataset_id: "dataset",
            candidate_id: "candidate",
            overall_passed: false,
            metrics,
          } as unknown as ReplayEvaluation
        }
      />,
    );
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/Gate details unavailable/)).toBeTruthy();
    if (metrics.baseline) expect(screen.getByText("75.0%")).toBeTruthy();
    expect(screen.queryByText("0.0%")).toBeNull();
  });

  it("retains actual zero metrics and does not replace missing modern metrics with zero", () => {
    render(
      <ReplayResult
        result={{
          id: "modern-evaluation",
          dataset_id: "dataset",
          candidate_id: "candidate",
          overall_passed: false,
          metrics: { examples: 2, baseline: { accuracy: 0 }, candidate: { accuracy: 0.5 } },
          gates: [{ gate: "known_regression", passed: false }],
        }}
      />,
    );
    expect(screen.getAllByText("0.0%")).toHaveLength(1);
    expect(screen.getByText("50.0%")).toBeTruthy();
    expect(screen.getAllByText("Unavailable")).toHaveLength(8);
    expect(screen.getByText("BLOCKED · known regression")).toBeTruthy();
  });

  it("blocks saving a deleted implicit target instead of sending a dangling graph", async () => {
    const save = vi.fn(async () => {});
    render(<GraphEditor service={service} onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove node Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Save new graph version" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Remove transitions to deleted nodes before saving.",
    );
    expect(save).not.toHaveBeenCalled();
    const target = screen.getByRole("combobox", { name: "Next node" });
    expect(target).toHaveProperty("value", "next");
    fireEvent.change(target, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new graph version" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0]).toEqual([expect.objectContaining({ transitions: [] })]);
  });

  it("allows another save after adding a node to a previously saved graph", async () => {
    const save = vi.fn(async () => {});
    render(<GraphEditor service={service} onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "Save new graph version" }));
    await screen.findByRole("status");
    fireEvent.click(screen.getByRole("button", { name: "Add node" }));
    expect(screen.getByRole("button", { name: "Save new graph version" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("does not present a failed replay load as an empty dataset inventory", async () => {
    const client = {
      evalDatasets: vi.fn(async () => {
        throw new Error("Session expired");
      }),
      decisionServices: vi.fn(async () => []),
      projectCandidates: vi.fn(async () => []),
      discoveryCandidates: vi.fn(async () => []),
      evaluations: vi.fn(async () => []),
    } as unknown as OpenClass;
    render(<ReplayWorkspace client={client} projectId="project" />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Session expired"));
    expect(screen.queryByText(/No datasets yet/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Create verified dataset" })).toBeNull();
  });
});
