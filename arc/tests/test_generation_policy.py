"""Regression tests for source-first scheduling and derived-test trust."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from acceptance import RunSummary, TestOutcome
from derived_case_review import collect_cases, sha, validate_review
from generation_policy import classify_observation, first_level_phases, phase_context
from main import Flow


def leaf(ident, dependencies=()):
    return {"id": ident, "type": "ATOMIC", "name": ident,
            "description": "Save a record and report its value.", "dependencies": list(dependencies)}


class GenerationPolicyTests(unittest.TestCase):
    def test_generated_spec_is_snapshotted_before_independent_review_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tests = root / ".arc/derived-tests"
            tests.mkdir(parents=True)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.md").write_text("official requirements\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, requirements)
            flow.tests_dir = flow.derived_tests_dir = tests
            flow.derived_as_specs = True
            flow.metric = Mock()
            flow.derived_scenario_coverage = Mock(return_value={"covered": 1, "total": 1})
            flow.adopt_derived_specs = Mock()

            def generate(_):
                (tests / "A.spec.ts").write_text("test('approved', () => {});\n")
                (tests / "review").mkdir(exist_ok=True)
                (tests / "review/plan.json").write_text('{"accepted": true}\n')

            def review(_):
                self.assertEqual(flow.restore_protected(), [])
                self.assertIn("approved", (tests / "A.spec.ts").read_text())
                (tests / "A.spec.ts").write_text("test('weakened', () => {});\n")
                self.assertTrue(flow.restore_protected())
                self.assertIn("approved", (tests / "A.spec.ts").read_text())

            flow.augment_derived_tests = Mock(side_effect=generate)
            flow.review_derived_cases = Mock(side_effect=review)
            flow.prepare_derived_spec_batch([leaf("A")])
            self.assertIn("approved", (tests / "A.spec.ts").read_text())
            self.assertEqual((tests / "review/plan.json").read_text(), '{"accepted": true}\n')

    def test_cross_category_cycle_is_a_contract_edge_not_a_gate(self):
        tree = {"id": "ROOT", "type": "FOLDER", "children": [
            {"id": "REQ-1", "type": "FOLDER", "name": "Editing", "children":
             [leaf("REQ-1-1", ["REQ-2-1"]), leaf("REQ-1-2")]},
            {"id": "REQ-2", "type": "FOLDER", "name": "Analysis", "children":
             [leaf("REQ-2-1", ["REQ-1-1"])]},
        ]}
        plan = first_level_phases(tree, {"routes": [{"method": "GET", "path": "/records",
            "purpose": "Read records", "requirements": ["REQ-1-1", "REQ-2-1"]}]})
        self.assertEqual(set(plan["leaf_phase"]), {"REQ-1-1", "REQ-1-2", "REQ-2-1"})
        self.assertEqual([len(p["cross_dependencies"]) for p in plan["phases"]], [1, 1])
        self.assertEqual({item["owner"] for phase in plan["phases"] for item in phase["artifacts"]},
                         {"REQ-1"})
        self.assertIn("REQ-2-1", phase_context(plan, ["REQ-1-1"]))
        self.assertNotIn("Analysis: leaves", phase_context(plan, ["REQ-1-1"]))

    def test_generated_reach_timeout_is_low_signal_even_if_case_was_approved(self):
        self.assertEqual(classify_observation("not reachable within 3 navigation clicks",
                                              source="derived", reliable=True)[0], "T")
        self.assertEqual(classify_observation("SyntaxError: missing export",
                                              source="runtime", reliable=True)[0], "F0")
        self.assertEqual(classify_observation("backend: data is not iterable",
                                              source="runtime", reliable=True)[0], "F0")
        self.assertEqual(classify_observation("other spec failed to load",
                                              source="runtime", reliable=True)[0], "I")
        self.assertEqual(classify_observation("expected account to remain signed in",
                                              source="derived", reliable=True, core=True)[0], "F1")
        self.assertEqual(classify_observation("Unauthorized access: expected 403, received 200",
                                              source="official", reliable=True, core=True)[0], "F0")
        self.assertEqual(classify_observation("Unauthorized access: expected 403, received 200",
                                              source="derived", reliable=True, core=True)[0], "F0")
        self.assertEqual(classify_observation("Unauthorized access: expected 403, received 200",
                                              source="derived", reliable=False, core=True)[0], "T")

    def test_independent_case_review_requires_exact_witness_and_stales_on_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = ("test('REQ-1-1: Scenario 1 [model]', async ({ page }) => {\n"
                      "  await h.clickNamed(page, 'Save record');\n"
                      "  await h.expectTextsVisible(page, ['Record saved successfully']);\n});\n")
            path = directory / "REQ-1-1.spec.ts"
            path.write_text(source)
            target = {"id": "S1", "node_id": "REQ-1-1", "title": "REQ-1-1: Scenario 1",
                      "description": "After Save record, display Record saved successfully.",
                      "steps": ["WHEN: click Save record", "THEN: Record saved successfully"],
                      "required_actions": ["Save record"], "required_then_literal": "Record saved successfully"}
            rows = collect_cases(directory, [target], {"REQ-1-1"})
            self.assertEqual(len(rows), 1)
            decision = {"status": "approved_behavior", "requirement_quote": target["description"],
                        "test_quote": "await h.expectTextsVisible(page, ['Record saved successfully']);",
                        "reason": "The action precedes a grounded assertion."}
            self.assertTrue(validate_review(rows[0], decision))
            decision["test_quote"] = "await h.expectTextsVisible(page, ['Record saved']);"
            self.assertFalse(validate_review(rows[0], decision))
            flow = Flow(argparse.Namespace(web_port=3000), directory, directory)
            flow.tests_dir = flow.derived_tests_dir = directory
            flow.derived_as_specs = True
            flow._derived_scenario_targets = [target]
            rows[0]["status"] = "approved_behavior"
            rows[0]["helper_hash"] = ""
            from scenario_tests import suite_fixtures
            rows[0]["fixture_hash"] = sha(str(suite_fixtures([])))
            flow.derived_case_reviews = {("REQ-1-1", rows[0]["title"]): rows[0]}
            self.assertTrue(flow.trusted_derived_case("REQ-1-1", rows[0]["title"]))
            path.write_text(source + "\n// changed after approval\n")
            self.assertFalse(flow.trusted_derived_case("REQ-1-1", rows[0]["title"]))
            path.write_text(source)
            target["description"] = "The requirement changed after review."
            self.assertFalse(flow.trusted_derived_case("REQ-1-1", rows[0]["title"]))

    def test_unreviewed_generated_pass_is_not_recorded_as_product_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_case_reviews = {}
            flow.runtime = SimpleNamespace(traceability=SimpleNamespace(upsert_test=Mock()))
            outcome = TestOutcome("REQ-1-1: Scenario 1 [reach]", True, "passed", 1,
                                  file="REQ-1-1.spec.ts")
            flow.record_tests("REQ-1-1", ["REQ-1-1.spec.ts"], RunSummary(results=[outcome], total=1, passed=1))
            flow.runtime.traceability.upsert_test.assert_not_called()

    def test_final_generated_measurement_selects_reviewed_files_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "A.spec.ts").write_text("test('A: approved', async () => {});\n")
            (root / "B.spec.ts").write_text("test('B: reach', async () => {});\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.tests_dir = root
            flow.derived_as_specs = True
            flow.runner = SimpleNamespace(timeout_ms=1000)
            flow.trusted_derived_case = Mock(side_effect=lambda node, title: node == "A")
            flow.remaining = Mock(return_value=1000)
            flow.final_measurement_reserve = Mock(return_value=100)
            flow.run_specs = Mock(return_value=RunSummary(results=[
                TestOutcome("A: approved", True, "passed", 1, file="A.spec.ts")], total=1, passed=1))
            flow.suite_is_measured = Mock(return_value=True)
            flow.record_full_suite = Mock()
            flow.final_acceptance_passes()
            flow.run_specs.assert_called_once_with(["A.spec.ts"], workers=1, grader_like=True)
            flow.record_full_suite.assert_called_once()

    def test_generated_load_check_only_rechecks_changed_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / ".arc/derived-tests"
            directory.mkdir(parents=True)
            (directory / "A.spec.ts").write_text("test('A', () => {});\n")
            (directory / "B.spec.ts").write_text("test('B', () => {});\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_tests_dir = directory
            flow.runner = SimpleNamespace(list_specs=Mock(return_value=(True, "")))
            flow.snapshot_protected = Mock()
            flow.verify_derived_suite()
            flow.verify_derived_suite()
            (directory / "B.spec.ts").write_text("test('B changed', () => {});\n")
            flow.verify_derived_suite()
            self.assertEqual([call.args[0] for call in flow.runner.list_specs.call_args_list],
                             [["A.spec.ts", "B.spec.ts"], ["B.spec.ts"]])

    def test_changed_good_spec_does_not_clear_unchanged_blocked_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / ".arc/derived-tests"
            directory.mkdir(parents=True)
            (directory / "A.spec.ts").write_text("test('A', () => {});\n")
            (directory / "B.spec.ts").write_text("BROKEN")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_tests_dir = flow.tests_dir = directory
            flow.derived_as_specs = True
            def load(paths):
                return (False, "SyntaxError") if "B.spec.ts" in paths else (True, "")
            flow.runner = SimpleNamespace(list_specs=Mock(side_effect=load))
            flow.snapshot_protected = Mock()
            flow.verify_derived_suite()
            (directory / "A.spec.ts").write_text("test('A changed', () => {});\n")
            flow.verify_derived_suite()
            self.assertEqual(len(flow.generated_load_errors(["B.spec.ts"])), 1)
            self.assertFalse(flow.derived_suite_verified)

    def test_low_signal_self_audit_keeps_requirement_and_source_evidence_without_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "backend/server.js"
            source.parent.mkdir(parents=True)
            source.write_text("const app = require('express')();\napp.get('/records', readRecords);\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.requirement_nodes = {"A": {"id": "A", "description": "Save the record before reloading it."}}
            flow.phase_plan = {"phases": [{"id": "P", "leaves": ["A"],
                                            "artifacts": [{"path": "backend/server.js"}]}]}
            flow.whole_app_wave_gaps = Mock(return_value=[])
            flow.self_audit_node("A", "reach depth exceeded")
            row = json.loads((root / ".arc/review/source-self-audit.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["requirement_excerpt"], "Save the record before reloading it.")
            self.assertIn("backend/server.js", row["source_paths"])
            self.assertIn("/records", row["source_contracts"])
            self.assertEqual(row["status"], "reviewed_unverified")
            self.assertEqual(source.read_text(), "const app = require('express')();\napp.get('/records', readRecords);\n")

    def test_self_audit_maps_planned_url_and_reports_missing_static_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            route = root / "backend/routes/orgs.js"
            route.parent.mkdir(parents=True)
            route.write_text("const {orgs, collaborators} = require('../collections/orgs');\n"
                             "app.get('/api/orgs', () => collaborators.all());\n")
            collection = root / "backend/collections/orgs.js"
            collection.parent.mkdir(parents=True)
            collection.write_text("const orgs = {};\nmodule.exports = {orgs};\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.requirement_nodes = {"A": {"id": "A", "description": "List organizations."}}
            flow.phase_plan = {"phases": [{"id": "P", "leaves": ["A"],
                                           "artifacts": [{"path": "/api/orgs"}]}]}
            flow.whole_app_wave_gaps = Mock(return_value=[])
            flow.self_audit_node("A", "low signal test")
            row = json.loads((root / ".arc/review/source-self-audit.jsonl").read_text().splitlines()[0])
            self.assertIn("backend/routes/orgs.js", row["source_paths"])
            self.assertTrue(any("collaborators" in gap for gap in row["static_gaps"]))
            self.assertEqual(row["status"], "reviewed_unverified")

    def test_unreviewed_failure_cannot_enter_application_repair_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_tests_dir = flow.tests_dir = root
            flow.derived_case_reviews = {}
            outcome = TestOutcome(title="REQ-1-1: Scenario 1 [reach]", ok=False,
                                  status="failed", duration_ms=5, file="REQ-1-1.spec.ts",
                                  message="not reachable within 3 navigation clicks")
            summary = RunSummary(results=[outcome], total=1, passed=0)
            self.assertEqual(flow.disputed_generated_failures(summary), [("REQ-1-1", outcome.title)])
            self.assertEqual(flow.uncontested_derived_results(summary).total, 0)


if __name__ == "__main__":
    unittest.main()
