#!/usr/bin/env python3
"""Compare pohe-agent cue retrieval with a frozen study matrix.

The study's matrix records, for each pattern and repository, whether the
frozen detector retrieved at least one cue (``current_cue_present``). This
script walks the same repository checkouts with the agent's surface rules,
applies the agent's frozen cue set, and reports cell-level agreement plus
every disagreement.

Example:
    python tools/reproduce_study_matrix.py \
        --cache-dir ../pattern-mining-study/.cache/repositories \
        --manifest ../pattern-mining-study/data/manifests/current_41_repositories.csv \
        --matrix ../pattern-mining-study/data/derived/pattern_repo_full_matrix.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pohe_agent.walk import read_text, walk_repository  # noqa: E402

CUES: dict[str, re.Pattern[str]] = {}


def init_cues() -> None:
    from pohe_agent.catalog import load_catalog, records

    global CUES
    CUES = {record["id"]: re.compile(record["regex"]) for record in records(load_catalog())}


def scan_presence(root: Path, max_files: int) -> dict:
    files, skipped = walk_repository(root, max_files=max_files)
    present = {pattern_id: False for pattern_id in CUES}
    first: dict[str, dict] = {}
    for source in files:
        text = read_text(source.path)
        if text is None:
            continue
        for pattern_id, regex in CUES.items():
            if present[pattern_id]:
                continue
            found = regex.search(text)
            if found:
                present[pattern_id] = True
                first[pattern_id] = {
                    "file": source.rel,
                    "line": text.count("\n", 0, found.start()) + 1,
                    "kind": source.kind,
                    "text": " ".join(found.group(0).split())[:160],
                }
    return {
        "present": present,
        "files_scanned": len(files),
        "code": sum(1 for item in files if item.kind == "code"),
        "test": sum(1 for item in files if item.kind == "test"),
        "support": sum(1 for item in files if item.kind == "support"),
        "skipped": len(skipped),
        "first_match": first,
    }


def head_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def load_manifest(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as handle:
        return {row["repo_id"]: row for row in csv.DictReader(handle)}


def load_matrix(path: Path) -> dict[tuple[str, str], bool]:
    matrix: dict[tuple[str, str], bool] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            matrix[(row["candidate_id"], row["repo_slug"])] = (
                row["current_cue_present"].strip().lower() == "true"
            )
    return matrix


def summarize(cells: list[dict]) -> dict:
    agree = sum(1 for cell in cells if cell["study"] == cell["agent"])
    study_positive = sum(1 for cell in cells if cell["study"])
    agent_positive = sum(1 for cell in cells if cell["agent"])
    both = sum(1 for cell in cells if cell["study"] and cell["agent"])
    union = study_positive + agent_positive - both
    only_study = [cell for cell in cells if cell["study"] and not cell["agent"]]
    only_agent = [cell for cell in cells if cell["agent"] and not cell["study"]]
    by_pattern: dict[str, dict] = {}
    for cell in cells:
        bucket = by_pattern.setdefault(
            cell["pattern"],
            {"cells": 0, "agree": 0, "study": 0, "agent": 0, "only_study": 0, "only_agent": 0},
        )
        bucket["cells"] += 1
        bucket["agree"] += cell["study"] == cell["agent"]
        bucket["study"] += cell["study"]
        bucket["agent"] += cell["agent"]
        bucket["only_study"] += cell["study"] and not cell["agent"]
        bucket["only_agent"] += cell["agent"] and not cell["study"]
    return {
        "cells_compared": len(cells),
        "agreement": agree / len(cells) if cells else 0.0,
        "study_positive": study_positive,
        "agent_positive": agent_positive,
        "both_positive": both,
        "jaccard": both / union if union else 1.0,
        "precision": both / agent_positive if agent_positive else 1.0,
        "recall": both / study_positive if study_positive else 1.0,
        "only_study": only_study,
        "only_agent": only_agent,
        "by_pattern": by_pattern,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reproduction-report.json"))
    parser.add_argument("--max-files", type=int, default=0, help="0 keeps every candidate")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    matrix = load_matrix(args.matrix)
    started = time.time()
    repositories: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=max(1, args.jobs), initializer=init_cues) as pool:
        futures = {}
        for repo_id, row in sorted(manifest.items()):
            checkout = args.cache_dir / repo_id.replace(":", "_")
            if not checkout.is_dir():
                print(f"missing checkout: {checkout}", file=sys.stderr)
                continue
            futures[pool.submit(scan_presence, checkout, args.max_files)] = (repo_id, row, checkout)
        for future in as_completed(futures):
            repo_id, row, checkout = futures[future]
            result = future.result()
            result.update(
                repo_id=repo_id,
                slug=row["slug"],
                manifest_commit=row["commit_sha"],
                checkout_commit=head_commit(checkout),
            )
            repositories[repo_id] = result
            print(
                f"{row['slug']}: {result['files_scanned']} files, "
                f"{sum(result['present'].values())}/52 cues, "
                f"{time.time() - started:.0f}s",
                flush=True,
            )

    cells = []
    for (pattern_id, slug), expected in sorted(matrix.items()):
        result = next((item for item in repositories.values() if item["slug"] == slug), None)
        if result is None:
            continue
        cells.append(
            {
                "pattern": pattern_id,
                "repo": slug,
                "study": expected,
                "agent": result["present"].get(pattern_id, False),
            }
        )
    summary = summarize(cells)
    report = {
        "tool": "pohe-agent",
        "corpus": {
            "manifest": str(args.manifest),
            "matrix": str(args.matrix),
            "repositories": len(repositories),
            "checkout_commit_mismatches": [
                {"repo": item["slug"], "manifest": item["manifest_commit"], "checkout": item["checkout_commit"]}
                for item in repositories.values()
                if item["checkout_commit"] and item["checkout_commit"] != item["manifest_commit"]
            ],
        },
        **summary,
        "repositories": repositories,
        "cells": cells,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "cells_compared", "agreement", "study_positive", "agent_positive",
        "both_positive", "jaccard", "precision", "recall")}, indent=2))
    print(f"only study: {len(summary['only_study'])}  only agent: {len(summary['only_agent'])}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
