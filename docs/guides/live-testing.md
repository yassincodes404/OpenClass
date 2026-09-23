# First real-provider test

The current server registers only the deterministic decision and supervisor mocks.
An API key alone cannot enable real inference. The kernel can accept provider
implementations, but no Jev, Ollama, or OpenAI-compatible adapter is implemented.
Passing mock tests demonstrates integrity and plumbing, not model quality.

## Shortest path to measured results

Finish OC-016 integrity checks first. Then implement OC-003's provider configuration,
secret-safe errors, timeouts, bounded retries, redaction, usage capture and contract
tests alongside OC-004's Jev adapter. This decision-provider path does not depend
on OC-017. Verify the official Jev API before choosing payloads or authentication.
Do not infer its protocol from the OpenAI API.

Real Supervisor tests follow OC-018, whose current dependencies include OC-017's
historical instruction snapshots. Keep that separate from the first Jev experiment.
There is no need to build discovery, chat or automatic auditing to test classification.

## Bounded first experiment

Use a disposable migrated database and a small, manually labeled, non-sensitive
text dataset: clear known examples, withheld concepts expected to remain UNKNOWN,
ambiguous inputs, and deliberately difficult known examples. Freeze the ontology
and save dataset provenance, provider/model identity and configuration with results.
Agree on a maximum call count and spending cap before using a paid endpoint.

Keep the key in a local environment variable once the adapter defines its settings;
never put it in chat, source, fixtures or result files. Supply the official API docs
URL, endpoint and model separately from credentials.

First run adapter contracts offline, including malformed output, rate limits,
timeouts and upstream errors containing secrets. Then run an opt-in live smoke
check through the public API/SDK. Mandatory CI remains credential-free.

Report each input's expected human label, actual prediction, UNKNOWN decision,
latency, tokens and reported cost (unavailable usage stays null). Aggregate known
accuracy, UNKNOWN recall and false-UNKNOWN rate with denominators, plus failures
and total calls. A small smoke dataset is a diagnostic, not a benchmark claim.
Inspect mistakes before expanding the dataset or changing the architecture.

For a later real Supervisor experiment, compare findings with independent human
judgments and assert complete run, ontology and unknown-pool snapshots are unchanged.
A review is advisory evidence and must never become a verified label automatically.
