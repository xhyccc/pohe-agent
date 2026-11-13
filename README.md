# POHE Agent

**Detect harness design patterns. Match them to protected responsibilities. Plan evolution without losing authority.**

`pohe-agent` is a portable agent package and command-line tool for the
[Pattern-Oriented Harness Engineering](https://xhyccc.github.io/pohe/) field
guide. It brings the 52-record POHE harness pattern catalog to an arbitrary
repository, then helps an agent or maintainer decide what is actually there and
what may safely change.

The package is deliberately small and dependency-free. The scanner is Python
standard library only; the agent instructions and skills work with any coding
agent that reads `AGENTS.md` or `SKILL.md`.

## Quick start

```bash
git clone https://github.com/xhyccc/pohe-agent.git
cd pohe-agent
python3 -m pip install -e .
pohe-agent scan /path/to/your/repo --json findings.json --markdown findings.md
```

Then inspect the structural candidates for a record:

```bash
pohe-agent match /path/to/your/repo --pattern P01,P09 --markdown candidates.md
pohe-agent show P01
```

And turn findings into a reviewed evolution proposal:

```bash
pohe-agent plan /path/to/your/repo --findings findings.json \
  --patterns P01,P09 --goal "harden termination and tool discovery" \
  -o evolution.md
```

No installation is required for development:

```bash
PYTHONPATH=src python3 -m pohe_agent scan examples/mini_harness
```

## What it does

```
repository
   │
   ├── scan ────────► lexical cues (E1) + review priority
   │                    per record, file, line, contract, negative control
   │
   ├── match ───────► structural symbols + adjudication questions
   │                    Python AST, declaration syntax, alias hits
   │
   └── plan ────────► pattern-guided evolution proposal
                        protected contract, variation, tests, authority,
                        rollback, verification gates
```

### `scan`

Runs the frozen cue expressions over code, test, and support files. It excludes
dependency caches, build output, vendored trees, minified files, and files over
2 MB. The output is a JSON document plus an optional Markdown report.

Each observed record carries:

- join point and four pointcut dimensions,
- contract fields (`requires`, `ensures`, `invariant`, `violation`),
- the negative control,
- representative file and line matches,
- a review priority (`high`, `medium`, `low`),
- the next review action.

### `match`

Extracts function, class, and declaration symbols and checks them against the
record's cue and aliases. It returns candidates **and the questions** needed to
adjudicate them. It does not decide that a candidate is a pattern instance.

### `plan`

Builds a Markdown evolution plan from scan findings. It preserves the protected
contract, the permitted variation, the test obligation, the negative control,
and the evolution question for each selected record. The plan is a proposal:
authority, evidence, rollback, and retirement remain to be filled.

## The evidence ladder

| Level | Meaning | What the tool can produce |
| --- | --- | --- |
| E0 | Proposed record | The frozen specification |
| E1 | Retrieval cue | `scan` and `match` output |
| E2 | Source-located mechanism | An agent or maintainer reads the source |
| E3 | Contract support | Tests or runtime checks named per contract field |

**A cue is not an implementation.** Cue coverage is not prevalence. Absence of a
cue is not absence of a mechanism. The tool is a discovery and review
instrument, not a conformance classifier.

## Agent package

The repository is also an agent package:

```
AGENTS.md                                  operating manual for coding agents
agent.md                                   pointer for tools that look for agent.md
skills/pohe-pattern-detection/SKILL.md     scan and triage
skills/pohe-pattern-matching/SKILL.md      adjudicate a candidate
skills/pohe-harness-evolution/SKILL.md     plan and verify a change
```

An agent should load the relevant skill before the task, run the tool, read the
source, and report the evidence level it actually reached. The skills define the
required output format and the failure modes to avoid.

For Claude Code, copy or symlink `skills/*` into `.claude/skills/`, or point the
agent at this repository. For other agents, read `AGENTS.md` and follow the
skill files directly.

## The catalog

`src/pohe_agent/data/patterns.json` holds all 52 frozen records:

- 29 coding-agent mechanisms (P01–P29),
- 7 workflow and coordination patterns (W01–W07),
- 4 communication patterns (C01–C04),
- 2 reasoning and feedback patterns (R01–R02),
- 10 evolution mechanisms (E01–E10).

Each record includes its pointcut, contract, variation, test obligation,
negative control, evolution question, lexical cue, and canonical source
exemplar where one exists. The catalog is generated from the study through the
field guide; regenerate it with:

```bash
python3 tools/export_patterns.py \
  --catalog ../pohe-site/data/patterns.json \
  --out src/pohe_agent/data/patterns.json
```

Do not edit the catalog by hand to make a finding look better.

## Example

The bundled `examples/mini_harness` contains a bounded agent loop, deferred tool
discovery, and a permission prefix check. A scan retrieves P01, P09, P19, and
several low-priority leads; the report explains what to inspect and what remains
unobserved.

```bash
PYTHONPATH=src python3 -m pohe_agent scan examples/mini_harness
PYTHONPATH=src python3 -m pohe_agent match examples/mini_harness --pattern P01,P09
```

## Design boundaries

- **Not a linter.** A clean scan does not mean the harness is well designed.
- **Not a benchmark.** Hit counts are not quality or prevalence measures.
- **Not an auto-fixer.** `plan` writes a proposal; it does not edit code.
- **Not a replacement for review.** E2 and E3 require reading source and tests.
- **Not a closed-loop authority.** An agent may propose a contract change; a
  named human authority must approve it.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

The test suite covers catalog integrity, repository walking, cue retrieval,
structural candidate extraction, report boundaries, and plan generation.

## License

MIT. See [LICENSE](LICENSE).

## Citation

If you use this package, cite the POHE field guide:

> Haoyi Xiong. *Pattern-Oriented Harness Engineering.*
> https://xhyccc.github.io/pohe/
