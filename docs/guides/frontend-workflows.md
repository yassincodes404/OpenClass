# Supported frontend workflows

Both `apps/portal` (Vite) and `apps/web` (Next) remain supported. Public landing
pages do not require a session. Project routes use Keycloak; bearer tokens stay
in memory, are not persisted in browser storage, and are checked by the control
plane on every request.

## HTTP and ownership boundary

UI code uses `@openclass/sdk`. Next project pages use
`OpenClassWorkspaceClient`; portal evidence and shared replay/graph forms use
the same SDK. Existing portal platform views use `OpenClassControlClient`.
Neither browser receives an engine internal credential.

The workspace SDK resolves a project through `GET /control/projects/:identifier`,
then sends engine-shaped operations to
`/control/workspaces/:workspaceId/projects/:controlProjectId/workflow`.
The control plane checks membership, resolves the engine mapping, checks the
operation's role, validates its body/query, and forwards only supported routes.
Next's `/control/*` handler relays the end-user bearer through the HTTP SDK.
Configure its server-side `CONTROL_PLANE_URL` (or `CONTROL_PLANE_BASE_URL`) when
the control plane is not at `http://127.0.0.1:7400`.
The relay uses `OpenClassControlClient.requestWithStatus` to preserve upstream
success statuses (including 201, 207 and bodyless 204); existing SDK `request`
callers still receive only the response body.
Incoming relay bodies are capped at 5 MiB during streamed consumption with a
10-second read deadline, not buffered in full before rejection. Workflow event
ingestion shares the ordinary route's workspace quota and principal throttle.

Project lists enumerate real workspace memberships. Reconciliation imports only
engine projects explicitly owned by that workspace, never unowned legacy
projects or projects mapped to a different workspace. External SDK/CLI creation
must send `X-OpenClass-Workspace-Id` with a genuinely authorized workspace
identity; opening `/projects` reconciles the registry before inspecting a deep
link. Use project IDs for links: identical accessible slugs are ambiguous and
return 400 rather than choosing a workspace. Non-member projects return 404.

### Public classifier slugs versus internal engine slugs

The control API at
`POST /control/workspaces/:workspaceId/projects/:projectId/classifiers` accepts
a **project-local public slug** such as `support-intent`. Its response, mapping,
audit target and existing UI links retain that public slug. Two projects may
therefore each create `support-intent`.

The legacy engine classifier registry has a **globally unique** slug, constrained
to `^[a-z][a-z0-9-]{0,79}$` (at most 80 characters). New control-plane creations
send an internal engine slug of `ocp-` followed by the full 64-character SHA-256
hex digest of UTF-8 `JSON.stringify(["openclass.control.classifier.v1",
canonicalControlProjectId, fullPublicSlug])`. This is always 68 characters.
Project aliases resolve before hashing; no public-slug truncation, ambiguous
concatenation, random names, or conflict-driven renaming is used.

Compatibility policy:

- Existing `engine_classifier_id` mappings are authoritative. Reads, ontology
  access and classification continue using saved IDs, including legacy
  classifiers whose engine slug equals their public slug. No renaming,
  remapping, schema migration or change to legacy engine routes is performed.
- New control-created classifiers must be addressed through the public control
  mapping or saved engine ID. Do not assume their public slug is an engine
  global lookup alias. Direct legacy engine clients retain their existing slug
  behavior and global uniqueness constraint; `ocp-` is an internal naming
  convention, not an engine-enforced reserved prefix.
- A same-project duplicate remains a 400 before engine creation. Existing
  control-plane idempotency receipts retain their normal replay semantics.
  If the engine creation succeeds but local mapping persistence fails, a
  non-receipted retry uses the same internal slug and may return engine conflict.
  It never adopts an arbitrary engine classifier or creates a randomly renamed
  duplicate; inspect/reconcile the accepted remote effect before retrying.
- The full SHA-256 digest avoids truncation collisions; it is not a claim of
  mathematical collision impossibility. An existing conflicting engine slug
  fails closed rather than being silently reused.

## Workflow contract

Paths below are relative to the project workflow prefix.

| Capability                                                  | Method and path                                                              | Minimum role |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------ |
| Project, service, evidence, case, dataset, evaluation reads | `GET` on the supported resource/list                                         | viewer       |
| Raw-event ingestion and decision runs                       | `POST events`, `POST events/batch`, `POST decision-services/:id/runs`        | developer    |
| Create/update decision service graph                        | `POST decision-services`, `PATCH decision-services/:id`                      | admin        |
| Human evidence triage                                       | `PATCH evidence/:id/triage`                                                  | reviewer     |
| Advisory diagnosis / status transition                      | `POST evidence/:id/ai-diagnose`, `POST evidence/:id/transition`              | reviewer     |
| Case creation / evidence attachment                         | `POST evidence-cases`, `POST evidence-cases/:id/evidence`                    | reviewer     |
| Inactive proposal / rejection                               | `POST evolution/propose`, `POST candidates/:id/reject`                       | reviewer     |
| Verified dataset creation / sealing                         | `POST eval-datasets`, `POST eval-datasets/:id/seal`                          | admin        |
| Add independently verified example                          | `POST eval-datasets/:id/examples`                                            | reviewer     |
| Baseline/candidate replay                                   | `POST evaluations`                                                           | admin        |
| Integration create/delete/test                              | `POST integrations`, `DELETE integrations/:id`, `POST integrations/:id/test` | admin        |

`workflow-contracts.ts` is the authoritative closed allowlist, not a general
engine proxy. Unknown verbs/routes, extra body keys, unsafe identifiers and
unknown/out-of-range queries are rejected. The engine remains authoritative for
domain validity and audit events. Mutation failures are not automatically
retried: an interrupted response can follow an accepted remote mutation.

### Evidence and diagnosis

- Portal: `/projects/:id/evidence`; Next: `/projects/:id/evolution`
  ("Evidence & cases").
- Inspect provenance and the predicted choice. Request advisory diagnosis,
  optionally copy advice into an editable draft, then explicitly save human
  triage. Simulated advice is labeled. Advice never becomes verified ground
  truth or activates a proposal.
- Create/attach evidence cases; select ready evidence to request an **inactive**
  proposal. UNKNOWN is permanent and is not proof of a new class.
- Portal evidence/cases paginate in 25-row pages. Next evidence paginates in
  25-row pages; its status/trigger/search filters apply to the current page, as
  labeled. Next's existing case picker is limited to 50 cases. Candidate and
  service inventories retain backend list limits. These are not claims of
  unrestricted historical browsing.
- Failed reads show errors, not successful empty inventories. Role-denied
  mutations remain server-enforced even if a control is visible.

### Multi-node graph editing

- Portal: open a service under `/projects/:id/decisions/:serviceId`.
- Next: `/projects/:id/decisions`, then **Edit graph for _service name_**.
- Shared `GraphEditor` supports adding/removing nodes and known choices,
  instructions, risk/review settings, per-choice next nodes and transition
  approval. The first node remains the entrypoint. UNKNOWN cannot be removed or
  renamed. Legacy choice targets are normalized into editable transitions;
  dangling targets must be removed before saving.
- Saving requests a new immutable version. Existing runs keep their pinned
  historical version. The client rereads the service before PATCH and rejects
  an already-stale edit. This is a user-facing preflight, **not** an atomic
  compare-and-swap guarantee; a concurrent change after that read still depends
  on server version semantics.

### Verified replay

Both entry points expose `/projects/:id/evaluations` using the shared
`ReplayWorkspace`. Create a dataset, enter independently verified labels
(human or verified external), annotator identity, rationale, split and slice.
There is no prediction-to-label shortcut. Explicitly review provenance and
seal the dataset; sealed examples cannot be edited.

The modern picker uses only `GET discovery-candidates` via the typed SDK
`discoveryCandidates(project): Promise<DiscoveryCandidateSummary[]>`. These are
`cluster_candidates`, not the evidence-synthesis `project_choice_candidates`
returned by `GET candidates`. Only inactive `NEW_CLASS` entries with a nonblank
`canonical_name` are offered; active/rejected, blank-name and other proposal
types (including ALIAS) are excluded. The modern backend derives its choice key
by uppercasing `canonical_name`; the picker displays that key. Discovery summaries
have no `decision_service_id`, so the user must explicitly choose a service.
The DTO retains record/index compatibility for existing generic SDK callers.

Evidence proposals remain inspectable and rejectable in the evidence workspace,
but their IDs must not be submitted to modern replay: the existing backend only
resolves `cluster_candidates`. Canonical evidence-proposal integration and ALIAS
evaluation remain OC-BG-012/014 backend work. There is no supported automatic
evidence-proposal-to-modern-replay flow yet; this UI does not invent a mapping or
expose a legacy evaluation shortcut to create one.

Choose a sealed dataset, eligible discovery candidate and explicit decision
service. Replay sends
`{dataset_id, candidate_id, service_id}` to `POST evaluations`. Display the
persisted metrics, individual gates, blocked status and provider/model; simulated
replay is explicitly marked as not evidence of model quality. Missing metrics
are "Unavailable", never invented zeroes. Persisted runs can be reopened.

Passing replay does not activate anything. Legacy replay/promotion shortcuts
are deliberately unproxied because they cannot bind verified provenance and
explicit approval. This UI slice does not implement a new reviewed activation
contract; transactional promotion belongs to the evolution workstream.

## Validation and real-stack acceptance

`tests/web/project-workflows.spec.ts` is **route-mocked**, not E2E proof. It
checks the Next session gate, SDK/workspace wiring, multi-node editing with
keyboard controls, stale-edit denial, advisory triage, denied reads, sealed
replay, no automatic activation, and local relay rejection. Its
`__OPENCLASS_ROUTE_MOCKED_SESSION__` fixture only renders the shell; it cannot
authenticate against a real control plane. Screenshots under
`artifacts/frontend-workflows/playwright` are simulated browser evidence.
Portal component tests and SDK/control-plane unit tests use test doubles too.

The original OC-BG-027 acceptance remains open until the parent integration
lane runs against migrated disposable PostgreSQL, real Keycloak, the engine,
control plane and **both** frontends. Do not substitute these mocks for that gate.

### Real-stack classifier namespace regression

`services/control-plane/src/classifier-namespace.spec.ts` exercises the real
controller, service and engine HTTP client against simulated SQL/HTTP storage.
Its globally unique engine fixture is a regression test, not real-engine proof.
The integration lane must create two owned projects and POST this identical
body to each project's control `/classifiers` route using its authorized session:

```json
{
  "name": "Support intent",
  "slug": "support-intent",
  "unknown_fallback": true,
  "classes": [{ "canonical_name": "billing", "display_name": "Billing" }]
}
```

Expect two 201 responses with public slug `support-intent`, distinct control IDs
and `engine_classifier_id` mappings. Read each mapping through the control API
and each engine classifier/ontology by saved engine ID from the trusted
integration harness. Assert two distinct 68-character `ocp-` internal slugs,
matching the documented digest; do not expose engine credentials to a browser.
Repeat with two valid 80-character public slugs sharing their first 79
characters. A fresh same-project duplicate must return 400 with no extra engine
classifier; existing idempotency-key receipt replay is a separate contract.
Verify viewer 403, non-member/cross-workspace 404, malformed public slug 400, and
unchanged legacy classifier ID/ontology lookup.

In portal, visit `/projects/:projectId/classifiers` for each project:
`getByRole("button", {name: "+ New classifier", exact: true})`, then dialog
`getByRole("dialog", {name: "Create classifier"})`, label **Name** (`Support intent`),
label matching `/^Classes/` (`billing`), and button **Create classifier**. This
form intentionally omits `slug`, so the public slug derives from the same name.
Follow **Open classifier →** and assert heading **Support intent**, displayed
slug `support-intent`, class `billing`, and permanent UNKNOWN in both projects.
Also reload both existing frontend project entry points to verify owned-project
visibility remains intact. Do not invent a Next legacy-classifier screen or
substitute decision-service creation for this classifier regression.

### Real-stack browser recipe for the integration lane

Use a new browser context and a test-only workspace owner; disable traces and
storage-state capture so tokens are not written to artifacts.

1. Create an owned project via the external HTTP SDK/CLI with a unique name.
   Visit `/projects` on portal and Next with the actual Keycloak session.
   Assert `getByRole("link", {name: /unique project name/})` is visible in both.
   Follow the link, reload, and verify the same engine project ID and workspace
   mapping. Repeat creation through each frontend and inspect in the other.
2. Create a service and produce UNKNOWN/low-trust evidence through actual
   engine HTTP execution. Portal's evidence page exposes
   `getByRole("heading", {name: "Evidence, diagnosis & cases"})`; Next exposes
   `getByRole("button", {name: "Inspect & Triage"})`.
   In Next use `getByRole("region", {name: "Evidence detail"})`,
   `getByRole("button", {name: /Diagnose with Provider/})`,
   `getByLabel("Triage Rationale & Notes")`, and
   `getByRole("button", {name: "Save Triage", exact: true})`.
   In portal use **Request advisory diagnosis**, **Human rationale**, and
   **Save human triage**. Verify the engine readback and retained UNKNOWN;
   diagnosis alone must issue no triage or promotion mutation.
3. Open `getByRole("form", {name: "Decision graph editor"})` in both.
   Use **Add node**, **Node name**, the **Next node** combobox and
   **Human approval before this transition** checkbox; then
   **Save new graph version**. Verify engine version increments, transitions
   and permanent UNKNOWN. Inspect an earlier run's unchanged pinned version.
   Change the service in the other frontend before saving an older draft;
   assert **Service changed since loading** and no PATCH from the stale draft.
4. In `getByRole("region", {name: "Replay evaluation workspace"})`, create
   **New dataset name**, enter **Observation text**, **Verified label (or UNKNOWN)**,
   **Annotator / verified source identity**, and independent provenance.
   Select the review checkbox and **Seal verified dataset**.
   Verify sealed identity and examples by engine HTTP readback, including
   rejection of a further example addition. Use distinct holdout/discovery
   texts and the backend-required slice/split coverage.
5. Prepare a genuine inactive `NEW_CLASS` cluster-discovery candidate using the
   existing engine discovery workflow in the trusted integration harness. Read
   its ID and nonblank `canonical_name` through `GET discovery-candidates`, not
   `GET candidates`; evidence-synthesis proposal IDs are not eligible. Confirm
   ALIAS/rejected/active/blank-name entries do not appear in the modern picker.
   Select comboboxes **Dataset**, **Inactive candidate**, **Decision service**;
   click **Run sealed replay**. Inspect region **Replay result**, each persisted
   gate, blocked/passed status and simulation marker. Reload and reopen the
   evaluation from **Persisted replay history** in both frontends. Verify no
   activation and unchanged service version until a separately authorized
   reviewed promotion exists.
6. With a non-member context, visit the project by both control and engine ID;
   assert 404/no data. With a viewer, attempt triage/graph/replay and assert 403
   plus unchanged engine state. With two accessible same-slug projects, assert
   slug ambiguity is rejected and each explicit ID resolves correctly.
7. Restart PostgreSQL and the engine/control plane using the integration
   harness, then repeat owned-project read and history read. Verify recovery
   without restarting the browser and no leaked internal credentials in
   browser requests or rendered errors. Keep genuine failures separate from
   simulated provider output.
