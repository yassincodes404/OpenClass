/** Public HTTP client. No backend implementation imports. */
export interface Classifier {
  id: string;
  slug: string;
  name: string;
  description: string;
  classifier_type: "single_choice";
  active_ontology_version_id: string;
}

export interface Project {
  id: string;
  slug: string;
  name: string;
  description: string;
  status: "active" | "archived";
  owner_id: string | null;
  workspace_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary {
  events: number;
  decision_runs: number;
  unknowns: number;
  pending_evidence: number;
  active_policy: string | null;
  pending_candidates: number;
  audit_events: number;
}

export interface ProjectAnalytics {
  project_id: string;
  total_events: number;
  total_runs: number;
  unknown_runs: number;
  unknown_rate: number | null;
  real_inference_runs: number;
  simulated_runs: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  choices: Array<{ key: string; count: number }>;
  providers: Array<{ key: string; count: number }>;
  services: Array<{ key: string; count: number }>;
}

export type ProjectAuditEventType =
  | "project.created"
  | "project.updated"
  | "decision_service.created"
  | "decision_service.updated"
  | "choice_candidate.created"
  | "choice_candidate.promoted"
  | "choice_candidate.rejected"
  | "feedback.submitted"
  | "evidence.created"
  | "evidence.triaged"
  | "evidence.resolved"
  | "evidence.dismissed"
  | "evidence.ready_for_evolution"
  | "evidence.grouped"
  | "integration.created"
  | "integration.updated"
  | "integration.tested"
  | "integration.deleted"
  | "integration.webhook_ingested";

export type IntegrationType = "mcp" | "webhook" | "rest_api" | "provider" | "database";
export type IntegrationStatus = "connected" | "degraded" | "disconnected" | "pending";

export interface Integration {
  id: string;
  project_id: string;
  name: string;
  type: IntegrationType;
  status: IntegrationStatus;
  endpoint: string | null;
  secret_ref: string | null;
  capabilities: string[];
  latency_ms: number | null;
  last_health_check: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateIntegrationInput {
  project: string;
  name: string;
  type: IntegrationType;
  endpoint?: string | null;
  secret_ref?: string | null;
  capabilities?: string[];
  metadata?: Record<string, unknown>;
}

export interface UpdateIntegrationInput {
  project: string;
  integrationId: string;
  changes: {
    name?: string;
    status?: IntegrationStatus;
    endpoint?: string | null;
    secret_ref?: string | null;
    capabilities?: string[];
    metadata?: Record<string, unknown>;
  };
}

export interface TestIntegrationResult {
  integration_id: string;
  status: IntegrationStatus;
  latency_ms: number | null;
  capabilities: string[];
  error_message: string | null;
  timestamp?: string;
}

export interface WebhookIngestResult {
  event_id: string;
  project_id: string;
  integration_id: string;
  status: "ingested" | "duplicate";
  source: string;
  timestamp: string;
}

export interface SystemHealth {
  status: "healthy" | "unhealthy";
  database: {
    connected: boolean;
    latency_ms: number;
    schema_revision?: string | null;
    migration_current?: boolean;
  };
  decision_provider: string;
  discovery_provider: string;
  version: string;
}

export interface ProjectAuditEvent {
  id: string;
  project_id: string;
  event_type: ProjectAuditEventType;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export type EvidenceTriggerType =
  | "semantic_unknown"
  | "low_trust"
  | "human_correction"
  | "human_marked_missing_concept"
  | "supervisor_finding"
  | "postcondition_failure"
  | "repeated_pattern"
  | "state_gap"
  | "analytical_gap";

export type EvidenceStatus =
  "pending" | "triaged" | "resolved" | "dismissed" | "ready_for_evolution";

export type DiagnosisCategory =
  | "decision_space"
  | "procedure"
  | "state_representation"
  | "precondition"
  | "missing_capability"
  | "provider_failure"
  | "out_of_domain"
  | "ambiguous_or_insufficient"
  | "analytical_gap";

export type FeedbackAction =
  "confirm" | "correct" | "missing_concept" | "ambiguous" | "out_of_domain" | "note";

export interface EvidenceItem {
  id: string;
  project_id: string;
  raw_event_id: string | null;
  decision_run_id: string | null;
  decision_service_id: string | null;
  decision_node_id: string | null;
  evidence_case_id: string | null;
  trigger_type: EvidenceTriggerType;
  status: EvidenceStatus;
  diagnosis: DiagnosisCategory | null;
  diagnosis_rationale: string | null;
  selected_choice: string | null;
  probabilities_snapshot: Record<string, number>;
  unknown_probability: number;
  margin: number;
  supervision_outcome: string | null;
  supervision_reason: string | null;
  provider: string | null;
  model: string | null;
  execution_mode: string | null;
  source: "automatic" | "human" | "supervisor";
  human_note: string | null;
  corrected_choice: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface EvidenceCase {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: EvidenceStatus;
  decision_service_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunFeedback {
  id: string;
  project_id: string;
  decision_run_id: string;
  action: FeedbackAction;
  corrected_choice: string | null;
  note: string | null;
  author: string;
  created_at: string;
}

export interface EvolutionSummary {
  project_id: string;
  pending_evidence: number;
  triaged_evidence: number;
  ready_for_evolution: number;
  resolved_evidence: number;
  dismissed_evidence: number;
  total_evidence: number;
  open_cases: number;
  total_cases: number;
}

export interface DiagnosisResult {
  diagnosis: DiagnosisCategory;
  rationale: string;
  confidence: number;
  recommended_action: string | null;
  provider: string;
  model: string;
  simulated: boolean;
}

export interface RawEvent {
  id: string;
  project_id: string;
  source_type: "text" | "json" | "csv" | "webhook";
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface DecisionChoice {
  key: string;
  label: string;
  description: string;
}

export interface DecisionNode {
  id: string;
  name: string;
  instructions: string;
  choices: DecisionChoice[];
}

export interface DecisionService {
  id: string;
  project_id: string;
  slug: string;
  name: string;
  description: string;
  instructions: string;
  nodes: DecisionNode[];
  status: "active" | "draft" | "archived";
  provider_override: string | null;
  created_at: string;
  updated_at: string;
}

export interface DecisionRun {
  id: string;
  project_id: string;
  raw_event_id: string;
  decision_service_id: string;
  decision_node_id: string;
  provider: string;
  model: string;
  execution_mode: "in_process" | "daemon" | "deterministic_test_fallback" | "mock";
  real_inference: boolean;
  selected_choice: string;
  probabilities: Record<string, number>;
  top_probability: number;
  second_probability: number | null;
  margin: number;
  unknown_probability: number;
  supervision_outcome: "TRUSTED" | "REVIEW" | "UNKNOWN";
  supervision_reason: string;
  latency_ms: number;
  input_snapshot: Record<string, unknown>;
  instructions_snapshot: string;
  choices_snapshot: DecisionChoice[];
  provider_metadata: Record<string, unknown>;
  created_at: string;
}

export interface ProviderStatus {
  default_provider: string;
  laya: {
    status: string;
    mode: string;
    daemon_status: string;
    endpoint: string;
    model: string;
    default: boolean;
  };
  jev: {
    status: string;
    model: string;
    configured: boolean;
    default: boolean;
  };
}

export interface ClassificationResult {
  id: string;
  ontology_version_id: string;
  selected_class: string | null;
  novelty: { state: "known" | "uncertain" | "likely_novel"; score: number; reasons: string[] };
  decision: {
    provider: string;
    model: string;
    probabilities: Record<string, number>;
    unknown_probability: number;
  };
}

export interface ClassificationRecord {
  observation: {
    id: string;
    content: string;
    content_type: "text";
    metadata: Record<string, unknown>;
    created_at: string;
  };
  result: ClassificationResult;
}

export interface Candidate {
  id: string;
  classifier_id: string;
  base_ontology_version_id: string;
  proposal_type: string;
  canonical_name: string | null;
  display_name: string | null;
  description: string | null;
  confidence: number;
  rationale: string;
  status: "candidate" | "approved" | "rejected";
  evaluation_passed: boolean;
  rejection_reason: string | null;
  discovery_provider: string;
  discovery_model: string;
  evidence_ids: string[];
  created_at: string;
}

export interface ChoiceProposal {
  kind: "new_choice" | "existing_choice" | "insufficient_evidence";
  key: string | null;
  label: string | null;
  description: string | null;
  rationale: string;
  provider: string;
  model: string;
  simulated: boolean;
}

export interface ChoiceCandidate {
  id: string;
  project_id: string;
  decision_service_id: string;
  base_service_hash: string;
  evidence_run_ids: string[];
  proposal: ChoiceProposal;
  status: "candidate" | "rejected" | "promoted";
  rejection_reason: string | null;
  promoted_at: string | null;
  created_at: string;
}

export interface CandidateEvaluationResult {
  candidate_id: string;
  decision_service_id: string;
  passed: boolean;
  accuracy_on_knowns: number;
  disambiguation_rate: number;
  regressions: string[];
  evaluated_at: string;
}

export interface PromoteCandidateResponse {
  candidate: ChoiceCandidate;
  decision_service: DecisionService;
}

export type SupervisorFinding =
  | "no_issue"
  | "possible_misclassification"
  | "possible_missing_class"
  | "class_definition_issue"
  | "instruction_issue"
  | "schema_issue"
  | "out_of_domain"
  | "insufficient_evidence";

export type ReviewRecommendation =
  | "none"
  | "check_classification"
  | "propose_class"
  | "add_alias"
  | "revise_class_definition"
  | "revise_instruction"
  | "review_schema"
  | "mark_out_of_domain"
  | "collect_more_evidence";

export interface ReviewResult {
  provider: string;
  model: string;
  finding: SupervisorFinding;
  confidence: number;
  recommendation: ReviewRecommendation;
  rationale: string;
  suspected_class: string | null;
  proposed_class: string | null;
  proposed_instruction: string | null;
  provider_metadata: Record<string, unknown>;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost: number | null;
}

export interface SupervisorReview {
  id: string;
  classifier_id: string;
  classification_run_id: string;
  ontology_version_id: string;
  trigger: "manual";
  result: ReviewResult;
  created_at: string;
}

export class OpenClassError extends Error {
  constructor(public readonly status: number) {
    super(`OpenClass request failed (HTTP ${status})`);
  }
}

export interface OpenClassClientOptions {
  baseURL?: string;
  baseUrl?: string;
  workspaceId?: string;
  actor?: string;
  fetcher?: typeof fetch;
}

export interface OpenClassRequestOptions {
  workspaceId?: string;
  actor?: string;
  headers?: Record<string, string>;
}

export class OpenClass {
  private readonly baseURL: string;
  private readonly fetcher: typeof fetch;
  private readonly defaultWorkspaceId?: string;
  private readonly defaultActor?: string;

  constructor(
    baseURLOrOptions: string | OpenClassClientOptions = "http://localhost:7331",
    fetcher: typeof fetch = (...args) => globalThis.fetch(...args),
    options?: { workspaceId?: string; actor?: string },
  ) {
    if (typeof baseURLOrOptions === "string") {
      this.baseURL = baseURLOrOptions;
      this.fetcher = fetcher;
      this.defaultWorkspaceId = options?.workspaceId;
      this.defaultActor = options?.actor;
    } else {
      this.baseURL =
        baseURLOrOptions.baseURL ?? baseURLOrOptions.baseUrl ?? "http://localhost:7331";
      this.fetcher = baseURLOrOptions.fetcher ?? fetcher;
      this.defaultWorkspaceId = baseURLOrOptions.workspaceId ?? options?.workspaceId;
      this.defaultActor = baseURLOrOptions.actor ?? options?.actor;
    }
  }

  private async request<T>(
    path: string,
    body?: unknown,
    method?: "GET" | "POST" | "PATCH" | "DELETE",
    headersOrOptions?: Record<string, string> | OpenClassRequestOptions,
  ): Promise<T> {
    let extraHeaders: Record<string, string> = {};
    let workspaceId = this.defaultWorkspaceId;
    let actor = this.defaultActor;
    if (headersOrOptions) {
      if (
        "workspaceId" in headersOrOptions ||
        "actor" in headersOrOptions ||
        "headers" in headersOrOptions
      ) {
        const opts = headersOrOptions as OpenClassRequestOptions;
        if (opts.workspaceId !== undefined) workspaceId = opts.workspaceId;
        if (opts.actor !== undefined) actor = opts.actor;
        if (opts.headers) extraHeaders = { ...opts.headers };
      } else {
        extraHeaders = { ...(headersOrOptions as Record<string, string>) };
      }
    }
    const response = await this.fetcher(`${this.baseURL.replace(/\/$/, "")}${path}`, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(workspaceId ? { "X-OpenClass-Workspace-Id": workspaceId } : {}),
        ...(actor ? { "X-OpenClass-Actor": actor } : {}),
        ...extraHeaders,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new OpenClassError(response.status);
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  classifiers(): Promise<Classifier[]> {
    return this.request("/api/v1/classifiers");
  }
  health(): Promise<{ status: string }> {
    return this.request("/health/ready");
  }
  classify(input: { classifier: string; observation: string }): Promise<ClassificationResult> {
    return this.request(`/api/v1/classifiers/${encodeURIComponent(input.classifier)}/classify`, {
      observation: input.observation,
    });
  }
  runs(classifier: string): Promise<ClassificationRecord[]> {
    return this.request(`/api/v1/classifiers/${encodeURIComponent(classifier)}/runs`);
  }
  run(input: { classifier: string; runId: string }): Promise<ClassificationRecord> {
    return this.request(
      `/api/v1/classifiers/${encodeURIComponent(input.classifier)}/runs/${encodeURIComponent(input.runId)}`,
    );
  }
  reviewRun(input: { classifier: string; runId: string }): Promise<SupervisorReview> {
    return this.request(
      `/api/v1/classifiers/${encodeURIComponent(input.classifier)}/runs/${encodeURIComponent(input.runId)}/reviews`,
      { trigger: "manual" },
    );
  }
  reviews(classifier: string): Promise<SupervisorReview[]> {
    return this.request(`/api/v1/classifiers/${encodeURIComponent(classifier)}/reviews`);
  }
  candidates(classifier: string): Promise<Candidate[]> {
    return this.request(`/api/v1/classifiers/${encodeURIComponent(classifier)}/candidates`);
  }
  rejectCandidate(input: {
    classifier: string;
    candidateId: string;
    reason: string;
  }): Promise<Candidate> {
    return this.request(
      `/api/v1/classifiers/${encodeURIComponent(input.classifier)}/candidates/${encodeURIComponent(input.candidateId)}/reject`,
      { reason: input.reason },
    );
  }
  projects(options?: OpenClassRequestOptions): Promise<Project[]> {
    return this.request("/api/v1/projects", undefined, "GET", options);
  }
  createProject(
    input: { name: string; description?: string; workspaceId?: string },
    options?: OpenClassRequestOptions,
  ): Promise<Project> {
    const resolvedOptions =
      input.workspaceId !== undefined
        ? { ...options, workspaceId: options?.workspaceId ?? input.workspaceId }
        : options;
    return this.request(
      "/api/v1/projects",
      {
        name: input.name,
        description: input.description ?? "",
      },
      "POST",
      resolvedOptions,
    );
  }
  project(project: string, options?: OpenClassRequestOptions): Promise<Project> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(project)}`,
      undefined,
      "GET",
      options,
    );
  }
  claimProject(project: string, options?: OpenClassRequestOptions): Promise<Project> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(project)}/claim`,
      {},
      "POST",
      options,
    );
  }
  updateProject(
    project: string,
    changes: { name?: string; description?: string; status?: "active" | "archived" },
    options?: OpenClassRequestOptions,
  ): Promise<Project> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(project)}`,
      changes,
      "PATCH",
      options,
    );
  }
  projectSummary(project: string): Promise<ProjectSummary> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/summary`);
  }
  projectAnalytics(project: string): Promise<ProjectAnalytics> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/analytics`);
  }
  projectAudit(project: string): Promise<ProjectAuditEvent[]> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/audit`);
  }
  createEvent(input: {
    project: string;
    content: string;
    sourceType?: "text" | "json" | "csv" | "webhook";
    metadata?: Record<string, unknown>;
  }): Promise<RawEvent> {
    return this.request(`/api/v1/projects/${encodeURIComponent(input.project)}/events`, {
      content: input.content,
      source_type: input.sourceType ?? "text",
      metadata: input.metadata ?? {},
    });
  }
  async createEventsBatch(input: {
    project: string;
    items: Array<{ content: string; metadata?: Record<string, unknown>; source_type?: string }>;
    sourceType?: "text" | "json" | "csv" | "webhook";
  }): Promise<RawEvent[]> {
    const response = await this.request<
      RawEvent[] | { items?: Array<RawEvent | { event?: RawEvent }> }
    >(`/api/v1/projects/${encodeURIComponent(input.project)}/events/batch`, {
      items: input.items,
      source_type: input.sourceType ?? "text",
    });
    if (Array.isArray(response)) {
      return response;
    }
    if (response && typeof response === "object" && Array.isArray(response.items)) {
      return response.items
        .map((item) =>
          item && typeof item === "object" && "event" in item && item.event
            ? item.event
            : (item as RawEvent),
        )
        .filter((event): event is RawEvent =>
          Boolean(event && typeof event === "object" && "id" in event),
        );
    }
    return [];
  }
  ingestBatch(input: {
    project: string;
    items: Array<{ content: string; metadata?: Record<string, unknown>; source_type?: string }>;
    sourceType?: "text" | "json" | "csv" | "webhook";
  }): Promise<RawEvent[]> {
    return this.createEventsBatch(input);
  }
  events(project: string, options?: { limit?: number; offset?: number }): Promise<RawEvent[]> {
    const params = new URLSearchParams();
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/events${query}`);
  }
  event(input: { project: string; eventId: string }): Promise<RawEvent> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/events/${encodeURIComponent(input.eventId)}`,
    );
  }

  createDecisionService(input: {
    project: string;
    name: string;
    instructions: string;
    choices: Array<{ key: string; label: string; description?: string }>;
    description?: string;
    provider_override?: string | null;
  }): Promise<DecisionService> {
    return this.request(`/api/v1/projects/${encodeURIComponent(input.project)}/decision-services`, {
      name: input.name,
      instructions: input.instructions,
      choices: input.choices,
      description: input.description ?? "",
      provider_override: input.provider_override ?? null,
    });
  }

  decisionServices(project: string): Promise<DecisionService[]> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/decision-services`);
  }

  decisionService(input: { project: string; serviceId: string }): Promise<DecisionService> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/decision-services/${encodeURIComponent(input.serviceId)}`,
    );
  }

  updateDecisionService(input: {
    project: string;
    serviceId: string;
    changes: {
      name?: string;
      description?: string;
      instructions?: string;
      status?: "active" | "draft" | "archived";
      provider_override?: string | null;
    };
  }): Promise<DecisionService> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/decision-services/${encodeURIComponent(input.serviceId)}`,
      input.changes,
      "PATCH",
    );
  }

  executeDecisionRuns(input: {
    project: string;
    serviceId: string;
    rawEventIds: string[];
  }): Promise<DecisionRun[]> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/decision-services/${encodeURIComponent(input.serviceId)}/runs`,
      { raw_event_ids: input.rawEventIds },
    );
  }

  decisionRuns(
    project: string,
    options?: { limit?: number; offset?: number },
  ): Promise<DecisionRun[]> {
    const params = new URLSearchParams();
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/runs${query}`);
  }

  decisionRun(input: { project: string; runId: string }): Promise<DecisionRun> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/runs/${encodeURIComponent(input.runId)}`,
    );
  }

  providerStatus(): Promise<ProviderStatus> {
    return this.request("/api/v1/providers/status");
  }

  evidence(
    project: string,
    options?: { status?: string; limit?: number; offset?: number },
  ): Promise<EvidenceItem[]> {
    const params = new URLSearchParams();
    if (options?.status !== undefined) params.set("status", options.status);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/evidence${query}`);
  }

  evidenceItem(input: { project: string; evidenceId: string }): Promise<EvidenceItem> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence/${encodeURIComponent(input.evidenceId)}`,
    );
  }

  triageEvidence(input: {
    project: string;
    evidenceId: string;
    diagnosis: DiagnosisCategory;
    rationale?: string;
  }): Promise<EvidenceItem> {
    const body: Record<string, unknown> = { diagnosis: input.diagnosis };
    if (input.rationale !== undefined) body.rationale = input.rationale;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence/${encodeURIComponent(input.evidenceId)}/triage`,
      body,
      "PATCH",
    );
  }

  transitionEvidence(input: {
    project: string;
    evidenceId: string;
    targetStatus: EvidenceStatus;
    note?: string;
  }): Promise<EvidenceItem> {
    const body: Record<string, unknown> = { target_status: input.targetStatus };
    if (input.note !== undefined) body.note = input.note;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence/${encodeURIComponent(input.evidenceId)}/transition`,
      body,
      "POST",
    );
  }

  aiDiagnoseEvidence(input: { project: string; evidenceId: string }): Promise<DiagnosisResult> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence/${encodeURIComponent(input.evidenceId)}/ai-diagnose`,
      undefined,
      "POST",
    );
  }

  submitRunFeedback(input: {
    project: string;
    runId: string;
    action: FeedbackAction;
    correctedChoice?: string;
    note?: string;
  }): Promise<RunFeedback> {
    const body: Record<string, unknown> = { action: input.action };
    if (input.correctedChoice !== undefined) body.corrected_choice = input.correctedChoice;
    if (input.note !== undefined) body.note = input.note;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/runs/${encodeURIComponent(input.runId)}/feedback`,
      body,
      "POST",
    );
  }

  runFeedback(input: { project: string; runId: string }): Promise<RunFeedback[]> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/runs/${encodeURIComponent(input.runId)}/feedback`,
    );
  }

  createEvidenceCase(input: {
    project: string;
    title: string;
    description?: string;
    decisionServiceId?: string;
    evidenceIds?: string[];
  }): Promise<EvidenceCase> {
    const body: Record<string, unknown> = {
      title: input.title,
      description: input.description ?? "",
    };
    if (input.decisionServiceId !== undefined) {
      body.decision_service_id = input.decisionServiceId;
    }
    if (input.evidenceIds !== undefined) {
      body.evidence_ids = input.evidenceIds;
    }
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence-cases`,
      body,
      "POST",
    );
  }

  evidenceCases(
    project: string,
    options?: { status?: string; limit?: number; offset?: number },
  ): Promise<EvidenceCase[]> {
    const params = new URLSearchParams();
    if (options?.status !== undefined) params.set("status", options.status);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/evidence-cases${query}`);
  }

  evidenceCase(input: { project: string; caseId: string }): Promise<EvidenceCase> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence-cases/${encodeURIComponent(input.caseId)}`,
    );
  }

  caseEvidence(input: { project: string; caseId: string }): Promise<EvidenceItem[]> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence-cases/${encodeURIComponent(input.caseId)}/evidence`,
    );
  }

  addEvidenceToCase(input: {
    project: string;
    caseId: string;
    evidenceId: string;
  }): Promise<EvidenceCase> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evidence-cases/${encodeURIComponent(input.caseId)}/evidence`,
      { evidence_id: input.evidenceId },
      "POST",
    );
  }

  evolutionSummary(project: string): Promise<EvolutionSummary> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/evolution/summary`);
  }

  projectCandidates(project: string): Promise<ChoiceCandidate[]> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/candidates`);
  }

  projectCandidate(input: { project: string; candidateId: string }): Promise<ChoiceCandidate> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/candidates/${encodeURIComponent(input.candidateId)}`,
    );
  }

  proposeProjectChoice(input: {
    project: string;
    serviceId: string;
    runIds: string[];
  }): Promise<ChoiceCandidate> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/decision-services/${encodeURIComponent(input.serviceId)}/candidates`,
      { run_ids: input.runIds },
      "POST",
    );
  }

  proposeFromEvidence(input: {
    project: string;
    serviceId?: string;
    evidenceIds?: string[];
    evidenceCaseId?: string;
  }): Promise<ChoiceCandidate> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evolution/propose`,
      {
        service_id: input.serviceId,
        evidence_ids: input.evidenceIds,
        evidence_case_id: input.evidenceCaseId,
      },
      "POST",
    );
  }

  evaluateProjectCandidate(input: {
    project: string;
    candidateId: string;
  }): Promise<CandidateEvaluationResult> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/candidates/${encodeURIComponent(input.candidateId)}/evaluate`,
      undefined,
      "POST",
    );
  }

  promoteProjectCandidate(input: {
    project: string;
    candidateId: string;
    note?: string;
  }): Promise<PromoteCandidateResponse> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/candidates/${encodeURIComponent(input.candidateId)}/promote`,
      input.note !== undefined ? { note: input.note } : undefined,
      "POST",
    );
  }

  rejectProjectChoice(input: {
    project: string;
    candidateId: string;
    reason: string;
  }): Promise<ChoiceCandidate> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/candidates/${encodeURIComponent(input.candidateId)}/reject`,
      { reason: input.reason },
      "POST",
    );
  }

  // ── Integrations ──────────────────────────────────────────

  projectIntegrations(project: string): Promise<Integration[]> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/integrations`);
  }

  projectIntegration(input: { project: string; integrationId: string }): Promise<Integration> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/integrations/${encodeURIComponent(input.integrationId)}`,
    );
  }

  createProjectIntegration(input: CreateIntegrationInput): Promise<Integration> {
    return this.request(`/api/v1/projects/${encodeURIComponent(input.project)}/integrations`, {
      name: input.name,
      type: input.type,
      endpoint: input.endpoint ?? null,
      secret_ref: input.secret_ref ?? null,
      capabilities: input.capabilities ?? [],
      metadata: input.metadata ?? {},
    });
  }

  updateProjectIntegration(input: UpdateIntegrationInput): Promise<Integration> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/integrations/${encodeURIComponent(input.integrationId)}`,
      input.changes,
      "PATCH",
    );
  }

  deleteProjectIntegration(input: { project: string; integrationId: string }): Promise<void> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/integrations/${encodeURIComponent(input.integrationId)}`,
      undefined,
      "DELETE",
    );
  }

  testProjectIntegration(input: {
    project: string;
    integrationId: string;
  }): Promise<TestIntegrationResult> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/integrations/${encodeURIComponent(input.integrationId)}/test`,
      undefined,
      "POST",
    );
  }

  systemHealth(): Promise<SystemHealth> {
    return this.request("/api/v1/system/health");
  }

  ingestIntegrationWebhook(input: {
    project: string;
    integrationId: string;
    eventKey: string;
    content: string;
    source?: string;
    metadata?: Record<string, unknown>;
    token: string;
  }): Promise<WebhookIngestResult> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/integrations/${encodeURIComponent(input.integrationId)}/webhook`,
      {
        event_key: input.eventKey,
        content: input.content,
        source: input.source ?? "webhook",
        metadata: input.metadata ?? {},
      },
      "POST",
      { "X-OpenClass-Token": input.token },
    );
  }

  // ── Phase 05–16: Unknowns, Clustering, Discovery, Evaluation, Ontology & Ops ──

  projectUnknowns(
    project: string,
    options?: {
      state?: string;
      category?: string;
      query?: string;
      limit?: number;
      offset?: number;
    },
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    if (options?.state !== undefined) params.set("state", options.state);
    if (options?.category !== undefined) params.set("category", options.category);
    if (options?.query !== undefined) params.set("query", options.query);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/unknowns${query}`);
  }

  projectUnknownStats(project: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/unknowns/stats`);
  }

  projectUnknown(input: { project: string; runId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/unknowns/${encodeURIComponent(input.runId)}`,
    );
  }

  triageProjectUnknown(input: {
    project: string;
    runId: string;
    category: string;
    assignee?: string;
    note?: string;
  }): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { category: input.category };
    if (input.assignee !== undefined) body.assignee = input.assignee;
    if (input.note !== undefined) body.note = input.note;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/unknowns/${encodeURIComponent(input.runId)}/triage`,
      body,
      "POST",
    );
  }

  transitionProjectUnknown(input: {
    project: string;
    runId: string;
    to: string;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/unknowns/${encodeURIComponent(input.runId)}/transition`,
      { to: input.to },
      "POST",
    );
  }

  clusterUnknowns(input: {
    project: string;
    threshold?: number;
    limit?: number;
  }): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = {};
    if (input.threshold !== undefined) body.threshold = input.threshold;
    if (input.limit !== undefined) body.limit = input.limit;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/unknowns/cluster`,
      body,
      "POST",
    );
  }

  clusters(project: string): Promise<Array<Record<string, unknown>>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/unknowns/clusters`);
  }

  cluster(input: { project: string; clusterId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/unknowns/clusters/${encodeURIComponent(input.clusterId)}`,
    );
  }

  discoverCluster(input: { project: string; clusterId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/clusters/${encodeURIComponent(input.clusterId)}/discover`,
      {},
      "POST",
    );
  }

  discoveryCandidates(project: string): Promise<Array<Record<string, unknown>>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/discovery-candidates`);
  }

  discoveryCandidate(input: {
    project: string;
    candidateId: string;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/discovery-candidates/${encodeURIComponent(input.candidateId)}`,
    );
  }

  discoveryCandidateAction(input: {
    project: string;
    candidateId: string;
    action: "collect" | "request-review" | "review" | "reject";
    body?: Record<string, unknown>;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/discovery-candidates/${encodeURIComponent(input.candidateId)}/${encodeURIComponent(input.action)}`,
      input.body ?? {},
      "POST",
    );
  }

  discoveryCandidateHistory(input: {
    project: string;
    candidateId: string;
  }): Promise<Array<Record<string, unknown>>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/discovery-candidates/${encodeURIComponent(input.candidateId)}/history`,
    );
  }

  evalDatasets(project: string): Promise<Array<Record<string, unknown>>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/eval-datasets`);
  }

  createEvalDataset(input: {
    project: string;
    name: string;
    description?: string;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/eval-datasets`,
      { name: input.name, description: input.description ?? "" },
      "POST",
    );
  }

  evalDataset(input: { project: string; datasetId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/eval-datasets/${encodeURIComponent(input.datasetId)}`,
    );
  }

  addEvalExample(input: {
    project: string;
    datasetId: string;
    content: string;
    expectedChoice: string;
    split?: "dev" | "holdout";
    sourceType?: string;
    verifiedBy?: string;
    runId?: string;
  }): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = {
      content: input.content,
      expected_choice: input.expectedChoice,
      split: input.split ?? "dev",
      source_type: input.sourceType ?? "verified_manual",
      verified_by: input.verifiedBy ?? "operator",
    };
    if (input.runId !== undefined) body.run_id = input.runId;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/eval-datasets/${encodeURIComponent(input.datasetId)}/examples`,
      body,
      "POST",
    );
  }

  sealEvalDataset(input: { project: string; datasetId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/eval-datasets/${encodeURIComponent(input.datasetId)}/seal`,
      {},
      "POST",
    );
  }

  runEvaluation(input: {
    project: string;
    datasetId: string;
    candidateId: string;
    serviceId?: string;
  }): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = {
      dataset_id: input.datasetId,
      candidate_id: input.candidateId,
    };
    if (input.serviceId !== undefined) body.service_id = input.serviceId;
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evaluations`,
      body,
      "POST",
    );
  }

  evaluations(project: string): Promise<Array<Record<string, unknown>>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/evaluations`);
  }

  evaluation(input: { project: string; evaluationId: string }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/evaluations/${encodeURIComponent(input.evaluationId)}`,
    );
  }

  promoteDiscoveryCandidate(input: {
    project: string;
    candidateId: string;
    evaluationId: string;
    reviewer: string;
    rationale: string;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/discovery-candidates/${encodeURIComponent(input.candidateId)}/promote`,
      {
        evaluation_id: input.evaluationId,
        reviewer: input.reviewer,
        rationale: input.rationale,
      },
      "POST",
    );
  }

  projectOntology(project: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/ontology`);
  }

  projectOntologyDiff(input: {
    project: string;
    fromVersion: number;
    toVersion: number;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/ontology/diff?from_version=${encodeURIComponent(String(input.fromVersion))}&to_version=${encodeURIComponent(String(input.toVersion))}`,
    );
  }

  rollbackProjectOntology(input: {
    project: string;
    fromVersion: number;
    rationale: string;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/ontology/rollback`,
      { from_version: input.fromVersion, rationale: input.rationale },
      "POST",
    );
  }

  operationsSummary(project: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/analytics/summary`);
  }

  alertRules(project: string): Promise<Array<Record<string, unknown>>> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/alerts/rules`);
  }

  createAlertRule(input: {
    project: string;
    name: string;
    metric: string;
    operator: string;
    threshold: number;
  }): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(input.project)}/alerts/rules`,
      {
        name: input.name,
        metric: input.metric,
        operator: input.operator,
        threshold: input.threshold,
      },
      "POST",
    );
  }

  evaluateAlerts(project: string): Promise<Record<string, unknown>> {
    return this.request(
      `/api/v1/projects/${encodeURIComponent(project)}/alerts/evaluate`,
      {},
      "POST",
    );
  }

  opsEvents(project: string, after?: string): Promise<Array<Record<string, unknown>>> {
    const query = after !== undefined ? `?after=${encodeURIComponent(after)}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}/ops/events${query}`);
  }

  resumeDecisionRun(
    inputOrProject:
      | ({
          project: string;
          runId: string;
        } & ResumeDecisionRunInput)
      | string,
    runId?: string,
    body?: ResumeDecisionRunInput,
  ): Promise<Record<string, unknown>> {
    if (typeof inputOrProject === "string") {
      return this.request(
        `/api/v1/projects/${encodeURIComponent(inputOrProject)}/runs/${encodeURIComponent(runId ?? "")}/resume`,
        serializeResumeBody(body),
        "POST",
      );
    }
    return this.request(
      `/api/v1/projects/${encodeURIComponent(inputOrProject.project)}/runs/${encodeURIComponent(inputOrProject.runId)}/resume`,
      serializeResumeBody(inputOrProject),
      "POST",
    );
  }

  cancelDecisionRun(
    inputOrProject:
      | ({
          project: string;
          runId: string;
        } & CancelDecisionRunInput)
      | string,
    runId?: string,
    body?: CancelDecisionRunInput,
  ): Promise<Record<string, unknown>> {
    if (typeof inputOrProject === "string") {
      return this.request(
        `/api/v1/projects/${encodeURIComponent(inputOrProject)}/runs/${encodeURIComponent(runId ?? "")}/cancel`,
        serializeCancelBody(body ?? { reason: "" }),
        "POST",
      );
    }
    return this.request(
      `/api/v1/projects/${encodeURIComponent(inputOrProject.project)}/runs/${encodeURIComponent(inputOrProject.runId)}/cancel`,
      serializeCancelBody(inputOrProject),
      "POST",
    );
  }
}

export { OpenClass as OpenClassClient };

export interface ResumeDecisionRunInput {
  approved_choice?: string | null;
  approvedChoice?: string | null;
  operator?: string;
  rationale?: string;
  strict_version_check?: boolean;
  strictVersionCheck?: boolean;
  use_pinned_version?: boolean;
  usePinnedVersion?: boolean;
  expected_checkpoint_revision?: number;
  expectedCheckpointRevision?: number;
  expected_node_key?: string;
  expectedNodeKey?: string;
  force_recover_stale_claim?: boolean;
  forceRecoverStaleClaim?: boolean;
}

export interface CancelDecisionRunInput {
  operator?: string;
  reason: string;
}

function serializeResumeBody(body?: ResumeDecisionRunInput): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  const approvedChoice = body?.approved_choice ?? body?.approvedChoice;
  if (approvedChoice !== undefined) payload.approved_choice = approvedChoice;
  if (body?.operator !== undefined) payload.operator = body.operator;
  if (body?.rationale !== undefined) payload.rationale = body.rationale;
  const strictVersionCheck = body?.strict_version_check ?? body?.strictVersionCheck;
  if (strictVersionCheck !== undefined) payload.strict_version_check = strictVersionCheck;
  const usePinnedVersion = body?.use_pinned_version ?? body?.usePinnedVersion;
  if (usePinnedVersion !== undefined) payload.use_pinned_version = usePinnedVersion;
  const expectedRevision = body?.expected_checkpoint_revision ?? body?.expectedCheckpointRevision;
  if (expectedRevision !== undefined) payload.expected_checkpoint_revision = expectedRevision;
  const expectedNode = body?.expected_node_key ?? body?.expectedNodeKey;
  if (expectedNode !== undefined) payload.expected_node_key = expectedNode;
  const forceRecover = body?.force_recover_stale_claim ?? body?.forceRecoverStaleClaim;
  if (forceRecover !== undefined) payload.force_recover_stale_claim = forceRecover;
  return payload;
}

function serializeCancelBody(body: CancelDecisionRunInput): Record<string, unknown> {
  const payload: Record<string, unknown> = { reason: body.reason };
  if (body.operator !== undefined) payload.operator = body.operator;
  return payload;
}

export class ControlApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string = `Request failed (${status})`,
  ) {
    super(detail);
    this.name = "ControlApiError";
  }
}

export interface ControlRequestInit extends Omit<RequestInit, "body"> {
  token?: string;
  idempotencyKey?: string;
  workspaceId?: string;
  body?: BodyInit | Record<string, unknown> | unknown[] | null;
}

export interface OpenClassControlClientOptions {
  baseUrl?: string;
  baseURL?: string;
  token?: string;
  workspaceId?: string;
  fetcher?: typeof fetch;
}

export interface ControlProject {
  id: string;
  workspace_id: string;
  engine_project_id: string;
  slug: string;
  name: string;
  created_at: string;
  redaction_enabled?: boolean;
  retention_days?: number;
}

export interface ControlApiKey {
  id: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
}

export class OpenClassControlClient {
  private readonly baseUrl: string;
  private readonly defaultToken?: string;
  private readonly defaultWorkspaceId?: string;
  private readonly fetcher: typeof fetch;

  constructor(
    optionsOrBaseUrl: OpenClassControlClientOptions | string = "/control",
    fetcher?: typeof fetch,
  ) {
    if (typeof optionsOrBaseUrl === "string") {
      this.baseUrl = optionsOrBaseUrl.replace(/\/$/, "") || "/control";
      this.fetcher = fetcher ?? ((...args) => globalThis.fetch(...args));
    } else {
      const rawBase = optionsOrBaseUrl.baseUrl ?? optionsOrBaseUrl.baseURL ?? "/control";
      this.baseUrl = rawBase.replace(/\/$/, "") || "/control";
      this.defaultToken = optionsOrBaseUrl.token;
      this.defaultWorkspaceId = optionsOrBaseUrl.workspaceId;
      this.fetcher =
        optionsOrBaseUrl.fetcher ?? fetcher ?? ((...args) => globalThis.fetch(...args));
    }
  }

  private resolveUrl(path: string): string {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    if (this.baseUrl.endsWith("/control") && normalizedPath.startsWith("/control/")) {
      return `${this.baseUrl}${normalizedPath.slice("/control".length)}`;
    }
    if (this.baseUrl.endsWith("/control") && normalizedPath === "/control") {
      return this.baseUrl;
    }
    return `${this.baseUrl}${normalizedPath}`;
  }

  private projectPrefix(projectId: string, workspaceId?: string): string {
    if (workspaceId) {
      return `/workspaces/${encodeURIComponent(workspaceId)}/projects/${encodeURIComponent(projectId)}`;
    }
    return `/projects/${encodeURIComponent(projectId)}`;
  }

  async request<T = unknown>(path: string, init?: ControlRequestInit): Promise<T> {
    const {
      token: initToken,
      idempotencyKey,
      workspaceId: initWorkspaceId,
      body,
      headers: initHeaders,
      ...restInit
    } = init ?? {};
    const resolvedToken = initToken ?? this.defaultToken;
    const resolvedWorkspaceId = initWorkspaceId ?? this.defaultWorkspaceId;
    const hasBody = body !== undefined && body !== null;
    const serializedBody = !hasBody
      ? undefined
      : typeof body === "string" ||
          body instanceof ArrayBuffer ||
          body instanceof Uint8Array ||
          (typeof FormData !== "undefined" && body instanceof FormData) ||
          (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) ||
          (typeof Blob !== "undefined" && body instanceof Blob)
        ? (body as BodyInit)
        : JSON.stringify(body);

    const headers: Record<string, string> = {
      ...(hasBody ? { "content-type": "application/json" } : {}),
      ...(resolvedToken ? { Authorization: `Bearer ${resolvedToken}` } : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      ...(resolvedWorkspaceId ? { "X-OpenClass-Workspace-Id": resolvedWorkspaceId } : {}),
    };
    if (initHeaders) {
      if (initHeaders instanceof Headers) {
        initHeaders.forEach((value, key) => {
          headers[key] = value;
        });
      } else if (Array.isArray(initHeaders)) {
        for (const [key, value] of initHeaders) {
          headers[key] = value;
        }
      } else {
        Object.assign(headers, initHeaders);
      }
    }

    const fetchInit: RequestInit = {
      ...restInit,
      ...(serializedBody !== undefined ? { body: serializedBody } : {}),
      headers,
    };

    const response = await this.fetcher(this.resolveUrl(path), fetchInit);
    if (response.status === 204) return undefined as T;
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: unknown;
        message?: unknown;
        error?: unknown;
      };
      const detail =
        typeof payload.detail === "string" && payload.detail.trim()
          ? payload.detail
          : typeof payload.message === "string" && payload.message.trim()
            ? payload.message
            : typeof payload.error === "string" && payload.error.trim()
              ? payload.error
              : response.status === 401
                ? "Session expired"
                : `Request failed (${response.status})`;
      throw new ControlApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }

  listProjects(
    workspaceOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<ControlProject[]> {
    if (typeof workspaceOrInit === "string") {
      return this.request<ControlProject[]>(
        `/workspaces/${encodeURIComponent(workspaceOrInit)}/projects`,
        init,
      );
    }
    return this.request<ControlProject[]>("/projects", workspaceOrInit);
  }

  createProject(
    workspaceOrInput: string | { name: string; description?: string; workspaceId?: string },
    inputOrInit?: { name: string; description?: string } | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<ControlProject> {
    if (typeof workspaceOrInput === "string") {
      const payload = (inputOrInit ?? { name: "" }) as { name: string; description?: string };
      return this.request<ControlProject>(
        `/workspaces/${encodeURIComponent(workspaceOrInput)}/projects`,
        {
          ...init,
          method: "POST",
          body: { name: payload.name, description: payload.description ?? "" },
        },
      );
    }
    const reqInit = inputOrInit as ControlRequestInit | undefined;
    const path = workspaceOrInput.workspaceId
      ? `/workspaces/${encodeURIComponent(workspaceOrInput.workspaceId)}/projects`
      : "/projects";
    return this.request<ControlProject>(path, {
      ...reqInit,
      method: "POST",
      body: { name: workspaceOrInput.name, description: workspaceOrInput.description ?? "" },
    });
  }

  getProject(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<ControlProject> {
    if (typeof projectIdOrInit === "string") {
      return this.request<ControlProject>(
        this.projectPrefix(projectIdOrInit, projectOrWorkspaceId),
        init,
      );
    }
    return this.request<ControlProject>(this.projectPrefix(projectOrWorkspaceId), projectIdOrInit);
  }

  getProjectSummary(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<ProjectSummary> {
    if (typeof projectIdOrInit === "string") {
      return this.request<ProjectSummary>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/summary`,
        init,
      );
    }
    return this.request<ProjectSummary>(
      `${this.projectPrefix(projectOrWorkspaceId)}/summary`,
      projectIdOrInit,
    );
  }

  listEvents(
    projectOrWorkspaceId: string,
    optionsOrProjectId?:
      | string
      | { limit?: number; offset?: number; cursor?: string; q?: string; source_type?: string },
    optionsOrInit?:
      | { limit?: number; offset?: number; cursor?: string; q?: string; source_type?: string }
      | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<unknown> {
    const isWorkspaceScoped = typeof optionsOrProjectId === "string";
    const prefix = isWorkspaceScoped
      ? this.projectPrefix(optionsOrProjectId, projectOrWorkspaceId)
      : this.projectPrefix(projectOrWorkspaceId);
    const options = (isWorkspaceScoped ? optionsOrInit : optionsOrProjectId) as
      | { limit?: number; offset?: number; cursor?: string; q?: string; source_type?: string }
      | undefined;
    const reqInit = (isWorkspaceScoped ? init : optionsOrInit) as ControlRequestInit | undefined;
    const params = new URLSearchParams();
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    if (options?.cursor !== undefined) params.set("cursor", options.cursor);
    if (options?.q !== undefined) params.set("q", options.q);
    if (options?.source_type !== undefined) params.set("source_type", options.source_type);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request(`${prefix}/events${query}`, reqInit);
  }

  ingestEvent(
    projectOrWorkspaceId: string,
    bodyOrProjectId:
      string | { content: string; source_type?: string; metadata?: Record<string, unknown> },
    bodyOrInit?:
      | { content: string; source_type?: string; metadata?: Record<string, unknown> }
      | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<unknown> {
    const isWorkspaceScoped = typeof bodyOrProjectId === "string";
    const prefix = isWorkspaceScoped
      ? this.projectPrefix(bodyOrProjectId, projectOrWorkspaceId)
      : this.projectPrefix(projectOrWorkspaceId);
    const payload = (isWorkspaceScoped ? bodyOrInit : bodyOrProjectId) as {
      content: string;
      source_type?: string;
      metadata?: Record<string, unknown>;
    };
    const reqInit = (isWorkspaceScoped ? init : bodyOrInit) as ControlRequestInit | undefined;
    return this.request(`${prefix}/events`, {
      ...reqInit,
      method: "POST",
      body: {
        content: payload.content,
        source_type: payload.source_type ?? "text",
        ...(payload.metadata ? { metadata: payload.metadata } : {}),
      },
    });
  }

  listDecisionServices(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<DecisionService[]> {
    if (typeof projectIdOrInit === "string") {
      return this.request<DecisionService[]>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/decision-services`,
        init,
      );
    }
    return this.request<DecisionService[]>(
      `${this.projectPrefix(projectOrWorkspaceId)}/decision-services`,
      projectIdOrInit,
    );
  }

  getDecisionRun(
    projectOrWorkspaceId: string,
    runIdOrProjectId: string,
    runIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<DecisionRun> {
    if (typeof runIdOrInit === "string") {
      return this.request<DecisionRun>(
        `${this.projectPrefix(runIdOrProjectId, projectOrWorkspaceId)}/runs/${encodeURIComponent(runIdOrInit)}`,
        init,
      );
    }
    return this.request<DecisionRun>(
      `${this.projectPrefix(projectOrWorkspaceId)}/runs/${encodeURIComponent(runIdOrProjectId)}`,
      runIdOrInit,
    );
  }

  resumeDecisionRun(
    projectOrWorkspaceId: string,
    runIdOrProjectId: string,
    bodyOrRunId?: ResumeDecisionRunInput | string,
    bodyOrInit?: ResumeDecisionRunInput | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    if (typeof bodyOrRunId === "string") {
      return this.request<Record<string, unknown>>(
        `${this.projectPrefix(runIdOrProjectId, projectOrWorkspaceId)}/runs/${encodeURIComponent(bodyOrRunId)}/resume`,
        {
          ...init,
          method: "POST",
          body: serializeResumeBody(bodyOrInit as ResumeDecisionRunInput | undefined),
        },
      );
    }
    return this.request<Record<string, unknown>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/runs/${encodeURIComponent(runIdOrProjectId)}/resume`,
      {
        ...(bodyOrInit as ControlRequestInit | undefined),
        method: "POST",
        body: serializeResumeBody(bodyOrRunId),
      },
    );
  }

  cancelDecisionRun(
    projectOrWorkspaceId: string,
    runIdOrProjectId: string,
    bodyOrRunId: CancelDecisionRunInput | string,
    bodyOrInit?: CancelDecisionRunInput | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    if (typeof bodyOrRunId === "string") {
      return this.request<Record<string, unknown>>(
        `${this.projectPrefix(runIdOrProjectId, projectOrWorkspaceId)}/runs/${encodeURIComponent(bodyOrRunId)}/cancel`,
        {
          ...init,
          method: "POST",
          body: serializeCancelBody((bodyOrInit as CancelDecisionRunInput) ?? { reason: "" }),
        },
      );
    }
    return this.request<Record<string, unknown>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/runs/${encodeURIComponent(runIdOrProjectId)}/cancel`,
      {
        ...(bodyOrInit as ControlRequestInit | undefined),
        method: "POST",
        body: serializeCancelBody(bodyOrRunId),
      },
    );
  }

  listUnknowns(
    projectOrWorkspaceId: string,
    optionsOrProjectId?:
      | string
      | {
          state?: string;
          category?: string;
          q?: string;
          query?: string;
          limit?: number;
          offset?: number;
        },
    optionsOrInit?:
      | {
          state?: string;
          category?: string;
          q?: string;
          query?: string;
          limit?: number;
          offset?: number;
        }
      | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    const isWorkspaceScoped = typeof optionsOrProjectId === "string";
    const prefix = isWorkspaceScoped
      ? this.projectPrefix(optionsOrProjectId, projectOrWorkspaceId)
      : this.projectPrefix(projectOrWorkspaceId);
    const options = (isWorkspaceScoped ? optionsOrInit : optionsOrProjectId) as
      | {
          state?: string;
          category?: string;
          q?: string;
          query?: string;
          limit?: number;
          offset?: number;
        }
      | undefined;
    const reqInit = (isWorkspaceScoped ? init : optionsOrInit) as ControlRequestInit | undefined;
    const params = new URLSearchParams();
    if (options?.state !== undefined) params.set("state", options.state);
    if (options?.category !== undefined) params.set("category", options.category);
    if (options?.q !== undefined) params.set("q", options.q);
    if (options?.query !== undefined) params.set("query", options.query);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<Record<string, unknown>>(`${prefix}/unknowns${query}`, reqInit);
  }

  clusterUnknowns(
    projectOrWorkspaceId: string,
    bodyOrProjectId?: string | { threshold?: number; limit?: number },
    bodyOrInit?: { threshold?: number; limit?: number } | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    const isWorkspaceScoped = typeof bodyOrProjectId === "string";
    const prefix = isWorkspaceScoped
      ? this.projectPrefix(bodyOrProjectId, projectOrWorkspaceId)
      : this.projectPrefix(projectOrWorkspaceId);
    const body = (isWorkspaceScoped ? bodyOrInit : bodyOrProjectId) as
      { threshold?: number; limit?: number } | undefined;
    const reqInit = (isWorkspaceScoped ? init : bodyOrInit) as ControlRequestInit | undefined;
    const payload: Record<string, unknown> = {};
    if (body?.threshold !== undefined) payload.threshold = body.threshold;
    if (body?.limit !== undefined) payload.limit = body.limit;
    return this.request<Record<string, unknown>>(`${prefix}/unknowns/cluster`, {
      ...reqInit,
      method: "POST",
      body: payload,
    });
  }

  listClusters(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Array<Record<string, unknown>>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Array<Record<string, unknown>>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/unknowns/clusters`,
        init,
      );
    }
    return this.request<Array<Record<string, unknown>>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/unknowns/clusters`,
      projectIdOrInit,
    );
  }

  listDiscoveryCandidates(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Array<Record<string, unknown>>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Array<Record<string, unknown>>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/unknowns/candidates`,
        init,
      );
    }
    return this.request<Array<Record<string, unknown>>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/discovery-candidates`,
      projectIdOrInit,
    );
  }

  listEvaluationDatasets(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Array<Record<string, unknown>>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Array<Record<string, unknown>>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/eval-datasets`,
        init,
      );
    }
    return this.request<Array<Record<string, unknown>>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/eval-datasets`,
      projectIdOrInit,
    );
  }

  listEvaluations(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Array<Record<string, unknown>>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Array<Record<string, unknown>>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/evaluations`,
        init,
      );
    }
    return this.request<Array<Record<string, unknown>>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/evaluations`,
      projectIdOrInit,
    );
  }

  listServiceVersions(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Record<string, unknown>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/unknowns/ontology`,
        init,
      );
    }
    return this.request<Record<string, unknown>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/ontology`,
      projectIdOrInit,
    );
  }

  getAnalyticsSummary(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Record<string, unknown>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Record<string, unknown>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/analytics/summary`,
        init,
      );
    }
    return this.request<Record<string, unknown>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/analytics/summary`,
      projectIdOrInit,
    );
  }

  listIntegrations(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<Array<Record<string, unknown>>> {
    if (typeof projectIdOrInit === "string") {
      return this.request<Array<Record<string, unknown>>>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/integrations`,
        init,
      );
    }
    return this.request<Array<Record<string, unknown>>>(
      `${this.projectPrefix(projectOrWorkspaceId)}/integrations`,
      projectIdOrInit,
    );
  }

  listApiKeys(
    projectOrWorkspaceId: string,
    projectIdOrInit?: string | ControlRequestInit,
    init?: ControlRequestInit,
  ): Promise<ControlApiKey[]> {
    if (typeof projectIdOrInit === "string") {
      return this.request<ControlApiKey[]>(
        `${this.projectPrefix(projectIdOrInit, projectOrWorkspaceId)}/keys`,
        init,
      );
    }
    return this.request<ControlApiKey[]>(
      `${this.projectPrefix(projectOrWorkspaceId)}/keys`,
      projectIdOrInit,
    );
  }
}
