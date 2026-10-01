# Teacher Protocol v1.1: empirical Jev contract

Experimental successor to [Teacher Protocol v1](teacher-protocol.md). Historical v1
proof runners and requests remain unchanged. The executable contract is
`scripts/jev_contract/teacher.py`, used by the new precision benchmark.

Every request contains one deterministic failed layer, relevant graph slice, matching
StateSchema, JevProfile-derived operating manual with exact identity and limits,
evidence references, candidate history, permitted operators and capability signatures
with argument domains. Optional prior feedback must name a predeclared protocol and
contain only bounded counts of evaluated, passed and regressed cases. Hidden cases,
labels, evaluator predicates and another Teacher's answer are never disclosed.

The Teacher may propose changes but cannot apply or activate them. The deterministic
applier produces only an inactive copy referencing the immutable base policy hash.
No approval or activation operator exists. A stale base, wrong target, wrong layer,
invalid argument, missing capability or unsupported provider shape is rejected.

The implemented operator subset is deliberate:

| Failed layer          | Permitted change/answer                                                       |
| --------------------- | ----------------------------------------------------------------------------- |
| STATE_REPRESENTATION  | ADD_STATE_FEATURE                                                             |
| DECISION_SPACE        | ADD_CHOICE, MISSING_CAPABILITY                                                |
| SEMANTIC_ROUTING      | GENERALIZE_CHOICE, retaining its existing target                              |
| PROCEDURE             | REPLACE_PROCEDURE, MISSING_CAPABILITY                                         |
| PRECONDITION          | CHANGE_PRECONDITION                                                           |
| POSTCONDITION         | CHANGE_POSTCONDITION                                                          |
| SAFETY_GUARD          | CHANGE_SAFETY_GUARD (cannot remove old guards), NO_CHANGE, MISSING_CAPABILITY |
| MISSING_CAPABILITY    | MISSING_CAPABILITY                                                            |
| INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE                                                         |
| INFRASTRUCTURE        | NO_CHANGE, INSUFFICIENT_EVIDENCE                                              |

INSUFFICIENT_EVIDENCE and PROVIDER_COMPATIBILITY are available to every layer. Other
v1 conceptual operators remain unimplemented, and are not advertised as callable.
REPLACE_PROCEDURE explicitly repairs a procedure within a new policy version rather
than registering an unreachable new macro and asking for an unrelated routing edit.

Hard rules in every system prompt:

- Never repair routing by changing a procedure, or hide procedure failure by changing
  routing. A different diagnosis requires fresh deterministic evidence and a new request.
- Never make Jev responsible for deterministic safety. UNKNOWN alone is insufficient
  evidence for a new semantic choice.
- Never memorize exact environment strings as semantic aliases without evidence for a
  literal distinction. Literal procedure arguments are allowed when registered and
  supported by the failed step's evidence.
- Prefer concrete, self-contained choices, explicitly resolved state, retained relevant
  evidence and domain-justified hierarchy within the measured profile.
- Return PROVIDER_COMPATIBILITY if canonical semantics cannot fit the current profile;
  do not silently degrade or split the policy.
- Never infer hidden evaluation cases, invent primitives, claim human authority or
  activate candidates. Return MISSING_CAPABILITY or INSUFFICIENT_EVIDENCE when warranted.

The schema closes procedure arguments against the supplied capability catalog. Unknown
fields and operator/payload mismatches fail deterministic validation. Candidate rationale
and confidence are advisory. Confidence never authorizes execution or promotion.

The paired precision benchmark freezes identical messages, schema and evidence for both
models. Historical D/E inputs are retained as hashed source packages; normalized new
fixtures are explicitly identified. Valid-but-wrong first responses remain failures.
Neither a single better response nor a higher aggregate score switches the main Teacher.
