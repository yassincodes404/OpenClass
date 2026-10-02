import { BadGatewayException, BadRequestException, Injectable, NotFoundException } from "@nestjs/common";

export type EngineProject = { id: string; slug: string; name: string; description: string; status?: string };
export type EngineClassifier = {
  id: string;
  slug: string;
  name: string;
  description?: string;
  active_ontology_version_id: string;
};
export type EngineOntologyClass = { canonical_name: string; display_name: string; aliases?: string[] };
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

/**
 * HTTP-only client for the FastAPI engine. The engine stays the sole owner of
 * decision/ontology logic; the control plane only proxies and maps ids.
 */
@Injectable()
export class EngineClient {
  private readonly baseUrl = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:7331";

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
    return this.request<EngineClassifier>("GET", `/api/v1/classifiers/${encodeURIComponent(identifier)}`);
  }

  async getOntology(identifier: string): Promise<EngineOntology> {
    return this.request<EngineOntology>("GET", `/api/v1/classifiers/${encodeURIComponent(identifier)}/ontology`);
  }

  async providers(): Promise<unknown[]> {
    return this.request<unknown[]>("GET", "/api/v1/providers");
  }

  async providerStatus(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("GET", "/api/v1/providers/status");
  }

  async ingestEvent(
    engineProjectId: string,
    body: { content: string; source_type?: string; metadata?: Record<string, unknown> },
    idempotencyKey?: string,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    return this.requestStatus("POST", `/api/v1/projects/${engineProjectId}/events`, body, [200, 201], idempotencyKey);
  }

  async ingestEventsBatch(
    engineProjectId: string,
    body: { items: Array<{ content: string; metadata?: Record<string, unknown> }>; source_type?: string },
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
    return this.request<EngineRawEvent>("GET", `/api/v1/projects/${engineProjectId}/events/${eventId}`);
  }

  async projectSummary(engineProjectId: string): Promise<{ events: number }> {
    return this.request<{ events: number }>("GET", `/api/v1/projects/${engineProjectId}/summary`);
  }

  private async requestStatus(
    method: string,
    path: string,
    body: unknown,
    expectedStatuses: number[],
    idempotencyKey?: string,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          "content-type": "application/json",
          ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        },
        body: JSON.stringify(body),
      });
    } catch {
      throw new BadGatewayException("Engine is temporarily unavailable");
    }
    const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (expectedStatuses.includes(response.status)) return { status: response.status, body: payload };
    const message = typeof payload.detail === "string" ? payload.detail : "Engine rejected the request";
    if (response.status === 404) throw new NotFoundException(message);
    if (response.status === 429) throw new BadGatewayException("Engine rate limit reached; retry shortly");
    if (response.status >= 400 && response.status < 500) throw new BadRequestException(message);
    throw new BadGatewayException("Engine request failed");
  }

  async request<T>(method: string, path: string, body?: unknown, expectedStatus = 200): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: body ? { "content-type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new BadGatewayException("Engine is temporarily unavailable");
    }
    if (response.status === expectedStatus) return (await response.json()) as T;
    const detail = await this.errorMessage(response);
    if (response.status === 404) throw new NotFoundException(detail);
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
