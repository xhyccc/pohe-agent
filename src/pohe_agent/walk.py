"""Deterministic repository walking with the study's surface rules."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs", ".rs",
    ".go", ".java", ".kt", ".kts", ".rb", ".php", ".swift", ".scala", ".lua",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".m", ".mm",
}
TEST_EXTENSIONS = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs", ".rs", ".go", ".java", ".kt", ".rb"}
SUPPORT_EXTENSIONS = {".yaml", ".yml", ".toml", ".json", ".md", ".mdx", ".txt", ".cfg", ".ini", ".jsonc"}

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "dist",
    "build", "coverage", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "vendor", "vendored", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "site-packages", "Pods", "DerivedData",
}
EXCLUDED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock", ".DS_Store",
}
EXCLUDED_SUFFIXES = (".min.js", ".min.css", ".map", ".lock", ".snap")
MAX_BYTES = 2_000_000
KIND_PRIORITY = {"code": 0, "test": 1, "support": 2}


@dataclass(frozen=True)
class SourceFile:
    path: Path
    rel: str
    kind: str
    size: int


def classify(rel: str, suffix: str) -> str:
    lowered = rel.lower()
    parts = lowered.split("/")
    name = parts[-1]
    if suffix in CODE_EXTENSIONS and (
        "test" in parts
        or "/tests/" in f"/{lowered}"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    ):
        return "test"
    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in SUPPORT_EXTENSIONS:
        return "support"
    return "other"


def is_excluded(rel: str, name: str, suffix: str) -> bool:
    if name in EXCLUDED_NAMES or suffix in {".pyc", ".so", ".dylib", ".dll", ".exe", ".bin"}:
        return True
    if name.endswith(EXCLUDED_SUFFIXES):
        return True
    parts = set(rel.split("/"))
    return bool(parts & EXCLUDED_DIRS)


def walk_repository(root: Path, max_files: int = 0) -> tuple[list[SourceFile], list[str]]:
    """Return candidate files and paths skipped for size or decoding reasons.

    A ``max_files`` of 0 keeps every candidate. When a budget is given, it is
    applied after classification, keeping code first, then tests, then support
    material. Applying it during traversal lets a large docs, cassette, or data
    subtree exhaust the budget before the scanner ever reaches the source files,
    which would silently bias the report.
    """
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    candidates: list[SourceFile] = []
    skipped: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            path = Path(current) / filename
            rel = path.relative_to(root).as_posix()
            suffix = path.suffix.lower()
            if is_excluded(rel, filename, suffix):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size == 0 or size > MAX_BYTES:
                skipped.append(rel)
                continue
            kind = classify(rel, suffix)
            if kind == "other":
                continue
            candidates.append(SourceFile(path=path, rel=rel, kind=kind, size=size))
    candidates.sort(key=lambda item: (KIND_PRIORITY[item.kind], item.rel))
    if max_files and len(candidates) > max_files:
        skipped.append(
            f"file limit reached at {max_files}: kept {max_files} of "
            f"{len(candidates)} candidates (code first, then tests, then support)"
        )
        candidates = candidates[:max_files]
    return candidates, skipped


def read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")
