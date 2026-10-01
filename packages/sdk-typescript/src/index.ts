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

export class OpenClass {
  constructor(
    private readonly baseURL = "http://localhost:7331",
    private readonly fetcher: typeof fetch = (...args) => globalThis.fetch(...args),
  ) {}

  private async request<T>(
    path: string,
    body?: unknown,
    method?: "GET" | "POST" | "PATCH" | "DELETE",
    headers?: Record<string, string>,
  ): Promise<T> {
    const response = await this.fetcher(`${this.baseURL.replace(/\/$/, "")}${path}`, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...headers,
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
  projects(): Promise<Project[]> {
    return this.request("/api/v1/projects");
  }
  createProject(input: { name: string; description?: string }): Promise<Project> {
    return this.request("/api/v1/projects", {
      name: input.name,
      description: input.description ?? "",
    });
  }
  project(project: string): Promise<Project> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}`);
  }
  updateProject(
    project: string,
    changes: { name?: string; description?: string; status?: "active" | "archived" },
  ): Promise<Project> {
    return this.request(`/api/v1/projects/${encodeURIComponent(project)}`, changes, "PATCH");
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
  createEventsBatch(input: {
    project: string;
    items: Array<{ content: string; metadata?: Record<string, unknown>; source_type?: string }>;
    sourceType?: "text" | "json" | "csv" | "webhook";
  }): Promise<RawEvent[]> {
    return this.request(`/api/v1/projects/${encodeURIComponent(input.project)}/events/batch`, {
      items: input.items,
      source_type: input.sourceType ?? "text",
    });
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
}
