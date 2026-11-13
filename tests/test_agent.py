from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pohe_agent.catalog import load_catalog
from pohe_agent.match import match_repository
from pohe_agent.plan import build_plan
from pohe_agent.report import scan_to_markdown
from pohe_agent.scan import scan_repository
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
