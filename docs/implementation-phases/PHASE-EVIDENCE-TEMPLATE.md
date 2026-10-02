# Phase NN — evidence record

Copy this template to a new phase-specific evidence file; keep this reusable template unchanged. Exclude secrets and unnecessary customer data. Store large/private artifacts in an approved access-controlled location and reference hashes/IDs rather than checking sensitive content into Git.

## Identity and scope

- Phase, status, date and responsible reviewer:
- Branch, reviewed commit, worktree and deployment/build identity:
- Existing tickets / scoped child tickets / RFC and decision:
- Prerequisite evidence links and unresolved blockers:
- Intended public behavior; explicit scope exclusions:

## Fresh audit

| Requirement | Existing/wired/simulated/broken/missing | Source/migration/API/SDK/UI evidence | Repair and outcome |
|---|---|---|---|
| Fill | Fill | Fill | Fill |

## Implementation and persistence

- Domain contracts/services and public API/SDK compatibility:
- New/changed migrations; fresh-install and existing-data upgrade results:
- Transaction/ownership/idempotency/concurrency rules:
- Immutable version/audit/source handling:
- Rollback/reconciliation and operational instructions:
- Product UI routes and actual user steps:

## Protocol frozen before live execution

- Business operation, operator/resource authorization and external-write scope:
- Hypothesis and signed quality/risk/operational acceptance limits:
- Input source/time window/selection/truncation/provenance hashes:
- Independent reference-label source, reviewer and unresolved disagreements:
- Discovery/calibration/evaluation/retention splits and contamination controls:
- Baseline/candidate/spec/ontology/policy/provider/binding versions:
- Attempt/unique-source/cohort reconciliation and failure-denominator rules:
- Environment, real provider identities and budget; simulation/fixture scope:

## Actual measured results

| Metric/gate | Numerator | Denominator/sample count | Result/uncertainty | Coverage/exclusions | Evidence |
|---|---|---|---|---|---|
| Completed source cases | Fill | All attempted distinct cases | Fill | Failed/pending count | Fill |
| Known-reference agreement | Fill | Independently labeled completed known cases | Fill | Label coverage | Fill |
| Trusted-reference error | Fill | Independently checked trusted cases | Fill | Risk limit/profile | Fill |
| UNKNOWN detection | Fill | Eligible labeled withheld completed cases | Fill | Also show all-cohort detection yield | Fill |
| Retention/regression | Fill | Same frozen historical eligible cases | Fill | Versions and gate | Fill |
| External verification | Fill | Completed verification attempts | Fill | Pending/ambiguous/missing separate | Fill |
| Provider/Teacher usage | Actual attempts | Distinct ingested events | Fill | Retries/failures included | Fill |
| Cost/latency | Actual measured usage | Declared scope/sample count | Fill | Missing cost is unavailable | Fill |

Delete metrics irrelevant to this phase; do not fill future-stage values with invented zeros. Distinguish measured savings from counterfactual estimates. Incomplete provider coverage cannot support an unqualified ranking.

## Required checks

| Command/check | Target/configuration | Actual outcome | Log/artifact reference |
|---|---|---|---|
| make check | Fill | Fill | Fill |
| make test | Fill | Fill | Fill |
| npm run build | Fill | Fill | Fill |
| uv build --all-packages | Fill | Fill | Fill |
| Migrated disposable PostgreSQL | Fill | Fill | Fill |
| API + SDK + browser E2E | Fill | Fill | Fill |
| Reload/API/database restart | Fill | Fill | Fill |
| Isolation/permission negative checks | Fill | Fill | Fill |
| Phase-specific failure/concurrency checks | Fill | Fill | Fill |

Offline mock fixtures and live application datasets must use distinct environments/records. Record failed checks even if apparently unrelated; identify confirmed baseline versus newly introduced failures.

## Reconstruction proof

- Workspace/project/source/state/run/evidence/candidate/evaluation/version IDs:
- Before/after hashes and independent destination verification references:
- Restart procedure and post-restart SDK/UI observations:
- Tenant/role boundaries exercised, denied paths and results:
- Failure records retained; audit readable and attributable:
- Logs/screenshots/manifests are credential-free and appropriately access-controlled:

## Exit review

- Each acceptance criterion: PASS / FAIL / BLOCKED / NOT_APPLICABLE with rationale and evidence:
- Engineering gate versus live quality/business gate:
- Unsupported or incomplete behavior and operational risk:
- Reviewer decision; permitted pilot mode; launch/deployment authorization if separately supplied:
- Next phase prerequisites/blockers and concrete follow-up tickets:

Do not mark COMPLETE_WITH_EVIDENCE while required criteria fail. Negative learning findings can validate safety while leaving improvement unproven.
