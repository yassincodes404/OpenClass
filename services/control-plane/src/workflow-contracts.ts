import { BadGatewayException, BadRequestException, NotFoundException } from "@nestjs/common";
import { z } from "zod";
import type { Role } from "./workspace.service.js";

const text = (max: number) => z.string().trim().min(1).max(max);
const providerStatus = z.object({
  default_provider: text(100),
  laya: z.object({
    status: text(100),
    mode: text(100),
    daemon_status: text(100),
    model: text(200),
    default: z.boolean(),
  }),
  jev: z.object({
    status: text(100),
    model: text(200),
    configured: z.boolean(),
    default: z.boolean(),
  }),
});

/** Project viewers need runtime status, not private connection/credential fields. */
export function publicProviderStatus(value: unknown) {
  const parsed = providerStatus.safeParse(value);
  if (!parsed.success) throw new BadGatewayException("Provider status unavailable");
  return { ...parsed.data, laya: { ...parsed.data.laya, endpoint: "" } };
}

const id = z.string().uuid();
const choice = z
  .object({
    key: text(50).regex(/^[A-Z][A-Z0-9_]*$/),
    label: text(100),
    description: z.string().max(1000).optional(),
    aliases: z.array(text(100)).max(50).optional(),
    target_node_id: id.nullable().optional(),
    target_node_name: text(100).nullable().optional(),
  })
  .strict();
const node = z
  .object({
    id: id.optional(),
    name: text(100),
    instructions: text(2000),
    choices: z.array(choice).min(1).max(50),
    risk_level: z.enum(["ordinary", "high"]).optional(),
    min_margin: z.number().min(0).max(1).nullable().optional(),
    max_unknown_probability: z.number().min(0).max(1).nullable().optional(),
    pause_on_review: z.boolean().optional(),
  })
  .strict();
const transition = z
  .object({
    from_node_key: text(200),
    choice_key: text(120),
    to_node_key: text(200),
    require_approval: z.boolean(),
  })
  .strict();
const service = z
  .object({
    name: text(200),
    instructions: text(4000),
    description: z.string().max(2000).optional(),
    provider_override: text(100).nullable().optional(),
    choices: z.array(choice).min(1).max(49).optional(),
    nodes: z.array(node).min(1).max(50).optional(),
    transitions: z.array(transition).max(500).optional(),
  })
  .strict();
const diagnosis = z.enum([
  "decision_space",
  "procedure",
  "state_representation",
  "precondition",
  "missing_capability",
  "provider_failure",
  "out_of_domain",
  "ambiguous_or_insufficient",
  "analytical_gap",
]);
const status = z.enum(["pending", "triaged", "resolved", "dismissed", "ready_for_evolution"]);
const empty = z.object({}).strict();
const integration = z
  .object({
    name: text(60),
    type: z.enum(["mcp", "webhook", "rest_api", "provider", "database"]),
    endpoint: text(2048).nullable().optional(),
    capabilities: z.array(text(200)).max(100).optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
    secret_ref: text(200).nullable().optional(),
  })
  .strict();
type Rule = {
  method: string;
  path: RegExp;
  role: Role;
  status?: number;
  body?: z.ZodType;
};
const uuid = "[0-9a-fA-F-]{36}";
const rules: Rule[] = [
  { method: "GET", path: /^$/, role: "viewer" },
  {
    method: "PATCH",
    path: /^$/,
    role: "admin",
    body: z
      .object({
        name: text(200).optional(),
        description: z.string().max(2000).optional(),
        status: z.enum(["active", "archived"]).optional(),
      })
      .strict(),
  },
  {
    method: "GET",
    path: /^(summary|analytics|audit|evolution\/summary|ops\/summary|ops\/events|analytics\/summary|provider-status)$/,
    role: "viewer",
  },
  {
    method: "GET",
    path: /^(events|runs|decision-services|evidence|evidence-cases|candidates|discovery-candidates|eval-datasets|evaluations|integrations)$/,
    role: "viewer",
  },
  {
    method: "GET",
    path: new RegExp(
      `^(events|runs|decision-services|evidence|evidence-cases|candidates|eval-datasets|evaluations|integrations)/${uuid}$`,
    ),
    role: "viewer",
  },
  {
    method: "GET",
    path: new RegExp(`^(evidence-cases/${uuid}/evidence|runs/${uuid}/feedback)$`),
    role: "viewer",
  },
  {
    method: "POST",
    path: /^events$/,
    role: "developer",
    status: 201,
    body: z
      .object({
        content: text(100_000),
        source_type: z.enum(["text", "json", "csv", "webhook"]).optional(),
        metadata: z.record(z.string(), z.unknown()).optional(),
      })
      .strict(),
  },
  {
    method: "POST",
    path: /^events\/batch$/,
    role: "developer",
    status: 207,
    body: z
      .object({
        source_type: z.enum(["text", "json", "csv", "webhook"]).optional(),
        items: z
          .array(
            z
              .object({
                content: text(100_000),
                metadata: z.record(z.string(), z.unknown()).optional(),
              })
              .strict(),
          )
          .min(1)
          .max(1000),
      })
      .strict(),
  },
  {
    method: "POST",
    path: /^decision-services$/,
    role: "admin",
    status: 201,
    body: service.refine((v) => Boolean(v.choices?.length || v.nodes?.length)),
  },
  {
    method: "PATCH",
    path: new RegExp(`^decision-services/${uuid}$`),
    role: "admin",
    body: service
      .omit({ choices: true })
      .partial()
      .extend({ status: z.enum(["active", "draft", "archived"]).optional() })
      .strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^decision-services/${uuid}/runs$`),
    role: "developer",
    status: 201,
    body: z
      .object({
        content: text(10_000).optional(),
        raw_event_ids: z.array(id).min(1).max(100).optional(),
      })
      .strict()
      .refine((v) => Boolean(v.content || v.raw_event_ids?.length)),
  },
  {
    method: "PATCH",
    path: new RegExp(`^evidence/${uuid}/triage$`),
    role: "reviewer",
    body: z.object({ diagnosis, rationale: text(2000) }).strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^evidence/${uuid}/transition$`),
    role: "reviewer",
    body: z.object({ target_status: status, note: z.string().max(2000).optional() }).strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^evidence/${uuid}/ai-diagnose$`),
    role: "reviewer",
    body: empty,
  },
  {
    method: "POST",
    path: /^evidence-cases$/,
    role: "reviewer",
    status: 201,
    body: z
      .object({
        title: text(200),
        description: z.string().max(2000).optional(),
        decision_service_id: id.optional(),
        evidence_ids: z.array(id).max(200).optional(),
      })
      .strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^evidence-cases/${uuid}/evidence$`),
    role: "reviewer",
    body: z.object({ evidence_id: id }).strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^runs/${uuid}/feedback$`),
    role: "reviewer",
    status: 201,
    body: z
      .object({
        action: z.enum([
          "confirm",
          "correct",
          "missing_concept",
          "ambiguous",
          "out_of_domain",
          "note",
        ]),
        corrected_choice: text(100).optional(),
        note: z.string().max(2000).optional(),
      })
      .strict(),
  },
  {
    method: "POST",
    path: /^evolution\/propose$/,
    role: "reviewer",
    status: 201,
    body: z
      .object({
        service_id: id.optional(),
        evidence_ids: z.array(id).min(3).max(20).optional(),
        evidence_case_id: id.optional(),
      })
      .strict()
      .refine((v) => Boolean(v.evidence_case_id || (v.service_id && v.evidence_ids))),
  },
  {
    method: "POST",
    path: new RegExp(`^candidates/${uuid}/reject$`),
    role: "reviewer",
    body: z.object({ reason: text(1000) }).strict(),
  },
  // Compatibility evaluation/promotion routes are deliberately NOT proxied:
  // they cannot bind a verified dataset and explicit approval.
  {
    method: "POST",
    path: /^eval-datasets$/,
    role: "admin",
    status: 201,
    body: z
      .object({ name: text(200).min(2), description: z.string().max(2000).optional() })
      .strict(),
  },
  {
    method: "POST",
    path: new RegExp(`^eval-datasets/${uuid}/examples$`),
    role: "reviewer",
    status: 201,
    body: z
      .object({
        text: text(10_000),
        label: text(100),
        source: z.enum(["human", "verified_external"]),
        annotator: text(200).min(2),
        rationale: z.string().max(2000).optional(),
        slice_tag: z.enum(["historical", "recent", "rare", "hard", "unknown", "adversarial"]),
        source_type: z.enum(["verified_holdout", "regression_baseline", "calibration_dev"]),
        split: z.enum(["holdout", "regression", "calibration"]),
      })
      .strict(),
  },
  { method: "POST", path: new RegExp(`^eval-datasets/${uuid}/seal$`), role: "admin", body: empty },
  {
    method: "POST",
    path: /^evaluations$/,
    role: "admin",
    status: 201,
    body: z.object({ dataset_id: id, candidate_id: id, service_id: id.optional() }).strict(),
  },
  { method: "POST", path: /^integrations$/, role: "admin", status: 201, body: integration },
  { method: "DELETE", path: new RegExp(`^integrations/${uuid}$`), role: "admin", status: 204 },
  { method: "POST", path: new RegExp(`^integrations/${uuid}/test$`), role: "admin", body: empty },
];

/** A closed route/verb/body allowlist, never a general engine reverse proxy. */
export function workflowContract(method: string, path: string, body: unknown) {
  const rule = rules.find((r) => r.method === method && r.path.test(path));
  if (!rule) throw new NotFoundException("Workflow action is not supported");
  const parsed = rule.body?.safeParse(body ?? {});
  if (parsed && !parsed.success) throw new BadRequestException("Invalid workflow request");
  return { role: rule.role, status: rule.status ?? 200, body: parsed?.data };
}

export function workflowQuery(query: Record<string, unknown>): string {
  const schema = z
    .object({
      limit: z.coerce.number().int().min(1).max(200).optional(),
      offset: z.coerce.number().int().min(0).optional(),
      status: status.optional(),
      trigger_type: text(100).optional(),
      decision_service_id: id.optional(),
      after: text(200).optional(),
    })
    .strict();
  const result = schema.safeParse(query);
  if (!result.success) throw new BadRequestException("Invalid workflow query");
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(result.data))
    if (value !== undefined) params.set(key, String(value));
  return params.size ? `?${params}` : "";
}
