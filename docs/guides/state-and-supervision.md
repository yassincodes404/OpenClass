# Runtime state and supervision

Decision-service create, patch, and read APIs expose additive `runtime_config`
configuration. OpenAPI includes the complete typed models. Configuration changes
create a new service version; no node fields or SQL migrations are required.
These are operator configuration endpoints, not authenticated calibration
attestation services. Restrict access through the deployment's trusted boundary.

## Declared state

Example service configuration:

```json
{
  "runtime_config": {
    "version": 1,
    "state_schema": {
      "id": "customer_state",
      "version": 1,
      "features": [
        {
          "id": "blocked",
          "kind": "boolean",
          "sensor_field": "refund_blocked",
          "source": "metadata",
          "required": true,
          "nullable": false
        }
      ]
    },
    "node_preconditions": {
      "refund-router": [{"field": "blocked", "equals": false}]
    },
    "budgets": {
      "max_field_chars": 4096,
      "max_field_bytes": 16384,
      "max_total_bytes": 131072,
      "max_estimated_tokens": 131072
    }
  }
}
```

Ingest metadata using `POST /api/v1/projects/{project}/events`, then execute
using its `raw_event_ids`. The raw event remains unchanged. The compiler copies
only declared `string`, `integer`, and `boolean` values; optional nullable values
are supported. It never coerces `"false"` to false or false to 0. An absent
optional field is omitted from facts and tagged `missing`; explicit null is a
present fact tagged `null`. Missing required values and incorrect types fail.
No schema means no metadata facts are forwarded, not unrestricted metadata.

`source: "prior_decision"` reads a captured prior node's actual selected/approved
choice, with `sensor_field` identifying its exact node name or UUID. It does not
read a similarly named metadata value. Prior decisions are model decisions or
operator selections, never automatically verified labels. Provenance records
source, field, event ID, presence, and prior node identity where applicable, with
`verified_ground_truth: false`. There is no state classification or expression
evaluation. Node preconditions are exact equality predicates keyed by node UUID
or name (UUID takes precedence); missing fields fail predicates.

Facts, provenance and actual prior decisions reach `Observation.metadata` and
Jev/Laya state payloads, Laya's in-process router, and Gateway user context as
bounded JSON untrusted data. They are not concatenated into service instructions.
Undeclared approval, claim and profile metadata grants no authority.

## Bounds and representation errors

The limits above are defaults, not model capacity claims. Per-field limits count
string characters and serialized JSON bytes. Total limits cover the compiled
snapshot including provenance/configuration, the complete choice request, and a
conservative serialization of the actual adapter payload including choices,
instructions and nested context. Unicode JSON escaping is included; bounds may
reject earlier than a more compact HTTP encoding would.

Estimated token units equal serialized UTF-8 bytes. This is a conservative
budgeting proxy for supported text protocols, **not a measured token count or
tokenizer guarantee**. Actual provider token usage, when supplied, remains
separate telemetry. Select limits below a provider's independently established
context capacity; do not infer capacity from these defaults.

Wire-behavior note: the GLM gateway's previous fixed 4000-character observation
excerpt was removed so full observations and state reach the provider. Gateway
payloads are now bounded only by the configurable total budget
(`provider_payload_budget_exceeded`, default 128 KB serialized). Operators
constraining upstream cost or latency should set `max_total_bytes` /
`max_estimated_tokens` explicitly rather than relying on the former excerpt
limit.

No values are silently truncated. Nonfinite numbers, unsupported source values,
invalid JSON, missing/type errors, unsatisfied preconditions and exceeded budgets
raise `StateCompilationError`. HTTP execution returns 422:

```json
{"detail": {"kind": "state_compilation", "code": "precondition_unsatisfied"}}
```

Codes include `invalid_json`, `missing_required_field`, `wrong_field_type`,
`field_budget_exceeded`, `total_budget_exceeded`,
`provider_payload_budget_exceeded`, and `precondition_unsatisfied`.
Messages/events do not echo field contents. A failed initial representation
appends `decision_run.failed` with `stage: "state_compilation"` and no fabricated
semantic run, probabilities, usage or UNKNOWN observation. Resume failures use
the existing fenced checkpoint failure event/status. Provider failures retain
their existing error kinds and HTTP behavior.

## Provider-neutral supervision

`runtime_config.supervision` has defaults `min_margin: 0.25`,
`max_unknown_probability: 0.2`, `min_top_probability: 0.5`, `max_choices: 50`.
Node thresholds can tighten, never relax, these limits. High-risk nodes always
require review, and `pause_on_review` still forces an approval gate.
Semantic UNKNOWN always remains UNKNOWN.

`runtime_config.operating_profile` is an optional trusted operator-supplied
`OperatingProfile`. Otherwise the executor captures the configured adapter's
typed `operating_profile`. No provider-name or wire-metadata trust branches
exist. Missing, unknown, or uncalibrated profiles require review.

Profiles distinguish `declared_max_choices` from `measured_max_choices`;
counts include UNKNOWN. Calibrated continuation additionally requires
`calibration_status: "calibrated"` and `validation_artifact_hash`, a measured
choice limit, and passing all policy/profile boundaries. This configuration
references operator-reviewed evidence; the runtime neither creates nor verifies
an empirical calibration artifact. Unit fixtures using calibrated profiles are
synthetic, not evidence of model quality. Non-unit `temperature` requires review:
this runtime does not pretend to perform validated temperature scaling or ECE
fitting.

Jev, Laya and Gateway default to uncalibrated profiles: declarations alone never
establish production confidence. Laya separately preserves declared capability
and OpenClass measurements. Mock explicitly declares
`calibration_status: "simulated", allow_simulated_continuation: true` to retain
the no-key demo; its reason and provenance remain simulated, not empirical
confidence. Laya's lexical fallback remains labeled simulated and conservative.

Calibration also requires the current result's **adapter-owned execution
provenance**. Providers return the additive core `ProvenancedChoiceResult`
subtype with an `InferenceProvenance` identifying their actual inference path.
Plain `ChoiceResult` responses remain valid protocol results but cannot grant
automatic continuation. Metadata fields named `real_inference`, `simulated`,
`calibration_status` or `inference_provenance` cannot substitute for this typed
contract. Registered adapter code is trusted; an upstream response is not.
Explicit upstream simulation/fallback reports can withhold provenance, never
grant calibration authority.

Jev HTTP, Laya HTTP/in-process and Gateway calls identify their adapter execution
paths; this does not attest to a remote server's internal implementation or
establish empirical quality. Mock and Laya lexical fallback identify simulated
execution. A calibrated profile cannot authorize a simulated result, even if
`allow_simulated_continuation` is true. Simulated continuation requires both a
simulated profile with that explicit opt-in and typed simulated execution facts.
Real inference cannot masquerade as the no-key demo either.

Each step records its current inference provenance (or null when unavailable).
Resume evaluates every newly executed node using fresh execution provenance
against the captured profile. Approval of an earlier node never calibrates a
later fallback. These records use existing run/checkpoint JSON; no SQL schema or
client service/node contract changes are introduced by the provenance correction.

## Persistence and compatibility

Service JSON stores the schema, policies and budgets; captured run/checkpoint
state stores the effective profile too. Pending operations retain the complete
service snapshot. Restart/resume uses those captured objects, not newly edited
active configuration or an adapter's newly changed profile. Revision CAS,
renewable lease fencing, actual-node approval validation, cancellation and
append-only initial run storage remain unchanged.

Default-only runtime configuration is omitted **only from the service hash** to
preserve legacy fingerprints; it is not dropped from stored/returned models.
Older checkpoints without captured runtime configuration cannot gain trust from
a newly named provider. Their fallback configuration remains conservative.
Historical choices-only version rows cannot reconstruct missing schema/profile
history; existing pinned-hash checks fail closed if the full snapshot is absent.

Clients must preserve service-level `runtime_config` on read/edit round trips.
No node-schema extension is required. Strict client create/patch schemas need an
optional typed `runtime_config` extension to configure this feature; unknown-field
stripping must not silently discard it. Graph-only edits can omit it because
patches preserve the existing configuration.
