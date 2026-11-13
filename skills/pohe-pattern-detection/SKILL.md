---
name: pohe-pattern-detection
description: Detect POHE harness design-pattern cues in an arbitrary repository. Use when asked to scan a codebase for agent-harness mechanisms, produce a pattern inventory, or triage where design responsibilities live. Returns retrieval evidence and review priorities, not implementation claims.
---

# POHE pattern detection

## When to use

Use this skill when the task is to **find leads** in a repository: which POHE
records have vocabulary or symbols worth reading. Do not use it to certify that
a pattern is implemented.

## Procedure

1. Confirm the target path is a checkout, not a dependency cache. Ask before
   scanning outside the workspace.
2. Run:
   ```bash
   pohe-agent scan <repo> --json findings.json --markdown findings.md
   ```
   If the package is not installed, run from the package root:
   ```bash
   PYTHONPATH=src python3 -m pohe_agent scan <repo> --json findings.json --markdown findings.md
   ```
3. Read `summary`, `by_family`, and the `high`/`medium` priority records.
4. For each selected record, open the representative match before summarizing.
5. Report **E1 retrieval cue** only. State the file and line that made the
   record worth review.

## Interpreting the output

- `observed` means the frozen expression matched this checkout. It does not mean
  the mechanism exists, is correct, or is used.
- `not_observed` means this cue pass did not retrieve the record. It does not
  mean the mechanism is absent. Vocabulary, generated code, vendored code, and
  excluded directories all change yield.
- `priority` orders review effort:
  - `high` — code hits in multiple files plus test evidence.
  - `medium` — at least one code file and repeated hits.
  - `low` — a lead, often support files or a single mention.
- `files` and `hits` describe the checkout only. Never turn them into a
  percentage of repositories, teams, or products.

## Required output

Report:

1. The scanned path, file counts, and exclusions.
2. A table of observed records with priority, hits, files, and one
   representative location.
3. The unobserved records, labeled unobserved.
4. The evidence boundary: E1 only; no prevalence or conformance claim.
5. Recommended next action: which records to adjudicate with
   `pohe-pattern-matching`.

## Failure modes to avoid

- Treating a common word (`router`, `memory`, `loop`) as a pattern instance.
- Reporting the number of cue hits as importance.
- Hiding unobserved records because the table looks cleaner.
- Promoting a record because its name appears in a README.
- Scanning `node_modules`, `.venv`, `dist`, or generated files and inflating
  coverage. The walker excludes these by default; do not override it casually.

## Handoff

For any record the maintainer wants to act on, load
`skills/pohe-pattern-matching/SKILL.md` and produce a source-level adjudication
packet before planning a change.
