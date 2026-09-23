/** Public HTTP client. No backend implementation imports. */
export interface Classifier {
  id: string;
  slug: string;
  name: string;
  description: string;
  classifier_type: "single_choice";
  active_ontology_version_id: string;
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
  observation: { id: string; content: string; content_type: "text"; created_at: string };
  result: ClassificationResult;
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

  private async request<T>(path: string, body?: unknown): Promise<T> {
    const response = await this.fetcher(`${this.baseURL.replace(/\/$/, "")}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new OpenClassError(response.status);
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
}
