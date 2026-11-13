"""Load and query the frozen POHE pattern catalog."""
from __future__ import annotations

import json
from pathlib import Path


def catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "patterns.json"


def load_catalog(path: Path | None = None) -> dict:
    target = path or catalog_path()
    data = json.loads(target.read_text(encoding="utf-8"))
    if len(data.get("patterns", [])) != 52:
        raise ValueError(f"expected 52 records, found {len(data.get('patterns', []))}")
    ids = [record["id"] for record in data["patterns"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate record identifiers in catalog")
    return data


def records(catalog: dict) -> list[dict]:
    return catalog["patterns"]


def by_id(catalog: dict) -> dict[str, dict]:
    return {record["id"]: record for record in catalog["patterns"]}


def select(catalog: dict, spec: str | None) -> list[dict]:
    """Select records by id, family, or comma-separated ids."""
    if not spec:
        return records(catalog)
    wanted = {token.strip() for token in spec.split(",") if token.strip()}
    selected = [
        record
        for record in records(catalog)
        if record["id"] in wanted or record["family"] in wanted
    ]
    unknown = wanted - {record["id"] for record in selected} - {record["family"] for record in selected}
    if unknown:
        raise SystemExit(f"unknown record or family: {', '.join(sorted(unknown))}")
    return selected
