import {
  BadGatewayException,
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";

export type EngineProject = {
  id: string;
  slug: string;
  name: string;
  description: string;
  status?: string;
};
export type EngineClassifier = {
  id: string;
  slug: string;
  name: string;
  description?: string;
  active_ontology_version_id: string;
};
export type EngineOntologyClass = {
  canonical_name: string;
  display_name: string;
  aliases?: string[];
};
export type EngineOntology = { id: string; version_number: number; classes: EngineOntologyClass[] };
export type EngineRawEvent = {
  id: string;
  project_id: string;
  source_type: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  deduped?: boolean;
};
export type EngineDecisionService = {
  id: string;
  project_id: string;
  slug: string;
  name: string;
  instructions: string;
  status: string;
  provider_override?: string | null;
  nodes: Array<{
    id: string;
    name: string;
    instructions: string;
    choices: Array<{ key: string; label: string; description?: string }>;
  }>;
};
export type EngineDecisionRun = {
  id: string;
  project_id: string;
  raw_event_id: string;
  decision_service_id: string;
  provider: string;
  model?: string;
  execution_mode?: string;
  selected_choice: string;
  supervision_outcome: string;
  probabilities: Record<string, number>;
  top_probability?: number;
  margin?: number;
  unknown_probability?: number;
  latency_ms?: number;
  created_at: string;
};

/**
 * HTTP-only client for the FastAPI engine. The engine stays the sole owner of
 * decision/ontology logic; the control plane only proxies and maps ids.
 */
@Injectable()
export class EngineClient {
  private readonly baseUrl = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:7331";
  private readonly internalToken = process.env.OPENCLASS_INTERNAL_TOKEN ?? "";

  private buildHeaders(
    hasBody: boolean,
    extra?: Record<string, string | undefined>,
  ): Record<string, string> {
    const headers: Record<string, string> = {};
    if (hasBody) {
      headers["content-type"] = "application/json";
    }
    const token = this.internalToken.trim();
    if (token) {
      headers["X-OpenClass-Internal-Token"] = token;
    }
    if (extra) {
      for (const [key, value] of Object.entries(extra)) {
        if (value && value.trim()) {
          headers[key] = value.trim();
        }
      }
    }
    return headers;
  }

  async createProject(name: string, description: string): Promise<EngineProject> {
    return this.request<EngineProject>("POST", "/api/v1/projects", { name, description }, 201);
  }

  async getProject(identifier: string): Promise<EngineProject> {
    return this.request<EngineProject>("GET", `/api/v1/projects/${encodeURIComponent(identifier)}`);
  }

  async createClassifier(body: {
    slug: string;
    name: string;
    description: string;
    classes: EngineOntologyClass[];
  }): Promise<EngineClassifier> {
    return this.request<EngineClassifier>("POST", "/api/v1/classifiers", body, 201);
  }

  async listClassifiers(): Promise<EngineClassifier[]> {
    return this.request<EngineClassifier[]>("GET", "/api/v1/classifiers");
  }

  async getClassifier(identifier: string): Promise<EngineClassifier> {
    return this.request<EngineClassifier>(
      "GET",
      `/api/v1/classifiers/${encodeURIComponent(identifier)}`,
    );
  }

  async getOntology(identifier: string): Promise<EngineOntology> {
    return this.request<EngineOntology>(
      "GET",
      `/api/v1/classifiers/${encodeURIComponent(identifier)}/ontology`,
    );
  }

  async providers(): Promise<unknown[]> {
    return this.request<unknown[]>("GET", "/api/v1/providers");
  }

  async providerStatus(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("GET", "/api/v1/providers/status");
  }

  async testProvider(provider: string): Promise<unknown> {
    return this.request<unknown>("POST", "/api/v1/providers/test", { provider });
  }

  async providerUsage(engineProjectId: string, from?: string, to?: string): Promise<unknown[]> {
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const query = params.toString();
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/providers/usage${query ? `?${query}` : ""}`,
    );
  }

  async ingestEvent(
    engineProjectId: string,
    body: { content: string; source_type?: string; metadata?: Record<string, unknown> },
    idempotencyKey?: string,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    return this.requestStatus(
      "POST",
      `/api/v1/projects/${engineProjectId}/events`,
      body,
      [200, 201],
      idempotencyKey,
    );
  }

  async ingestEventsBatch(
    engineProjectId: string,
    body: {
      items: Array<{ content: string; metadata?: Record<string, unknown> }>;
      source_type?: string;
    },
    idempotencyKey?: string,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    return this.requestStatus(
      "POST",
      `/api/v1/projects/${engineProjectId}/events/batch`,
      body,
      [200, 207],
      idempotencyKey,
    );
  }

  async listEvents(
    engineProjectId: string,
    limit: number,
    offset: number,
  ): Promise<EngineRawEvent[]> {
    return this.request<EngineRawEvent[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/events?limit=${limit}&offset=${offset}`,
    );
  }

  async getEvent(engineProjectId: string, eventId: string): Promise<EngineRawEvent> {
    return this.request<EngineRawEvent>(
      "GET",
      `/api/v1/projects/${engineProjectId}/events/${eventId}`,
    );
  }

  async projectSummary(engineProjectId: string): Promise<{ events: number }> {
    return this.request<{ events: number }>("GET", `/api/v1/projects/${engineProjectId}/summary`);
  }

  async createDecisionService(
    engineProjectId: string,
    body: {
      name: string;
      instructions: string;
      description?: string;
      choices: Array<{ key: string; label: string; description?: string }>;
    },
  ): Promise<EngineDecisionService> {
    return this.request<EngineDecisionService>(
      "POST",
      `/api/v1/projects/${engineProjectId}/decision-services`,
      body,
      201,
    );
  }

  async listDecisionServices(engineProjectId: string): Promise<EngineDecisionService[]> {
    return this.request<EngineDecisionService[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/decision-services`,
    );
  }

  async getDecisionService(
    engineProjectId: string,
    serviceId: string,
  ): Promise<EngineDecisionService> {
    return this.request<EngineDecisionService>(
      "GET",
      `/api/v1/projects/${engineProjectId}/decision-services/${encodeURIComponent(serviceId)}`,
    );
  }

  async runDecisions(
    engineProjectId: string,
    serviceId: string,
    body: { content?: string; raw_event_ids?: string[] },
  ): Promise<EngineDecisionRun[]> {
    return this.request<EngineDecisionRun[]>(
      "POST",
      `/api/v1/projects/${engineProjectId}/decision-services/${encodeURIComponent(serviceId)}/runs`,
      body,
      201,
    );
  }

  async listRuns(
    engineProjectId: string,
    limit: number,
    offset: number,
  ): Promise<EngineDecisionRun[]> {
    return this.request<EngineDecisionRun[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/runs?limit=${limit}&offset=${offset}`,
    );
  }

  async getRun(engineProjectId: string, runId: string): Promise<EngineDecisionRun> {
    return this.request<EngineDecisionRun>(
      "GET",
      `/api/v1/projects/${engineProjectId}/runs/${runId}`,
    );
  }

  async listUnknowns(
    engineProjectId: string,
    filters: { state?: string; category?: string; query?: string; limit?: number; offset?: number },
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (filters.state) params.set("state", filters.state);
    if (filters.category) params.set("category", filters.category);
    if (filters.query) params.set("query", filters.query);
    params.set("limit", String(filters.limit ?? 50));
    params.set("offset", String(filters.offset ?? 0));
    return this.request("GET", `/api/v1/projects/${engineProjectId}/unknowns?${params}`);
  }

  async unknownStats(engineProjectId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/unknowns/stats`);
  }

  async unknownDetail(engineProjectId: string, runId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/unknowns/${runId}`);
  }

  async triageUnknown(
    engineProjectId: string,
    runId: string,
    body: { category: string; assignee?: string; note?: string },
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/unknowns/${runId}/triage`,
      body,
      200,
    );
  }

  async transitionUnknown(engineProjectId: string, runId: string, to: string): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/unknowns/${runId}/transition`,
      { to },
      200,
    );
  }

  async runClustering(engineProjectId: string, threshold?: number): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/unknowns/cluster`, {
      ...(threshold !== undefined ? { threshold } : {}),
    });
  }

  async listClusters(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>("GET", `/api/v1/projects/${engineProjectId}/unknowns/clusters`);
  }

  async clusterDetail(engineProjectId: string, clusterId: string): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns/clusters/${clusterId}`,
    );
  }

  async discoverCluster(engineProjectId: string, clusterId: string): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/clusters/${clusterId}/discover`,
      {},
      201,
    );
  }

  async listCandidates(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates`,
    );
  }

  async candidateDetail(engineProjectId: string, candidateId: string): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}`,
    );
  }

  async candidateAction(
    engineProjectId: string,
    candidateId: string,
    action: "collect" | "request-review" | "review" | "reject",
    body?: unknown,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/${action}`,
      body ?? {},
      200,
    );
  }

  async candidateHistory(engineProjectId: string, candidateId: string): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/history`,
    );
  }

  async listDatasets(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>("GET", `/api/v1/projects/${engineProjectId}/eval-datasets`);
  }

  async createDataset(
    engineProjectId: string,
    body: { name: string; description?: string },
  ): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/eval-datasets`, body, 201);
  }

  async datasetDetail(engineProjectId: string, datasetId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}`);
  }

  async addExample(engineProjectId: string, datasetId: string, body: unknown): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}/examples`,
      body,
      201,
    );
  }

  async sealDataset(engineProjectId: string, datasetId: string): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}/seal`,
      {},
      200,
    );
  }

  async runEvaluation(
    engineProjectId: string,
    body: { dataset_id: string; candidate_id: string; service_id?: string },
  ): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/evaluations`, body, 201);
  }

  async listEvaluations(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>("GET", `/api/v1/projects/${engineProjectId}/evaluations`);
  }

  async evaluationDetail(engineProjectId: string, evaluationId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/evaluations/${evaluationId}`);
  }

  async promoteCandidate(
    engineProjectId: string,
    candidateId: string,
    body: { evaluation_id: string; reviewer: string; rationale: string },
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/promote`,
      body,
      200,
    );
  }

  async ontology(engineProjectId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/ontology`);
  }

  async ontologyDiff(
    engineProjectId: string,
    fromVersion: number,
    toVersion: number,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/ontology/diff?from_version=${fromVersion}&to_version=${toVersion}`,
    );
  }

  async rollbackOntology(
    engineProjectId: string,
    fromVersion: number,
    rationale: string,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/ontology/rollback`,
      { from_version: fromVersion, rationale },
      200,
    );
  }

  async analyticsSummary(engineProjectId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/projects/${engineProjectId}/analytics/summary`);
  }

  async listAlertRules(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>("GET", `/api/v1/projects/${engineProjectId}/alerts/rules`);
  }

  async createAlertRule(
    engineProjectId: string,
    body: { metric: string; threshold: number; window?: string },
  ): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/alerts/rules`, body, 201);
  }

  async evaluateAlerts(engineProjectId: string): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/alerts/evaluate`, {}, 200);
  }

  async opsEvents(engineProjectId: string, after?: string): Promise<unknown> {
    const query = after ? `?after=${encodeURIComponent(after)}` : "";
    return this.request("GET", `/api/v1/projects/${engineProjectId}/ops/events${query}`);
  }

  async listIntegrations(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>("GET", `/api/v1/projects/${engineProjectId}/integrations`);
  }

  async createIntegration(
    engineProjectId: string,
    body: { name: string; type: string; secret_ref?: string; endpoint?: string },
  ): Promise<unknown> {
    return this.request("POST", `/api/v1/projects/${engineProjectId}/integrations`, body, 201);
  }

  async listAdapters(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/adapters`,
    );
  }

  async listRoutes(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/routes`,
    );
  }

  async createRoute(
    engineProjectId: string,
    integrationId: string,
    body: { match_choice: string; action: string; action_value?: string },
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/integrations/${integrationId}/routes`,
      body,
      201,
    );
  }

  async routingOutcomes(engineProjectId: string): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/outcomes`,
    );
  }

  private async requestStatus(
    method: string,
    path: string,
    body: unknown,
    expectedStatuses: number[],
    idempotencyKey?: string,
    context?: { workspaceId?: string; actor?: string },
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.buildHeaders(true, {
          "Idempotency-Key": idempotencyKey,
          "X-OpenClass-Workspace-Id": context?.workspaceId,
          "X-OpenClass-Actor": context?.actor,
        }),
        body: JSON.stringify(body),
      });
    } catch {
      throw new BadGatewayException("Engine is temporarily unavailable");
    }
    const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (expectedStatuses.includes(response.status))
      return { status: response.status, body: payload };
    const message =
      typeof payload.detail === "string" ? payload.detail : "Engine rejected the request";
    if (response.status === 404) throw new NotFoundException(message);
    if (response.status === 429)
      throw new BadGatewayException("Engine rate limit reached; retry shortly");
    if (response.status >= 400 && response.status < 500) throw new BadRequestException(message);
    throw new BadGatewayException("Engine request failed");
  }

  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    expectedStatus = 200,
    context?: { workspaceId?: string; actor?: string },
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.buildHeaders(Boolean(body), {
          "X-OpenClass-Workspace-Id": context?.workspaceId,
          "X-OpenClass-Actor": context?.actor,
        }),
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new BadGatewayException("Engine is temporarily unavailable");
    }
    if (response.status === expectedStatus) return (await response.json()) as T;
    const detail = await this.errorMessage(response);
    if (response.status === 404) throw new NotFoundException(detail);
    if (response.status === 409) throw new ConflictException(detail);
    if (response.status >= 400 && response.status < 500) throw new BadRequestException(detail);
    throw new BadGatewayException("Engine request failed");
  }

  private async errorMessage(response: Response): Promise<string> {
    try {
      const payload = (await response.json()) as { detail?: unknown };
      const detail = payload.detail;
      if (typeof detail === "string") return detail.slice(0, 300);
      if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === "string") {
        return `Invalid engine payload: ${detail[0].msg}`.slice(0, 300);
      }
    } catch {
      // fall through to the generic engine message
    }
    return "Engine rejected the request";
  }
}
