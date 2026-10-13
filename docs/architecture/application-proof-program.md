# Application proof program

Date: 2026-10-02. Direction: founder-authorized development priority.
Status: delivery plan; runtime contracts below require scoped design review and
implementation. OpenClass remains an unreleased Genesis foundation.

## Objective and priority

Prove that different applications can repeatedly produce useful, verified outcomes
through the same Core:

**Connect → Observe → Decide → Act → Verify → Learn → Improve.**

Core execution, integrations and measured application outcomes take priority over
additional isolated Jev research and peripheral SaaS work. Defer billing, teams,
enterprise permissions, marketplace and polished onboarding. Security needed for
an actual integration remains part of that integration's scope. The portal serves
application operation, evidence inspection and review through HTTP SDKs.

This supersedes the immediate research-first sequencing in
[Discovery productionization](discovery-productionization.md); its reuse assessment,
frozen artifacts and evaluation safeguards remain applicable. Existing ticket IDs
and Genesis/Discovery release gates remain intact.

No major Core capability is mature until an application uses it through persistence,
backend, public API, SDK, UI/user action, persisted outcome and reload/restart.
An offline contract check establishes implementation behavior; a simulated
application establishes simulator behavior; neither establishes live deployment
quality. Record the evidence level explicitly.

## Delivery order

1. Restore CI on the actual target branch. Validate installation, migrations,
   contracts and builds without live provider credentials.
2. Stabilize the execution path: Project, typed State with source/freshness
   provenance, DecisionService/DecisionGraph, Choice, Transition, Capability,
   Execution and independent Verification. Ship one bounded transition with a
   real adapter before implementing every transition kind.
3. Establish integration manifests, scoped bindings and adapter contracts alongside
   that implementation. Extend existing authenticated webhook ingestion rather
   than creating a competing ingress path.
4. Add generic HTTP/webhook, PostgreSQL query, CSV/JSON and MQTT adapters in small
   slices, each driven by a concrete application requirement.
5. Application A: customer operations. Begin with authorized support data and one
   observable routing action. Reuse OC-028/030 for this application.
6. Application B: developer operations, including OpenClass dogfooding in a
   disposable environment. Reuse OC-029's confinement and postcondition review.
7. Strengthen shared Core from failures in A/B; complete verified evaluation and
   immutable reviewed activation (OC-008/009/017) before claiming learning.
8. Application C: smart-home simulation, then authorized Home Assistant/MQTT use.
9. Application D: robot simulator with structured perception input and deterministic
   control. Physical hardware follows separate application evidence.
10. Compare all four under declared protocols, then expand productization.

## Choice, transition and execution boundary

A Choice is semantic: `PAYMENT_PROBLEM`. A separately versioned Transition binds
that choice to an approved operation such as `check_customer_payment`. A model
selects a bounded choice; deterministic Core rules resolve allowed transitions.
UNKNOWN remains available and may wait, collect evidence or request review; it
never grants authority to invent an action or a class.

Target transition kinds include capability, query, workflow, LLM/Teacher, human,
wait, next decision and termination. Their presence in a target design does not
make them supported. Start with a capability and termination; add each kind only
with typed inputs/results, safe errors, persistence, events and contracts.

Each execution captures project, source event/state identity, decision run, exact
policy/ontology/spec versions, transition/binding version, operation identity,
idempotency identity and timestamps. Verification records an independently
observed postcondition and its provenance. An adapter returning success, HTTP 200,
or a model predicting success is insufficient unless it is the declared observable
postcondition. A verification result is execution evidence, not a semantic label.

Persist intent before external side effects. Record timeout/ambiguous outcomes;
reconcile before retrying non-idempotent actions. Do not promise exactly-once
external effects. Bounded retries, permissions and independent verifiers belong
in the first write-capability slice. Infrastructure failures stay distinct from
semantic UNKNOWN and cannot become novelty evidence automatically.

Core owns types, ports and rules; server adapters own transports and secret
resolution. Providers never receive writable ontology access. Applications and
clients use public HTTP SDKs, including application configuration and reports.

## Integration subsystem

The target manifest advertises supported SOURCE, QUERY, CAPABILITY, TRIGGER and
SINK operations, typed schemas, verifier identities and adapter version. Connections
bind those operations within a project using opaque environment secret references.
Health/connectivity and granted execution authority are separate states.

`connect`, `health`, `subscribe`, `fetch`, `execute` and `verify` are conceptual
operations, not six mandatory methods on every adapter. Use narrow typed ports
for implemented roles. Unsupported roles report explicitly unsupported behavior.
Teacher proposals may reference registered operations; they cannot manufacture
permissions, integrations or arbitrary executable code.

| Integration group     | Initial application need                           | Expansion gate                                                                   |
| --------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------- |
| HTTP/webhook          | Support ingestion and one verified outbound action | Bounded transport, credentials, replay/conflict and verification contracts       |
| PostgreSQL            | Read application state                             | Scoped read permissions and typed query results; no arbitrary generated SQL      |
| CSV/JSON              | Import authorized support data                     | Provenance, validation, partial failure and restart-safe deduplication           |
| MQTT                  | Sensor/state events and simulator control          | Delivery identity, state freshness, reconnect and postcondition checks           |
| GitHub/Docker/process | Developer operations                               | Allowlisted operations and disposable application environment                    |
| Email/Slack/Discord   | Routing and notifications                          | Explicit send authorization and independently observable receipt where available |
| n8n                   | Existing external workflows                        | Optional adapter; no requirement for a no-n8n deployment                         |
| AI providers          | Decisions and Teacher proposals                    | Provider-neutral contracts, sanitized failures and measured usage                |
| Perception            | Robot simulator state                              | Typed CV results, source timestamps and missing/stale state handling             |

Redis Streams, Kafka, object storage and camera/video transport follow demonstrated
needs; this priority list does not authorize speculative infrastructure.

## Four application protocols

| Application             | Input / bounded decisions                                                                               | Action and verification                                                                    | Evidence required                                                                                      |
| ----------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| A: Customer operations  | Authorized tickets/CSV/webhooks; intent, severity, escalation, UNKNOWN                                  | Route/create a ticket; read its destination/state independently                            | Human/verified routing labels, UNKNOWN rate, verified outcomes, Teacher usage, measured latency/cost   |
| B: Developer operations | Logs, CI/process/container/HTTP state; port conflict, DB readiness, migration pending, healthy, UNKNOWN | One allowlisted recovery; test exit status, health probe and expected Git/filesystem state | Recovery failures, false interventions, postconditions, retained scenarios and restart behavior        |
| C: Smart home           | MQTT/simulated sensors, device and occupancy state; dim/off/cool/keep/alert, UNKNOWN                    | Scene/device change; independent state observation                                         | State age, repeated patterns, stale/missing input failures, device outcome and energy data if measured |
| D: Robot simulator      | Structured simulator/CV state; forward/left/right/stop, UNKNOWN                                         | Deterministic simulator movement; simulator position/collision/goal checks                 | Seeds, task outcomes, unsafe moves, perception failures and control latency; explicitly simulated      |

All four use the same versioned Core contracts, with domain code in adapters and
application configuration. A comparison fails its generalization gate if an
application requires a hidden domain-specific fork of Core. Do not count five
support demos as five domains or simulation runs as physical-device evidence.

## Proof reports and metrics

Reports derive from persisted scoped records. Capture application, period/timezone,
dataset/source provenance, protocol version, policy/provider/binding versions,
deployment identity, metric formulas, counts/denominators and evidence links.
Report failed experiments and incomplete verification alongside successes.

| Metric family | Required definition                                                                                                                                                                |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decisions     | decision_count counts completed runs; known_rate and unknown_rate share that denominator; escalation_rate counts actual escalation records against completed runs                  |
| Quality       | decision_accuracy uses independently labeled eligible runs; trusted_error_rate uses independently checked trusted runs; show label coverage and undefined values                   |
| Execution     | execution_success_rate uses terminal execution outcomes; verification_success_rate uses completed verification attempts; report pending, missing and ambiguous outcomes separately |
| Teacher       | Actual calls and calls per 1,000 ingested distinct events, including failed calls; no inference from candidate count                                                               |
| Candidates    | Proposal count, accepted/rejected counts and rates against reviewed candidates; pending candidates remain visible                                                                  |
| Retention     | knowledge_retention_rate compares eligible historical verified cases under baseline/candidate replay; regressions_prevented counts recorded regression-blocked evaluations         |
| Cost/latency  | Measured provider/Teacher usage and costs with currency/source; decision/execution latency sample counts and quantiles; cost_per_event includes only declared measured components  |
| Improvement   | Exact before/after policy versions, same retained dataset and declared later-event cohort; report changes and failures                                                             |

Missing usage/cost or missing labels yields unavailable metrics, not zero. Publish
an avoided-Teacher-call count only when linked later reuse records and a declared
baseline policy justify it; label counterfactual estimates separately from measured
calls. Partial reports are allowed, but must expose unavailable learning metrics
until evaluation/review/versioning exist. No sample figures from the product
proposal become repository results.

Each experiment records hypothesis, success criteria before execution, environment,
source authorization/provenance, result, failures, retained evidence, diagnosed
layer and resulting ticket. A failed occupancy experiment may motivate freshness
metadata; it must not silently become a successful lighting proof after redesign.

## Next reviewable slices

See OC-034–039 in [tickets](../contributing/tickets.md). The immediate deliverable
is CI repair and a reviewed execution/integration contract followed by one customer
operations vertical. Evaluation and activation remain blocked until OC-008/009/017
pass their existing acceptance criteria. No deployment or release is implied.
