"""Command-line interface for pohe-agent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .analyze import analyze_repository, analyze_to_markdown
from .catalog import load_catalog, select
from .match import match_repository
from .plan import build_plan
from .report import match_to_markdown, scan_to_markdown
from .scan import scan_repository
from .signatures import load_signatures


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def cmd_list(args: argparse.Namespace) -> None:
    catalog = load_catalog()
    for record in select(catalog, args.patterns):
        print(f"{record['id']:>3}  {record['family']}  {record['name']}")
        print(f"      join point: {record['join_point']}")


def cmd_show(args: argparse.Namespace) -> None:
    catalog = load_catalog()
    record = next((item for item in catalog["patterns"] if item["id"] == args.id), None)
    if record is None:
        raise SystemExit(f"unknown record: {args.id}")
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return
    print(f"{record['id']} — {record['name']}")
    print(f"Family: {record['family']} — {record['family_name']}")
    print(f"Activities: {', '.join(record['activities'])}")
    print(f"Join point: {record['join_point']}")
    print()
    print("Pointcut")
    for key in ("context", "trigger", "structure", "effect"):
        print(f"  {key.title()}: {record['pointcut'][key]}")
    print()
    print("Contract")
    for key in ("requires", "ensures", "invariant", "violation"):
        print(f"  {key.title()}: {record[key]}")
    print()
    print(f"Variation: {record['variation']}")
    print(f"Negative control: {record['negative_control']}")
    print(f"Test obligation: {record['test_obligation']}")
    print(f"Evolution question: {record['evolution_question']}")
    print(f"Lexical cue: {record['regex']}")
    if record.get("canonical"):
        print(f"Canonical exemplar: {record['canonical']['url']}")


def cmd_scan(args: argparse.Namespace) -> None:
    result = scan_repository(Path(args.repo), max_files=args.max_files)
    if args.patterns:
        result = filter_patterns(result, args.patterns)
    if args.json:
        write_json(Path(args.json), result)
    if args.markdown:
        write_text(Path(args.markdown), scan_to_markdown(result, Path(args.repo)))
    if not args.json and not args.markdown:
        print(scan_to_markdown(result, Path(args.repo)))


def cmd_match(args: argparse.Namespace) -> None:
    result = match_repository(Path(args.repo), pattern_spec=args.pattern, max_files=args.max_files)
    if args.json:
        write_json(Path(args.json), result)
    if args.markdown:
        write_text(Path(args.markdown), match_to_markdown(result))
    if not args.json and not args.markdown:
        print(match_to_markdown(result))


def cmd_analyze(args: argparse.Namespace) -> None:
    signatures = load_signatures(Path(args.signatures)) if args.signatures else None
    result = analyze_repository(
        Path(args.repo),
        signatures=signatures,
        pattern_spec=args.pattern,
        max_files=args.max_files,
        top=args.top,
        min_verdict=args.min_verdict,
        include_tests=args.include_tests,
    )
    if args.json:
        write_json(Path(args.json), result)
    if args.markdown:
        write_text(Path(args.markdown), analyze_to_markdown(result))
    if not args.json and not args.markdown:
        print(analyze_to_markdown(result))


def cmd_plan(args: argparse.Namespace) -> None:
    findings_path = Path(args.findings)
    scan_result = json.loads(findings_path.read_text(encoding="utf-8"))
    plan = build_plan(scan_result, load_catalog(), args.goal, args.patterns)
    if args.output:
        write_text(Path(args.output), plan)
    else:
        print(plan)


def filter_patterns(result: dict, spec: str) -> dict:
    selected = {record["id"] for record in select(load_catalog(), spec)}
    result = dict(result)
    result["patterns"] = [item for item in result["patterns"] if item["id"] in selected]
    observed = [item for item in result["patterns"] if item["status"] == "observed"]
    result["summary"] = {
        **result["summary"],
        "records": len(result["patterns"]),
        "observed": len(observed),
        "not_observed": len(result["patterns"]) - len(observed),
        "high_priority": sum(1 for item in observed if item["priority"] == "high"),
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pohe-agent",
        description="Detect POHE harness design patterns and build pattern-guided evolution plans.",
    )
    parser.add_argument("--version", action="version", version=f"pohe-agent {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list catalog records")
    list_parser.add_argument("--patterns", help="comma-separated ids or families")
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="show one record")
    show_parser.add_argument("id")
    show_parser.add_argument("--json", action="store_true")
    show_parser.set_defaults(func=cmd_show)

    scan_parser = subparsers.add_parser("scan", help="retrieve lexical cues from a repository")
    scan_parser.add_argument("repo")
    scan_parser.add_argument("--json", help="write JSON findings")
    scan_parser.add_argument("--markdown", help="write a Markdown report")
    scan_parser.add_argument("--patterns", help="restrict output to ids or families")
    scan_parser.add_argument(
        "--max-files", type=int, default=0,
        help="cap candidate files; 0 keeps every candidate (default)",
    )
    scan_parser.set_defaults(func=cmd_scan)

    match_parser = subparsers.add_parser("match", help="extract structural candidates")
    match_parser.add_argument("repo")
    match_parser.add_argument("--pattern", help="comma-separated ids or families; default all")
    match_parser.add_argument("--json", help="write JSON candidates")
    match_parser.add_argument("--markdown", help="write a Markdown packet")
    match_parser.add_argument(
        "--max-files", type=int, default=0,
        help="cap candidate files; 0 keeps every candidate (default)",
    )
    match_parser.set_defaults(func=cmd_match)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="anchor cues to scopes and check operational signatures",
    )
    analyze_parser.add_argument("repo")
    analyze_parser.add_argument("--pattern", help="comma-separated ids or families; default all")
    analyze_parser.add_argument("--json", help="write JSON evidence packets")
    analyze_parser.add_argument("--markdown", help="write a Markdown analysis report")
    analyze_parser.add_argument("--signatures", help="override the bundled signature file")
    analyze_parser.add_argument("--top", type=int, default=5, help="candidates per record (default 5)")
    analyze_parser.add_argument(
        "--min-verdict",
        default="cue_only",
        choices=("rejected", "cue_only", "structural_candidate", "pointcut_candidate", "source_matched"),
        help="drop candidates below this verdict (default cue_only)",
    )
    analyze_parser.add_argument(
        "--include-tests", action="store_true",
        help="allow test scopes as primary candidates (default: tests are linkage only)",
    )
    analyze_parser.add_argument(
        "--max-files", type=int, default=0,
        help="cap candidate files; 0 keeps every candidate (default)",
    )
    analyze_parser.set_defaults(func=cmd_analyze)


    plan_parser = subparsers.add_parser("plan", help="build a pattern-guided evolution plan")
    plan_parser.add_argument("repo")
    plan_parser.add_argument("--findings", required=True, help="scan JSON written by this tool")
    plan_parser.add_argument("--goal", required=True, help="the evolution goal")
    plan_parser.add_argument("--patterns", help="comma-separated ids; default high/medium priority")
    plan_parser.add_argument("-o", "--output", help="write the plan; default stdout")
    plan_parser.set_defaults(func=cmd_plan)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
