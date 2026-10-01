# OpenClass — Product Experience & Adaptive Runtime Specification

**Document type:** Product / UX / Platform Implementation Specification  
**Status:** Implementation target  
**Working product name:** OpenClass  
**Tagline:** **Build decision systems that operate fast, observe everything, and improve over time.**  
**Audience:** Core maintainers, coding agents, frontend/backend engineers, SDK/plugin authors, integration developers, early users

---

## 0. Purpose of this document

This document defines what OpenClass must provide as a **real product**, how it should feel to use, how its major pages and tabs should work, how multiple projects coexist, how integrations are added, how fast decision providers and full LLMs cooperate, how decisions are monitored and improved, and how the product grows from an early alpha into an extensible platform.

This is intentionally **not** a research notebook and **not** a Jev-only specification.

OpenClass must become a general adaptive-decision runtime where:

- fast bounded decision providers such as **Jev** or **Laya** can remain in the frequent runtime path;
- full LLMs can inspect the system, investigate failures, review decisions, discover better decision structures, propose changes, and create or repair integrations;
- deterministic code owns permissions, execution constraints, validation, postconditions, persistence, versions, and safety boundaries;
- users can integrate browsers, APIs, MCP servers, webhooks, databases, workflows, sensors, game engines, business systems, or custom code;
- every important decision, action, model call, latency event, failure, change, and approval is observable;
- successful improvements become reusable versioned knowledge instead of being rediscovered on every request.

The core product promise is:

> **OpenClass lets developers and businesses build systems that make fast decisions, know when they are uncertain, observe the consequences, and improve their own decision knowledge through controlled AI-assisted evolution.**

---

# 1. Product identity

OpenClass is **not**:

- a classifier dashboard;
- a Jev wrapper;
- a generic LLM chat UI;
- an n8n skin;
- a browser automation app;
- a customer-support-only product;
- a single autonomous agent that is allowed to do anything;
- a prompt-management tool;
- a model benchmark dashboard.

OpenClass **is**:

> **An extensible, observable adaptive-decision runtime for building applications whose decision systems can operate quickly, execute through controlled capabilities, detect gaps in their current knowledge, and use stronger intelligence to propose evaluated improvements over time.**

A single OpenClass installation may contain many independent projects:

```text
OpenClass Workspace
│
├── Project: GymHolic Customer Intelligence
│   ├── customer feedback
│   ├── support decisions
│   ├── analytics
│   ├── CRM/API integrations
│   └── evolving knowledge
│
├── Project: Doom Agent
│   ├── game-state adapter
│   ├── Jev/Laya decision nodes
│   ├── game actions
│   ├── performance monitoring
│   └── evolution experiments
│
├── Project: Smart Home
│   ├── Home Assistant / MQTT
│   ├── sensors
│   ├── device capabilities
│   ├── routines
│   └── energy analytics
│
├── Project: Browser Operations
│   ├── browser integration
│   ├── CRM workflows
│   ├── page-state compiler
│   ├── browser capabilities
│   └── human approval rules
│
└── Project: Model Router
    ├── model providers
    ├── cost/latency state
    ├── routing decisions
    ├── escalation policies
    └── continuously improved routing knowledge
```

The projects are different. The core runtime is the same.

---

# 2. Three product responsibilities: Operate, Evolve, Understand

OpenClass should be understandable through three verbs.

## 2.1 Operate

Run the current decision system against real state.

```text
Reality
  ↓
State Providers
  ↓
State Compiler
  ↓
Decision Graph
  ↓
Jev / Laya / other DecisionProvider
  ↓
Choice
  ↓
Transition
  ↓
Capability / Query / Workflow / Human / LLM / Next Node
  ↓
Verifier
  ↓
Result
```

The frequent path should avoid general LLM reasoning when the current knowledge already knows what to do.

## 2.2 Evolve

When reality exposes a gap, OpenClass collects evidence and allows stronger intelligence to propose a change.

```text
UNKNOWN
low-trust decision
failed postcondition
repeated correction
new owner request
missing capability
unexpected latency/cost behavior
new external environment
        ↓
Failure / Gap Diagnosis
        ↓
Supervisor / Teacher LLM
        ↓
Typed Proposal
        ↓
Evaluation / Replay / Simulation
        ↓
Approval Policy
        ↓
Knowledge Version N+1
```

The LLM does not silently rewrite the live system.

## 2.3 Understand

Users need to understand what the system is doing.

OpenClass must expose:

- decisions and distributions;
- latency by provider/model/node;
- execution results;
- model escalations;
- UNKNOWN events;
- human interventions;
- failures;
- cost and usage;
- version history;
- evaluation outcomes;
- behavior changes before/after a version;
- analytics over project events;
- AI-generated explanations grounded in actual stored traces.

---

# 3. The most important architectural rule: fast-path decisions, slow-path intelligence

OpenClass must be designed around a latency hierarchy.

Jev/Laya-class decision models are intended for the **fast decision path**. General LLMs are used for **supervision, investigation, planning, evolution, integration assistance, and difficult exceptions**.

OpenClass must never assume that a full LLM belongs in every runtime decision.

```text
FAST PATH
────────────────────────────────────────────────────
StateSnapshot
   ↓
DecisionNode
   ↓
Jev / Laya / another bounded DecisionProvider
   ↓
Choice
   ↓
known transition
   ↓
controlled execution

SLOW / SUPERVISORY PATH
────────────────────────────────────────────────────
selected traces / failures / metrics / logs
   ↓
Supervisor LLM
   ↓
analysis
   ↓
proposal / explanation / integration repair
   ↓
evaluation
   ↓
optional approval
   ↓
new version
```

Actual latency must always be **measured**, not assumed.

OpenClass must record latency for:

- state compilation;
- provider request;
- provider response;
- decision compilation;
- supervision gate;
- tool/capability execution;
- query execution;
- browser operations;
- external API calls;
- general LLM calls;
- verifier execution;
- end-to-end run time.

The UI should make it easy to answer:

> What is slowing this project down?

> Did switching from provider A to provider B improve latency?

> Is the LLM being called too often?

> Which decision node has the worst p95 latency?

> What percentage of runs stay entirely on the fast path?

---

# 4. A Choice is not just a class — it can route the system

An OpenClass `Choice` represents the **semantic decision**.

A separate `Transition` defines **what happens because of that decision**.

This separation is mandatory.

Bad design:

```text
Choice = arbitrary executable script
```

Correct design:

```text
Choice
  = WHAT was decided

Transition
  = WHAT should happen next
```

Example:

```yaml
choice:
  id: investigate_with_llm
  name: Investigate with LLM
  description: Known automation is insufficient; deeper reasoning is required.

transition:
  type: LLM
  target: support_investigator
  approval_policy: automatic
  verifier: support_resolution_verifier
```

OpenClass should support at least these transition types:

```text
NEXT_DECISION
CAPABILITY
QUERY
WORKFLOW
LLM
HUMAN
WAIT
TERMINATE
```

Future transition providers may add other types without changing core decision semantics.

---

# 5. Core runtime architecture

```text
                           OPENCLASS PROJECT
                                  │
                                  ▼
                          REALITY / APPLICATION
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
             API               Browser             Sensors
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  ▼
                            STATE PROVIDERS
                                  │
                                  ▼
                            STATE COMPILER
                                  │
                                  ▼
                             StateSnapshot
                                  │
                                  ▼
                            DECISION GRAPH
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
                Jev              Laya            Other
                 │                │                │
                 └────────────────┼────────────────┘
                                  ▼
                                Choice
                                  │
                                  ▼
                              Transition
                                  │
       ┌───────────┬──────────┬───┼────┬──────────┬──────────┐
       ▼           ▼          ▼        ▼          ▼          ▼
     Next         Tool       Query   Workflow     LLM       Human
     Node
       │
       └──────────────────────┬───────────────────────────────
                              ▼
                       POLICY / PERMISSIONS
                              │
                              ▼
                        CAPABILITY RUNTIME
                              │
                              ▼
                            ACTION
                              │
                              ▼
                            REALITY
                              │
                              ▼
                           VERIFIER
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                   PASS                FAIL
                    │                   │
                    ▼                   ▼
                continue        Failure Diagnosis
                                        │
                            ┌───────────┴────────────┐
                            ▼                        ▼
                         recovery               Supervisor LLM
                                                     │
                                                  proposal
                                                     │
                                                  evaluation
                                                     │
                                                   approval
                                                     │
                                                Version N+1

                 ALL EVENTS → OBSERVABILITY / AUDIT / ANALYTICS
```

---

# 6. Provider model

OpenClass must not hard-code Jev, Laya, Gemini, GPT, Claude, a browser, or any other vendor into canonical project knowledge.

Provider contracts should be explicit.

## 6.1 DecisionProvider

Used for bounded semantic decisions.

Examples:

- Jev
- Laya
- future local decision models
- specialized classifier/decision providers

Interface concept:

```python
DecisionProvider.decide(
    state_snapshot,
    decision_spec,
    provider_profile,
) -> DecisionResult
```

`DecisionResult` should support:

- selected choice;
- full distribution if available;
- top score/probability;
- second score/probability;
- decision margin;
- UNKNOWN probability if available;
- provider/model identity;
- latency;
- provider usage metadata;
- error/infrastructure status.

## 6.2 TeacherProvider / SupervisorProvider

Used for deeper reasoning and system improvement.

Examples:

- Gemini
- GPT
- Claude
- GLM
- local LLM
- future model

Responsibilities may include:

- review selected runs;
- inspect wrong or suspicious decisions;
- analyze latency/cost patterns;
- propose new choices;
- merge/split choices;
- repair procedures;
- propose new state features;
- propose new routing nodes;
- suggest better provider configuration;
- identify unnecessary LLM escalation;
- propose missing integrations;
- diagnose repeated execution failures;
- create inactive integration or automation drafts;
- explain system behavior to users.

The Supervisor must produce typed proposals. It must not directly mutate live knowledge.

## 6.3 Embedding / Retrieval Provider

Optional provider for high-cardinality candidate spaces, semantic retrieval, clustering, evidence search, and similarity.

## 6.4 Perception Provider

Optional provider for converting raw media/sensors into structured observations.

Examples:

- vision model;
- speech-to-text;
- OCR;
- CV pipeline;
- sensor fusion;
- custom state adapter.

## 6.5 Tool Routing Provider

Optional specialized provider for selecting functions/arguments after a semantic decision has already been made.

This should remain separate from the DecisionProvider contract.

---

# 7. Supervisor LLM: monitoring, auditing, and discovering better decisions

The Supervisor is not only an UNKNOWN handler.

It should be able to monitor the running decision system itself.

## 7.1 What the Supervisor may inspect

Depending on user permissions and project policy:

- decision inputs;
- state snapshots;
- decision choices;
- selected choices;
- full distributions;
- margins;
- UNKNOWN probabilities;
- provider/model identity;
- model latency;
- end-to-end latency;
- tool-call latency;
- query latency;
- browser-step latency;
- outputs;
- postcondition results;
- human corrections;
- user feedback;
- prior versions;
- evaluation results;
- repeated failure clusters;
- cost/usage metrics;
- project-level trends.

## 7.2 Supervisor modes

### Interactive mode

The user asks:

> Why is this node calling the LLM so often?

> Review the last 200 refund decisions.

> Is there a better way to route these tickets?

> Why did latency increase yesterday?

> Can we handle these cases without the Teacher next time?

### Scheduled audit mode

A project can define controlled audits such as:

```text
Daily:
  inspect high-latency runs

Weekly:
  inspect UNKNOWN clusters
  inspect human overrides
  inspect suspicious low-margin decisions

Monthly:
  compare provider performance
  inspect unused choices
  inspect overused LLM escalations
```

### Triggered audit mode

Trigger Supervisor review when:

- latency exceeds a threshold;
- a provider failure rate changes;
- human override rate increases;
- UNKNOWN volume spikes;
- a postcondition fails;
- an expensive LLM path is used repeatedly;
- a decision distribution becomes unusually unstable;
- an integration starts returning a new error pattern.

## 7.3 Better-decision discovery

The Supervisor should be able to propose improvements such as:

```text
ADD_CHOICE
REMOVE_CHOICE
MERGE_CHOICES
SPLIT_CHOICE
CHANGE_CHOICE_DESCRIPTION
ADD_DECISION_NODE
CHANGE_TRANSITION
CHANGE_ESCALATION_POLICY
ADD_STATE_FEATURE
ADD_NORMALIZER
REPAIR_MACRO
ADD_CAPABILITY_BINDING
CHANGE_PROVIDER_ROUTING
ADD_RETRIEVAL_STAGE
ADD_VERIFIER
```

The system should distinguish:

```text
"The provider made a bad decision"

from

"The decision space itself is badly designed"

from

"The decision was correct but execution failed"

from

"Execution was correct but the state was incomplete"

from

"The route works but is too slow or expensive"
```

These diagnoses lead to different kinds of proposals.

---

# 8. Supervision policy: when to trust, inspect, escalate, or ask a human

A DecisionProvider can recommend a semantic route. It does not own permissions.

OpenClass must have a deterministic `SupervisionPolicy` layer.

Example:

```text
Jev/Laya result
    ↓
Distribution / margin / UNKNOWN / node / context
    ↓
SupervisionPolicy
    ↓
┌─────────────────────────────────────────────┐
│ continue_fast_path                          │
│ inspect_with_llm                            │
│ request_more_state                          │
│ ask_human                                   │
│ block                                       │
│ retry_provider                              │
│ fallback_provider                           │
└─────────────────────────────────────────────┘
```

Policies can depend on:

- node-specific risk;
- selected choice;
- margin;
- UNKNOWN probability;
- input completeness;
- execution risk;
- user/tenant permissions;
- monetary threshold;
- previous failures;
- human-required routes;
- provider health;
- rate limits;
- latency budget;
- cost budget.

High confidence must never bypass deterministic permissions.

---

# 9. Capabilities: controlled actions, not arbitrary model code

A `Capability` is a registered action OpenClass is allowed to invoke.

Examples:

```text
refund_customer
create_crm_task
send_email
run_sql_query
open_browser_page
click_browser_element
create_github_issue
run_n8n_workflow
turn_light_on
move_robot_forward
fire_doom_weapon
restart_container
ask_human
```

A capability should define:

```yaml
id: refund_customer
name: Refund Customer
provider: stripe
risk: high

input_schema:
  customer_id: string
  amount: money

permissions:
  - billing.refund

approval:
  required_when:
    - amount > 500

preconditions:
  - customer_verified
  - payment_exists

postconditions:
  - refund_record_exists

rollback:
  supported: false
```

The AI should select from capabilities. It should not invent unrestricted shell commands, URLs, database writes, or tool names when the capability universe is known.

---

# 10. Integrations: OpenClass must let users connect almost anything

OpenClass should treat integration as a first-class platform feature.

## 10.1 Integration categories

OpenClass should eventually support:

- MCP;
- REST APIs;
- GraphQL;
- webhooks;
- databases;
- message queues;
- browsers;
- n8n;
- GitHub;
- CRM/helpdesk tools;
- email;
- cloud services;
- local processes;
- Python/custom code;
- game engines;
- simulators;
- IoT / MQTT;
- Home Assistant;
- robotics middleware;
- camera/perception systems;
- custom SDK adapters.

The product must not require every integration to be built into OpenClass Core.

---

# 11. MCP support

OpenClass should support MCP in **both directions**.

## 11.1 OpenClass as an MCP client

A project can connect one or more MCP servers.

Example:

```text
Project
  ↓
Integrations
  ↓
Add MCP Server
  ↓
Discover tools/resources
  ↓
User selects what this project may access
  ↓
OpenClass registers allowed capabilities
```

The user should see:

```text
MCP: Internal DevOps
Status: Connected

Resources: 8
Tools: 17
Prompts: 3

Allowed in this project:
✓ read_deployment_status
✓ restart_staging_service
✓ inspect_logs
✗ delete_production_database
```

MCP tools must still pass through OpenClass capability permissions, policies, logging, and approval rules.

## 11.2 OpenClass as an MCP server

OpenClass should optionally expose a project or workspace through MCP so another AI application can use OpenClass.

Possible resources/tools:

```text
get_project_summary
get_decision_graph
get_recent_runs
get_unknown_clusters
get_latency_summary
get_evolution_candidates
submit_candidate
run_decision
query_analytics
```

Activation, secrets, unrestricted database mutation, and hidden evaluation data should not automatically be exposed.

MCP is an adapter over OpenClass services. It must not become the owner of policy or business authority.

---

# 12. API and SDK

Everything important in the UI must be backed by a public application API.

The web UI must not bypass the public service boundary.

OpenClass should eventually provide:

- REST API;
- Python SDK;
- TypeScript SDK;
- CLI;
- webhook/event interface;
- MCP adapter.

Example developer experience:

```python
from openclass import OpenClass

project = OpenClass.project("customer-intelligence")

project.state_provider(...)
project.decision_service(...)
project.capability(...)
project.verifier(...)

result = project.decide(
    service="support_route",
    state={"message": "I was charged twice"},
)
```

Or externally:

```http
POST /api/projects/{project_id}/decisions/{service_id}/run
```

Every run should return a stable run ID that can be inspected later.

---

# 13. Browser integration

Browser integration should be treated as a **real capability provider**, not a special hack.

A project may connect a controlled browser runtime.

Examples:

```text
Browser Integration
├── open URL
├── inspect page
├── read structured DOM/accessibility state
├── click registered target
├── type into allowed fields
├── download file
├── upload file
├── wait for condition
├── screenshot
└── verify resulting state
```

The browser adapter should convert raw browser information into structured state when possible.

```text
Web page
   ↓
Browser State Adapter
   ↓
StateSnapshot
   ↓
DecisionNode
   ↓
Jev / Laya
   ↓
known browser capability
   ↓
Browser
   ↓
Verifier
```

For a genuinely new UI state:

```text
unknown page state
   ↓
Supervisor LLM investigates
   ↓
proposes new state interpretation / route / recovery
   ↓
evaluation
   ↓
approval
   ↓
reusable knowledge
```

The full LLM may inspect screenshots/DOM/browser traces when required, but it should not replace the fast path for known states.

---

# 14. AI-assisted project creation

Users should not be forced to manually design every node before they can start.

OpenClass should include an **AI Project Builder**.

The user can describe the goal:

> I want a support system. It should classify customer issues, check the account if needed, use known procedures first, call a stronger LLM for unfamiliar problems, and ask a human before refunds over $500.

The builder then proposes an inactive project plan:

```text
Project: Support Automation

State
- customer_message
- account_status
- payment_status
- customer_tier

Decision Services
- issue_type
- resolution_route
- escalation_route

Capabilities
- lookup_customer
- lookup_payment
- refund_customer
- create_support_task
- call_support_llm
- ask_human

Providers
- Decision: Jev
- Teacher/Supervisor: Gemini

Policies
- refund > $500 → human approval
- low-trust resolution → Supervisor inspection

Integrations required
- CRM
- payment API
- helpdesk
```

The user can approve/edit this plan.

OpenClass creates the project structure, but the system remains in a safe draft/test state until required providers, integrations, secrets, and tests are complete.

---

# 15. AI integration assistant

The AI assistant should also help users add integrations.

Example:

> Connect OpenClass to my internal API at `/customers/{id}`. Use it only for reads.

The AI can:

1. inspect the supplied API schema/documentation;
2. propose an integration manifest;
3. propose capabilities;
4. propose input/output schemas;
5. run safe connectivity tests;
6. show results;
7. let the user approve registration.

If something fails:

```text
AI-generated integration
        ↓
test call fails
        ↓
trace + response + schema mismatch
        ↓
Supervisor analyzes failure
        ↓
revised inactive integration proposal
        ↓
retest
        ↓
user sees diff
        ↓
approve
```

This is a major OpenClass experience:

> **Describe what you want to connect; let the AI build the adapter around OpenClass's typed contracts; inspect the actual results; correct it when necessary; then keep the working integration as reusable project knowledge.**

---

# 16. Global product navigation

OpenClass should have a **workspace-level shell** and a **project-level shell**.

## 16.1 Workspace shell

```text
OpenClass
│
├── Projects
├── Activity
├── Integrations
├── Providers
├── Extensions
├── Usage
├── Audit
└── Workspace Settings
```

### Projects

All projects the user can access.

### Activity

Cross-project feed of meaningful events:

- evolution approved;
- provider failure spike;
- project needs attention;
- integration disconnected;
- latency regression;
- new candidate waiting for review;
- deployment/version event.

### Integrations

Workspace-level connected systems that may be shared with selected projects.

### Providers

Configured Jev/Laya/LLM/embedding/perception providers.

### Extensions

Installed adapters/plugins/capability packages.

### Usage

Cross-project usage, latency, calls, cost, and volume.

### Audit

Workspace-wide security and administrative actions.

### Workspace Settings

Users, teams, permissions, secrets policy, storage, deployment, backups, retention.

---

# 17. Projects page

The Projects page is the real home of OpenClass.

Suggested layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ OpenClass                                      + New Project │
├──────────────────────────────────────────────────────────────┤
│ Search...        Status: All        Owner: All              │
├──────────────────────────────────────────────────────────────┤
│ GymHolic Intelligence                                       │
│ Customer intelligence                                      │
│ HEALTHY                                                     │
│ 18.4k runs · 3 pending candidates · p95 91 ms              │
│                                                             │
│ Doom Agent                                                  │
│ Realtime game decision project                             │
│ RUNNING                                                     │
│ 2.8M decisions · fast-path 99.4% · p95 73 ms               │
│                                                             │
│ Browser Operations                                          │
│ Back-office automation                                     │
│ NEEDS ATTENTION                                             │
│ CRM integration disconnected                               │
└──────────────────────────────────────────────────────────────┘
```

Each project card should show only useful summary state, not every metric.

Possible indicators:

- status;
- active version;
- run volume;
- UNKNOWN rate;
- fast-path rate;
- pending candidate count;
- latency health;
- integration health;
- last meaningful event.

---

# 18. Creating a project

`+ New Project` should support:

```text
Blank Project

Templates
- Customer Intelligence
- Support Automation
- Smart Home Simulator
- Browser Operations
- Model Router
- Doom / Game Agent Demo

Describe with AI
```

## 18.1 Blank Project

For expert developers.

## 18.2 Template

Creates real project objects with editable defaults.

## 18.3 Describe with AI

Natural-language project design flow.

The AI must present what it plans to create before it creates or activates risky runtime behavior.

---

# 19. Project shell and tabs

Inside a project, the primary navigation should be:

```text
Project
│
├── Overview
├── Chat
├── Data
├── Decisions
├── Capabilities
├── Integrations
├── Knowledge
├── Evolution
├── Runs
├── Monitor
├── Analytics
├── Audit
└── Settings
```

Some tabs may be hidden in early Alpha builds until real functionality exists, but the long-term product should converge on this model.

---

# 20. Overview page

The Overview page answers:

> What is this project doing right now?

Suggested sections:

## Health row

```text
Status            Healthy
Active version    v12
Runs (24h)        84,219
Fast path         97.8%
UNKNOWN           1.4%
Human escalation  0.8%
Pending changes   3
```

## Latency

```text
Decision p50      48 ms
Decision p95      92 ms
LLM escalation    2.2%
LLM p95            1.8 s
End-to-end p95     126 ms fast path
```

## Attention required

Examples:

```text
3 evolution candidates waiting
1 integration degraded
refund_route latency +37% since v11
UNKNOWN spike in "requested_feature"
```

## Recent activity

Meaningful events, not raw logs.

## Project architecture mini-map

Compact visual summary:

```text
4 State Providers
6 Decision Services
23 Decision Nodes
41 Capabilities
7 Integrations
2 Decision Providers
1 Supervisor Provider
```

---

# 21. Chat page — OpenClass Copilot

Chat is the user's natural-language interface to the project.

The assistant should be able to:

- explain project behavior;
- inspect runs;
- inspect latency;
- inspect UNKNOWNs;
- search knowledge;
- create drafts;
- propose decision changes;
- build integrations;
- create analytics queries;
- compare versions;
- start evaluations;
- prepare inactive candidates;
- explain failures;
- create dashboards;
- guide setup.

Examples:

> Why are we calling Gemini on so many support tickets?

> Show me the slowest decision nodes from today.

> Review all human overrides of `refund_route` this week.

> I want to connect HubSpot. Give the project read-only access first.

> Add a browser integration for the admin portal.

> Can Laya replace Jev for this one node? Create an A/B evaluation, don't activate anything.

> These three UNKNOWN clusters look related. Investigate them.

> Why did run `#874192` ask a human?

The Copilot must ground answers in stored project data and distinguish observed facts from proposals.

---

# 22. Data page

The Data page contains project observations/events.

Sources may include:

- pasted text;
- CSV;
- JSON;
- webhook;
- API;
- browser;
- MCP;
- message queue;
- sensor stream;
- game state;
- imported historical logs.

Suggested UI:

```text
Data

[ Add Data ] [ Sources ] [ Reprocess ]

Time        Source       Type        Status
09:41       webhook      support     processed
09:41       webhook      support     processed
09:42       browser      page_state  processed
09:42       api          customer    processed
```

Opening an event should show:

- immutable raw input;
- normalized/compiled state;
- metadata;
- processing state;
- associated runs;
- derived semantic outputs;
- version used;
- provenance.

Never discard source observations simply because they were classified.

---

# 23. Decisions page

The Decisions page is where users understand and design the decision system.

## 23.1 Decision Services list

```text
Decision Services

support_issue_type
resolution_route
refund_risk
escalation_route
requested_feature
customer_sentiment
```

Each service shows:

- active version;
- provider;
- number of nodes;
- recent volume;
- UNKNOWN rate;
- p50/p95 latency;
- escalation rate;
- last modified time.

## 23.2 Decision Service detail

Tabs:

```text
Graph
Choices
Performance
Evaluations
Versions
```

### Graph

Visual DecisionGraph.

### Choices

Canonical semantic alternatives and descriptions.

### Performance

Accuracy/evaluation proxies, margin behavior, overrides, UNKNOWNs, latency.

### Evaluations

Frozen datasets and replay outcomes.

### Versions

Immutable version history and diffs.

---

# 24. Decision Graph UX

The graph editor should show semantic nodes, transitions, and execution targets.

Example:

```text
[ What kind of issue? ]

 billing ──────────────► [ billing_resolution ]
 technical ────────────► [ technical_resolution ]
 security ─────────────► HUMAN: security_team
 unknown ──────────────► SUPERVISOR
```

Clicking a choice shows:

```text
Choice: security

Description
Potential account-security or fraud issue.

Transition
HUMAN
Target: security_team

Policies
Always requires human review

Recent volume
211 / week

Latency
Decision p95: 68 ms

Overrides
0.4%
```

The user should be able to see the **difference between a semantic choice and its transition**.

---

# 25. Capabilities page

The Capabilities page answers:

> What can this project actually do?

Groups:

```text
Internal
API
MCP
Browser
Database
Workflow
Human
Device / Simulator
Custom
```

Example table:

```text
Capability             Provider        Risk      Status
lookup_customer        CRM API         low       ready
refund_customer        Stripe          high      ready
ask_human              OpenClass       medium    ready
browse_admin_portal    Browser         high      ready
create_github_issue    GitHub MCP      low       ready
rotate_certificate     DevOps MCP      high      disabled
```

Clicking a capability shows:

- schema;
- permissions;
- risk;
- preconditions;
- postconditions;
- approval policy;
- provider;
- test console;
- usage history;
- latency;
- failure rate.

---

# 26. Integrations page

The Integrations page is about connectivity.

```text
Integrations

HubSpot                  Connected
PostgreSQL               Connected
Internal MCP             Connected
Admin Browser            Connected
n8n                      Connected
Stripe                   Connected
Home Assistant           Not configured
```

For each integration:

```text
Connection
Credentials / secret refs
Capabilities imported
Permissions
Health
Latency
Last successful call
Recent failures
Projects using it
```

Users should be able to connect an integration at workspace level and then explicitly grant it to projects.

---

# 27. Knowledge page

Knowledge is the versioned state OpenClass has accumulated.

It should include more than labels.

Possible knowledge objects:

```text
StateSchema
StateNormalizer
DecisionSpec
DecisionGraph
Choice
Transition
Macro
CapabilityBinding
Verifier
SupervisionPolicy
AnalyticsSpec
ProviderProfile
IntegrationManifest
```

Knowledge page layout:

```text
Active Knowledge

DecisionGraph v12
StateSchema v7
AnalyticsSpec v5
SupervisionPolicy v4
Integration Manifest: CRM v3

[ View version history ]
```

Every active object should have:

- immutable version ID;
- created time;
- parent version;
- change origin;
- approving actor/policy;
- evaluation evidence;
- current status.

---

# 28. Evolution page

Evolution is where OpenClass visibly improves.

Primary sections:

```text
Needs Review
Evidence
Candidates
Evaluations
History
```

Example candidate card:

```text
Candidate #C-2031

Diagnosis
DECISION_SPACE

Problem
127 repeated UNKNOWN support events

Supervisor hypothesis
Missing concept: SUBSCRIPTION_PAUSE

Proposed change
ADD_CHOICE

Target
support_issue_type

Evaluation
Known-case retention        PASS
UNKNOWN retention           PASS
New concept coverage        PASS
Regressions                 0
Latency impact              +2 ms
Estimated LLM reduction     1,240 calls/month

[ View evidence ] [ View diff ]
[ Approve ] [ Reject ]
```

A candidate must not become active merely because the LLM believes it is correct.

---

# 29. Runs page

Runs are the authoritative execution history.

Suggested filters:

```text
Time
Decision Service
Provider
Choice
UNKNOWN
Human escalation
LLM escalation
Capability
Status
Latency
Version
```

Opening a run should reconstruct the complete flow.

Example:

```text
RUN #82,194

Project
Customer Support

Started
09:41:28.511

Policy version
v37

State
snapshot_93821

Decision Node
resolution_route

Provider
Jev / model X

Choices
HANDLE_KNOWN        0.07
CALL_LLM            0.71
ASK_HUMAN           0.14
RUN_QUERY           0.06
UNKNOWN             0.02

Selected
CALL_LLM

Decision latency
81 ms

Supervision
Allowed

Transition
LLM → support_investigator_v4

LLM latency
1.43 s

Capability / outcome
resolution_created

Verifier
PASS

Final status
SUCCESS
```

The run should link to:

- source event;
- provider trace;
- capability call;
- evaluation data if applicable;
- version diff;
- audit events;
- related runs.

---

# 30. Monitor page

`Runs` is detailed history. `Monitor` is system health and performance.

Monitor should include:

## Runtime health

- throughput;
- success rate;
- UNKNOWN rate;
- human escalation rate;
- LLM escalation rate;
- capability failure rate;
- provider errors.

## Latency

- p50/p95/p99 decision latency;
- state compilation latency;
- capability latency;
- end-to-end latency;
- latency by decision service;
- latency by provider/model;
- latency by integration.

## Fast-path efficiency

A signature OpenClass metric:

```text
Fast-path rate
= runs completed without full LLM escalation
```

Show:

- current value;
- history;
- by project;
- by service;
- effect of recent versions.

## Cost / usage

- decision-provider calls;
- LLM calls;
- tokens where applicable;
- external API usage;
- estimated/actual provider cost;
- cost per successful run;
- cost avoided through learned fast-path behavior.

## Knowledge quality indicators

- human override rate;
- repeated UNKNOWN clusters;
- regressions;
- candidate acceptance/rejection;
- stale capability rate;
- failed postconditions.

---

# 31. Analytics page

Analytics lets users ask questions about real project data.

The LLM should interpret the question. Deterministic engines should calculate the answer where possible.

```text
User question
    ↓
Query Interpreter
    ↓
Validated QuerySpec
    ↓
SQL / analytics engine
    ↓
real result
    ↓
chart/table
    ↓
optional LLM explanation
```

Example questions:

> What are the top UNKNOWN categories this week?

> Show decision latency by provider.

> Did v12 reduce LLM calls?

> Which human escalation reason is growing fastest?

> Show the most requested GymHolic features this month.

> Compare successful browser runs before and after the last integration update.

> How often does the Doom agent choose attack versus movement actions?

Analytics may itself reveal a knowledge gap. In that case OpenClass may propose an `AnalyticsSpec` evolution rather than invent an answer.

---

# 32. Audit page

Audit is different from Runs.

Runs answer:

> What did the runtime do?

Audit answers:

> Who or what changed the system and what authority allowed it?

Audit records should include:

- project creation;
- settings changes;
- provider changes;
- secret-reference changes;
- integration grants/revocations;
- candidate creation;
- evaluation execution;
- approval/rejection;
- version activation;
- capability enable/disable;
- human override;
- permission changes;
- data deletion/export;
- administrative actions.

---

# 33. Settings page

Project Settings should contain:

```text
General
Providers
Supervision
Permissions
Secrets
Data Retention
Runtime
Deployment
Danger Zone
```

## Providers

```text
Decision Provider
- Jev
- Laya
- Custom

Supervisor / Teacher
- Gemini
- GPT
- Claude
- Local
- Custom

Embedding Provider
Perception Provider
Tool Router
```

## Supervision

Configure:

- low-trust rules;
- LLM review rules;
- human-required rules;
- latency budget;
- cost budget;
- provider fallbacks;
- audit cadence.

## Runtime

- concurrency;
- retry rules;
- queue behavior;
- timeout policy;
- replay policy;
- environment.

---

# 34. Multi-project architecture

Projects must be isolated in data, policy, version history, and permissions.

Workspace-level providers/integrations may be shared, but each project explicitly receives a binding/grant.

Example:

```text
Workspace Integration: GitHub

Granted projects:
✓ DevOps Assistant
✓ Release Monitor
✗ Customer Intelligence
✗ Smart Home
```

Project A must never gain capability access simply because Project B has it.

OpenClass must support:

- project-scoped data;
- project-scoped policies;
- project-scoped versions;
- project-scoped audit;
- project-scoped usage;
- project-scoped provider configuration;
- optional workspace-shared provider credentials;
- project-specific permission grants.

---

# 35. Cross-project views

Workspace users need aggregate understanding.

## Workspace Activity

```text
10:41  Doom Agent         Provider latency recovered
10:36  GymHolic           Candidate C-2031 awaiting approval
10:21  Browser Ops        CRM integration degraded
09:58  Smart Home         Policy v8 activated
```

## Workspace Usage

Compare:

- run volume;
- LLM use;
- decision provider calls;
- latency;
- cost;
- UNKNOWN rate;
- active versions;
- project health.

## Workspace attention queue

One place for:

- candidates requiring approval;
- degraded integrations;
- provider outages;
- failed evaluations;
- unsafe blocked actions;
- projects exceeding budgets.

---

# 36. Project growth model

A project should be able to start very small and grow without being rewritten.

## Stage 0 — Draft

```text
project description
+ provider selection
+ zero integrations
```

## Stage 1 — Basic decision system

```text
one StateProvider
one DecisionService
Jev or Laya
few choices
UNKNOWN
manual test console
```

## Stage 2 — Controlled execution

```text
capabilities
transitions
preconditions
postconditions
human approval
runs
```

## Stage 3 — Real integration

```text
API / MCP / browser / webhook / DB / n8n
real data
real actions
monitoring
```

## Stage 4 — Evolution

```text
Supervisor
UNKNOWN evidence
failure diagnosis
candidate proposals
evaluation
versioning
approval
```

## Stage 5 — Analytics

```text
QuerySpec
SQL/analytics
charts
version comparisons
runtime optimization
```

## Stage 6 — Scale

```text
many DecisionServices
high volume
retrieval for large choice universes
provider routing
latency/cost optimization
project teams
multi-environment deployment
```

The product should make this growth visible rather than forcing users into enterprise complexity on day one.

---

# 37. High-cardinality decisions

OpenClass must not require sending enormous universes directly to one decision model.

A `DecisionCompiler` should be able to reduce a large universe.

```text
1,000,000 candidates
      ↓
filters / SQL / retrieval
      ↓
semantic pre-ranking
      ↓
small relevant set
      ↓
Jev / Laya final bounded choice
```

Developers should be able to define a decision service over a large domain without manually implementing provider-specific cardinality handling.

---

# 38. Versioning and immutability

Every knowledge-changing activation must create a new immutable version.

```text
v11
  ↓ approved candidate
v12
  ↓ approved candidate
v13
```

A historical run must remain reproducible enough to answer:

- which policy version ran;
- which provider/profile ran;
- which choices existed;
- what was selected;
- what transition was bound;
- what capability version executed;
- what verifier ran.

No UI action should rewrite historical truth.

---

# 39. Evaluation before knowledge

A Supervisor proposal is only a proposal.

Activation should support:

```text
Proposal
  ↓
Schema validation
  ↓
Static policy checks
  ↓
Replay / simulation
  ↓
Regression suite
  ↓
Security / permission checks
  ↓
Latency / cost impact estimate
  ↓
Approval policy
  ↓
Activation
```

Evaluation output should be visible in the UI.

A candidate can improve one metric and still be rejected if it causes unacceptable regressions.

---

# 40. Human control modes

OpenClass should support different trust models per project and per action.

## Manual

Every candidate/action requires user approval.

## Assisted

Low-risk known actions run automatically; important changes require approval.

## Guarded automatic

Candidates/actions may auto-activate only after deterministic policy and evaluation gates pass.

## Observe-only

OpenClass monitors and proposes but never executes actions.

This should be explicit in project settings.

---

# 41. OpenClass Demo mode

OpenClass should ship with zero-setup demo projects.

## Demo 1 — Customer Intelligence

Shows:

- ingest messages;
- Jev/Laya decisions;
- UNKNOWN concept;
- Supervisor discovery;
- candidate evaluation;
- approval;
- analytics chart changes.

## Demo 2 — Smart Home Simulator

Shows:

- live state;
- real-time decisions;
- capabilities;
- energy analytics;
- learned routine proposal;
- version history.

## Demo 3 — Doom / Game Agent

Shows:

- game state;
- fast decision loop;
- action distribution;
- live latency;
- provider comparison;
- run replay;
- Supervisor analysis of poor decisions.

These demos should prove that the same core supports radically different projects.

---

# 42. Extension ecosystem

OpenClass should eventually support installable packages.

Possible extension types:

```text
StateProvider extension
DecisionProvider extension
TeacherProvider extension
EmbeddingProvider extension
PerceptionProvider extension
CapabilityProvider extension
Integration extension
Verifier extension
Analytics extension
UI panel extension
Template extension
```

Examples:

```text
openclass-home-assistant
openclass-n8n
openclass-github
openclass-doom
openclass-browser
openclass-postgres
openclass-mqtt
openclass-shopify
openclass-robotics
```

Core must define stable extension contracts so extensions do not patch internal OpenClass code.

---

# 43. Extension UI

Workspace `Extensions` page:

```text
Installed
Available
Updates
Developer
```

Installed extension detail:

```text
OpenClass Browser
Version 0.4.1

Provides
- BrowserStateProvider
- BrowserCapabilityProvider
- 12 capabilities
- 2 UI panels

Used by
- Browser Operations
- Admin Support

Permissions
- Network
- Browser runtime
- Download directory
```

Extensions should declare capabilities and required permissions.

---

# 44. Security and permissions

OpenClass must assume that integrations may expose powerful operations.

Security boundaries include:

- secret storage;
- per-project grants;
- capability allowlists;
- action risk levels;
- approval policies;
- deterministic guards;
- network restrictions where supported;
- browser domain restrictions;
- database read/write separation;
- MCP tool allowlists;
- audit records;
- versioned configuration;
- least privilege.

A model should not gain access simply because a connector exists.

---

# 45. Failure separation

OpenClass must never collapse every failure into `UNKNOWN`.

Important categories include:

```text
SEMANTIC_UNKNOWN
LOW_TRUST_DECISION
STATE_REPRESENTATION
PRECONDITION
PROCEDURE
POSTCONDITION
MISSING_CAPABILITY
PERMISSION_DENIED
PROVIDER_FAILURE
INTEGRATION_FAILURE
TIMEOUT
RATE_LIMIT
HUMAN_REQUIRED
EVALUATION_FAILURE
```

The diagnosis determines which recovery/evolution operations are valid.

Example:

```text
Provider 502
≠ new semantic class

Browser session expired
≠ bad Jev choice

Correct decision + failed macro
≠ change decision graph
```

---

# 46. LLM escalation economics

OpenClass should explicitly measure whether learning is reducing repeated expensive reasoning.

Project metrics should include:

```text
LLM escalation rate
Fast-path completion rate
Repeated issue handled without LLM
LLM calls avoided after version activation
Estimated reasoning cost before/after
Average end-to-end latency before/after
```

A successful evolution might show:

```text
Before v12
LLM escalation: 14.8%

After v12
LLM escalation: 4.1%

Known-case success: unchanged
Human escalation: unchanged
p95 latency: improved
```

This makes OpenClass's learning thesis visible in the product.

---

# 47. Runtime provider comparison

Users should be able to compare providers without rewriting canonical policy.

Example experiment:

```text
Decision Service: support_issue_type

Variant A
Jev

Variant B
Laya

Same:
- state inputs
- choices
- evaluation dataset
- transitions

Compare:
- correctness/evaluation result
- UNKNOWN behavior
- margin/distribution behavior
- latency
- cost
- stability
```

Provider changes should be evaluated and versioned where they affect runtime behavior.

---

# 48. Environments

Projects should eventually support environments:

```text
Development
Staging
Production
```

Knowledge versions may move through promotion rules.

Example:

```text
Candidate
  ↓
Development evaluation
  ↓
Staging replay / shadow mode
  ↓
Human approval
  ↓
Production activation
```

Integrations/secrets may differ per environment.

---

# 49. Shadow mode

A powerful feature for real deployments:

OpenClass can run a proposed provider/policy without executing its action.

```text
Production choice
→ executes

Shadow vNext choice
→ recorded only
```

Compare:

- decision disagreement;
- latency;
- UNKNOWN rate;
- expected action difference;
- provider behavior.

This should become an important tool for safe growth.

---

# 50. Replay and backfill

OpenClass must support replaying historical events through new versions.

Use cases:

- evaluate candidate policy;
- compare providers;
- backfill new semantic fields;
- validate analytics changes;
- inspect regressions;
- estimate LLM savings;
- test new state compiler logic.

Historical raw data should remain unchanged; derived results may be versioned.

---

# 51. Notifications and attention model

Users should not need to stare at dashboards.

OpenClass should generate meaningful attention events such as:

```text
Critical
- unsafe action blocked repeatedly
- integration credentials invalid
- provider unavailable

Important
- candidate waiting for approval
- UNKNOWN spike
- latency regression
- human override spike

Informational
- version activated
- integration recovered
- evaluation complete
```

Delivery channels can later include:

- in-app;
- email;
- Slack/Teams;
- webhook;
- custom capability.

---

# 52. Developer mode

Advanced users need deeper technical visibility.

Developer mode may expose:

- raw provider payloads;
- compiled state;
- choice hashes;
- schema versions;
- trace IDs;
- tool payloads;
- policy JSON/YAML;
- SDK snippets;
- API examples;
- event replay controls;
- local extension development tools.

Normal users should not need to see all of this.

---

# 53. Product growth roadmap

## Phase A — Alpha 0.1: Real vertical slice

Goal:

> A user can open OpenClass, create a project, ingest real data, run a real decision provider, inspect UNKNOWNs, review a Teacher proposal, approve a version, inspect runs, and ask analytics questions through the UI.

Required product surface:

```text
Projects
Overview
Data
Decisions
Evolution
Runs
Analytics
Settings
```

Required engineering:

- PostgreSQL persistence;
- migrations;
- public API;
- TypeScript client;
- real web UI;
- project isolation;
- provider configuration;
- event ingestion;
- Jev DecisionProvider;
- UNKNOWN flow;
- Teacher candidate flow;
- evaluation;
- immutable versions;
- run history;
- minimal analytics;
- Docker deployment.

## Phase B — Alpha 0.2: Adaptive execution

Add:

- Capabilities;
- transitions;
- deterministic guards;
- postconditions;
- human routing;
- API integration framework;
- MCP client support;
- browser prototype;
- Monitor page;
- latency/cost metrics;
- supervision policies.

## Phase C — Alpha 0.3: Open integration platform

Add:

- extension SDK;
- n8n adapter;
- robust MCP adapter;
- browser provider;
- custom integration builder;
- AI-assisted integration setup;
- workspace integration grants;
- provider comparison/shadow mode.

## Phase D — Beta: Multi-project operational platform

Add:

- strong auth/teams;
- environments;
- RBAC;
- backups/restore;
- production monitoring;
- notifications;
- multi-project usage/cost;
- extension registry;
- secret management hardening;
- deployment hardening;
- retention/compliance controls.

## Phase E — Ecosystem

Add:

- official extension marketplace/registry;
- community project templates;
- provider packs;
- integration packs;
- benchmark/evaluation packs;
- hosted OpenClass option;
- enterprise controls.

---

# 54. Vertical-slice implementation rule

OpenClass must be built vertically.

A feature is not complete because a class or endpoint exists.

For each user-facing feature:

```text
DATABASE
   ↓
DOMAIN / SERVICE
   ↓
PUBLIC API
   ↓
SDK / CLIENT
   ↓
REAL UI
   ↓
USER ACTION
   ↓
PERSISTED RESULT
   ↓
RELOAD / RESTART
   ↓
RESULT STILL EXISTS
```

Example build order:

```text
Slice 1  Create Project
Slice 2  Ingest Event
Slice 3  Run Decision
Slice 4  Inspect UNKNOWN
Slice 5  Teacher Candidate
Slice 6  Approve Version
Slice 7  Inspect Run
Slice 8  Monitor Latency
Slice 9  Add Capability
Slice 10 Add Integration
Slice 11 MCP Tool
Slice 12 Browser Capability
Slice 13 AI Integration Builder
Slice 14 Ask Analytics Question
```

---

# 55. Definition of Done

A stateful user feature is not complete unless applicable items are satisfied.

```text
Real domain implementation                     required
Real persistence                               required
Migration                                      required
Repository/service layer                       required
Public API                                     required
SDK/client                                     required
Actual UI                                      required
Loading state                                  required
Empty state                                    required
Validation errors                              required
Server/provider error state                    required
Project isolation                              required
Audit event where meaningful                   required
Run/trace visibility where meaningful          required
Reload persistence                             required
Tests                                          required
End-to-end test                                required
Manual/demo evidence                           required
No experiment-only shortcut                    required
```

For integrations:

```text
Permission model                               required
Secret handling                                required
Health check                                   required
Failure state                                  required
Latency telemetry                              required
Capability registration                        required
Audit trail                                    required
```

For evolution:

```text
Typed proposal                                 required
Evaluation                                     required
Regression checks                              required
Version diff                                   required
Approval policy                                required
Immutable activation                           required
Rollback/previous-version reference            required
```

---

# 56. Canonical user journey — creating a business project

```text
1. Open OpenClass
2. Projects → New Project
3. Choose "Describe with AI"
4. Type:
   "Analyze customer support messages, detect issues and feature requests,
    use Jev for normal classification, call an LLM for unfamiliar cases,
    and ask humans before refunds."
5. AI proposes project structure
6. User approves draft
7. Settings → configure Jev + Supervisor LLM
8. Integrations → connect CRM/helpdesk/payment API
9. Data → import historical messages
10. Run intelligence
11. Overview begins showing real metrics
12. UNKNOWN evidence accumulates
13. Evolution page shows candidate
14. User inspects evidence/evaluation
15. Approves v2
16. Fast-path rate increases
17. Monitor page shows lower LLM escalation
18. Analytics → ask business questions
```

This is the kind of journey the product must make possible without editing source code.

---

# 57. Canonical user journey — connecting a browser

```text
1. Project → Integrations → Add Browser
2. Configure allowed domains
3. Open test session
4. User asks Copilot:
   "I want OpenClass to look up a customer in this portal and read the invoice status."
5. AI inspects allowed browser state
6. AI proposes:
   - BrowserState schema
   - find_customer capability
   - read_invoice capability
   - verifier
7. OpenClass runs test flow
8. Something fails because the portal has an extra confirmation page
9. Supervisor inspects trace/screenshot/state
10. Supervisor proposes recovery branch
11. Test passes
12. User approves integration version
13. Known future cases run through the fast path
14. New UI states go through controlled investigation
```

---

# 58. Canonical user journey — fast model monitored by LLM

```text
1. Jev/Laya handles 100,000 runtime decisions.
2. OpenClass records distributions, latency, outcomes and postconditions.
3. Supervisor audit finds:
   - node X has unusually low margins;
   - human overrides are concentrated in two choices;
   - node Y calls the LLM 18% of the time;
   - provider latency increased 35%.
4. Supervisor proposes:
   - split one overlapping choice;
   - add a state feature;
   - change the LLM escalation rule;
   - test Laya against Jev on node Y.
5. OpenClass creates evaluations.
6. User reviews actual measured results.
7. Approved changes create vNext.
8. Monitor compares before/after.
```

This demonstrates that the LLM is not replacing the fast model; it is **supervising and improving the system built around it**.

---

# 59. Product success metrics

OpenClass should eventually make these measurable per project:

## Operational

- total runs;
- success rate;
- p50/p95/p99 latency;
- fast-path completion rate;
- UNKNOWN rate;
- human escalation rate;
- provider failure rate;
- capability failure rate.

## Evolution

- candidates proposed;
- candidates accepted;
- candidates rejected;
- regression rate;
- knowledge retention;
- UNKNOWN reduction after activation;
- human-override reduction;
- LLM-call reduction;
- latency change after activation.

## Economics

- cost per run;
- LLM cost per run;
- provider cost;
- external API cost where available;
- estimated savings from reusable learned behavior.

## Product health

- connected integrations;
- degraded integrations;
- active capabilities;
- project versions;
- unresolved attention items.

---

# 60. Non-negotiable product principles

1. **Fast decisions stay fast.** Full LLMs do not enter the normal path unless required by policy.
2. **Measure latency.** Never rely on provider marketing or assumptions.
3. **Models choose; policy authorizes.** AI confidence does not grant permission.
4. **Choices and transitions are separate.** Semantic decisions remain provider-neutral.
5. **LLMs propose; OpenClass validates.** No silent self-modification.
6. **Every meaningful change is versioned.** Historical truth remains immutable.
7. **Integrations are capabilities with permissions.** Connection does not equal authority.
8. **MCP is an adapter, not the control plane.** OpenClass owns project policy and audit.
9. **Browser access is controlled.** Domain, action, permission and verification boundaries apply.
10. **Keep the raw evidence.** Derived knowledge does not replace source events.
11. **Failure types remain distinct.** Provider outage is not semantic UNKNOWN.
12. **User experience is part of the architecture.** A feature does not count until users can use it through the real product.
13. **Projects can grow gradually.** OpenClass should support tiny experiments and serious operational systems with the same core objects.
14. **The core remains general.** Customer support, Doom, smart home, robotics, browser operations and business intelligence are projects/extensions, not separate OpenClass architectures.
15. **Observability is first-class.** Decisions, latency, execution, versions, model calls and human actions must be inspectable.

---

# 61. Final product picture

The mature OpenClass experience should feel like this:

```text
You open OpenClass.

You create a project.

You describe what the system should do.

OpenClass helps you define state, decisions, capabilities and integrations.

You connect Jev, Laya or another fast decision provider.

You connect a stronger LLM as Supervisor/Teacher.

You connect whatever reality the project needs:
API, MCP, browser, DB, n8n, sensors, game engine, CRM, robot, custom code.

The project starts running.

Fast known decisions remain on the fast path.

Every decision is observable.

Every action is permissioned.

Every important outcome is verified.

When the system does not know something, OpenClass records evidence.

When something repeatedly goes wrong, the Supervisor investigates.

When latency/cost/quality can be improved, the Supervisor can propose a better design.

OpenClass evaluates the proposal.

The user or policy approves it.

A new immutable version becomes active.

The fast runtime now knows more than it did before.

And the user can see exactly what changed, why, what evidence justified it,
and whether the system actually became faster, cheaper, or better.
```

That is the OpenClass product.

---

# 62. Immediate implementation priority

Do not attempt to build every integration first.

The implementation order should prove the platform through increasingly powerful vertical slices:

```text
1. Projects
2. Data ingestion
3. Real DecisionProvider runtime
4. Runs / traces
5. UNKNOWN handling
6. Supervisor candidate
7. Evaluation + approval + immutable version
8. Monitor / latency
9. Capabilities + transitions
10. API integration
11. MCP integration
12. Browser integration
13. AI integration builder
14. Analytics
15. Multi-project usage/audit
16. Extension SDK
```

The first release does not need every future page at full depth.

It does need the fundamental product loop to be real:

> **Create → Connect → Decide → Observe → Investigate → Improve → Evaluate → Approve → Version → Measure.**
