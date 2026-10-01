# Z.AI GLM discovery provider

This adapter uses Z.AI's OpenAI-compatible general API by default:
`https://api.z.ai/api/paas/v4/chat/completions`. Configure
`OPENCLASS_GLM_API_KEY` through the environment, along with
`OPENCLASS_DISCOVERY_PROVIDER=glm` and `OPENCLASS_GLM_MODEL=glm-5.3-flash`.

The Coding Plan endpoint is intentionally not selected by default. Z.AI documents
Coding Plan usage as restricted to supported coding tools; use the general API with
an account balance or resource package for OpenClass custom application work.

Responses are requested as JSON and validated strictly before becoming a discovery
result. The provider cannot access repositories or mutate ontology state. HTTP
errors, malformed JSON and invalid proposal shapes become a generic safe provider
failure. Credentials and request content are never persisted in candidates/events.
