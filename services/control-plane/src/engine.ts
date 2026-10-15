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
  workspace_id?: string | null;
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

export type EngineRequestOptions = {
  workspaceId?: string;
  actor?: string;
  idempotencyKey?: string;
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

  async createProject(
    name: string,
    description: string,
    options?: EngineRequestOptions,
  ): Promise<EngineProject> {
    return this.request<EngineProject>(
      "POST",
      "/api/v1/projects",
      { name, description },
      201,
      options,
    );
  }

  async listProjects(options?: EngineRequestOptions): Promise<EngineProject[]> {
    return this.request<EngineProject[]>("GET", "/api/v1/projects", undefined, 200, options);
  }

  async getProject(identifier: string, options?: EngineRequestOptions): Promise<EngineProject> {
    return this.request<EngineProject>(
      "GET",
      `/api/v1/projects/${encodeURIComponent(identifier)}`,
      undefined,
      200,
      options,
    );
  }

  async claimProject(identifier: string, options?: EngineRequestOptions): Promise<EngineProject> {
    return this.request<EngineProject>(
      "POST",
      `/api/v1/projects/${encodeURIComponent(identifier)}/claim`,
      {},
      200,
      options,
    );
  }

  async createClassifier(
    body: {
      slug: string;
      name: string;
      description: string;
      classes: EngineOntologyClass[];
    },
    options?: EngineRequestOptions,
  ): Promise<EngineClassifier> {
    return this.request<EngineClassifier>("POST", "/api/v1/classifiers", body, 201, options);
  }

  async listClassifiers(options?: EngineRequestOptions): Promise<EngineClassifier[]> {
    return this.request<EngineClassifier[]>("GET", "/api/v1/classifiers", undefined, 200, options);
  }

  async getClassifier(
    identifier: string,
    options?: EngineRequestOptions,
  ): Promise<EngineClassifier> {
    return this.request<EngineClassifier>(
      "GET",
      `/api/v1/classifiers/${encodeURIComponent(identifier)}`,
      undefined,
      200,
      options,
    );
  }

  async getOntology(identifier: string, options?: EngineRequestOptions): Promise<EngineOntology> {
    return this.request<EngineOntology>(
      "GET",
      `/api/v1/classifiers/${encodeURIComponent(identifier)}/ontology`,
      undefined,
      200,
      options,
    );
  }

  async providers(options?: EngineRequestOptions): Promise<unknown[]> {
    return this.request<unknown[]>("GET", "/api/v1/providers", undefined, 200, options);
  }

  async providerStatus(options?: EngineRequestOptions): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      "GET",
      "/api/v1/providers/status",
      undefined,
      200,
      options,
    );
  }

  async testProvider(provider: string, options?: EngineRequestOptions): Promise<unknown> {
    return this.request<unknown>("POST", "/api/v1/providers/test", { provider }, 200, options);
  }

  async providerUsage(
    engineProjectId: string,
    from?: string,
    to?: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const query = params.toString();
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/providers/usage${query ? `?${query}` : ""}`,
      undefined,
      200,
      options,
    );
  }

  async ingestEvent(
    engineProjectId: string,
    body: { content: string; source_type?: string; metadata?: Record<string, unknown> },
    idempotencyKeyOrOptions?: string | EngineRequestOptions,
    options?: EngineRequestOptions,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    const resolvedOptions =
      typeof idempotencyKeyOrOptions === "object" && idempotencyKeyOrOptions !== null
        ? idempotencyKeyOrOptions
        : options;
    const resolvedIdempotencyKey =
      typeof idempotencyKeyOrOptions === "string"
        ? idempotencyKeyOrOptions
        : resolvedOptions?.idempotencyKey;
    return this.requestStatus(
      "POST",
      `/api/v1/projects/${engineProjectId}/events`,
      body,
      [200, 201],
      resolvedIdempotencyKey,
      resolvedOptions,
    );
  }

  async ingestEventsBatch(
    engineProjectId: string,
    body: {
      items: Array<{ content: string; metadata?: Record<string, unknown> }>;
      source_type?: string;
    },
    idempotencyKeyOrOptions?: string | EngineRequestOptions,
    options?: EngineRequestOptions,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    const resolvedOptions =
      typeof idempotencyKeyOrOptions === "object" && idempotencyKeyOrOptions !== null
        ? idempotencyKeyOrOptions
        : options;
    const resolvedIdempotencyKey =
      typeof idempotencyKeyOrOptions === "string"
        ? idempotencyKeyOrOptions
        : resolvedOptions?.idempotencyKey;
    return this.requestStatus(
      "POST",
      `/api/v1/projects/${engineProjectId}/events/batch`,
      body,
      [200, 207],
      resolvedIdempotencyKey,
      resolvedOptions,
    );
  }

  async listEvents(
    engineProjectId: string,
    limit: number,
    offset: number,
    options?: EngineRequestOptions,
  ): Promise<EngineRawEvent[]> {
    return this.request<EngineRawEvent[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/events?limit=${limit}&offset=${offset}`,
      undefined,
      200,
      options,
    );
  }

  async getEvent(
    engineProjectId: string,
    eventId: string,
    options?: EngineRequestOptions,
  ): Promise<EngineRawEvent> {
    return this.request<EngineRawEvent>(
      "GET",
      `/api/v1/projects/${engineProjectId}/events/${eventId}`,
      undefined,
      200,
      options,
    );
  }

  async projectSummary(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<{ events: number }> {
    return this.request<{ events: number }>(
      "GET",
      `/api/v1/projects/${engineProjectId}/summary`,
      undefined,
      200,
      options,
    );
  }

  async createDecisionService(
    engineProjectId: string,
    body: {
      name: string;
      instructions: string;
      description?: string;
      choices: Array<{ key: string; label: string; description?: string }>;
    },
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionService> {
    return this.request<EngineDecisionService>(
      "POST",
      `/api/v1/projects/${engineProjectId}/decision-services`,
      body,
      201,
      options,
    );
  }

  async listDecisionServices(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionService[]> {
    return this.request<EngineDecisionService[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/decision-services`,
      undefined,
      200,
      options,
    );
  }

  async getDecisionService(
    engineProjectId: string,
    serviceId: string,
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionService> {
    return this.request<EngineDecisionService>(
      "GET",
      `/api/v1/projects/${engineProjectId}/decision-services/${encodeURIComponent(serviceId)}`,
      undefined,
      200,
      options,
    );
  }

  async runDecisions(
    engineProjectId: string,
    serviceId: string,
    body: { content?: string; raw_event_ids?: string[] },
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionRun[]> {
    return this.request<EngineDecisionRun[]>(
      "POST",
      `/api/v1/projects/${engineProjectId}/decision-services/${encodeURIComponent(serviceId)}/runs`,
      body,
      201,
      options,
    );
  }

  async listRuns(
    engineProjectId: string,
    limit: number,
    offset: number,
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionRun[]> {
    return this.request<EngineDecisionRun[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/runs?limit=${limit}&offset=${offset}`,
      undefined,
      200,
      options,
    );
  }

  async getRun(
    engineProjectId: string,
    runId: string,
    options?: EngineRequestOptions,
  ): Promise<EngineDecisionRun> {
    return this.request<EngineDecisionRun>(
      "GET",
      `/api/v1/projects/${engineProjectId}/runs/${runId}`,
      undefined,
      200,
      options,
    );
  }

  async listUnknowns(
    engineProjectId: string,
    filters: { state?: string; category?: string; query?: string; limit?: number; offset?: number },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (filters.state) params.set("state", filters.state);
    if (filters.category) params.set("category", filters.category);
    if (filters.query) params.set("query", filters.query);
    params.set("limit", String(filters.limit ?? 50));
    params.set("offset", String(filters.offset ?? 0));
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns?${params}`,
      undefined,
      200,
      options,
    );
  }

  async unknownStats(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns/stats`,
      undefined,
      200,
      options,
    );
  }

  async unknownDetail(
    engineProjectId: string,
    runId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns/${runId}`,
      undefined,
      200,
      options,
    );
  }

  async triageUnknown(
    engineProjectId: string,
    runId: string,
    body: { category: string; assignee?: string; note?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/unknowns/${runId}/triage`,
      body,
      200,
      options,
    );
  }

  async transitionUnknown(
    engineProjectId: string,
    runId: string,
    to: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/unknowns/${runId}/transition`,
      { to },
      200,
      options,
    );
  }

  async runClustering(
    engineProjectId: string,
    threshold?: number,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/unknowns/cluster`,
      {
        ...(threshold !== undefined ? { threshold } : {}),
      },
      200,
      options,
    );
  }

  async clusterUnknowns(
    engineProjectId: string,
    thresholdOrOptions?: number | EngineRequestOptions,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    if (typeof thresholdOrOptions === "number") {
      return this.runClustering(engineProjectId, thresholdOrOptions, options);
    }
    return this.runClustering(engineProjectId, undefined, thresholdOrOptions ?? options);
  }

  async listClusters(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns/clusters`,
      undefined,
      200,
      options,
    );
  }

  async clusterDetail(
    engineProjectId: string,
    clusterId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/unknowns/clusters/${clusterId}`,
      undefined,
      200,
      options,
    );
  }

  async discoverCluster(
    engineProjectId: string,
    clusterId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/clusters/${clusterId}/discover`,
      {},
      201,
      options,
    );
  }

  async proposeCandidate(
    engineProjectId: string,
    clusterId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.discoverCluster(engineProjectId, clusterId, options);
  }

  async listCandidates(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates`,
      undefined,
      200,
      options,
    );
  }

  async candidateDetail(
    engineProjectId: string,
    candidateId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}`,
      undefined,
      200,
      options,
    );
  }

  async candidateAction(
    engineProjectId: string,
    candidateId: string,
    action: "collect" | "request-review" | "review" | "reject",
    body?: unknown,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/${action}`,
      body ?? {},
      200,
      options,
    );
  }

  async candidateHistory(
    engineProjectId: string,
    candidateId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/history`,
      undefined,
      200,
      options,
    );
  }

  async listDatasets(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/eval-datasets`,
      undefined,
      200,
      options,
    );
  }

  async createDataset(
    engineProjectId: string,
    body: { name: string; description?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/eval-datasets`,
      body,
      201,
      options,
    );
  }

  async datasetDetail(
    engineProjectId: string,
    datasetId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}`,
      undefined,
      200,
      options,
    );
  }

  async addExample(
    engineProjectId: string,
    datasetId: string,
    body: unknown,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}/examples`,
      body,
      201,
      options,
    );
  }

  async sealDataset(
    engineProjectId: string,
    datasetId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/eval-datasets/${datasetId}/seal`,
      {},
      200,
      options,
    );
  }

  async runEvaluation(
    engineProjectId: string,
    body: { dataset_id: string; candidate_id: string; service_id?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/evaluations`,
      body,
      201,
      options,
    );
  }

  async listEvaluations(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/evaluations`,
      undefined,
      200,
      options,
    );
  }

  async evaluationDetail(
    engineProjectId: string,
    evaluationId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/evaluations/${evaluationId}`,
      undefined,
      200,
      options,
    );
  }

  async promoteCandidate(
    engineProjectId: string,
    candidateId: string,
    body: { evaluation_id: string; reviewer: string; rationale: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/discovery-candidates/${candidateId}/promote`,
      body,
      200,
      options,
    );
  }

  async ontology(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/ontology`,
      undefined,
      200,
      options,
    );
  }

  async ontologyDiff(
    engineProjectId: string,
    fromVersion: number,
    toVersion: number,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/ontology/diff?from_version=${fromVersion}&to_version=${toVersion}`,
      undefined,
      200,
      options,
    );
  }

  async rollbackOntology(
    engineProjectId: string,
    fromVersion: number,
    rationale: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/ontology/rollback`,
      { from_version: fromVersion, rationale },
      200,
      options,
    );
  }

  async analyticsSummary(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/analytics/summary`,
      undefined,
      200,
      options,
    );
  }

  async listAlertRules(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/alerts/rules`,
      undefined,
      200,
      options,
    );
  }

  async createAlertRule(
    engineProjectId: string,
    body: { metric: string; threshold: number; window?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/alerts/rules`,
      body,
      201,
      options,
    );
  }

  async evaluateAlerts(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/alerts/evaluate`,
      {},
      200,
      options,
    );
  }

  async opsEvents(
    engineProjectId: string,
    after?: string,
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    const query = after ? `?after=${encodeURIComponent(after)}` : "";
    return this.request(
      "GET",
      `/api/v1/projects/${engineProjectId}/ops/events${query}`,
      undefined,
      200,
      options,
    );
  }

  async listIntegrations(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations`,
      undefined,
      200,
      options,
    );
  }

  async createIntegration(
    engineProjectId: string,
    body: { name: string; type: string; secret_ref?: string; endpoint?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/integrations`,
      body,
      201,
      options,
    );
  }

  async listAdapters(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/adapters`,
      undefined,
      200,
      options,
    );
  }

  async listRoutes(engineProjectId: string, options?: EngineRequestOptions): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/routes`,
      undefined,
      200,
      options,
    );
  }

  async createRoute(
    engineProjectId: string,
    integrationId: string,
    body: { match_choice: string; action: string; action_value?: string },
    options?: EngineRequestOptions,
  ): Promise<unknown> {
    return this.request(
      "POST",
      `/api/v1/projects/${engineProjectId}/integrations/${integrationId}/routes`,
      body,
      201,
      options,
    );
  }

  async routingOutcomes(
    engineProjectId: string,
    options?: EngineRequestOptions,
  ): Promise<unknown[]> {
    return this.request<unknown[]>(
      "GET",
      `/api/v1/projects/${engineProjectId}/integrations/outcomes`,
      undefined,
      200,
      options,
    );
  }

  private async requestStatus(
    method: string,
    path: string,
    body: unknown,
    expectedStatuses: number[],
    idempotencyKey?: string,
    context?: EngineRequestOptions,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.buildHeaders(true, {
          "Idempotency-Key": idempotencyKey ?? context?.idempotencyKey,
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
    expectedStatusOrContext: number | EngineRequestOptions = 200,
    context?: EngineRequestOptions,
  ): Promise<T> {
    const expectedStatus =
      typeof expectedStatusOrContext === "number" ? expectedStatusOrContext : 200;
    const resolvedContext =
      typeof expectedStatusOrContext === "object" && expectedStatusOrContext !== null
        ? expectedStatusOrContext
        : context;
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.buildHeaders(Boolean(body), {
          "Idempotency-Key": resolvedContext?.idempotencyKey,
          "X-OpenClass-Workspace-Id": resolvedContext?.workspaceId,
          "X-OpenClass-Actor": resolvedContext?.actor,
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
