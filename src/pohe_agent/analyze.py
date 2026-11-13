"""Scope-anchored evidence triangulation for POHE records.

The analyzer answers a narrower question than "is this pattern present?":
which source scopes exhibit the roles an operational signature requires, which
pointcut dimensions are supported or missing, and which negative-control
contrast the scope fails. Every field is evidence for review, not a verdict
about semantic conformance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .catalog import load_catalog, select
from .features import (
    Scope,
    ScopeFacts,
    evaluate_tags,
    extract_facts,
    extract_scopes,
    line_modality,
    scope_for_line,
    source_tokens,
)
from .signatures import for_record, load_signatures
from .walk import SourceFile, read_text, walk_repository

VERDICT_ORDER = {
    "rejected": 0,
    "cue_only": 1,
    "structural_candidate": 2,
    "pointcut_candidate": 3,
    "source_matched": 4,
}
VERDICT_RANK = {name: rank for name, rank in VERDICT_ORDER.items()}
MAX_HITS_PER_PATTERN_PER_FILE = 200
MAX_EXCERPT_LINES = 16

# Python's \b treats underscore as a word character. The catalog uses \b at
# identifier boundaries, so "prompt_cache_key" does not match \bprompt_cache\b.
# This boundary treats underscores as separators, matching the tokenizer's view.
IDENT_BOUNDARY = (
    r"(?:(?<=[A-Za-z0-9])(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])(?=[A-Za-z0-9])"
    r"|(?<=[a-z])(?=[A-Z]))"
)


def compile_cue(pattern: str) -> re.Pattern[str]:
    """Compile a catalog or signature cue with identifier-aware boundaries."""
    return re.compile(pattern.replace(r"\b", IDENT_BOUNDARY), re.IGNORECASE)


def compile_cues(record: dict, signature: dict) -> list[tuple[str, re.Pattern[str]]]:
    """Return the frozen lexical cue plus optional operational cues.

    Operational cues are calibrated aliases stored with the signature. They
    repair retrieval when the frozen cue's vocabulary misses its own exemplar;
    they never add structural evidence.
    """
    cues = [("lexical", compile_cue(record["regex"]))]
    cues.extend(("operational", compile_cue(cue)) for cue in signature.get("cues", []))
    return cues


@dataclass(frozen=True)
class NegativeRule:
    tags_any: tuple[str, ...] = ()
    tags_all: tuple[str, ...] = ()
    syntax_any: tuple[str, ...] = ()
    severity: str = "high"
    detail: str = ""


NEGATIVE_RULES = {
    "one_shot": NegativeRule(syntax_any=("loop", "recursion"), detail="no loop or recursive cycle"),
    "no_transition": NegativeRule(("state_machine",), detail="no enumerated state transition"),
    "sequential_calls": NegativeRule(("delegation", "correlation"), detail="calls lack a delegation envelope or result correlation"),
    "single_function": NegativeRule(("plan", "delegation"), detail="single call without workflow ownership"),
    "single_score": NegativeRule(("pareto", "constraint"), detail="one score without an objective vector or constraints"),
    "no_holdout": NegativeRule(("holdout",), detail="selection has no final holdout"),
    "hard_coded": NegativeRule(("middleware", "registry"), detail="no middleware chain or registry"),
    "static_inventory": NegativeRule(("registry", "discovery", "invocation"), detail="no discovery, registry, or invocation handle"),
    "sync_list": NegativeRule(("yield",), detail="no yield/stream path"),
    "global_list": NegativeRule(("queue", "state_machine"), detail="no queue or transition core"),
    "generic_cache": NegativeRule(("adapter", "schema"), severity="medium", detail="no provider dialect or cache-control schema"),
    "single_vendor": NegativeRule(("adapter", "protocol"), severity="medium", detail="no provider boundary"),
    "unrelated_limit": NegativeRule(("truncate", "artifact"), severity="medium", detail="cap has no observation-boundary machinery"),
    "in_memory_queue": NegativeRule(("append", "cursor", "ack"), detail="no durable append, cursor, or acknowledgement"),
    "mutable_array": NegativeRule(("projector", "schema"), detail="no event schema or projector"),
    "prompt_template": NegativeRule(("manifest", "resource", "loader"), detail="no manifest, resource bundle, or loader"),
    "direct_log": NegativeRule(("event", "registry", "interception"), detail="no event schema, registration, or interception"),
    "post_run_test": NegativeRule(("verifier", "stop"), detail="no stop interception or verifier"),
    "depth_limit": NegativeRule(("escalation", "decision", "intervention"), detail="no semantic intervention path"),
    "constant_limit": NegativeRule(("ledger",), detail="cap exists without a resource ledger"),
    "prompt_only": NegativeRule(("reflection", "revision"), detail="no produced feedback or revision input"),
    "substring_denylist": NegativeRule(("parser",), detail="no parser or normalized command tree"),
    "single_allowlist": NegativeRule(("floor", "merge"), detail="no protected floor or merge operator"),
    "prompt_warning": NegativeRule(("sandbox",), detail="no sandbox profile or enforcement point"),
    "post_hoc": NegativeRule(("approval",), syntax_any=("conditional", "raise"), detail="approval has no blocking decision path"),
    "admin_flag": NegativeRule(("grant", "revocation", "profile"), detail="no scope grant, profile, or revocation state"),
    "workspace_only": NegativeRule(("branch",), detail="no conversation branch operation"),
    "generic_truncate": NegativeRule(("lineage",), detail="compaction has no lineage metadata"),
    "generic_history": NegativeRule(("reflection", "retrieval", "update"), detail="history has no reflection, retrieval, or update policy"),
    "signature_only": NegativeRule(("protocol",), severity="medium", detail="no protocol adapter or compatibility boundary"),
    "independent_prompts": NegativeRule(("stage",), detail="no ordered stage or handoff"),
    "prompt_if": NegativeRule(("route", "classifier"), detail="no attributable route or classifier"),
    "no_fan_in": NegativeRule(("reducer",), detail="fan-out exists without a reducer"),
    "fixed_sequence": NegativeRule(("synthesis", "delegation"), detail="no generated plan or delegation envelope"),
    "self_claim": NegativeRule(("evaluator",), detail="no independent evaluator"),
    "no_integration": NegativeRule(("integration",), detail="workers are launched without integration"),
    "function_call": NegativeRule(("handoff", "control"), detail="no peer control transfer"),
    "global_object": NegativeRule(("mediator", "routing"), detail="no mediator or routing policy"),
    "polling": NegativeRule(("observer", "subscription"), detail="no observer registration or notification"),
    "direct_dispatch": NegativeRule(("topic", "broker", "subscriber", "delivery"), detail="direct invocation without topic delivery"),
    "local_factory": NegativeRule(("transport",), detail="no resolved transport or request/reply boundary"),
    "thought_only": NegativeRule(("action", "observation"), detail="reasoning without an external action or observation"),
    "hierarchy_only": NegativeRule(("dispatch", "subtype"), detail="hierarchy without base-typed dispatch"),
    "helpers_only": NegativeRule(("composition", "component"), detail="helpers without a component composition boundary"),
    "model_only": NegativeRule(("joint",), detail="no joint harness/policy evaluation"),
    "prompt_variation": NegativeRule(("executor", "fitness", "archive"), detail="variation without executable selection"),
    "citation_only": NegativeRule(("adaptation", "target"), detail="no adaptation controller or target selection"),
    "two_loops": NegativeRule(("feedback", "synchronization"), detail="two loops without a feedback link"),
    "logging_only": NegativeRule(("analyzer", "trace"), detail="logging without trace analysis"),
}


def _ratio(primary: list[str], tags: dict) -> tuple[float, list[str], list[str]]:
    matched = [tag for tag in primary if tag in tags]
    missing = [tag for tag in primary if tag not in tags]
    return (len(matched) / len(primary) if primary else 0.0), matched, missing


def _status(ratio: float, *, supported: float = 0.66, partial: float = 0.30) -> str:
    if ratio >= supported:
        return "supported"
    if ratio >= partial:
        return "partial"
    return "contradicted"


def _dimension_evidence(tags: dict, matched: list[str], missing: list[str]) -> list[str]:
    evidence: list[str] = []
    for tag in matched:
        item = tags[tag]
        evidence.extend(item["evidence"][:1])
    if not evidence:
        evidence = [f"missing roles: {', '.join(missing)}"] if missing else []
    return evidence[:3]


def evaluate_dimensions(
    signature: dict,
    tags: dict,
    facts: ScopeFacts,
    scope: Scope,
    source_kind: str,
    hits: list[dict],
) -> dict:
    dimensions: dict[str, dict] = {}
    for dimension in ("context", "trigger", "structure", "effect"):
        primary = signature[dimension]
        ratio, matched, missing = _ratio(primary, tags)
        status = _status(ratio)
        if dimension == "context":
            if source_kind == "support" and status == "supported":
                status = "partial"
        if dimension in {"structure", "effect"} and source_kind == "support" and status == "supported":
            status = "partial"
        elif dimension == "trigger":
            code_hits = [hit for hit in hits if hit["modality"] == "code"]
            if not code_hits and status == "supported":
                status = "partial"
        elif dimension == "effect":
            terminal = bool(facts.syntax & {"return", "raise", "yield"} or facts.counts["call"])
            if status == "supported" and not terminal:
                status = "partial"
        dimensions[dimension] = {
            "status": status,
            "coverage": round(ratio, 3),
            "primary": primary,
            "matched": matched,
            "missing": missing,
            "evidence": _dimension_evidence(tags, matched, missing),
        }
    return dimensions


def check_negative_control(signature: dict, tags: dict, facts: ScopeFacts) -> dict:
    checks: list[dict] = []
    risk = False
    for code in signature.get("negative", []):
        rule = NEGATIVE_RULES.get(code)
        if rule is None:
            continue
        absent_tags = [tag for tag in rule.tags_any if tag not in tags]
        missing_all = [tag for tag in rule.tags_all if tag not in tags]
        missing_syntax = [name for name in rule.syntax_any if name not in facts.syntax]
        failed = False
        detail = rule.detail
        if rule.tags_any and len(absent_tags) == len(rule.tags_any):
            failed = True
        if missing_all:
            failed = True
        if rule.syntax_any and len(missing_syntax) == len(rule.syntax_any):
            failed = True
        if failed:
            risk = True
            checks.append({
                "code": code,
                "status": "risk",
                "severity": rule.severity,
                "detail": detail,
            })
        else:
            checks.append({
                "code": code,
                "status": "clear",
                "severity": "clear",
                "detail": detail,
            })
    return {
        "status": "risk" if risk else "clear",
        "checks": checks,
    }


def contract_probes(record: dict, facts: ScopeFacts) -> list[dict]:
    has_guard = bool(facts.syntax & {"raise", "assert"} or facts.counts["conditional"])
    has_return = bool(facts.counts["return"] or facts.counts["yield"])
    has_check = bool(facts.syntax & {"raise", "assert"} or facts.counts["conditional"])
    has_error = bool(facts.syntax & {"raise", "try"} or facts.tokens & {"error", "exception", "failure", "violation"})
    rows = [
        ("requires", record["requires"], "guard mechanism visible" if has_guard else "no guard visible", has_guard),
        ("ensures", record["ensures"], "return or yield path visible" if has_return else "no result path visible", has_return),
        ("invariant", record["invariant"], "check mechanism visible" if has_check else "no check visible", has_check),
        ("violation", record["violation"], "error path visible" if has_error else "no error path visible", has_error),
    ]
    return [
        {
            "field": field,
            "claim": claim,
            "observation": observation,
            "status": "mechanism_present" if present else "not_visible",
        }
        for field, claim, observation, present in rows
    ]


def decide_verdict(
    dimensions: dict,
    negative: dict,
    source_kind: str,
    scope: Scope,
) -> str:
    if any(
        check["status"] == "risk" and check["severity"] == "high"
        for check in negative["checks"]
    ):
        return "rejected"
    medium_risk = any(
        check["status"] == "risk" and check["severity"] == "medium"
        for check in negative["checks"]
    )
    structure = dimensions["structure"]
    if structure["status"] == "contradicted" or not structure["matched"]:
        return "cue_only"
    if any(item["status"] == "contradicted" for key, item in dimensions.items() if key != "structure"):
        return "cue_only"
    if structure["status"] == "partial":
        verdict = "structural_candidate"
    elif all(
        dimensions[key]["status"] == "supported"
        for key in ("context", "structure", "effect")
    ):
        if dimensions["trigger"]["status"] == "supported":
            verdict = (
                "source_matched"
                if dimensions["structure"]["coverage"] >= 0.999
                else "pointcut_candidate"
            )
        else:
            verdict = "pointcut_candidate"
    else:
        verdict = "structural_candidate"
    if medium_risk:
        verdict = min(verdict, "structural_candidate", key=lambda name: VERDICT_ORDER[name])
    if source_kind != "code" or scope.kind == "file":
        verdict = min(verdict, "structural_candidate", key=lambda name: VERDICT_ORDER[name])
    return verdict


def score_candidate(dimensions: dict, hits: list[dict], source_kind: str, scope: Scope) -> float:
    weights = {"context": 1.0, "trigger": 1.0, "structure": 2.0, "effect": 1.0}
    total = sum(weights[key] * dimensions[key]["coverage"] for key in weights)
    score = total / 5.0
    score += 0.04 * min(len(hits), 5)
    if source_kind == "code":
        score += 0.05
    elif source_kind == "support":
        score -= 0.25
    elif source_kind == "test":
        score -= 0.03
    if scope.kind in {"function", "method", "class"}:
        score += 0.03
    if scope.kind == "class":
        score -= 0.02
    return round(score, 3)


def _excerpt(lines: list[str], scope: Scope, hit_lines: list[int]) -> list[dict]:
    first = min(hit_lines) if hit_lines else scope.start
    start = max(scope.start, first - 3)
    end = min(scope.end, start + MAX_EXCERPT_LINES - 1)
    return [
        {"line": number, "text": lines[number - 1][:220]}
        for number in range(start, end + 1)
        if 0 < number <= len(lines)
    ]


def _test_links(files: list[SourceFile], candidates: list[dict], limit: int = 3) -> None:
    tests = [source for source in files if source.kind == "test"]
    cache: dict[str, str | None] = {}
    for candidate in candidates:
        candidate.setdefault("tests", [])
        name = candidate["symbol"]
        if name.startswith("<"):
            continue
        found: list[dict] = candidate["tests"]
        for source in tests:
            if source.rel not in cache:
                cache[source.rel] = read_text(source.path)
            text = cache[source.rel]
            if not text:
                continue
            match = re.search(rf"\b{re.escape(name)}\b", text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                found.append({
                    "file": source.rel,
                    "line": line,
                    "text": text.splitlines()[line - 1].strip()[:160],
                })
                if len(found) >= limit:
                    break
        candidate["tests"] = found


def analyze_repository(
    root: Path,
    catalog: dict | None = None,
    signatures: dict | None = None,
    pattern_spec: str | None = None,
    max_files: int = 0,
    top: int = 5,
    min_verdict: str = "cue_only",
    include_tests: bool = False,
) -> dict:
    catalog = catalog or load_catalog()
    signatures = signatures or load_signatures()
    selected = select(catalog, pattern_spec)
    missing = [record["id"] for record in selected if record["id"] not in signatures["patterns"]]
    if missing:
        raise SystemExit(f"no operational signature for: {', '.join(missing)}")
    if min_verdict not in VERDICT_ORDER:
        raise SystemExit(f"unknown verdict: {min_verdict}")
    compiled = {
        record["id"]: compile_cues(record, for_record(signatures, record["id"]))
        for record in selected
    }
    files, skipped = walk_repository(root, max_files=max_files)
    kind_by_rel = {source.rel: source.kind for source in files}
    line_cache: dict[str, list[str]] = {}
    candidates_by_pattern: dict[str, dict[tuple, dict]] = {record["id"]: {} for record in selected}
    facts_cache: dict[tuple[str, int, int], ScopeFacts] = {}
    tag_cache: dict[tuple[str, int, int], dict] = {}
    threshold = VERDICT_ORDER[min_verdict]

    for source in files:
        text = read_text(source.path)
        if text is None:
            continue
        lines = text.splitlines()
        line_cache[source.rel] = lines
        scopes = extract_scopes(text, source.rel, source.path.suffix.lower())
        touched: dict[str, set[tuple]] = {record["id"]: set() for record in selected}
        for record in selected:
            seen_offsets: set[int] = set()
            for cue_source, regex in compiled[record["id"]]:
                for hit_index, match in enumerate(regex.finditer(text)):
                    if hit_index >= MAX_HITS_PER_PATTERN_PER_FILE:
                        break
                    if match.start() in seen_offsets:
                        continue
                    seen_offsets.add(match.start())
                    line_number = text.count("\n", 0, match.start()) + 1
                    line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
                    scope = scope_for_line(scopes, line_number)
                    key = (scope.start, scope.end, scope.name, scope.kind)
                    bucket = candidates_by_pattern[record["id"]].setdefault(key, {
                        "scope": scope,
                        "hits": [],
                        "cue_sources": set(),
                        "aggregated": False,
                    })
                    bucket["cue_sources"].add(cue_source)
                    bucket["hits"].append({
                        "line": line_number,
                        "text": " ".join(line.strip().split())[:180],
                        "modality": line_modality(line),
                        "cue": cue_source,
                    })
                    touched[record["id"]].add(key)
        for record in selected:
            for key in touched[record["id"]]:
                bucket = candidates_by_pattern[record["id"]][key]
                scope = bucket["scope"]
                cache_key = (scope.rel, scope.start, scope.end)
                if cache_key in facts_cache:
                    continue
                scope_lines = lines[scope.start - 1:min(len(lines), scope.start - 1 + 1200)]
                scope_text = "\n".join(scope_lines)
                facts = extract_facts(scope_text, scope, source.path.suffix.lower())
                parent = next(
                    (
                        item for item in scopes
                        if item.kind == "class"
                        and item is not scope
                        and item.start <= scope.start
                        and scope.end <= item.end
                    ),
                    None,
                )
                if parent is not None:
                    facts.add_token(parent.name)
                facts_cache[cache_key] = facts
                tag_cache[cache_key] = evaluate_tags(facts)

    results = []
    for record in selected:
        signature = for_record(signatures, record["id"])
        candidates: list[dict] = []
        for bucket in candidates_by_pattern[record["id"]].values():
            scope = bucket["scope"]
            cache_key = (scope.rel, scope.start, scope.end)
            facts = facts_cache[cache_key]
            tags = tag_cache[cache_key]
            hits = _dedupe_hits(bucket["hits"])
            source_kind = kind_by_rel.get(scope.rel, "other")
            if source_kind == "test" and not include_tests:
                continue
            dimensions = evaluate_dimensions(signature, tags, facts, scope, source_kind, hits)
            negative = check_negative_control(signature, tags, facts)
            verdict = decide_verdict(dimensions, negative, source_kind, scope)
            if VERDICT_ORDER[verdict] < threshold:
                continue
            code_hits = [hit for hit in hits if hit["modality"] == "code"]
            candidate = {
                **scope.to_dict(),
                "source_kind": source_kind,
                "aggregated": bool(bucket["aggregated"]),
                "verdict": verdict,
                "score": score_candidate(dimensions, hits, source_kind, scope),
                "cue_hits": len(hits),
                "cue_sources": sorted(bucket["cue_sources"]),
                "cue_lines": sorted({hit["line"] for hit in hits})[:12],
                "cue_modality": "code" if code_hits else "support",
                "dimensions": dimensions,
                "negative_control": negative,
                "contract_probes": contract_probes(record, facts),
                "tests": [],
                "excerpt": _excerpt(line_cache.get(scope.rel, []), scope, [hit["line"] for hit in hits]),
                "facts": {
                    "loops": facts.counts["loop"],
                    "conditionals": facts.counts["conditional"],
                    "returns": facts.counts["return"],
                    "raises": facts.counts["raise"],
                    "calls": facts.counts["call"],
                    "parse": facts.parse,
                },
            }
            candidate["why"] = why(candidate, record)
            candidates.append(candidate)
        candidates.sort(key=lambda item: (-item["score"], item["file"], item["start_line"]))
        _test_links(files, candidates[:top])
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
            "signature": signature,
            "candidates": candidates[:top],
            "candidate_count": len(candidates),
        })

    with_candidates = [item for item in results if item["candidates"]]
    return {
        "schema_version": "2.1.0",
        "tool": "pohe-agent",
        "method": {
            "name": "scope-anchored evidence triangulation",
            "version": "1.1.0",
            "signature_version": signatures.get("version", "unknown"),
        },
        "root": str(root.resolve()),
        "corpus": {
            "files_scanned": len(files),
            "code": sum(1 for item in files if item.kind == "code"),
            "test": sum(1 for item in files if item.kind == "test"),
            "support": sum(1 for item in files if item.kind == "support"),
            "skipped": skipped[:50],
        },
        "summary": {
            "records": len(results),
            "with_candidates": len(with_candidates),
            "structural_candidates": sum(
                1 for item in with_candidates
                if item["candidates"][0]["verdict"] in {"structural_candidate", "pointcut_candidate", "source_matched"}
            ),
            "pointcut_candidates": sum(
                1 for item in with_candidates
                if item["candidates"][0]["verdict"] in {"pointcut_candidate", "source_matched"}
            ),
            "source_matched": sum(
                1 for item in with_candidates if item["candidates"][0]["verdict"] == "source_matched"
            ),
            "rejected": sum(
                1 for item in with_candidates if item["candidates"][0]["verdict"] == "rejected"
            ),
        },
        "patterns": results,
    }


def _dedupe_hits(hits: list[dict]) -> list[dict]:
    seen: set[int] = set()
    unique: list[dict] = []
    for hit in hits:
        if hit["line"] in seen:
            continue
        seen.add(hit["line"])
        unique.append(hit)
    return unique


def why(candidate: dict, record: dict) -> str:
    structure = candidate["dimensions"]["structure"]
    missing = structure["missing"]
    negative = candidate["negative_control"]["status"]
    return (
        f"{candidate['scope_kind']} {candidate['symbol']} at {candidate['file']}:"
        f"{candidate['start_line']} has {len(structure['matched'])}/{len(structure['primary'])} "
        f"structure roles; missing {', '.join(missing) if missing else 'none'}; "
        f"negative control {negative}."
    )


def analyze_to_markdown(result: dict) -> str:
    summary = result["summary"]
    corpus = result["corpus"]
    lines = [
        "# Scope-anchored pattern analysis",
        "",
        f"- Repository: `{result['root']}`",
        f"- Files scanned: {corpus['files_scanned']} "
        f"({corpus['code']} code, {corpus['test']} test, {corpus['support']} support)",
        f"- Records with a candidate: {summary['with_candidates']} of {summary['records']}",
        f"- Source-level candidates: {summary['source_matched']}; "
        f"pointcut candidates: {summary['pointcut_candidates']}; "
        f"structural candidates: {summary['structural_candidates']}",
        "",
        "> **What this report is.** Each cue is anchored to the smallest enclosing",
        "> declaration. The scope is then checked against an operational signature:",
        "> the observable roles the record needs, kept separate from its prose",
        "> pointcut. A signature is a detection contract, not proof that the pointcut",
        "> or contract is satisfied. Contract probes report visible mechanisms only.",
        "",
        "## How to read a verdict",
        "",
        "| Verdict | Meaning |",
        "| --- | --- |",
        "| `rejected` | The scope matches the record's negative-control contrast. |",
        "| `cue_only` | A cue is present, but structure is missing or contradicted. |",
        "| `structural_candidate` | At least one structure role is supported; context, trigger, or effect still needs review. |",
        "| `pointcut_candidate` | Context, structure, and effect are supported; one or more structure roles are still missing. |",
        "| `source_matched` | All four dimensions are supported and every signature role is visible. Contract fields remain open. |",
        "",
    ]
    for pattern in result["patterns"]:
        if not pattern["candidates"]:
            continue
        signature = pattern["signature"]
        lines.append(f"## {pattern['id']} — {pattern['name']}")
        lines.append("")
        lines.append(
            "Signature: "
            f"context {', '.join(signature['context'])} · "
            f"trigger {', '.join(signature['trigger'])} · "
            f"structure {', '.join(signature['structure'])} · "
            f"effect {', '.join(signature['effect'])}"
        )
        lines.append("")
        lines.append(f"Negative control: {pattern['negative_control']}")
        lines.append("")
        lines.append("| Verdict | Scope | Structure | Missing roles | Control |")
        lines.append("| --- | --- | ---: | --- | --- |")
        for candidate in pattern["candidates"]:
            structure = candidate["dimensions"]["structure"]
            control = candidate["negative_control"]["status"]
            lines.append(
                f"| `{candidate['verdict']}` | `{candidate['file']}:{candidate['start_line']}` "
                f"`{candidate['symbol']}` ({candidate['scope_kind']}) | "
                f"{len(structure['matched'])}/{len(structure['primary'])} | "
                f"{', '.join(structure['missing']) or 'none'} | {control} |"
            )
        lines.append("")
        top = pattern["candidates"][0]
        lines.append(f"### Lead candidate — `{top['symbol']}`")
        lines.append("")
        lines.append(
            f"`{top['file']}:{top['start_line']}` ({top['scope_kind']}, "
            f"{top['source_kind']}, cue hits {top['cue_hits']} via "
            f"{'+'.join(top.get('cue_sources', [])) or 'unknown'}, "
            f"{'aggregate scope' if top['aggregated'] else 'direct scope'})"
        )
        lines.append("")
        for key in ("context", "trigger", "structure", "effect"):
            dimension = top["dimensions"][key]
            lines.append(
                f"- **{key.title()}**: {dimension['status']} "
                f"({len(dimension['matched'])}/{len(dimension['primary'])}; "
                f"matched {', '.join(dimension['matched']) or 'none'}"
                f"{'; missing ' + ', '.join(dimension['missing']) if dimension['missing'] else ''})"
            )
        controls = top["negative_control"]["checks"]
        if controls:
            lines.append("- **Negative control**: " + "; ".join(
                f"{check['code']} {check['status']}" for check in controls
            ))
        lines.append("")
        lines.append("Contract probes:")
        lines.append("")
        for probe in top["contract_probes"]:
            lines.append(
                f"- `{probe['field']}` — {probe['status']}: {probe['observation']}"
            )
            lines.append(f"  - Claim: {probe['claim']}")
        lines.append("")
        if top["tests"]:
            lines.append("Test evidence (linkage only; not contract proof):")
            lines.append("")
            for test in top["tests"]:
                lines.append(f"- `{test['file']}:{test['line']}` — `{_md(test['text'])}`")
        else:
            lines.append("Test evidence: no test reference found for the candidate symbol.")
        lines.append("")
        lines.append(f"Why this ranked first: {top['why']}")
        lines.append("")
        lines.append("Excerpt:")
        lines.append("")
        lines.append("```text")
        for item in top["excerpt"]:
            lines.append(f"{item['line']:>5}  {item['text']}")
        lines.append("```")
        lines.append("")
    missing = [item for item in result["patterns"] if not item["candidates"]]
    if missing:
        lines.append("## Records without a structural candidate")
        lines.append("")
        lines.append(", ".join(f"{item['id']} {item['name']}" for item in missing))
        lines.append("")
        lines.append(
            "This is not evidence of absence. The operational signature, cue vocabulary, "
            "or file boundary may have missed a mechanism; inspect the record's negative "
            "control before concluding that it is absent."
        )
        lines.append("")
    lines.extend([
        "## Commands",
        "",
        "```bash",
        "pohe-agent analyze <repo> --pattern P01 --markdown analysis.md",
        "pohe-agent analyze <repo> --min-verdict pointcut_candidate --json packets.json",
        "```",
        "",
    ])
    return "\n".join(lines)


def _md(text: str) -> str:
    return text.replace("`", "'")
