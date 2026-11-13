#!/usr/bin/env python3
"""Export the frozen POHE record catalog into the agent's portable data file.

The study remains the source of truth. This script only selects and renames
fields so the scanner has no dependency on the website generator or the study
checkout at runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compact_record(record: dict) -> dict:
    source = next((anchor for anchor in record["anchors"] if anchor.get("kind") == "source"), None)
    canonical = None
    if source:
        canonical = {
            "repo": source["repo_slug"],
            "commit": source["commit_sha"],
            "implementation": source["implementation"],
            "support": source.get("support", ""),
            "url": source["url"],
            "support_url": source.get("support_url", ""),
            "note": source.get("note", ""),
        }
    return {
        "id": record["id"],
        "name": record["name"],
        "family": record["family"],
        "family_name": record["family_name"],
        "activities": record["activities"],
        "problem": record["problem"],
        "join_point": record["join_point"],
        "pointcut": record["pointcut"],
        "requires": record["requires"],
        "ensures": record["ensures"],
        "invariant": record["invariant"],
        "violation": record["violation"],
        "variation": record["variation"],
        "test_obligation": record["test_obligation"],
        "negative_control": record["negative_control"],
        "evolution_question": record["evolution_question"],
        "aliases": record["aliases"],
        "regex": record["retrieval_cue"]["regex"],
        "regex_version": record["retrieval_cue"]["version"],
        "source_locator": record["source_locator"],
        "evidence_status": record["evidence"]["status"],
        "canonical": canonical,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="pohe-site data/patterns.json")
    parser.add_argument("--out", type=Path, default=Path("src/pohe_agent/data/patterns.json"))
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    records = [compact_record(record) for record in catalog["patterns"]]
    families = {}
    for record in records:
        families.setdefault(record["family"], record["family_name"])
    payload = {
        "schema_version": "1.0.0",
        "title": "POHE harness design pattern catalog",
        "record_count": len(records),
        "source": {
            "study_revision": catalog.get("study_revision", ""),
            "spec_version": catalog.get("spec_version", ""),
            "method": "Frozen lexical cue plus pointcut and contract specification.",
        },
        "families": families,
        "patterns": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} records to {args.out}")


if __name__ == "__main__":
    main()
