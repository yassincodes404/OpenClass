# Provider development

Only `providers/mock` is implemented in Genesis. It matches whole terms from
canonical names, aliases, and positive examples. Scores are deterministic fixtures.

Implement `openclass_core.providers.DecisionProvider.choice` with a ChoiceRequest
and ChoiceResult. Include every active canonical class, plus unknown_probability;
finite probabilities must sum to one. The service rejects missing or foreign labels.
Provider-specific details belong in provider_metadata. Preserve model, provider,
latency and optional usage/cost. Use ProviderError with safe messages; no secrets.

Adapters must not access a repository or mutate ontology state. Extend the shared
contract suite when adding adapters. Boolean/score/discovery/embedding interfaces
are planned with their implementations; do not ship untested method stubs.
See OC-003–006 for real-provider prerequisites.
