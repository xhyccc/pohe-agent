"""Scope anchoring and structural feature extraction for pattern analysis.

The analyzer does not treat a file-level cue as a match. It anchors each cue to
the smallest enclosing declaration, extracts observable facts from that scope,
and then asks which roles the catalog's pointcut actually requires. The facts
are deliberately shallow: control flow, calls, parameters, assignments, and
identifier vocabulary. They support review; they do not prove semantics.
"""
from __future__ import annotations

import ast
import re
import textwrap
from collections import Counter
from dataclasses import dataclass, field

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
DECLARATION = re.compile(
    r"\b(?:def|class|function|func|fn|interface|struct|trait|impl|type|enum|"
    r"module|namespace)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
)
ARROW_DECLARATION = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>"
)
METHOD_DECLARATION = re.compile(
    r"^\s*(?:public|private|protected|static|async|override|final|suspend|"
    r"virtual|internal|export|default|pub(?:\([^)]*\))?|\s)*"
    r"(?:[A-Za-z_$][A-Za-z0-9_$<>\[\],.? ]*\s+)?"
    r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^;]*\)\s*(?::[^{;]+)?\{"
)
NON_PYTHON = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs", ".rs", ".go",
    ".java", ".kt", ".kts", ".rb", ".php", ".swift", ".scala", ".lua",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".m", ".mm",
}
COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", ";")
KEYWORDS = {
    "if", "else", "elif", "for", "while", "return", "def", "class", "function",
    "func", "fn", "const", "let", "var", "new", "await", "async", "yield",
    "import", "from", "export", "default", "public", "private", "protected",
    "static", "try", "catch", "except", "finally", "raise", "throw", "switch",
    "case", "match", "with", "as", "in", "is", "not", "and", "or", "lambda",
    "true", "false", "none", "null", "undefined", "this", "self", "super",
}
MAX_SCOPE_LINES = 1200
SNIPPET_LIMIT = 3


@dataclass(frozen=True)
class Scope:
    rel: str
    start: int
    end: int
    name: str
    kind: str
    parent: str = ""

    @property
    def lines(self) -> int:
        return max(0, self.end - self.start + 1)

    def contains(self, line: int) -> bool:
        return self.start <= line <= self.end

    def label(self) -> str:
        return f"{self.name} [{self.kind}]"

    def to_dict(self) -> dict:
        return {
            "file": self.rel,
            "symbol": self.name,
            "scope_kind": self.kind,
            "start_line": self.start,
            "end_line": self.end,
            "parent": self.parent,
        }


@dataclass
class ScopeFacts:
    tokens: set[str] = field(default_factory=set)
    token_counts: Counter = field(default_factory=Counter)
    calls: set[str] = field(default_factory=set)
    params: set[str] = field(default_factory=set)
    assignments: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    bases: set[str] = field(default_factory=set)
    decorators: set[str] = field(default_factory=set)
    strings: list[str] = field(default_factory=list)
    syntax: set[str] = field(default_factory=set)
    counts: Counter = field(default_factory=Counter)
    signals: dict[str, list[str]] = field(default_factory=dict)
    parse: str = "none"

    def signal(self, name: str, text: str, line: int = 0) -> None:
        bucket = self.signals.setdefault(name, [])
        if len(bucket) >= SNIPPET_LIMIT:
            return
        snippet = " ".join(text.strip().split())
        if line:
            snippet = f"L{line}: {snippet}"
        bucket.append(snippet[:220])

    def add_token(self, value: str, count: int = 1) -> None:
        for part in split_identifier(value):
            if len(part) < 2 or part in KEYWORDS:
                continue
            self.tokens.add(part)
            self.token_counts[part] += count


def split_identifier(value: str) -> list[str]:
    spaced = CAMEL.sub(" ", value)
    return [part.lower() for part in re.split(r"[^A-Za-z0-9]+", spaced) if part]


def source_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in IDENT.finditer(text):
        tokens.update(split_identifier(match.group(0)))
    return tokens - KEYWORDS


def _python_scopes(text: str, rel: str) -> list[Scope]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    scopes: list[Scope] = []

    def visit(node: ast.AST, parents: list[tuple[str, str]]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_class = isinstance(child, ast.ClassDef)
                kind = "class" if is_class else (
                    "method" if any(parent_kind == "class" for parent_kind, _ in parents)
                    else "function"
                )
                starts = [child.lineno] + [item.lineno for item in getattr(child, "decorator_list", [])]
                scopes.append(Scope(
                    rel=rel,
                    start=min(starts),
                    end=child.end_lineno or child.lineno,
                    name=child.name,
                    kind=kind,
                    parent=".".join(name for _, name in parents),
                ))
                visit(child, parents + [(kind, child.name)])
            else:
                visit(child, parents)

    visit(tree, [])
    return scopes


def _line_blocks(lines: list[str], start: int) -> int:
    """Find a declaration's end using braces first, then indentation."""
    head = lines[start - 1]
    opening = head.count("{") - head.count("}")
    if "{" in head:
        depth = opening
        for number in range(start + 1, min(len(lines), start + MAX_SCOPE_LINES) + 1):
            line = lines[number - 1]
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                return number
        return min(len(lines), start + MAX_SCOPE_LINES)
    indent = len(head) - len(head.lstrip())
    for number in range(start + 1, min(len(lines), start + MAX_SCOPE_LINES) + 1):
        line = lines[number - 1]
        if not line.strip():
            continue
        current = len(line) - len(line.lstrip())
        if current <= indent:
            return number - 1
    return min(len(lines), start + MAX_SCOPE_LINES)


def _non_python_scopes(text: str, rel: str) -> list[Scope]:
    lines = text.splitlines()
    found: list[tuple[int, str, str]] = []
    for number, line in enumerate(lines, start=1):
        if line.strip().startswith(COMMENT_PREFIXES):
            continue
        match = DECLARATION.search(line) or ARROW_DECLARATION.search(line) or METHOD_DECLARATION.search(line)
        if not match:
            continue
        name = match.group(1)
        lower = line.lower()
        if name in KEYWORDS:
            continue
        kind = "class" if re.search(r"\b(class|interface|struct|trait|impl|enum|type)\b", lower) else "function"
        found.append((number, name, kind))
    scopes: list[Scope] = []
    for index, (start, name, kind) in enumerate(found):
        end = _line_blocks(lines, start)
        if index + 1 < len(found):
            end = min(end, found[index + 1][0] - 1)
        scopes.append(Scope(rel=rel, start=start, end=max(start, end), name=name, kind=kind))
    return scopes


def extract_scopes(text: str, rel: str, suffix: str) -> list[Scope]:
    total = max(1, text.count("\n") + 1)
    if suffix in {".py", ".pyi"}:
        scopes = _python_scopes(text, rel)
    elif suffix in NON_PYTHON:
        scopes = _non_python_scopes(text, rel)
    else:
        scopes = []
    scopes.append(Scope(rel=rel, start=1, end=total, name="<file>", kind="file"))
    scopes.sort(key=lambda item: (item.start, -item.end, item.kind != "file"))
    return scopes


def scope_for_line(scopes: list[Scope], line: int) -> Scope:
    containing = [scope for scope in scopes if scope.contains(line)]
    if not containing:
        return scopes[-1]
    containing.sort(key=lambda scope: (scope.lines, scope.kind == "file"))
    return containing[0]


def line_modality(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.startswith(COMMENT_PREFIXES):
        return "comment"
    return "code"


def _python_facts(text: str, scope: Scope) -> ScopeFacts:
    facts = ScopeFacts()
    dedented = textwrap.dedent(text)
    try:
        tree = ast.parse(dedented)
        facts.parse = "ast"
    except (SyntaxError, ValueError):
        return _regex_facts(text, scope)
    lines = dedented.splitlines()
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    def line_of(node: ast.AST) -> int:
        return scope.start + getattr(node, "lineno", 1) - 1

    def snippet(node: ast.AST) -> str:
        number = getattr(node, "lineno", 1)
        return lines[number - 1] if 0 < number <= len(lines) else ""

    def mark(name: str, node: ast.AST) -> None:
        facts.syntax.add(name)
        facts.counts[name] += 1
        facts.signal(name, snippet(node), line_of(node))

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.comprehension)):
            mark("loop", node)
        if isinstance(node, (ast.If, ast.IfExp, ast.Match)):
            mark("conditional", node)
        if isinstance(node, ast.Return):
            mark("return", node)
        if isinstance(node, ast.Raise):
            mark("raise", node)
        if isinstance(node, ast.Assert):
            mark("assert", node)
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            mark("yield", node)
        if isinstance(node, ast.Await):
            mark("await", node)
        if isinstance(node, ast.Break):
            mark("break", node)
        if isinstance(node, ast.Continue):
            mark("continue", node)
        if isinstance(node, ast.Try):
            mark("try", node)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            mark("with", node)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            mark("assignment", node)
            for target in _targets(node):
                facts.assignments.add(target)
                facts.add_token(target)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            facts.add_token(node.name)
            for decorator in node.decorator_list:
                name = _call_name(decorator) or _node_name(decorator)
                if name:
                    facts.decorators.add(name)
                    facts.add_token(name)
            for arg in list(node.args.args) + list(node.args.kwonlyargs) + list(node.args.posonlyargs):
                facts.params.add(arg.arg)
                facts.add_token(arg.arg)
        if isinstance(node, ast.ClassDef):
            facts.classes.add(node.name)
            facts.add_token(node.name)
            for base in node.bases:
                name = _node_name(base)
                if name:
                    facts.bases.add(name)
                    facts.add_token(name)
        if isinstance(node, ast.arg):
            facts.params.add(node.arg)
            facts.add_token(node.arg)
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name:
                facts.calls.add(name)
                facts.add_token(name)
                mark("call", node)
                if name in {"gather", "all", "race", "spawn", "map", "submit", "parallel"}:
                    mark("fanout", node)
                if name in {"reduce", "join", "merge", "collect", "aggregate"}:
                    mark("aggregate", node)
        if isinstance(node, ast.Name):
            facts.add_token(node.id)
        if isinstance(node, ast.Attribute):
            facts.add_token(node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            facts.strings.append(node.value[:200])
            for part in source_tokens(node.value):
                facts.tokens.add(part)
                facts.token_counts[part] += 1
        if isinstance(node, ast.keyword) and node.arg:
            facts.add_token(node.arg)
        if isinstance(node, ast.Name) and node.id == scope.name:
            facts.counts["recursion"] += 1
    if scope.name in facts.calls:
        facts.counts["recursion"] += 1
        facts.syntax.add("recursion")
    return facts


def _targets(node: ast.AST) -> list[str]:
    targets: list[str] = []
    for child in getattr(node, "targets", []) or [getattr(node, "target", None)]:
        if isinstance(child, ast.Name):
            targets.append(child.id)
        elif isinstance(child, ast.Attribute):
            targets.append(child.attr)
        elif isinstance(child, (ast.Tuple, ast.List)):
            targets.extend(_targets(child))
    return [item for item in targets if item]


def _node_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _node_name(node.value)
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return ""


def _regex_facts(text: str, scope: Scope) -> ScopeFacts:
    facts = ScopeFacts()
    facts.parse = "regex"
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        absolute = scope.start + number - 1
        facts.tokens.update(source_tokens(line))
        for token in source_tokens(line):
            facts.token_counts[token] += 1
        patterns = {
            "loop": r"\b(for|while|loop|forEach|map|filter|reduce)\b",
            "conditional": r"\b(if|else|elif|switch|case|when|match|guard)\b",
            "return": r"\breturn\b",
            "raise": r"\b(throw|raise|panic)\b",
            "assert": r"\bassert\b",
            "yield": r"\byield\b",
            "await": r"\b(await|async)\b",
            "break": r"\bbreak\b",
            "continue": r"\bcontinue\b",
            "try": r"\b(try|catch|except|rescue|finally)\b",
            "with": r"\b(with|using)\b",
        }
        for name, pattern in patterns.items():
            if re.search(pattern, line):
                facts.syntax.add(name)
                facts.counts[name] += 1
                facts.signal(name, line, absolute)
        assignment = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::=|=(?!=)|:(?!:))", line)
        if assignment:
            facts.syntax.add("assignment")
            facts.counts["assignment"] += 1
            facts.assignments.add(assignment.group(1))
            facts.signal("assignment", line, absolute)
        for match in re.finditer(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", line):
            name = match.group(1)
            if name in KEYWORDS:
                continue
            facts.calls.add(name)
            facts.syntax.add("call")
            facts.counts["call"] += 1
            facts.signal("call", line, absolute)
            if name in {"gather", "all", "race", "spawn", "map", "submit", "parallel"}:
                facts.syntax.add("fanout")
                facts.counts["fanout"] += 1
            if name in {"reduce", "join", "merge", "collect", "aggregate"}:
                facts.syntax.add("aggregate")
                facts.counts["aggregate"] += 1
        for match in re.finditer(r"[\"']([^\"']{1,200})[\"']", line):
            facts.strings.append(match.group(1))
        if re.search(r"\b(class|interface|struct|trait|impl|enum)\b", line):
            facts.syntax.add("class")
            facts.counts["class"] += 1
        if re.search(r"^\s*@", line):
            facts.syntax.add("decorator")
            facts.counts["decorator"] += 1
    if scope.name in facts.calls:
        facts.counts["recursion"] += 1
        facts.syntax.add("recursion")
    return facts


def extract_facts(text: str, scope: Scope, suffix: str) -> ScopeFacts:
    if suffix in {".py", ".pyi"}:
        return _python_facts(text, scope)
    return _regex_facts(text, scope)


@dataclass(frozen=True)
class TagRule:
    keywords: tuple[str, ...]
    syntax: tuple[str, ...] = ()
    syntax_alone: bool = False
    token_syntax: tuple[str, ...] = ()


# Keywords are matched against identifier tokens, never substrings. A tag is
# present when its keyword appears and its optional syntax condition holds.
TAG_RULES: dict[str, TagRule] = {
    "agent": TagRule(("agent", "agents", "assistant", "actor", "runner")),
    "model": TagRule(("model", "models", "llm", "llms", "completion", "completions", "generate", "generation")),
    "tool": TagRule(("tool", "tools", "action", "actions", "function", "functions"), syntax=("call", "loop")),
    "result": TagRule(("result", "results", "output", "outputs", "observation", "observations", "outcome", "outcomes"), syntax=("return",)),
    "message": TagRule(("message", "messages", "content", "contents", "conversation", "conversations")),
    "role": TagRule(("role", "roles", "persona", "personas", "prompt", "prompts", "instruction", "instructions")),
    "context": TagRule(("context", "contexts", "window", "windows")),
    "loop": TagRule(("loop", "loops", "turn", "turns", "iteration", "iterations", "iterate", "iterates", "cycle", "cycles", "repeat", "repeats", "retry", "retries"), syntax=("loop",), syntax_alone=True),
    "history": TagRule(("history", "record", "records", "transcript", "transcripts", "log", "logs", "ledger", "ledgers", "messages"), syntax=("assignment", "call")),
    "ledger": TagRule(("history", "ledger", "ledgers", "usage", "cost", "costs", "token", "tokens", "step", "steps", "turn", "turns", "record", "records"), syntax=("assignment", "loop")),
    "cap": TagRule(("max", "maximum", "limit", "limits", "budget", "budgets", "quota", "quotas", "threshold", "thresholds"), syntax=("conditional", "assignment")),
    "budget": TagRule(("budget", "budgets", "token", "tokens", "cost", "costs", "resource", "resources"), syntax=("assignment", "conditional")),
    "termination": TagRule(("terminate", "terminates", "termination", "stop", "stops", "exit", "exits", "finish", "finishes", "terminal", "end", "ends"), syntax=("return", "raise", "break"), syntax_alone=True, token_syntax=("loop",)),
    "decision": TagRule(("decide", "decides", "decision", "decisions", "choose", "chooses", "choice", "select", "selects", "branch", "branches", "predicate", "predicates"), syntax=("conditional",), syntax_alone=True),
    "middleware": TagRule(("middleware", "pipeline", "pipelines", "chain", "chains", "interceptor", "interceptors", "handler", "handlers", "hook", "hooks", "plugin", "plugins")),
    "continuation": TagRule(("continue", "continues", "continuation", "next", "subsequent", "downstream"), syntax=("call",)),
    "short_circuit": TagRule(("shortcircuit", "skip", "abort", "bypass"), syntax=("conditional", "return")),
    "registry": TagRule(("registry", "registries", "catalog", "catalogs", "table", "tables", "map", "maps", "index", "indexes", "directory", "directories"), syntax=("assignment", "call")),
    "discovery": TagRule(("discover", "discovers", "discovery", "search", "searches", "find", "finds", "lookup", "lookups", "resolve", "resolves", "list", "lists", "available", "deferred", "lazy"), syntax=("call", "loop")),
    "invocation": TagRule(("invoke", "invokes", "invocation", "execute", "executes", "execution", "dispatch", "dispatches", "call", "calls", "run", "runs"), syntax=("call",)),
    "authorization": TagRule(("authorize", "authorizes", "authorization", "permission", "permissions", "permitted", "policy", "policies", "allow", "allows", "allowed", "deny", "denies", "capability", "capabilities"), syntax=("conditional", "raise")),
    "approval": TagRule(("review", "reviews", "reviewer", "reviewers", "approval", "approvals", "approve", "approves", "reject", "rejects", "confirm", "confirms", "consent", "guardian"), syntax=("conditional", "return")),
    "escalation": TagRule(("escalate", "escalates", "escalation", "handoff", "handoffs", "human")),
    "event": TagRule(("event", "events", "topic", "topics", "publish", "publishes", "subscriber", "subscribers", "subscribe", "subscribes", "bus", "broker", "emit", "emits", "listener", "listeners"), syntax=("call",)),
    "delivery": TagRule(("deliver", "delivery", "consume", "consumes", "consumer", "consumers", "ack", "enqueue", "dequeue"), syntax=("call", "loop")),
    "memory": TagRule(("memory", "memories", "reflection", "reflections", "reflect", "reflects", "lesson", "lessons", "experience", "experiences")),
    "retrieval": TagRule(("retrieve", "retrieves", "retrieval", "recall", "search", "searches", "lookup", "lookups"), syntax=("call",)),
    "update": TagRule(("update", "updates", "append", "appends", "write", "writes", "store", "stores", "save", "saves"), syntax=("call", "assignment")),
    "fanout": TagRule(("parallel", "parallelism", "concurrent", "concurrency", "fanout", "spawn", "spawns", "worker", "workers"), syntax=("call", "loop", "await")),
    "aggregate": TagRule(("aggregate", "aggregates", "aggregation", "gather", "gathers", "reduce", "reducer", "reducers", "join", "joins", "merge", "merges", "collect", "collects", "correlate", "correlation", "reconcile"), syntax=("call",)),
    "partition": TagRule(("partition", "partitions", "shard", "shards", "batch", "batches", "chunk", "chunks"), syntax=("loop", "call")),
    "worker": TagRule(("worker", "workers", "task", "tasks", "subagent", "subagents")),
    "checkpoint": TagRule(("checkpoint", "checkpoints", "snapshot", "snapshots", "restore", "restores", "resume", "resumes", "fork", "forks")),
    "validation": TagRule(("validation", "validate", "validates", "valid", "split", "splits", "holdout", "train", "training", "evaluation", "eval")),
    "regularization": TagRule(("regularize", "regularizes", "regularization", "penalty", "penalties", "constraint", "constraints")),
    "holdout": TagRule(("holdout", "validation", "valid", "test", "tests", "unseen")),
    "sandbox": TagRule(("sandbox", "sandboxes", "container", "containers", "isolate", "isolates", "isolation", "docker"), syntax=("call",)),
    "retry": TagRule(("retry", "retries", "backoff", "attempt", "attempts"), syntax=("loop",)),
    "delegation": TagRule(("delegate", "delegates", "delegation", "subagent", "subagents", "worker", "workers", "handoff", "handoffs"), syntax=("call",)),
    "state_machine": TagRule(("transition", "transitions", "node", "nodes", "edge", "edges", "graph", "graphs", "statechart"), syntax=("conditional", "assignment")),
    "observability": TagRule(("trace", "traces", "span", "spans", "metric", "metrics", "telemetry", "event", "events", "log", "logs"), syntax=("call",)),
    "schema": TagRule(("schema", "schemas", "descriptor", "descriptors", "declaration", "declarations", "definition", "definitions", "contract", "contracts")),
    "error": TagRule(("error", "errors", "exception", "exceptions", "fail", "fails", "failure", "failures", "violation", "violations", "invalid"), syntax=("raise",), syntax_alone=True),
    "write": TagRule(("write", "writes", "edit", "edits", "patch", "patches", "modify", "modifies", "update", "updates"), syntax=("call",)),
    "plan": TagRule(("plan", "plans", "planning", "todo", "todos", "step", "steps")),
    "reflection": TagRule(("reflect", "reflects", "reflection", "reflections", "critique", "critiques", "review", "reviews"), syntax=("call", "assignment")),
    "skill": TagRule(("skill", "skills", "capability", "capabilities")),
    "lock": TagRule(("lock", "locks", "mutex", "semaphore"), syntax=("call", "with")),
    "transaction": TagRule(("transaction", "transactions", "commit", "commits", "rollback", "rollbacks", "atomic"), syntax=("call",)),
    "correlation": TagRule(("correlation", "correlate", "correlates", "correlator", "identity", "id", "ids", "order", "ordering"), syntax=("assignment", "call")),
}

TAG_RULES.update({
    "yield": TagRule(("yield", "yields", "stream", "streams", "streaming", "emit", "emits"), syntax=("yield",), syntax_alone=True),
    "cleanup": TagRule(("cleanup", "finally", "close", "closes", "release", "releases", "dispose", "disposes"), syntax=("try", "with")),
    "queue": TagRule(("queue", "queues", "enqueue", "buffer", "inbox", "mailbox"), syntax=("assignment", "call")),
    "cancellation": TagRule(("cancel", "cancels", "cancellation", "abort", "timeout", "timeouts"), syntax=("conditional", "raise", "call")),
    "async": TagRule(("async", "asynchronous", "await", "stream", "streaming"), syntax=("await", "yield"), syntax_alone=True),
    "program": TagRule(("program", "programs", "code", "executable", "executables")),
    "thought": TagRule(("thought", "thoughts", "reasoning", "rationale", "reason")),
    "manifest": TagRule(("manifest", "manifests", "skill", "skills", "file", "files")),
    "loader": TagRule(("load", "loads", "loader", "loaders", "discover", "discovers", "discovery"), syntax=("call",)),
    "resource": TagRule(("resource", "resources", "bundle", "bundles", "asset", "assets")),
    "protocol": TagRule(("protocol", "protocols", "interface", "interfaces", "contract", "contracts", "abstractmethod")),
    "provider": TagRule(("provider", "providers", "backend", "backends", "vendor", "vendors")),
"cache": TagRule(("cache", "caches", "cached", "caching", "cachekey", "cachecontrol", "cachedialect")),
"capability": TagRule(("capability", "capabilities", "support", "supports", "supported", "feature", "features")),
    "transport": TagRule(("transport", "transports", "request", "requests", "response", "responses")),
    "adapter": TagRule(("adapter", "adapters", "dialect", "dialects", "adapt", "adapts")),
    "component": TagRule(("component", "components", "module", "modules", "plugin", "plugins")),
    "composition": TagRule(("compose", "composes", "composition", "builder", "builders", "build", "builds"), syntax=("call", "assignment")),
    "evaluator": TagRule(("evaluator", "evaluators", "evaluate", "evaluates", "evaluation", "evaluations", "score", "scores", "judge", "judges"), syntax=("call",)),
    "proposal": TagRule(("propose", "proposes", "proposal", "proposals", "candidate", "candidates")),
    "probe": TagRule(("probe", "probes", "trial", "trials", "test", "tests"), syntax=("call", "loop")),
    "artifact": TagRule(("artifact", "artifacts", "payload", "payloads", "output", "outputs")),
    "provenance": TagRule(("provenance", "source", "sources", "origin", "origins", "traceable")),
    "trace": TagRule(("trace", "traces", "telemetry", "observability", "span", "spans")),
    "analyzer": TagRule(("analyze", "analyzes", "analyzer", "analysis", "diagnose", "diagnoses", "diagnosis"), syntax=("call",)),
    "edit_scope": TagRule(("edit", "edits", "patch", "patches", "diff", "diffs", "mutation", "mutations")),
    "regression": TagRule(("regression", "regressions", "suite", "suites")),
    "objective": TagRule(("objective", "objectives", "metric", "metrics", "score", "scores")),
    "constraint": TagRule(("constraint", "constraints", "budget", "budgets", "limit", "limits")),
    "candidate": TagRule(("candidate", "candidates", "alternative", "alternatives")),
    "pareto": TagRule(("pareto", "tradeoff", "tradeoffs", "frontier")),
    "generator": TagRule(("generate", "generates", "generator", "generators", "mutate", "mutates"), syntax=("call", "loop")),
    "executor": TagRule(("execute", "executes", "executor", "executors", "runtime", "runner"), syntax=("call",)),
    "fitness": TagRule(("fitness", "reward", "rewards", "score", "scores")),
    "archive": TagRule(("archive", "archives", "population", "populations", "generation", "generations")),
    "joint": TagRule(("joint", "jointly", "coadapt", "coadaptation")),
    "attribution": TagRule(("attribution", "attributable", "provenance", "attribute", "attributes")),
    "adaptation": TagRule(("adaptation", "adaptations", "adapt", "adapts", "adaptive", "controller", "controllers")),
    "target": TagRule(("target", "targets", "select", "selects", "selection", "selections")),
    "weight": TagRule(("weight", "weights", "parameter", "parameters")),
    "planner": TagRule(("planner", "planners", "plan", "plans", "planning")),
    "synchronization": TagRule(("synchronize", "synchronizes", "synchronization", "sync", "channel", "channels")),
    "stage": TagRule(("stage", "stages", "step", "steps", "chain", "chains", "sequence", "sequences")),
    "handoff": TagRule(("handoff", "handoffs", "handover", "transfer", "transfers", "delegate", "delegates")),
    "route": TagRule(("route", "routes", "routing", "dispatch", "dispatches")),
    "classifier": TagRule(("classify", "classifies", "classifier", "rule", "rules", "router", "routers")),
    "unsupported": TagRule(("unsupported", "unknown", "fallback", "fallbacks", "default")),
    "reducer": TagRule(("reduce", "reduces", "reducer", "reducers", "gather", "gathers", "join", "joins", "merge", "merges", "collect", "collects"), syntax=("call",)),
    "synthesis": TagRule(("synthesize", "synthesizes", "synthesis", "integrate", "integrates", "integration", "merge", "merges")),
    "manager": TagRule(("manager", "managers", "coordinator", "coordinators", "orchestrator", "orchestrators", "lead")),
    "integration": TagRule(("integrate", "integrates", "integration", "synthesize", "synthesis", "merge", "merges")),
    "control": TagRule(("control", "controls", "transfer", "transfers", "handoff", "handoffs")),
    "authority": TagRule(("authority", "permission", "permissions", "privilege", "privileges", "scope", "scopes")),
    "mediator": TagRule(("mediator", "mediators", "coordinator", "coordinators", "router", "routers")),
    "participant": TagRule(("participant", "participants", "agent", "agents", "component", "components")),
    "routing": TagRule(("routing", "route", "routes", "dispatch", "dispatches")),
    "response": TagRule(("response", "responses", "reply", "replies", "result", "results")),
    "subscription": TagRule(("subscription", "subscriptions", "subscribe", "subscribes", "register", "registers")),
    "observer": TagRule(("observer", "observers", "listener", "listeners", "callback", "callbacks")),
    "notification": TagRule(("notify", "notifies", "notification", "notifications", "event", "events", "publish", "publishes")),
    "request": TagRule(("request", "requests", "call", "calls")),
    "reply": TagRule(("reply", "replies", "response", "responses")),
    "reasoning": TagRule(("reason", "reasons", "reasoning", "thought", "thoughts", "rationale")),
    "action": TagRule(("action", "actions", "tool", "tools")),
    "observation": TagRule(("observation", "observations", "result", "results", "feedback")),
    "base": TagRule(("base", "abstract", "interface", "parent", "superclass")),
    "override": TagRule(("override", "overrides", "subclass", "subclasses", "implements")),
    "subtype": TagRule(("subtype", "subtypes", "subclass", "subclasses", "implementation", "implementations")),
    "dispatch": TagRule(("dispatch", "dispatches", "route", "routes", "invoke", "invokes"), syntax=("call",)),
    "harness": TagRule(("harness", "harnesses", "scaffold", "scaffolding")),
})

TAG_RULES.update({
    "intervention": TagRule(('intervene', 'intervenes', 'intervention', 'interventions', 'redirect', 'redirects', 'escalate', 'escalates', 'stop', 'stops')),
    "command": TagRule(('command', 'commands', 'shell', 'bash')),
    "parser": TagRule(('parse', 'parses', 'parser', 'parsers', 'tree', 'trees', 'ast')),
    "merge": TagRule(('merge', 'merges', 'compose', 'composes', 'composition', 'combine', 'combines')),
    "floor": TagRule(('floor', 'minimum', 'mandatory', 'protected', 'baseline')),
    "profile": TagRule(('profile', 'profiles', 'policy', 'policies', 'permission', 'permissions')),
    "enforcement": TagRule(('enforce', 'enforces', 'enforcement', 'gate', 'gates', 'block', 'blocks')),
    "review": TagRule(('review', 'reviews', 'reviewer', 'reviewers', 'approval', 'approvals')),
    "principal": TagRule(('principal', 'principals', 'operator', 'operators', 'session', 'sessions', 'caller', 'callers', 'user', 'users')),
    "grant": TagRule(('grant', 'grants', 'scope', 'scopes', 'capability', 'capabilities')),
    "revocation": TagRule(('revoke', 'revokes', 'revocation', 'revocations', 'expire', 'expires', 'deny', 'denies')),
    "branch": TagRule(('branch', 'branches', 'fork', 'forks', 'checkpoint', 'checkpoints')),
    "ancestry": TagRule(('ancestry', 'ancestor', 'ancestors', 'parent', 'parents', 'history')),
    "compaction": TagRule(('compact', 'compacts', 'compaction', 'summarize', 'summarizes', 'summarization', 'truncate', 'truncates', 'truncation')),
    "summarizer": TagRule(('summarize', 'summarizes', 'summarizer', 'summarizers', 'summary', 'summaries', 'compact', 'compaction')),
    "lineage": TagRule(('lineage', 'provenance', 'ancestry', 'source', 'sources')),
    "identity": TagRule(('identity', 'identities', 'id', 'ids', 'principal', 'session')),
    "service": TagRule(('service', 'services', 'endpoint', 'endpoints', 'server', 'servers')),
    "evaluation": TagRule(('evaluate', 'evaluates', 'evaluation', 'evaluations', 'evaluator', 'evaluators', 'score', 'scores')),
    "revision": TagRule(('revise', 'revises', 'revision', 'revisions', 'retry', 'retries', 'rewrite', 'rewrites')),
    "feedback": TagRule(('feedback', 'critique', 'critiques', 'reflection', 'reflections', 'evaluation', 'evaluations')),
})

TAG_RULES.update({
    "broker": TagRule(("broker", "brokers", "bus", "middleware", "exchange")),
    "subscriber": TagRule(("subscriber", "subscribers", "subscribe", "subscribes", "consumer", "consumers", "listener", "listeners")),
})

TAG_RULES.update({
    "ordering": TagRule(('order', 'orders', 'ordering', 'priority', 'priorities', 'sequence', 'sequences')),
    "truncate": TagRule(('truncate', 'truncates', 'truncation', 'truncations')),
    "append": TagRule(('append', 'appends', 'appendonly', 'log', 'logs', 'record', 'records')),
    "cursor": TagRule(('cursor', 'cursors', 'offset', 'offsets', 'position', 'positions')),
    "ack": TagRule(('ack', 'acks', 'acknowledge', 'acknowledges', 'acknowledgement', 'acknowledgements', 'commit', 'commits')),
    "projector": TagRule(('project', 'projects', 'projector', 'projectors', 'reduce', 'reduces', 'apply', 'applies')),
    "interception": TagRule(('intercept', 'intercepts', 'interception', 'interceptions', 'wrap', 'wraps')),
    "verifier": TagRule(('verify', 'verifies', 'verifier', 'verifiers', 'validate', 'validates', 'validator', 'validators', 'check', 'checks')),
    "stop": TagRule(('stop', 'stops', 'finish', 'finishes', 'terminate', 'terminates', 'exit', 'exits')),
    "policy": TagRule(('policy', 'policies', 'rule', 'rules', 'guard', 'guards', 'constraint', 'constraints')),
    "topic": TagRule(('topic', 'topics', 'subject', 'subjects')),
})

DIMENSIONS = ("context", "trigger", "structure", "effect")
PRIMARY_COUNT = {"context": 2, "trigger": 2, "structure": 4, "effect": 2}


def tags_in_text(text: str) -> dict[str, list[str]]:
    tokens = source_tokens(text)
    found: dict[str, list[str]] = {}
    for tag, rule in TAG_RULES.items():
        hits = [word for word in rule.keywords if word in tokens]
        if hits:
            found[tag] = hits
    return found


def tag_specificity(records: list[dict]) -> dict[str, float]:
    frequency: Counter = Counter()
    for record in records:
        text = " ".join(record["pointcut"][key] for key in DIMENSIONS)
        for tag in tags_in_text(text):
            frequency[tag] += 1
    total = max(1, len(records))
    return {tag: 1.0 - (frequency[tag] / total) for tag in TAG_RULES}


def infer_requirements(record: dict, specificity: dict[str, float]) -> dict:
    """Derive pointcut requirements from the record's own prose.

    The catalog already states what must be present in each dimension. This
    function maps that prose onto the observable tag vocabulary, keeping the
    most specific tags per dimension as primary requirements.
    """
    result: dict[str, dict] = {}
    for dimension in DIMENSIONS:
        text = record["pointcut"][dimension]
        matched = tags_in_text(text)
        ordered = sorted(
            matched,
            key=lambda tag: (-specificity.get(tag, 0.5), -len(matched[tag]), tag),
        )
        limit = PRIMARY_COUNT[dimension]
        primary = ordered[:limit]
        if dimension == "structure" and len(primary) < 2:
            for source in (record["join_point"], record["name"]):
                for tag, hits in tags_in_text(source).items():
                    if tag not in matched:
                        matched[tag] = hits
                        ordered.append(tag)
                    if tag not in primary and len(primary) < 2:
                        primary.append(tag)
        result[dimension] = {
            "primary": primary,
            "supporting": [tag for tag in ordered if tag not in primary],
            "because": {tag: matched.get(tag, []) for tag in ordered},
        }
    return result


def evaluate_tags(facts: ScopeFacts) -> dict[str, dict]:
    """Return the tags observable in a scope with short evidence strings."""
    present: dict[str, dict] = {}
    for tag, rule in TAG_RULES.items():
        hits = sorted(word for word in rule.keywords if word in facts.tokens)
        syntax_hits = [name for name in rule.syntax if name in facts.syntax]
        if rule.token_syntax and not all(name in facts.syntax for name in rule.token_syntax):
            syntax_hits = []
        if not hits and not (rule.syntax_alone and syntax_hits):
            continue
        if not hits and rule.token_syntax and not all(name in facts.syntax for name in rule.token_syntax):
            continue
        evidence: list[str] = []
        for word in hits[:2]:
            evidence.append(f"token:{word}")
        for name in syntax_hits[:2]:
            evidence.extend(facts.signals.get(name, [])[:1])
        strength = 0.5 + 0.2 * len(hits) + 0.15 * len(syntax_hits)
        if rule.token_syntax and all(name in facts.syntax for name in rule.token_syntax):
            strength += 0.1
        present[tag] = {
            "strength": round(min(1.0, strength), 2),
            "tokens": hits,
            "syntax": syntax_hits,
            "evidence": evidence[:3],
        }
    return present


def scope_text(text: str, scope: Scope) -> str:
    lines = text.splitlines()
    start = max(1, scope.start)
    end = min(len(lines), scope.end, start + MAX_SCOPE_LINES - 1)
    return "\n".join(lines[start - 1:end])
