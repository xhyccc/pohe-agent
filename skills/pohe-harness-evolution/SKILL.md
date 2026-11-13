---
name: pohe-harness-evolution
description: Plan pattern-guided evolution of an agent harness. Use when a maintainer wants to change a harness responsibly, preserve protected responsibilities, add contract tests, and record evidence. Produces a reviewed change plan with authority, rollback, and retirement conditions; does not authorize unreviewed rewrites.
---

# Pattern-guided harness evolution

## When to use

Use this skill after detection and matching, when the task is to **change** a
harness: harden a loop, add a permission boundary, replace a router, improve
termination, or redesign an evidence path.

The output is a proposal. Code changes require maintainer approval.

## Preconditions

Do not plan a change until these exist:

1. A named record (`pohe-agent show <ID>`).
2. A source-level adjudication from `pohe-pattern-matching`.
3. A maintainer's goal and the authority to change the behavior.
4. A baseline: current tests, traces, or outcome measurements.
5. A known rollback point.

If any precondition is missing, stop and report what is missing.

## Procedure

1. Build the proposal:
   ```bash
   pohe-agent plan <repo> --findings findings.json --patterns <IDS> \
     --goal "<one sentence>" -o evolution.md
   ```
2. Keep the **protected contract** and **permitted variation** separate. A
   change inside the seam is maintenance; a change to the contract is a return
   from A3 to A1 and needs explicit authority.
3. Add the contract test first. The test must fail for the reason the change
   addresses, not merely fail because the code is absent.
4. Keep the negative control as a permanent test where possible.
5. Implement the smallest change that satisfies the contract. Do not move
   authority silently.
6. Run a canary on one real task. Compare outcome, cost, failure handling, and
   termination.
7. Update the record with evidence level, files, tests, unknowns, authority,
   rollback, and retirement trigger.

## Change gate

Reject the change if any answer is unsatisfactory:

- Does the negative control still stay unmatched?
- Does each contract field map to code, a test, or an explicit runtime check?
- Are failure, cancellation, and termination paths exercised?
- Did the change stay inside the permitted variation?
- Is there a named authority for any contract change?
- Is there a rollback point and a retirement trigger?
- Is the record updated to the evidence level actually demonstrated?

## Plan template

Use the generated plan, then fill the review fields:

```markdown
### <ID> — <name>

**Observed signal.** <file:line and evidence level>

**Pointcut to confirm.** <context / trigger / structure / effect>

**Protected contract.** <requires / ensures / invariant / violation>

**Permitted variation.** <what may change without reopening the contract>

**Negative control.** <what must remain unmatched>

**Proposed change.** <specific, minimal, reversible>

**Authority.** <who approved the contract or behavior change>

**Verification.** <tests and canary>

**Rollback.** <commit, flag, or configuration>

**Retirement trigger.** <condition under which the mechanism is removed>
```

## Rules

- Do not rewrite a protected contract because the implementation is inconvenient.
- Do not remove a negative control to make a test pass.
- Do not claim safety, cost, or reliability improvement without a measurement.
- Do not let a closed-loop agent approve its own contract change.
- Do not leave the record at E1 after implementing and verifying the mechanism.
- If the change fails a gate, report the failure and keep the plan open. A
  rejected change is a valid outcome.
