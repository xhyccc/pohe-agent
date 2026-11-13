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
    end_line: int = 0


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
            symbols.append(Symbol(node.name, node.lineno, "function", node.end_lineno or node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(node.name, node.lineno, "class", node.end_lineno or node.lineno))
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


def symbols_from_text(path: SourceFile, text: str) -> list[Symbol]:
    if path.path.suffix.lower() in {".py", ".pyi"}:
        return python_symbols(text)
    if path.path.suffix.lower() in NON_PYTHON_CODE:
        return declaration_symbols(text)
    return []


def symbols_for(path: SourceFile) -> list[Symbol]:
    text = read_text(path.path)
    if text is None:
        return []
    return symbols_from_text(path, text)


def candidate_reason(
    record: dict, symbol: Symbol, regex: re.Pattern[str], body: str
) -> str:
    if regex.search(symbol.name):
        return "cue in symbol name"
    normal = normalize(symbol.name)
    for alias in record["aliases"]:
        alias_normal = normalize(alias)
        if len(alias_normal) >= 8 and alias_normal in normal:
            return f"alias {alias!r} in symbol name"
    if body and regex.search(body):
        return "cue in symbol body"
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
    compiled = {record["id"]: re.compile(record["regex"]) for record in selected}
    candidates_by_pattern: dict[str, list[dict]] = {record["id"]: [] for record in selected}
    symbol_count = 0
    for source in files:
        text = read_text(source.path)
        if text is None:
            continue
        lines = text.splitlines()
        for symbol in symbols_from_text(source, text):
            symbol_count += 1
            body = (
                "\n".join(lines[symbol.line - 1:symbol.end_line])
                if symbol.end_line > symbol.line
                else ""
            )
            for record in selected:
                reason = candidate_reason(record, symbol, compiled[record["id"]], body)
                if reason:
                    candidates_by_pattern[record["id"]].append({
                        "file": source.rel,
                        "line": symbol.line,
                        "symbol": symbol.name,
                        "kind": symbol.kind,
                        "reason": reason,
                    })
    results = []
    for record in selected:
        candidates = sorted(
            candidates_by_pattern[record["id"]],
            key=lambda item: (
                0 if item["reason"] != "cue in symbol body" else 1,
                item["file"], item["line"], item["symbol"],
            ),
        )
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
            "symbols_extracted": symbol_count,
            "skipped": skipped[:50],
        },
        "patterns": results,
    }
