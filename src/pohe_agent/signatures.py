"""Load operational detection signatures for catalog records.

A signature is deliberately separate from the prose pointcut. The pointcut
states the design obligation; the signature states which observable roles a
scope must exhibit before the tool will call it a candidate. Keeping the two
apart makes a pointcut disagreement visible instead of silently changing the
matcher.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DIMENSIONS = ("context", "trigger", "structure", "effect")


def signatures_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "signatures.json"


def load_signatures(path: Path | None = None) -> dict:
    data = json.loads((path or signatures_path()).read_text(encoding="utf-8"))
    patterns = data.get("patterns", {})
    if not patterns:
        raise ValueError("signature file contains no patterns")
    for pattern_id, signature in patterns.items():
        for dimension in DIMENSIONS:
            tags = signature.get(dimension)
            if not isinstance(tags, list) or not tags:
                raise ValueError(f"{pattern_id}: {dimension} needs a non-empty tag list")
        if not isinstance(signature.get("negative", []), list):
            raise ValueError(f"{pattern_id}: negative must be a list")
        cues = signature.get("cues", [])
        if not isinstance(cues, list) or any(
            not isinstance(cue, str) or not cue.strip() for cue in cues
        ):
            raise ValueError(f"{pattern_id}: cues must be non-empty regex strings")
        for cue in cues:
            try:
                re.compile(cue)
            except re.error as error:
                raise ValueError(f"{pattern_id}: invalid cue {cue!r}: {error}") from error
    return data


def for_record(signatures: dict, record_id: str) -> dict:
    signature = signatures["patterns"].get(record_id)
    if signature is None:
        raise KeyError(f"missing operational signature for {record_id}")
    return signature
