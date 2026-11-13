"""Structural candidate extraction for source-level POHE matching."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from .catalog import load_catalog, select
from .walk import CODE_EXTENSIONS, SourceFile, read_text, walk_repository

DECLARATION = re.compile(
    r"\b(?:def|class|function|func|fn|interface|struct|trait|impl|type|enum)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)"
)
NON_PYTHON_CODE = CODE_EXTENSIONS - {".py", ".pyi"}


@dataclass(frozen=True)
class Symbol:
    name: str
    line: int
    kind: str


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def python_symbols(text: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(Symbol(node.name, node.lineno, "function"))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(node.name, node.lineno, "class"))
    return symbols


def declaration_symbols(text: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "*", "/*")):
            continue
        for match in DECLARATION.finditer(line):
            symbols.append(Symbol(match.group(1), number, "declaration"))
    return symbols


def symbols_for(path: SourceFile) -> list[Symbol]:
    text = read_text(path.path)
    if text is None:
        return []
    if path.path.suffix.lower() in {".py", ".pyi"}:
        return python_symbols(text)
    if path.path.suffix.lower() in NON_PYTHON_CODE:
        return declaration_symbols(text)
    return []


def candidate_reason(record: dict, symbol: Symbol, regex: re.Pattern[str]) -> str:
    if regex.search(symbol.name):
        return "cue in symbol name"
    normal = normalize(symbol.name)
    for alias in record["aliases"]:
        alias_normal = normalize(alias)
        if len(alias_normal) >= 8 and alias_normal in normal:
            return f"alias {alias!r} in symbol name"
    return ""


def match_repository(
    root: Path,
    catalog: dict | None = None,
    pattern_spec: str | None = None,
    max_files: int = 0,
) -> dict:
    catalog = catalog or load_catalog()
    selected = select(catalog, pattern_spec)
    files, skipped = walk_repository(root, max_files=max_files)
    symbols: list[tuple[SourceFile, Symbol]] = []
    for source in files:
        for symbol in symbols_for(source):
            symbols.append((source, symbol))
    compiled = {record["id"]: re.compile(record["regex"]) for record in selected}
    results = []
    for record in selected:
        regex = compiled[record["id"]]
        candidates = []
        for source, symbol in symbols:
            reason = candidate_reason(record, symbol, regex)
            if reason:
                candidates.append({
                    "file": source.rel,
                    "line": symbol.line,
                    "symbol": symbol.name,
                    "kind": symbol.kind,
                    "reason": reason,
                })
        results.append({
            "id": record["id"],
            "name": record["name"],
            "family": record["family"],
            "join_point": record["join_point"],
            "pointcut": record["pointcut"],
            "contract": {
                "requires": record["requires"],
                "ensures": record["ensures"],
                "invariant": record["invariant"],
                "violation": record["violation"],
            },
            "negative_control": record["negative_control"],
            "test_obligation": record["test_obligation"],
            "candidates": candidates,
            "questions": [
                f"Context: does the candidate operate in the stated context — {record['pointcut']['context']}",
                f"Trigger: is it activated by the stated trigger — {record['pointcut']['trigger']}",
                f"Structure: are the required roles and state present — {record['pointcut']['structure']}",
                f"Effect: is the stated effect observable — {record['pointcut']['effect']}",
                f"Requires: {record['requires']}",
                f"Ensures: {record['ensures']}",
                f"Invariant: {record['invariant']}",
                f"Violation: {record['violation']}",
                f"Negative control: {record['negative_control']}",
            ],
        })
    return {
        "schema_version": "1.0.0",
        "tool": "pohe-agent",
        "root": str(root.resolve()),
        "corpus": {
            "files_scanned": len(files),
            "symbols_extracted": len(symbols),
            "skipped": skipped[:50],
        },
        "patterns": results,
    }
