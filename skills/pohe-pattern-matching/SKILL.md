---
name: pohe-pattern-matching
description: Adjudicate a POHE source candidate against a record's pointcut, contract, and negative control. Use after detection when deciding whether a harness mechanism is a real instance, what evidence level it reaches, and what remains unverified. Produces a reviewable record, not an automatic classifier.
---

# POHE pattern matching

## When to use

Use this skill when a specific file, symbol, or candidate has been retrieved and
the question is: **is this a POHE record, and at what evidence level?**

Detection gives leads. Matching is a source-reading task. It cannot be reduced
to the regex. The operational signature used by `analyze` is also not the
pointcut: it is the observable-role proxy the tool can check. When signature and
pointcut disagree, read the canonical exemplar and record the disagreement
instead of forcing either side.

## Inputs

- The record: `pohe-agent show <ID>`
- Structural candidates:
  ```bash
  pohe-agent match <repo> --pattern <ID> --markdown candidates.md
  ```
- A scope-anchored evidence packet:
  ```bash
  pohe-agent analyze <repo> --pattern <ID> --markdown analysis.md
  ```
  Read its dimension status, missing roles, negative-control checks, and
  contract probes. Its verdict is a review lead, not an evidence level.
  `cue_sources` tells you whether the scope was reached by the frozen lexical
  cue or by a calibrated operational alias. An operational-only hit is still
  only a retrieval lead; it is not structural evidence.
- The canonical anchor and `docs/calibration.md`. If the anchor is a file,
  interface, prompt, or configuration, or if it is missing signature roles,
  treat that as a pointcut/exemplar question to record, not as a reason to
  loosen the signature until the anchor passes.
- The candidate source file and its tests.

## Adjudication procedure

Work through all four pointcut dimensions separately. Do not collapse them into
one judgment.

1. **Context.** Does the mechanism operate in the stated harness boundary or
   lifecycle? If not, stop: the candidate is out of scope.
2. **Trigger.** Is it activated by the stated event? Name the call site or state
   transition that activates it.
3. **Structure.** Are the required roles, state, callbacks, and policies
   present? Distinguish a real role from a name.
4. **Effect.** Is the stated consequence observable? Name what changes in
   control flow, data, authority, or records.

Then map the contract:

| Field | Question |
| --- | --- |
| Requires | What must hold before the mechanism acts? |
| Ensures | What must be true after it acts? |
| Invariant | What must hold throughout? |
| Violation | What happens on failure, cancellation, or misuse? |

Finally apply the **negative control**. Find a similar-looking construct that
must not count. If the negative control also passes, the adjudication is
overbroad.

## Evidence levels

- **E1 — retrieval cue.** Regex or symbol hit only. Do not describe this as an
  implementation.
- **E2 — source-located mechanism.** You read the source, identified roles and
  control flow, and can point to the file and symbol.
- **E3 — contract support.** E2 plus executable or explicit contract evidence
  for ordering, errors, or boundaries. Name the test or runtime check per
  contract field.

A repository can contain a real E2 mechanism with weak E3 support. Record that
honestly.

## Required output

```yaml
record: P01
repository: owner/name
status: confirmed | partial | rejected | unresolved
evidence_level: E2
candidate:
  file: path/to/file.py
  symbol: run_agent
pointcut:
  context: <what was observed>
  trigger: <what was observed>
  structure: <roles and state>
  effect: <observable consequence>
contract:
  requires: <mapped evidence or unknown>
  ensures: <mapped evidence or unknown>
  invariant: <mapped evidence or unknown>
  violation: <mapped evidence or unknown>
negative_control:
  construct: <similar construct that must not count>
  result: stays unmatched | matched (overbroad)
tests:
  - path:line
unknowns:
  - <what could not be verified>
```

## Rules

- Never promote because the code is popular, recent, or in a directory named
  `agent`.
- Never infer contract support from file names or from the presence of tests.
- Keep `unknowns` populated. An empty unknowns list usually means the review was
  shallow.
- A rejected candidate is a useful result; record why the negative control or
  pointcut failed.
- If the maintainer wants to change the code, hand off to
  `skills/pohe-harness-evolution/SKILL.md`. Matching is not authorization to
  edit.
