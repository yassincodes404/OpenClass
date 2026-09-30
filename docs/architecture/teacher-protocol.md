# Teacher Protocol v1 (experimental)

The Teacher is the discovery-side LLM (currently Gemini through the gateway, as
in Proof #2B). It proposes changes to a versioned PolicyGraph; it never applies
them. This protocol defines how OpenClass asks, what the Teacher may answer, and
what it is never given.

## 1. Diagnose the failed layer before asking for evolution

Every teacher request carries exactly one typed diagnosis, produced by
deterministic analysis of the execution trace (never by the teacher):

```text
INFRASTRUCTURE          provider/transport/executor failure; not learning evidence
STATE_REPRESENTATION    the compiler omitted or distorted a fact the router needed
DECISION_SPACE          no offered choice semantically fits (node gap)
SEMANTIC_ROUTING        a fitting choice existed but was not selected
PROCEDURE               choice correct; the macro's steps no longer work
PRECONDITION            the macro ran without required state in place
SAFETY_GUARD            execution was (correctly) refused; policy or permission gap
POSTCONDITION           steps ran but the verified outcome did not hold
MISSING_CAPABILITY      required primitive is not registered
INSUFFICIENT_EVIDENCE   the trace cannot support a diagnosis
```

Worked attributions from the recorded proofs:

- Proof #2B: Jev chose correctly, macro succeeded, literal gate rejected →
  SEMANTIC_ROUTING / STATE_REPRESENTATION territory — explicitly _not_ PROCEDURE.
- Macro executed, postcondition failed after environment drift → PROCEDURE or
  STATE_REPRESENTATION (decide by re-observation), never routing.

The teacher receives only evidence relevant to the diagnosed layer — not the
entire run — plus the current graph slice, the empirical `JevProfile`, prior
candidate history, and aggregate prior-evaluation feedback when a predeclared
protocol allows it.

## 2. Typed evolution operators

```text
ADD_CHOICE            add a choice to one node (with target)
GENERALIZE_CHOICE     widen a choice's semantic description (not its id)
SPLIT_CHOICE          one choice becomes two, with retargeted edges
MERGE_CHOICES         collapse synonyms, preserving one target
ADD_DECISION_NODE     new node; existing edges may retarget to it
RESTRUCTURE_NODE      change one node's choices/question (structure only)
ADD_MACRO             new macro from registered primitives
ADD_MACRO_BRANCH      add a guarded branch to an existing macro's procedure
DEPRECATE_MACRO       mark a macro unused (no deletion; graphs are append-only)
ADD_STATE_FEATURE     extend the state schema (versioned)
ADD_NORMALIZER        add a deterministic raw→state normalization rule
CHANGE_PRECONDITION   modify one typed precondition
CHANGE_POSTCONDITION  modify one verified postcondition
MISSING_CAPABILITY    the needed primitive does not exist; humans must register it
NO_CHANGE             evidence supports the current graph
INSUFFICIENT_EVIDENCE evidence does not justify any change
```

A candidate normally modifies **one conceptual layer**. If the teacher believes
two layers are wrong, it emits separate candidates; evaluation scores them
independently.

## 3. Candidate envelope (typed)

The candidate is a JSON document validated against a strict schema (implemented
as pydantic models in the harness; the JSON Schema is generated from them):

```text
TeacherCandidate
  candidate_type       one of the operators above
  target_id            node/macro/edge/state-field the change applies to
  payload              operator-specific typed content
  semantic_description what the change means, in router-consumable language
  rationale            evidence-cited reasoning
  confidence           0..1, advisory only
  base_policy_id       the version the candidate applies to
```

Hard schema rules mirror Proof #2B: procedures may only reference registered
primitives; unknown primitives must yield MISSING_CAPABILITY; descriptions are
bounded; no executable code, shell, regex, or paths; strict mode; extra fields
forbidden.

## 4. Teacher system prompt v1

> You are the OpenClass Teacher. Your role is to improve versioned decision
> knowledge used by a bounded semantic decision provider called Jev.
>
> Jev is not a general planner, shell generator, safety authority, or source of
> ground truth. Jev chooses among a bounded set of semantic alternatives supplied
> by OpenClass. Measured characterization (the supplied JevProfile): Jev classifies
> robustly up to at least 32 concrete choices; it is degraded by abstract group
> descriptions, by anaphoric references to earlier decisions, and at the
> borderline between a plausible class and UNKNOWN. Design within those limits.
>
> OpenClass executes only registered capabilities and independently verifies
> outcomes. A supplied failure diagnosis names the layer that failed. Do not
> change a working procedure to repair a routing problem. Do not change routing to
> hide an execution failure.
>
> Prefer the smallest reusable change supported by the evidence. Do not add
> literal aliases merely to memorize observations when the evidence supports a
> stable semantic concept; do not generalize beyond the evidence merely because
> abstraction seems elegant.
>
> Preserve known-good behavior. A candidate that gains coverage by regressing
> verified previous behavior will normally fail evaluation.
>
> Never invent executable shell, Python, paths, environment variables,
> credentials, or primitive names. You may only compose registered primitives. If
> the required operation is unavailable, return MISSING_CAPABILITY.
>
> Never assume model output is ground truth. Never activate your own proposal.
> Never claim human approval. Hidden evaluation cases are unavailable to you; do
> not attempt to infer benchmark contents from aggregate scores.
>
> If the evidence is insufficient to justify a reusable change, return
> INSUFFICIENT_EVIDENCE. Use the supplied empirical JevProfile when designing
> decision nodes. Output only the supplied typed candidate schema.

## 5. Disclosure and evaluation rules

- Hidden evaluation cases stay hidden. Aggregate prior evaluation feedback (the
  Proof #2B cycle-2 rule) may be included only when the experiment's
  pre-registered protocol says so, and only as counts — never per-case identities
  or labels.
- One candidate per request; a valid-but-failing candidate is retained, not
  repaired or retried.
- Infrastructure failures are never learning evidence and never shown as semantic
  outcomes.
- The teacher never receives credentials, unrestricted shell, storage mutation,
  or activation authority. Approval is human-only, explicit, and scoped.
