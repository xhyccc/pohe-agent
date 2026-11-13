"""Build a pattern-guided harness evolution plan from scan findings."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .catalog import by_id


def select_records(scan_result: dict, pattern_spec: str | None) -> list[dict]:
    observed = {item["id"]: item for item in scan_result["patterns"] if item["status"] == "observed"}
    if pattern_spec:
        wanted = [token.strip() for token in pattern_spec.split(",") if token.strip()]
        selected = [observed[key] for key in wanted if key in observed]
        missing = [key for key in wanted if key not in observed]
        if missing:
            raise SystemExit(f"no retrieved cue for: {', '.join(missing)}")
        return selected
    selected = [item for item in observed.values() if item["priority"] in {"high", "medium"}]
    return selected or list(observed.values())


def build_plan(scan_result: dict, catalog: dict, goal: str, pattern_spec: str | None = None) -> str:
    selected = select_records(scan_result, pattern_spec)
    if not selected:
        raise SystemExit("no observed record selected; pass --patterns with ids that have a retrieved cue")
    lookup = by_id(catalog)
    lines = [
        "# Pattern-guided harness evolution plan",
        "",
        f"- Repository: `{scan_result['root']}`",
        f"- Goal: {goal}",
        f"- Status: **proposal for review**",
        f"- Date: {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "> This plan protects responsibilities, not component names. A cue is only a",
        "> reason to inspect. No protected contract changes without named authority,",
        "> a failing or new test, and a recorded decision.",
        "",
        "## Operating rules",
        "",
        "1. Freeze the current behavior and record the baseline before editing.",
        "2. State the protected contract and its authority before proposing a change.",
        "3. Add the contract test first; the test must fail for the reason the change addresses.",
        "4. Keep customization inside the declared variation seam.",
        "5. Treat a protected-contract change as a return from A3 to A1, not as maintenance.",
        "6. Record evidence, rollback, and the retirement trigger with the change.",
        "",
        "## Evidence base",
        "",
        "| Record | Pattern | Review priority | Cue hits | Files | Evidence |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in selected:
        lines.append(
            f"| {item['id']} | {item['name']} | {item['priority']} | {item['hits']} | "
            f"{item['files']} | E1 retrieval cue |"
        )
    lines.append("")
    lines.append("E1 is retrieval only. Promote a record to E2 only after reading the source and identifying roles and control flow; promote to E3 only with executable or contract support.")
    lines.append("")
    lines.append("## Protected responsibilities")
    lines.append("")
    for item in selected:
        record = lookup[item["id"]]
        lines.extend([
            f"### {item['id']} — {item['name']}",
            "",
            f"**Observed signal.** {item['hits']} cue hits across {item['files']} files. Representative location: "
            + (f"`{item['matches'][0]['file']}:{item['matches'][0]['line']}`." if item["matches"] else "none."),
            "",
            "**Pointcut to confirm.**",
            "",
            f"- Context: {record['pointcut']['context']}",
            f"- Trigger: {record['pointcut']['trigger']}",
            f"- Structure: {record['pointcut']['structure']}",
            f"- Effect: {record['pointcut']['effect']}",
            "",
            "**Protected contract.**",
            "",
            f"- Requires: {record['requires']}",
            f"- Ensures: {record['ensures']}",
            f"- Invariant: {record['invariant']}",
            f"- Violation: {record['violation']}",
            "",
            "**Permitted variation.** " + record["variation"],
            "",
            "**Negative control.** " + record["negative_control"],
            "",
            "**Test obligation.** " + record["test_obligation"],
            "",
            "**Evolution question.** " + record["evolution_question"],
            "",
            "**Proposed change.** _To be completed by the reviewing agent after source inspection._",
            "",
            "**Authority and rollback.** _Name who may approve the change, the rollback point, and the condition that retires the mechanism._",
            "",
        ])
    lines.extend([
        "## Change sequence",
        "",
        "1. **Baseline.** Run the harness's existing tests and capture the trace or outcome used for comparison.",
        "2. **Contract tests.** Add the tests named above, including the negative control.",
        "3. **Seam.** Implement behind the declared variation seam; do not move authority silently.",
        "4. **Canary.** Exercise one real task and compare cost, failure handling, and termination.",
        "5. **Record.** Update the pattern record with evidence level, files, test links, and remaining unknowns.",
        "",
        "## Verification gates",
        "",
        "- [ ] The negative control stays unmatched.",
        "- [ ] Each contract field maps to code, a test, or an explicit runtime check.",
        "- [ ] Failure and termination paths are exercised, not just the happy path.",
        "- [ ] The change stays inside the permitted variation; contract changes have named authority.",
        "- [ ] The record is updated from E1 to the evidence level actually demonstrated.",
        "- [ ] A rollback path and retirement trigger are recorded.",
        "",
        "## Record update template",
        "",
        "```yaml",
        "record: " + selected[0]["id"],
        "repository: " + scan_result["root"],
        "evidence_level: E1  # change only with source or executable support",
        "protected_contract:",
        "  requires: " + lookup[selected[0]["id"]]["requires"],
        "  ensures: " + lookup[selected[0]["id"]]["ensures"],
        "  invariant: " + lookup[selected[0]["id"]]["invariant"],
        "  violation: " + lookup[selected[0]["id"]]["violation"],
        "variation: " + lookup[selected[0]["id"]]["variation"],
        "negative_control: " + lookup[selected[0]["id"]]["negative_control"],
        "authority: TBD",
        "evidence: TBD",
        "rollback: TBD",
        "retirement_trigger: TBD",
        "```",
        "",
        "_Generated by pohe-agent. The plan is a proposal; it is not evidence that any change was implemented or verified._",
        "",
    ])
    return "\n".join(lines)
