from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pohe_agent.analyze import NEGATIVE_RULES, analyze_repository, analyze_to_markdown, compile_cue
from pohe_agent.catalog import load_catalog
from pohe_agent.features import TAG_RULES, evaluate_tags, extract_facts, extract_scopes
from pohe_agent.match import match_repository
from pohe_agent.plan import build_plan
from pohe_agent.report import scan_to_markdown
from pohe_agent.scan import scan_repository
from pohe_agent.signatures import load_signatures
from pohe_agent.walk import walk_repository

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "mini_harness"


class CatalogTests(unittest.TestCase):
    def test_catalog_has_52_unique_records(self) -> None:
        catalog = load_catalog()
        self.assertEqual(len(catalog["patterns"]), 52)
        ids = [record["id"] for record in catalog["patterns"]]
        self.assertEqual(len(ids), len(set(ids)))
        for record in catalog["patterns"]:
            self.assertEqual(set(record["pointcut"]), {"context", "trigger", "structure", "effect"})
            self.assertTrue(record["regex"])
            self.assertTrue(record["negative_control"])


class WalkTests(unittest.TestCase):
    def test_walk_excludes_dependency_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("while True: pass\n")
            (root / "node_modules" / "dep").mkdir(parents=True)
            (root / "node_modules" / "dep" / "index.js").write_text("while (true) {}\n")
            files, _ = walk_repository(root)
            self.assertEqual([item.rel for item in files], ["app.py"])

    def test_file_budget_keeps_code_before_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(3):
                (root / f"docs-{index}.md").write_text("# notes\n")
            (root / "runtime").mkdir()
            (root / "runtime" / "loop.py").write_text("while True: pass\n")
            files, skipped = walk_repository(root, max_files=2)
            self.assertEqual([item.rel for item in files], ["runtime/loop.py", "docs-0.md"])
            self.assertTrue(any("file limit reached" in note for note in skipped))


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = scan_repository(FIXTURE)

    def test_summary_is_consistent(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["records"], 52)
        self.assertEqual(summary["observed"] + summary["not_observed"], 52)
        self.assertEqual(summary["observed"], sum(1 for item in self.result["patterns"] if item["status"] == "observed"))

    def test_example_harness_retrieves_known_cues(self) -> None:
        observed = {item["id"]: item for item in self.result["patterns"] if item["status"] == "observed"}
        self.assertIn("P01", observed)
        self.assertIn("P09", observed)
        self.assertEqual(observed["P01"]["evidence_level"], "E1")
        self.assertTrue(observed["P01"]["matches"])
        self.assertTrue(any(match["kind"] == "code" for match in observed["P01"]["matches"]))

    def test_report_carries_the_evidence_boundary(self) -> None:
        report = scan_to_markdown(self.result, FIXTURE)
        self.assertIn("Evidence boundary", report)
        self.assertIn("not a confirmed", report)
        self.assertIn("implementation, pointcut match, or contract proof", report)
        self.assertIn("P01", report)
        self.assertIn("Negative control", report)


class MatchTests(unittest.TestCase):
    def test_symbol_level_candidate(self) -> None:
        result = match_repository(FIXTURE, pattern_spec="P09")
        candidates = result["patterns"][0]["candidates"]
        self.assertTrue(any(item["symbol"] == "discover_tools" for item in candidates))

    def test_cue_in_symbol_body_is_a_candidate(self) -> None:
        result = match_repository(FIXTURE, pattern_spec="P01")
        candidates = result["patterns"][0]["candidates"]
        runner = next(item for item in candidates if item["symbol"] == "run_agent")
        self.assertEqual(runner["reason"], "cue in symbol body")



class SignatureTests(unittest.TestCase):
    def test_signatures_cover_every_record_and_use_known_tags(self) -> None:
        catalog = load_catalog()
        signatures = load_signatures()
        ids = {record["id"] for record in catalog["patterns"]}
        self.assertEqual(set(signatures["patterns"]), ids)
        for pattern_id, signature in signatures["patterns"].items():
            with self.subTest(pattern=pattern_id):
                for dimension in ("context", "trigger", "structure", "effect"):
                    self.assertTrue(signature[dimension])
                    for tag in signature[dimension]:
                        self.assertIn(tag, TAG_RULES)
                for code in signature["negative"]:
                    self.assertIn(code, NEGATIVE_RULES)
                for cue in signature.get("cues", []):
                    self.assertIsInstance(cue, str)
                    self.assertTrue(cue.strip())


class CueTests(unittest.TestCase):
    def test_boundaries_treat_underscores_and_camel_case_as_separators(self) -> None:
        underscore = compile_cue(r"\bprompt[_-]?cache\b")
        camel = compile_cue(r"\bgroup[_-]?chat[_-]?manager\b")
        self.assertTrue(underscore.search("PROMPT_CACHE_KEY_FIELD = 'prompt_cache_key'"))
        self.assertTrue(camel.search("class BaseGroupChatManager(ABC):"))

    def test_operational_cue_recovers_an_exemplar_the_frozen_cue_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_agent_hooks.py").write_text(
                "AGENT_HOOKS = {\n"
                "    'pre_model_call': pre_model_call,\n"
                "    'post_tool_call': post_tool_call,\n"
                "}\n"
            )
            result = analyze_repository(root, pattern_spec="P16", top=10, min_verdict="rejected")
            candidates = result["patterns"][0]["candidates"]
            self.assertTrue(candidates)
            self.assertTrue(any("operational" in item["cue_sources"] for item in candidates))
            self.assertTrue(all("lexical" not in item["cue_sources"] for item in candidates))

    def test_frozen_cue_reaches_snake_case_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cache.py").write_text(
                "PROMPT_CACHE_KEY_FIELD = 'prompt_cache_key'\n"
                "def resolve(model, settings):\n"
                "    if settings.prompt_cache_key:\n"
                "        return settings.prompt_cache_key\n"
                "    return None\n"
            )
            result = analyze_repository(root, pattern_spec="P07", top=10, min_verdict="rejected")
            candidates = result["patterns"][0]["candidates"]
            self.assertTrue(any("lexical" in item["cue_sources"] for item in candidates))

    def test_call_and_return_syntax_do_not_create_role_tags(self) -> None:
        code = "def f(helper):\n    return helper()\n"
        scope = extract_scopes(code, "f.py", ".py")[0]
        tags = evaluate_tags(extract_facts(code, scope, ".py"))
        for tag in ("fanout", "aggregate", "reducer", "yield"):
            self.assertNotIn(tag, tags)


class AnalyzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = analyze_repository(FIXTURE, pattern_spec="P01,P09,P19", top=5)

    def test_p01_anchors_to_the_function_and_passes_the_signature(self) -> None:
        pattern = self.result["patterns"][0]
        top = pattern["candidates"][0]
        self.assertEqual(top["symbol"], "run_agent")
        self.assertEqual(top["scope_kind"], "method")
        self.assertEqual(top["verdict"], "source_matched")
        self.assertEqual(top["dimensions"]["structure"]["missing"], [])
        self.assertEqual(top["negative_control"]["status"], "clear")
        self.assertTrue(any(item["file"] == "tests/test_loop.py" for item in top["tests"]))

    def test_p09_records_the_missing_authorization_role(self) -> None:
        pattern = next(item for item in self.result["patterns"] if item["id"] == "P09")
        top = pattern["candidates"][0]
        self.assertEqual(top["file"], "runtime/tools.py")
        self.assertIn("authorization", top["dimensions"]["structure"]["missing"])
        self.assertNotEqual(top["verdict"], "source_matched")

    def test_one_shot_function_is_rejected_by_the_negative_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime.py").write_text(
                "def run_loop(task, model):\n"
                "    return model.complete(task)\n"
            )
            result = analyze_repository(root, pattern_spec="P01", top=3, min_verdict="rejected")
            top = result["patterns"][0]["candidates"][0]
            self.assertEqual(top["verdict"], "rejected")
            self.assertTrue(any(
                check["code"] == "one_shot" and check["status"] == "risk"
                for check in top["negative_control"]["checks"]
            ))

    def test_tests_are_linkage_not_primary_candidates(self) -> None:
        self.assertTrue(all(
            candidate["source_kind"] != "test"
            for pattern in self.result["patterns"]
            for candidate in pattern["candidates"]
        ))
        with_tests = analyze_repository(
            FIXTURE, pattern_spec="P01", top=10, include_tests=True, min_verdict="rejected"
        )
        self.assertTrue(any(
            candidate["source_kind"] == "test"
            for candidate in with_tests["patterns"][0]["candidates"]
        ))

    def test_report_preserves_the_evidence_boundary(self) -> None:
        report = analyze_to_markdown(self.result)
        self.assertIn("operational signature", report)
        self.assertIn("not proof", report)
        self.assertIn("Contract probes", report)
        self.assertIn("Negative control", report)
        self.assertIn("source_matched", report)
        self.assertIn("P01", report)


class PlanTests(unittest.TestCase):
    def test_plan_preserves_contract_and_review_status(self) -> None:
        scan = scan_repository(FIXTURE)
        plan = build_plan(scan, load_catalog(), "harden the runtime", "P01")
        self.assertIn("proposal for review", plan)
        self.assertIn("Protected contract", plan)
        self.assertIn("Negative control", plan)
        self.assertIn("P01", plan)
        self.assertIn("E1 retrieval cue", plan)


if __name__ == "__main__":
    unittest.main()
