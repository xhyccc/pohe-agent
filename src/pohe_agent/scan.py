"""Lexical retrieval of POHE pattern cues in an arbitrary repository."""
from __future__ import annotations

import re
from pathlib import Path

from .catalog import load_catalog, records
from .walk import SourceFile, read_text, walk_repository

MAX_HITS_PER_PATTERN = 400
MAX_LINES_PER_FILE = 12
MAX_MATCHES_IN_REPORT = 12


def compile_cues(catalog: dict) -> dict[str, re.Pattern[str]]:
    compiled: dict[str, re.Pattern[str]] = {}
    for record in records(catalog):
        try:
            compiled[record["id"]] = re.compile(record["regex"])
        except re.error as exc:  # pragma: no cover - data is frozen and validated
            raise ValueError(f"invalid cue for {record['id']}: {exc}") from exc
    return compiled


def scan_lines(
    lines: list[str], rel: str, kind: str, regex: re.Pattern[str], budget: int
) -> tuple[int, list[dict]]:
    total = 0
    matches: list[dict] = []
    for number, line in enumerate(lines, start=1):
        found = list(regex.finditer(line))
        if not found:
            continue
        total += len(found)
        if len(matches) < MAX_LINES_PER_FILE:
            snippet = " ".join(line.strip().split())
            matches.append({"file": rel, "line": number, "text": snippet[:180], "kind": kind})
        if total >= budget:
            break
    return total, matches


def scan_file(path: SourceFile, regex: re.Pattern[str], budget: int) -> tuple[int, list[dict]]:
    text = read_text(path.path)
    if text is None:
        return 0, []
    return scan_lines(text.splitlines(), path.rel, path.kind, regex, budget)


def priority(code_files: int, test_files: int, hits: int) -> str:
    if code_files >= 2 and test_files >= 1 and hits >= 3:
        return "high"
    if code_files >= 1 and hits >= 2:
        return "medium"
    return "low"


def scan_repository(root: Path, catalog: dict | None = None, max_files: int = 0) -> dict:
    catalog = catalog or load_catalog()
    compiled = compile_cues(catalog)
    files, skipped = walk_repository(root, max_files=max_files)
    state = {
        record["id"]: {
            "regex": compiled[record["id"]],
            "hits": 0,
            "matches": [],
            "kinds": {"code": 0, "test": 0, "support": 0},
            "files": set(),
        }
        for record in records(catalog)
    }
    for source in files:
        text = read_text(source.path)
        if text is None:
            continue
        lines = text.splitlines()
        for pattern_id, item in state.items():
            if item["hits"] >= MAX_HITS_PER_PATTERN:
                continue
            count, found = scan_lines(
                lines, source.rel, source.kind, item["regex"],
                MAX_HITS_PER_PATTERN - item["hits"],
            )
            if count:
                item["hits"] += count
                item["files"].add(source.rel)
                item["kinds"][source.kind] = item["kinds"].get(source.kind, 0) + 1
                item["matches"].extend(found)
    result_patterns = []
    for record in records(catalog):
        item = state[record["id"]]
        hits = item["hits"]
        matches = item["matches"]
        kinds = item["kinds"]
        observed = hits > 0
        matches.sort(key=lambda item: ({"code": 0, "test": 1, "support": 2}.get(item["kind"], 3), item["file"], item["line"]))
        top_match = next((item for item in matches if item["kind"] == "code"), matches[0] if matches else None)
        top = top_match["file"] if top_match else ""
        result_patterns.append({
            "id": record["id"],
            "name": record["name"],
            "family": record["family"],
            "activity": record["activities"],
            "status": "observed" if observed else "not_observed",
            "evidence_level": "E1" if observed else "none",
            "priority": priority(kinds["code"], kinds["test"], hits) if observed else "none",
            "hits": hits,
            "files": len(item["files"]),
            "code_files": kinds["code"],
            "test_files": kinds["test"],
            "support_files": kinds["support"],
            "matches": matches[:MAX_MATCHES_IN_REPORT],
            "truncated": len(matches) > MAX_MATCHES_IN_REPORT or hits > len(matches),
            "join_point": record["join_point"],
            "contract": {
                "requires": record["requires"],
                "ensures": record["ensures"],
                "invariant": record["invariant"],
                "violation": record["violation"],
            },
            "negative_control": record["negative_control"],
            "next_step": (
                f"Inspect {top} against the four pointcut dimensions and the contract; "
                "apply the negative control before calling it an implementation."
                if observed else
                "No cue retrieved. Check for the mechanism under different vocabulary before treating it as absent."
            ),
        })
    observed = [item for item in result_patterns if item["status"] == "observed"]
    family_counts = {}
    for item in result_patterns:
        bucket = family_counts.setdefault(item["family"], {"observed": 0, "total": 0})
        bucket["total"] += 1
        if item["status"] == "observed":
            bucket["observed"] += 1
    return {
        "schema_version": "1.0.0",
        "tool": "pohe-agent",
        "root": str(root.resolve()),
        "corpus": {
            "files_scanned": len(files),
            "code": sum(1 for f in files if f.kind == "code"),
            "test": sum(1 for f in files if f.kind == "test"),
            "support": sum(1 for f in files if f.kind == "support"),
            "skipped": skipped[:50],
        },
        "summary": {
            "records": len(result_patterns),
            "observed": len(observed),
            "not_observed": len(result_patterns) - len(observed),
            "high_priority": sum(1 for item in observed if item["priority"] == "high"),
            "by_family": family_counts,
        },
        "patterns": result_patterns,
    }
