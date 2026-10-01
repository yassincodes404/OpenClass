# Jev decision provider

The HTTP adapter implements single-choice classification with an explicit UNKNOWN
option. It sends observation text and the captured ontology's names, definitions,
aliases and examples; observation metadata stays local. Treat all submitted text
and ontology content as data disclosed to the selected remote provider.

Select `OPENCLASS_DECISION_PROVIDER=jev` and supply `OPENCLASS_JEV_API_KEY` through
the environment. The default endpoint is `https://ai-gateway.vercel.sh/typesafe`
with model `typesafe-ai/jev`; `https://api.typesafe.ai` is also allowed. Credentials
must match the selected endpoint. Mock remains the default decision provider and
the only supervisor provider.

Calls use a 20-second timeout per attempt and zero retries by default. Configure
`OPENCLASS_PROVIDER_TIMEOUT_SECONDS` (up to 60) and
`OPENCLASS_PROVIDER_MAX_RETRIES` (0–2). Transport failures, HTTP 429 and server
errors may retry; redirects and malformed responses do not. Each retry can incur
another remote call. Responses are bounded to 1 MB and distributions must exactly
match the ontology plus UNKNOWN. Upstream error bodies and arbitrary metadata
are discarded. Request-content logging is not enabled by the adapter.

Results preserve reported model, latency, token counts and gateway cost when
available; unavailable usage remains null. Failed decisions return a generic 502
and append `provider.error`, without creating a completed run. No prediction
changes the ontology or becomes a verified label.

Run offline contracts with `uv run pytest tests/contract/test_jev_provider.py`.
See [live testing](../../docs/guides/live-testing.md) for the opt-in pilot.
