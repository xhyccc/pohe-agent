# Scope-anchored evidence triangulation

`analyze` is the structural matcher behind the newer detection surface. It
replaces file-level cue counting and symbol-name matching with a review packet:
a cue is anchored to an enclosing declaration, observable roles are extracted
from that scope, and each pointcut dimension is marked supported, partial, or
contradicted.

The method exists because a lexical cue answers only "where should I look?" It
does not answer "is the mechanism here?" and it cannot apply a negative control.
It also does not assume the prose pointcut is correct. Pointcuts are design
hypotheses; the matcher uses a separate **operational signature** that can be
reviewed and corrected without rewriting the record.

## The pipeline

```
file
  │
  ├── cue hit ──────────────► smallest enclosing scope
  │                            function, method, class, declaration, file
  │
  ├── scope facts ──────────► loops, branches, returns, raises, calls,
  │                            parameters, assignments, decorators, tokens
  │
  ├── signature check ──────► context / trigger / structure / effect
  │                            supported · partial · contradicted
  │
  ├── negative control ─────► explicit contrast, at scope level
  │
  ├── contract probes ──────► visible mechanism or not visible
  │
  └── verdict ──────────────► rejected · cue_only · structural_candidate
                               pointcut_candidate · source_matched
```

### 1. Scope anchoring

Every cue hit is mapped to the smallest declaration that contains it. A
function-level cue is not promoted to a file, and a file-level hit is not
promoted to an implementation. For methods and functions, the enclosing class
name contributes context, but the class body does not. This avoids the common
false positive where one large class contains every vocabulary word somewhere.

Python scopes come from `ast` (`end_lineno` included). Other languages use
declaration matching plus brace balance, with an indentation fallback. A scope
is capped at 1,200 lines; beyond that the analyzer reports a bounded scope and
the reviewer must widen it manually. The cap is deliberately above the longest
canonical exemplar method so a single large method is not silently truncated.

### Retrieval is two-layered

The frozen catalog regex is the first layer. It is high-specificity and
sometimes misses its own exemplar: `\bprompt_cache\b` does not match
`PROMPT_CACHE_KEY_FIELD` in Python because `\b` treats `_` as a word character,
and `\bgroup_chat_manager\b` does not match `BaseGroupChatManager` because the
separator is a camel-case transition. The analyzer therefore compiles every cue
with an **identifier-aware boundary**: a boundary exists at start/end, at
underscore or hyphen, or at a lower-to-upper camel transition. This is a
property of the tokenizer, not a per-record patch, and it repairs the
snake_case and camelCase cases without loosening the phrase itself.

The second layer is an optional `cues` list stored with the operational
signature. These are calibrated aliases such as `agent[-_]?hooks` for P16 or
`self[-_]?verif` for P17. They exist only because the frozen vocabulary missed
the canonical exemplar. Operational cues are labels in the packet
(`cue_sources: lexical | operational`); they never add structural evidence.
A candidate reached only by an operational cue is reported as such.

`tools/audit_canonical.py` checks both layers against all 51 records that have a
canonical anchor and writes `docs/calibration.md`. The audit currently retrieves
51 of 51 anchors, of which 17 needed an operational cue. Retrieval alone is not
a match: the same audit reports 12 anchors that are file or non-code units, 34
anchors with missing signature roles, and 6 whose own negative control fires.
Those are the records where the pointcut, the exemplar, or the signature needs
review.

### 2. Structural facts

Facts are deliberately shallow and explainable:

- control flow: loops, conditionals, returns, raises, `yield`, `await`, `break`,
  `continue`, `try`, `with`;
- names: calls, parameters, assignments, classes, bases, decorators;
- vocabulary: identifier tokens split on snake/camel case, plus string literals
  used for event names, tool names, and schema keys;
- parse mode: `ast` for Python, `regex` for other languages or unparsable
  scopes.

Docstrings and comments are excluded from token evidence. A comment that says
"middleware" is not a middleware chain.

### 3. Operational signatures

`src/pohe_agent/data/signatures.json` holds one signature per record. A
signature lists observable roles for each pointcut dimension and one or more
negative-control codes:

```json
{
  "P09": {
    "context": ["tool", "discovery"],
    "trigger": ["discovery", "invocation"],
    "structure": ["discovery", "registry", "authorization", "invocation"],
    "effect": ["tool", "authorization", "schema"],
    "negative": ["static_inventory"]
  }
}
```

A signature is **not** a restatement of the pointcut. It is the detection
contract the tool can actually check. Keeping it separate makes disagreement
visible: if a signature is too strict, its canonical exemplar will fail it; if a
pointcut is wrong, the signature can still find the mechanism and the mismatch
can be reviewed.

Roles are matched through an explicit tag vocabulary in
`src/pohe_agent/features.py`. A tag such as `authorization` is satisfied by
authorization vocabulary plus a conditional or raise path, not by the word
alone. `loop` requires actual loop syntax or recursion. `event` requires a call
or channel construct. A call alone does not create `fanout`, `aggregate`, or
`reducer`; a return alone does not create `yield` or `termination`. The rules
are intentionally conservative; add a tag only when it names an observable
role, not a topic.

Signatures are allowed to be stricter than their canonical exemplar. P08's
canonical anchor is the abstract `ModelProvider`; the signature requires a
`subtype` and an `error` boundary as well, so the anchor is reported as a
`structural_candidate` rather than silently promoted. P07's anchor is a cache
key resolver, not a provider dialect adapter; the signature asks for the cache
identity, capability gate, and correlation the source actually shows, and the
audit records the missing adapter as a pointcut question.

### 4. Dimensions and verdicts

| Dimension | What is checked |
| --- | --- |
| Context | Is the scope in the right kind of code, with the right subject vocabulary? |
| Trigger | Is there a code cue in this scope, and does it carry the activation role? |
| Structure | Are the declared roles visible in one scope? |
| Effect | Is there an observable terminal, result, error, or emission path? |

| Verdict | Meaning |
| --- | --- |
| `rejected` | The scope matches a high-severity negative-control contrast. |
| `cue_only` | A cue is present, but structure is missing or contradicted. |
| `structural_candidate` | At least one structure role is supported; other dimensions still need review. |
| `pointcut_candidate` | Context, structure, and effect are supported, but at least one signature role is missing. |
| `source_matched` | All four dimensions are supported and every structure role is visible. |

`source_matched` is a **scope-level structural match**, not E2 and not contract
support. It says the source contains the roles a reviewer should inspect. The
contract probes and the test obligation remain open.

### 5. Negative controls

Negative controls are executable contrasts, not checkboxes. Examples:

- `one_shot`: a P01 candidate with no loop or recursion is rejected even if the
  function name contains `loop`.
- `static_inventory`: a P09 candidate needs discovery, registry, or invocation
  machinery; a literal tool list is rejected.
- `post_hoc`: a P24 candidate needs a blocking conditional or raise before the
  action; a warning after execution is rejected.
- `no_fan_in`: a W03 candidate needs a reducer; bare `Promise.all` is rejected.
- `generic_history`: R02 and P28 need reflection, retrieval, or update policy;
  a retained transcript is rejected.

The rules live in `NEGATIVE_RULES` in `src/pohe_agent/analyze.py`. Each rule
names the tags or syntax facts that must be present for the contrast to remain
clear. A high-severity risk rejects the candidate; a medium-severity risk caps
it at `structural_candidate`.

### 6. Contract probes

Each contract field gets an observation, never a satisfaction claim:

- `requires`: is a guard (conditional, assert, raise) visible?
- `ensures`: is a return or yield path visible?
- `invariant`: is a check mechanism visible?
- `violation`: is an error path visible?

`mechanism_present` means only that the scope contains a mechanism of the right
shape. It does not mean the contract text is guaranteed.

## Running it

```bash
pohe-agent analyze /path/to/repo --pattern P01,P09 --markdown analysis.md
pohe-agent analyze /path/to/repo --min-verdict pointcut_candidate --json packets.json
pohe-agent analyze /path/to/repo --include-tests --top 10
```

Useful options:

- `--pattern`: comma-separated record ids or families; default all 52.
- `--top`: candidates per record; default 5.
- `--min-verdict`: discard candidates below this verdict; default `cue_only`.
  Pass `rejected` to inspect negative-control failures.
- `--include-tests`: allow test scopes as primary candidates. By default tests
  are used only as linkage evidence for code candidates.
- `--signatures`: load an alternative signature file for calibration.
- `--max-files`: cap the repository walk; `0` keeps every candidate (default).

## Calibration and limits

The method is deterministic and dependency-free. It is not a classifier and it
does not infer semantic conformance. Its known failure modes are:

1. **Vocabulary drift.** A mechanism can implement a role without using the
   tag's vocabulary. The candidate is then under-scored, not disproved.
2. **Scope boundaries.** A mechanism split across files, or across a scope
   larger than 1,200 lines, may not be triangulated in one packet.
3. **Signature error.** The operational signature is a curation artifact. When
   a canonical exemplar fails its own signature, treat that as a signal to
   inspect both the signature and the pointcut.
4. **Exemplar mismatch.** A canonical anchor is a locating example, not the
   whole pattern. It may be an interface, a prompt constant, a configuration
   file, or a single field. When the anchor's evidence unit is weaker than the
   pointcut's structure sentence, the audit records `anchor_gap` or
   `structure_gap`; that is a pointcut/exemplar question, not an analyzer
   failure.
5. **Test isolation.** Test files are excluded from primary candidates because
   fixtures often contain every role at once. They remain visible as test
   evidence for a code candidate.
6. **Language coverage.** Python gets AST facts. Other languages get
   declaration and regex facts, which are weaker and are reported as
   `parse: regex` in the candidate packet.

## Canonical calibration

`docs/calibration.md` is generated by:

```bash
python tools/audit_canonical.py --markdown docs/calibration.md --json /tmp/calibration.json
```

It anchors each canonical line to its smallest enclosing scope and runs the
same dimension, negative-control, and verdict logic on that scope. It reports
retrieval (frozen vs operational cue), anchor unit (implementation, interface,
file, config), structural coverage, and a gap list. Use it when changing a
signature or a cue: a change is only an improvement if it recovers an anchor
without turning the anchor's own negative control into a false match.

The current audit is deliberately not a scoreboard. A high count of
`structure_gap` rows means the signatures ask for roles the exemplars do not
show, which is exactly the disagreement the method is meant to expose.

The right use is triage: read the top candidate, check the missing roles, apply
the negative control, then decide E2 or E3 from source and test evidence.
