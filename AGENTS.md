# AGENTS.md — POHE harness pattern agent

You are working in the POHE agent package. Your job is to help a maintainer
**detect**, **adjudicate**, and **evolve** harness responsibilities in an
arbitrary repository using the 52 frozen POHE records.

The package has three layers:

1. `pohe-agent scan` retrieves lexical cues from a checkout.
2. `pohe-agent match` extracts structural candidates for source review.
3. `pohe-agent analyze` anchors cues to scopes and checks an operational
   signature, negative control, and contract probes.
4. `pohe-agent plan` turns findings into a pattern-guided evolution proposal.

The catalog in `src/pohe_agent/data/patterns.json` is frozen study data. Do not
rewrite it to make a finding look better.

## Read this first

A cue is not an implementation. The evidence ladder is:

| Level | Meaning | Required evidence |
| --- | --- | --- |
| E0 | Proposed record | The frozen specification only |
| E1 | Retrieval cue | A regex or symbol hit |
| E2 | Source-located mechanism | Source read: roles, state, and control flow identified |
| E3 | Contract support | Executable or explicit contract evidence for ordering, errors, or boundaries |

Never promote a record from E1 to E2 without naming the file, symbol, and control
flow. Never promote to E3 because tests exist somewhere in the repository; name
the test or runtime check that covers the contract field.

## Standard workflow

1. **Orient.** Read `README.md` and the target repository's own instructions.
   Identify whether the task is detection only, matching, or evolution.
2. **Scan.** Run:
   ```bash
   pohe-agent scan <repo> --json findings.json --markdown findings.md
   ```
   Read the summary and the family table. Note unobserved records remain
   unobserved; do not describe them as absent.
3. **Select.** Prefer `high` and `medium` priority records, or records named by
   the maintainer. Treat `low` as a lead only.
4. **Match.** Run structural extraction for the selected records:
   ```bash
   pohe-agent match <repo> --pattern P01,P09 --markdown candidates.md
   ```
   For a dimension-level packet, run:
   ```bash
   pohe-agent analyze <repo> --pattern P01,P09 --markdown analysis.md
   ```
5. **Adjudicate.** For each candidate, answer the pointcut questions and
   contract questions in `skills/pohe-pattern-matching/SKILL.md`. Apply the
   negative control. Record E1, E2, E3, or "not this record". `analyze` verdicts
   are scope-level evidence, not E2 promotion.
6. **Plan.** For evolution work:
   ```bash
   pohe-agent plan <repo> --findings findings.json --patterns P01,P09 \
     --goal "harden termination and tool discovery" -o evolution.md
   ```
   Fill the proposal only after adjudication. Keep the protected contract and
   the permitted variation separate.
7. **Change.** Editing code requires explicit maintainer approval, a failing
   contract test, and a rollback point. Follow
   `skills/pohe-harness-evolution/SKILL.md`.
8. **Record.** Report evidence level, files, tests, remaining unknowns, and the
   authority for any contract change.

## Commands

```bash
pohe-agent list [--patterns P,W]
pohe-agent show P01 [--json]
pohe-agent scan <repo> [--json FILE] [--markdown FILE] [--patterns IDS] [--max-files N]  # N=0 means all files
pohe-agent match <repo> [--pattern IDS] [--json FILE] [--markdown FILE]
pohe-agent analyze <repo> [--pattern IDS] [--top N] [--min-verdict V] [--include-tests] [--jobs N] [--json FILE] [--markdown FILE]
pohe-agent plan <repo> --findings FILE --goal TEXT [--patterns IDS] [-o FILE]
```

Run from a checkout: `PYTHONPATH=src python3 -m pohe_agent ...`, or install with
`pip install -e .` and use `pohe-agent ...`.

## Hard rules

- Do not call cue coverage prevalence. It describes this checkout only.
- Do not state that a pattern is implemented because a regex matched.
- Do not delete or rewrite a protected contract without named authority.
- Do not modify the frozen catalog under `src/pohe_agent/data/`.
- Do not run destructive commands, rewrite git history, or push without the
  maintainer's instruction.
- Do not place secrets, tokens, or private repository contents in reports.
- Keep the negative control visible in every adjudication.
- Do not edit `data/signatures.json` to make a candidate pass. A signature is a
  reviewable detection contract; change it only with a stated reason and rerun
  the canonical examples:
  `python tools/audit_canonical.py --markdown docs/calibration.md`.
- Leave unobserved records visible as unobserved.

## Repository map

```
AGENTS.md                     this file
agent.md                      pointer for tools that look for agent.md
README.md                     user-facing overview
src/pohe_agent/catalog.py     load and select records
src/pohe_agent/walk.py        deterministic repository walking
src/pohe_agent/scan.py        lexical cue retrieval
src/pohe_agent/match.py       structural candidates and questions
src/pohe_agent/features.py    scope anchoring, facts, tag vocabulary
src/pohe_agent/signatures.py  operational signature loader
src/pohe_agent/analyze.py     evidence triangulation and verdicts
src/pohe_agent/data/signatures.json  one operational signature per record
src/pohe_agent/plan.py        evolution plan builder
src/pohe_agent/report.py      Markdown rendering
src/pohe_agent/cli.py         command-line interface
src/pohe_agent/data/          frozen 52-record catalog
skills/                       task-specific agent skills
examples/mini_harness/        runnable example
tests/                        stdlib test suite
tools/export_patterns.py      regenerate catalog data from the field guide
tools/reproduce_study_matrix.py  compare cue retrieval with the study matrix
tools/audit_canonical.py      audit signatures and cues against canonical anchors
docs/reproduction.md          method and results of the 41-repository run
docs/analysis.md              scope-anchored evidence triangulation
docs/calibration.md           generated canonical-anchor audit
```

## Skills

Load the relevant skill before the task, not after:

- `skills/pohe-pattern-detection/SKILL.md` — scan and interpret retrieval cues.
- `skills/pohe-pattern-matching/SKILL.md` — adjudicate a source candidate.
- `skills/pohe-harness-evolution/SKILL.md` — plan and verify a harness change.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m pohe_agent scan examples/mini_harness
PYTHONPATH=src python3 -m pohe_agent match examples/mini_harness --pattern P01,P09
```

Report what you ran, what failed, and what remains unverified. Do not claim a
pattern is implemented when only a cue was retrieved.
