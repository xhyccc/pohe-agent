#!/usr/bin/env python3
"""Audit the frozen catalog against its own canonical exemplars.

For each of the 52 records, this tool asks three separable questions:

1. Retrieval: does either the frozen cue or a signature cue reach the canonical
   file, and does a hit fall in the anchored scope?
2. Anchoring: which declaration contains the canonical line (function, method,
   class, file)?
3. Structure: which operational-signature roles are visible in that scope?

The output is a calibration report, not a quality score. A canonical anchor is
one locating example, not a population estimate, and some anchors are
declarations, prompts, or configuration rather than full implementations. A
gap here means the pointcut, the exemplar, or the signature needs review; it
does not mean the pattern is absent from the repository.

Usage:
    python tools/audit_canonical.py \
      --cache-dir ../pattern-mining-study/.cache/repositories \
      --manifest ../pattern-mining-study/data/manifests/current_41_repositories.csv \
      --markdown docs/calibration.md --json calibration.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from pohe_agent.analyze import (  # noqa: E402
    VERDICT_ORDER,
    check_negative_control,
    compile_cue,
    decide_verdict,
    evaluate_dimensions,
)
from pohe_agent.catalog import load_catalog  # noqa: E402
from pohe_agent.features import (  # noqa: E402
    evaluate_tags,
    extract_facts,
    extract_scopes,
    line_modality,
    scope_for_line,
)
from pohe_agent.signatures import for_record, load_signatures  # noqa: E402
from pohe_agent.walk import classify  # noqa: E402

DIMENSIONS = ("context", "trigger", "structure", "effect")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PACKAGE_ROOT.parent / "pattern-mining-study/.cache/repositories",
        help="directory holding one checkout per repo_id",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PACKAGE_ROOT.parent / "pattern-mining-study/data/manifests/current_41_repositories.csv",
        help="manifest with repo_id, canonical_url, and commit_sha",
    )
    parser.add_argument("--json", type=Path, help="write the full audit as JSON")
    parser.add_argument("--markdown", type=Path, help="write a readable report")
    parser.add_argument(
        "--pattern",
        help="comma-separated record ids or families (default: every record with a canonical anchor)",
    )
    return parser.parse_args()


def canonical_path(anchor: dict) -> tuple[str, int]:
    path, _, line = anchor["implementation"].rpartition(":")
    return path.lstrip("./"), int(line)


def hits_for(text: str, record: dict, signature: dict) -> tuple[list[dict], list[str]]:
    """Return cue hits with their source labels, deduplicated by line."""
    cues = [("lexical", compile_cue(record["regex"]))]
    cues.extend(("operational", compile_cue(cue)) for cue in signature.get("cues", []))
    hits: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for source, regex in cues:
        for match in regex.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            line = text.splitlines()[line_number - 1] if line_number else ""
            key = (line_number, source)
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                "line": line_number,
                "text": " ".join(line.strip().split())[:180],
                "modality": line_modality(line),
                "cue": source,
            })
    return hits, sorted({hit["cue"] for hit in hits})


def audit_record(record: dict, checkout: Path, signature: dict) -> dict:
    rel, line = canonical_path(record["canonical"])
    path = checkout / rel
    row = {
        "id": record["id"],
        "name": record["name"],
        "repo": record["canonical"]["repo"],
        "file": rel,
        "line": line,
        "found": False,
        "scope_kind": "missing",
        "scope_name": "",
        "frozen_hits": 0,
        "operational_hits": 0,
        "cue_sources": [],
        "verdict": None,
        "missing": [],
        "dimension_status": {},
        "source_kind": "missing",
        "negative_control": "unknown",
    }
    if not path.is_file():
        row["gaps"] = ["anchor_missing"]
        return row
    text = path.read_text(encoding="utf-8", errors="replace")
    hits, cue_sources = hits_for(text, record, signature)
    row["frozen_hits"] = sum(1 for hit in hits if hit["cue"] == "lexical")
    row["operational_hits"] = sum(1 for hit in hits if hit["cue"] == "operational")
    row["cue_sources"] = cue_sources
    row["found"] = bool(hits)
    source_kind = classify(rel, path.suffix.lower())
    row["source_kind"] = source_kind
    scopes = extract_scopes(text, rel, path.suffix.lower())
    scope = scope_for_line(scopes, line)
    if scope is None:
        row["gaps"] = ["anchor_missing"]
        return row
    scope_hits = [hit for hit in hits if scope.start <= hit["line"] <= scope.end]
    scope_text = "\n".join(
        text.splitlines()[scope.start - 1:min(len(text.splitlines()), scope.start - 1 + 1200)]
    )
    facts = extract_facts(scope_text, scope, path.suffix.lower())
    tags = evaluate_tags(facts)
    dimensions = evaluate_dimensions(signature, tags, facts, scope, source_kind, scope_hits)
    negative = check_negative_control(signature, tags, facts)
    verdict = decide_verdict(dimensions, negative, source_kind, scope)
    row.update({
        "scope_kind": scope.kind,
        "scope_name": scope.name,
        "scope_hits": len(scope_hits),
        "verdict": verdict,
        "missing": dimensions["structure"]["missing"],
        "dimension_status": {key: dimensions[key]["status"] for key in DIMENSIONS},
        "negative_control": negative["status"],
    })
    row["gaps"] = classify_gaps(row)
    return row


def classify_gaps(row: dict) -> list[str]:
    gaps: list[str] = []
    if not row["found"]:
        gaps.append("retrieval_gap")
        return gaps
    if row["frozen_hits"] == 0 and row["operational_hits"]:
        gaps.append("frozen_cue_miss")
    if not row.get("scope_hits"):
        gaps.append("hit_outside_scope")
    if row["scope_kind"] == "file" or row["source_kind"] != "code":
        gaps.append("anchor_gap")
    if row["missing"]:
        gaps.append("structure_gap")
    if row["dimension_status"].get("context") == "contradicted":
        gaps.append("context_gap")
    if row["dimension_status"].get("trigger") == "contradicted":
        gaps.append("trigger_gap")
    if row["negative_control"] == "risk":
        gaps.append("negative_control_risk")
    return gaps


def summarize(rows: list[dict]) -> dict:
    audited = [row for row in rows if "anchor_missing" not in row["gaps"]]
    return {
        "records": len(rows),
        "audited": len(audited),
        "retrieved": sum(1 for row in audited if row["found"]),
        "retrieval_gap": sum(1 for row in audited if "retrieval_gap" in row["gaps"]),
        "frozen_cue_miss": sum(1 for row in audited if "frozen_cue_miss" in row["gaps"]),
        "hit_outside_scope": sum(1 for row in audited if "hit_outside_scope" in row["gaps"]),
        "anchor_gap": sum(1 for row in audited if "anchor_gap" in row["gaps"]),
        "structure_gap": sum(1 for row in audited if "structure_gap" in row["gaps"]),
        "negative_control_risk": sum(
            1 for row in audited if "negative_control_risk" in row["gaps"]
        ),
        **{
            verdict: sum(1 for row in audited if row["verdict"] == verdict)
            for verdict in VERDICT_ORDER
        },
        "anchor_missing": len(rows) - len(audited),
    }


def render_markdown(rows: list[dict], summary: dict) -> str:
    lines = [
        "# Canonical calibration audit",
        "",
        "This report checks each frozen record against the one canonical example",
        "stored in the catalog. It separates retrieval, anchor scope, and",
        "structural coverage. A gap is a review signal about the pointcut, the",
        "exemplar, or the operational signature; it is not a prevalence estimate.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Records audited | {summary['audited']} |",
        f"| Canonical anchor retrieved | {summary['retrieved']} |",
        f"| Retrieval gaps | {summary['retrieval_gap']} |",
        f"| Frozen cue missed, operational cue recovered | {summary['frozen_cue_miss']} |",
        f"| Cue hit did not enter the anchored scope | {summary['hit_outside_scope']} |",
        f"| Anchor is a file or non-code unit | {summary['anchor_gap']} |",
        f"| Structure roles missing | {summary['structure_gap']} |",
        f"| Negative-control risk | {summary['negative_control_risk']} |",
        f"| `source_matched` | {summary['source_matched']} |",
        f"| `pointcut_candidate` | {summary['pointcut_candidate']} |",
        f"| `structural_candidate` | {summary['structural_candidate']} |",
        f"| `cue_only` | {summary['cue_only']} |",
        f"| `rejected` | {summary['rejected']} |",
        f"| Anchor missing | {summary['anchor_missing']} |",
        "",
        "## Records",
        "",
        "| Record | Anchor | Scope | Cue hits | Verdict | Missing roles | Gaps |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: item["id"]):
        anchor = f"`{row['file']}:{row['line']}`"
        scope = row["scope_kind"] + (f" `{row['scope_name']}`" if row["scope_name"] else "")
        cue = f"{row['frozen_hits']} frozen / {row['operational_hits']} operational"
        if row.get("scope_hits") is not None:
            cue += f" / {row['scope_hits']} in scope"
        missing = ", ".join(row.get("missing", [])) or "—"
        verdict = row["verdict"] or "not retrieved"
        gaps = ", ".join(row.get("gaps", [])) or "—"
        lines.append(
            f"| {row['id']} | {anchor} | {scope} | {cue} | `{verdict}` | {missing} | {gaps} |"
        )
    lines.extend(["", "## Review queue", ""])
    queues = [
        ("Frozen cue missed its own exemplar (operational cue recovered)", "frozen_cue_miss"),
        ("Anchor is a file or non-code unit", "anchor_gap"),
        ("Negative control fires on the anchor", "negative_control_risk"),
        ("Structure roles missing", "structure_gap"),
        ("Cue hit outside the anchored declaration", "hit_outside_scope"),
    ]
    for title, gap in queues:
        ids = [row["id"] for row in sorted(rows, key=lambda item: item["id"]) if gap in row.get("gaps", [])]
        lines.append(f"- **{title}** ({len(ids)}): {', '.join(ids) if ids else '—'}")
    lines.extend([
        "",
        "## How to read a gap",
        "",
        "- **retrieval_gap** — neither cue family reaches the canonical file.",
        "- **frozen_cue_miss** — the frozen regex does not match its own exemplar,",
        "  but a signature cue does. This is a catalog/vocabulary disagreement.",
        "- **hit_outside_scope** — a cue is present in the file but not in the",
        "  declaration that contains the canonical line. The anchor and the cue",
        "  point at different evidence units.",
        "- **anchor_gap** — the anchor is a file, declaration, prompt, or",
        "  configuration. It can locate the record but cannot evidence a full",
        "  implementation.",
        "- **structure_gap** — the anchor scope lacks signature roles. Treat it as",
        "  a question: is the pointcut too strong, the anchor partial, or the",
        "  signature too strict?",
        "- **negative_control_risk** — the anchor scope matches the record's own",
        "  contrast. Inspect before treating the anchor as an exemplar.",
        "",
        "## Method",
        "",
        "The audit anchors the canonical line to the smallest enclosing scope,",
        "then runs the same dimension, negative-control, and verdict logic as",
        "`analyze`. Retrieval applies the frozen regex plus any operational cues",
        "stored with the signature; both use identifier-aware boundaries so",
        "snake_case and camelCase identifiers match their token forms. This is a",
        "direct exemplar check, not a repository-wide ranking.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    catalog = load_catalog()
    signatures = load_signatures()
    if args.pattern:
        wanted = {item.strip() for item in args.pattern.split(",") if item.strip()}
        records = [
            record
            for record in catalog["patterns"]
            if record.get("canonical")
            and (record["id"] in wanted or record["family"] in wanted)
        ]
    else:
        records = [record for record in catalog["patterns"] if record.get("canonical")]
    manifest = list(csv.DictReader(args.manifest.open(encoding="utf-8")))
    by_url = {row["canonical_url"].lower().rstrip("/"): row for row in manifest}
    rows: list[dict] = []
    for record in records:
        url = ("https://github.com/" + record["canonical"]["repo"]).lower().rstrip("/")
        manifest_row = by_url.get(url)
        checkout = (
            args.cache_dir / manifest_row["repo_id"].replace(":", "_")
            if manifest_row
            else None
        )
        signature = for_record(signatures, record["id"])
        if checkout is None or not checkout.is_dir():
            rows.append({
                "id": record["id"],
                "name": record["name"],
                "repo": record["canonical"]["repo"],
                "file": canonical_path(record["canonical"])[0],
                "line": canonical_path(record["canonical"])[1],
                "found": False,
                "scope_kind": "missing",
                "scope_name": "",
                "frozen_hits": 0,
                "operational_hits": 0,
                "cue_sources": [],
                "verdict": None,
                "missing": [],
                "dimension_status": {},
                "source_kind": "missing",
                "negative_control": "unknown",
                "gaps": ["checkout_missing"],
            })
            continue
        rows.append(audit_record(record, checkout, signature))
    summary = summarize(rows)
    payload = {"summary": summary, "records": rows}
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(rows, summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
