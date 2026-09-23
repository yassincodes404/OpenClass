# Hidden intents — benchmark plan

Status: planned (OC-013). No benchmark scores or runnable benchmark command yet.

Initial concepts: billing, technical, sales. Withheld concepts: cancellation,
password_reset, refund_status, shipping, account_compromise, feature_request.

Build independently reviewed labeled examples with provenance and a fixed split/seed.
Run the initial and evolved ontologies on the same held-out set. Measure correct/
false/duplicate discoveries, coverage, macro F1, unknown precision/recall, provider
calls/cost and runtime. Include ambiguous, synonym and regression cases.

The lexical mock checks the workflow, not open-world model quality. Never report
mock scores as an external-provider benchmark or fabricate flattering constants.
