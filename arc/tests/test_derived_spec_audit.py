"""Generated-spec corrections must precede application repairs and stay scoped."""
import argparse
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from derived_spec_audit import repair_failed_generated_specs, replace_failed_test_preserving_oracle
from main import Flow
from scenario_tests import Fixtures


SHEET = {
    "id": "REQ-1-3-1", "description": "Import CSV creates a workbook named after the file.",
    "scenarios": [{"steps": [{"keyword": "GIVEN", "content":
                              "The seeded workbook is `Q3 Sales` with cell A1 value `Region`."}]}],
}
RECOVERY = {
    "id": "REQ-1-1-3",
    "description": ("After the visitor enters an address in the Email field and clicks “Send reset link”, "
                    "the page shows the Verification code field."),
    "scenarios": [],
}


def outcome(title="bad", ok=False):
    return RunSummary(passed=int(ok), total=1, results=[TestOutcome(
        title=title, ok=ok, status="passed" if ok else "failed", duration_ms=1, file="REQ-1-3-1.spec.ts")])


class GeneratedSpecRepairTests(unittest.TestCase):
    def test_model_action_repair_must_keep_the_original_assertion(self):
        source = "test('bad [model]', async ({ page }) => {\n  await h.expectTextsVisible(page, ['Done']);\n});\n"
        weaker = "test('bad [model]', async ({ page }) => {\n  await h.expectTextsVisible(page, ['Open']);\n});\n"
        self.assertIsNone(replace_failed_test_preserving_oracle(source, "bad [model]", weaker))
        stronger = ("test('bad [model]', async ({ page }) => {\n"
                    "  await h.clickNamed(page, 'Open');\n"
                    "  await h.expectTextsVisible(page, ['Done']);\n});\n")
        self.assertIn("h.clickNamed(page, 'Open')",
                      replace_failed_test_preserving_oracle(source, "bad [model]", stronger))
    def test_csv_assertions_are_derived_from_uploaded_content_and_filename(self):
        source = ("import { test } from '@playwright/test';\n"
                  "test('bad', async ({ page }) => {\n"
                  "  await h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800');\n"
                  "  await h.clickNamed(page, 'Confirm import');\n"
                  "  await h.expectTextsVisible(page, ['Region']);\n"
                  "  await h.expectTextsVisible(page, ['derived-c514bf']);\n"
                  "});\n")
        fixed = repair_failed_generated_specs(source, ["bad"], SHEET, Fixtures())
        self.assertEqual(fixed.changed_titles, ("bad",))
        self.assertIn("h.expectCell(page, 'A1', 'East')", fixed.source)
        self.assertIn("h.expectTextsVisible(page, ['derived-import'])", fixed.source)
        self.assertNotIn("['Region']", fixed.source)
        self.assertNotIn("derived-c514bf", fixed.source)

    def test_conditionally_visible_field_requires_the_documented_action(self):
        source = ("test('bad', async ({ page }) => {\n"
                  "  await h.clickNamed(page, 'Forgot password');\n"
                  "  await h.expectReachable(page, 'Verification code');\n"
                  "});\n")
        fixed = repair_failed_generated_specs(source, ["bad"], RECOVERY,
                                              Fixtures(email="alice.dev@example.test"))
        self.assertIn("h.fillField(page, 'Email', 'alice.dev@example.test')", fixed.source)
        self.assertLess(fixed.source.index("Send reset link"), fixed.source.index("Verification code"))
        self.assertEqual(len(fixed.reasons), 1)

    def test_does_not_substitute_registered_fixture_into_unknown_email_scenario(self):
        node = dict(RECOVERY, scenarios=[{"name": "Unknown address", "steps": [
            {"keyword": "WHEN", "content": "The visitor enters an unknown email address."}]}])
        source = ("test('Unknown address [model]', async ({ page }) => {\n"
                  "  await h.expectReachable(page, 'Verification code');\n});\n")
        fixed = repair_failed_generated_specs(source, ["Unknown address [model]"], node,
                                              Fixtures(email="alice.dev@example.test"))
        self.assertEqual(fixed.source, source)

    def test_only_failed_tests_are_repaired(self):
        source = ("test('passed', async ({ page }) => {\n"
                  "  await h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800');\n"
                  "  await h.expectTextsVisible(page, ['Region']);\n});\n"
                  "test('bad', async ({ page }) => {\n"
                  "  await h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800');\n"
                  "  await h.expectTextsVisible(page, ['Region']);\n});\n")
        fixed = repair_failed_generated_specs(source, ["bad"], SHEET, Fixtures())
        self.assertIn("test('passed'", fixed.source)
        self.assertEqual(fixed.source.count("['Region']"), 1)

    def test_unknown_failure_is_not_rewritten(self):
        source = "test('bad', async ({ page }) => { await h.expectReachable(page, 'Settings'); });\n"
        self.assertEqual(repair_failed_generated_specs(source, ["bad"], RECOVERY, Fixtures()).source, source)

    def test_reopening_seeded_workbook_preserves_its_original_cell_assertion(self):
        source = ("test('bad', async ({ page }) => {\n"
                  "  await h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800');\n"
                  "  await h.clickNamed(page, 'Q3 Sales');\n"
                  "  await h.expectTextsVisible(page, ['Region']);\n});\n")
        fixed = repair_failed_generated_specs(source, ["bad"], SHEET, Fixtures())
        self.assertEqual(fixed.source, source)

    def test_multiple_uploads_are_not_guessed_from_the_first_file(self):
        source = ("test('bad', async ({ page }) => {\n"
                  "  await h.uploadFile(page, 'CSV file', 'East,1200');\n"
                  "  await h.uploadFile(page, 'CSV file', 'West,1000');\n"
                  "  await h.expectTextsVisible(page, ['Region']);\n});\n")
        fixed = repair_failed_generated_specs(source, ["bad"], SHEET, Fixtures())
        self.assertEqual(fixed.source, source)


class FlowAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.directory = self.root / ".arc" / "derived-tests"
        self.directory.mkdir(parents=True)
        self.path = self.directory / "REQ-1-3-1.spec.ts"
        self.path.write_text("test('bad', async ({ page }) => {\n"
                             "  await h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800');\n"
                             "  await h.expectTextsVisible(page, ['Region']);\n});\n")
        self.flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.tests_dir = self.directory
        self.flow.derived_tests_dir = self.directory
        self.flow.derived_as_specs = True
        self.flow.requirement_nodes = {SHEET["id"]: SHEET}
        self.flow.derived_nodes = [SHEET]
        self.flow.runner = SimpleNamespace(list_specs=Mock(return_value=(True, "")))
        self.flow.run_specs = Mock(return_value=outcome(ok=True))
        self.flow.snapshot_protected = Mock()

    def test_failed_generated_spec_is_load_checked_then_retested(self):
        observed = self.flow.audit_failed_derived_specs(SHEET["id"], [self.path.name], outcome())
        self.assertTrue(observed.all_passed)
        self.flow.runner.list_specs.assert_called_once_with([self.path.name])
        self.flow.run_specs.assert_called_once_with([self.path.name])
        self.flow.snapshot_protected.assert_called_once()
        self.assertIn("h.expectCell(page, 'A1', 'East')", self.path.read_text())
        self.assertEqual(len(list((self.root / ".arc" / "spec-audit" / SHEET["id"]).glob("*.spec.ts"))), 1)

    def test_standard_specs_are_never_rewritten(self):
        original = self.path.read_text()
        self.flow.derived_as_specs = False
        self.assertIsNone(self.flow.audit_failed_derived_specs(SHEET["id"], [self.path.name], outcome()))
        self.assertEqual(self.path.read_text(), original)
        self.flow.run_specs.assert_not_called()

    def test_same_title_in_passing_file_is_not_edited(self):
        other = self.directory / "other.spec.ts"
        other.write_text(self.path.read_text())
        summary = RunSummary(passed=1, total=2, results=[
            TestOutcome("bad", False, "failed", 1, file=self.path.name),
            TestOutcome("bad", True, "passed", 1, file=other.name),
        ])
        self.flow.audit_failed_derived_specs(SHEET["id"], [self.path.name, other.name], summary)
        self.assertIn("h.expectCell(page, 'A1', 'East')", self.path.read_text())
        self.assertIn("h.expectTextsVisible(page, ['Region'])", other.read_text())

    def test_load_failure_restores_original_spec(self):
        original = self.path.read_text()
        self.flow.runner.list_specs.return_value = (False, "parse error")
        self.assertIsNone(self.flow.audit_failed_derived_specs(SHEET["id"], [self.path.name], outcome()))
        self.assertEqual(self.path.read_text(), original)
        self.flow.snapshot_protected.assert_not_called()

    def test_acceptance_uses_corrected_spec_result_before_app_repair(self):
        self.flow.repair_rounds = 0
        self.flow.derived_review_needed = Mock(return_value=False)
        self.flow.head = Mock(return_value="head")
        self.flow.commit = Mock()
        self.flow.record_tests = Mock()
        self.flow.repair_source_index = Mock(return_value=SimpleNamespace(versions={}))
        self.flow.affected_regression_specs = Mock(return_value=[])
        result = self.flow.acceptance_loop(SHEET["id"], [self.path.name], time.time() + 120,
                                           initial_summary=outcome())
        self.assertTrue(result)
        self.flow.run_specs.assert_called_once_with([self.path.name])
        self.flow.commit.assert_called_once()

    def test_reach_only_pass_remains_unverified(self):
        self.path.write_text("test('entry [entry]', async ({ page }) => {});\n")
        self.flow.repair_rounds = 0
        self.flow.head = Mock(return_value="head")
        self.flow.record_tests = Mock()
        self.flow.commit = Mock()
        self.flow.repair_source_index = Mock(return_value=SimpleNamespace(versions={}))
        green = RunSummary(passed=1, total=1, results=[
            TestOutcome("entry [entry]", True, "passed", 1, file=self.path.name)])
        self.assertIsNone(self.flow.acceptance_loop(SHEET["id"], [self.path.name],
                                                     time.time() + 120, initial_summary=green))
        self.assertFalse(self.flow.last_node_own_pass)
        self.flow.commit.assert_not_called()
        self.flow.spec_map = {SHEET["id"]: [self.path.name]}
        self.flow.record_full_suite(green, {})
        self.assertIsNone(self.flow.test_verdict[SHEET["id"]])

    def test_each_scenario_needs_its_own_behavior_check(self):
        node = {"id": "REQ-2", "name": "Two outcomes", "description": "The page has controls “Open” and “Save”.",
                "scenarios": [{"name": title, "steps": [
                    {"keyword": "WHEN", "content": f"The visitor clicks “{action}”."},
                    {"keyword": "THEN", "content": f"The page shows “{result}”."}]}
                    for title, action, result in (("REQ-2: Open", "Open", "Opened"),
                                                  ("REQ-2: Save", "Save", "Saved"))]}
        self.flow.derived_nodes = [node]
        self.flow._derived_scenario_targets = None
        path = self.directory / "REQ-2.spec.ts"
        path.write_text("test('REQ-2: Open [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Opened']);\n});\n")
        coverage = self.flow.derived_scenario_coverage("REQ-2")
        self.assertEqual((coverage["covered"], coverage["total"]), (1, 2))
        self.assertTrue(self.flow.derived_review_needed("REQ-2"))
        self.flow.write_derived_coverage()
        report = json.loads((self.root / ".arc" / "derived-coverage.json").read_text())
        self.assertEqual(report["totals"], {"scenarios": 2, "covered": 1, "missing": 1, "disputed": 0})
        path.write_text(path.read_text() + "\ntest('REQ-2: Save [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Save');\n"
                        "  await h.expectTextsVisible(page, ['Saved']);\n});\n")
        self.assertFalse(self.flow.derived_review_needed("REQ-2"))

    def test_action_and_assertion_with_wrong_result_do_not_cover_scenario(self):
        node = {"id": "REQ-2", "name": "Open", "description": "Open shows Done.",
                "scenarios": [{"name": "REQ-2: Open", "steps": [
                    {"keyword": "WHEN", "content": "The visitor clicks “Open”."},
                    {"keyword": "THEN", "content": "The page shows “Done”."}]}]}
        self.flow.derived_nodes = [node]
        self.flow._derived_scenario_targets = None
        path = self.directory / "REQ-2.spec.ts"
        path.write_text("test('REQ-2: Open [script]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Open']);\n});\n")
        self.assertTrue(self.flow.derived_review_needed("REQ-2"))
        path.write_text(path.read_text().replace("['Open']", "['Done']"))
        self.assertFalse(self.flow.derived_review_needed("REQ-2"))

    def test_disputed_generated_oracle_blocks_application_repair(self):
        node = {"id": "REQ-1", "name": "Open", "description": "The page has “Open”.",
                "scenarios": [{"name": "REQ-1: action", "steps": [
                    {"keyword": "WHEN", "content": "The visitor clicks “Open”."},
                    {"keyword": "THEN", "content": "The page shows “Done”."}]}]}
        path = self.directory / "REQ-1.spec.ts"
        path.write_text("test('REQ-1: action [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Done']);\n});\n")
        self.flow.requirement_nodes = {"REQ-1": node}
        self.flow.derived_nodes = [node]
        self.flow._derived_scenario_targets = None
        self.flow.spec_map = {"REQ-1": [path.name]}
        self.path.unlink()
        self.flow.driver = object()
        self.flow.wound_down = Mock(return_value=False)
        self.flow.remaining = Mock(return_value=1000)
        self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.text_turn = Mock(return_value=(True,
            '{"verdict":"oracle_dispute","evidence":"The expected Done assertion may conflict with the requirement",'
            '"scenarios":[]}'))
        self.flow.node_repair_turn = Mock()
        self.flow.record_tests = Mock()
        failed = RunSummary(passed=0, total=1, results=[TestOutcome(
            "REQ-1: action [model]", False, "failed", 1, file=path.name)])
        self.assertIsNone(self.flow.acceptance_loop("REQ-1", [path.name], time.time() + 120,
                                                    initial_summary=failed))
        self.flow.node_repair_turn.assert_not_called()
        self.assertTrue(self.flow.derived_review_needed("REQ-1"))
        self.assertEqual(self.flow.derived_scenario_coverage("REQ-1")["scenarios"][0]["status"], "disputed")
        self.flow.final_acceptance(initial_summary=failed)
        self.assertTrue(self.flow.final_spec_dispute)
        self.assertIsNone(self.flow.test_verdict["REQ-1"])
        report = json.loads((self.root / ".arc" / "derived-coverage.json").read_text())
        self.assertEqual(report["features"][0]["scenarios"][0]["runtime"], "failed")
        self.flow.clear_derived_spec_dispute("REQ-1", "REQ-1: action [model]")
        self.flow.derived_failure_reviews.clear()
        self.flow.text_turn.return_value = (True, '{"verdict":"uncertain",'
                                                 '"evidence":"A locator race is possible", "scenarios":[]}')
        self.assertIsNone(self.flow.review_failed_derived_spec_with_model("REQ-1", [path.name], failed))
        self.assertEqual(self.flow.derived_spec_disputes, {})

    def test_related_regression_audits_its_spec_then_remeasures_both_features(self):
        other = self.directory / "other.spec.ts"
        other.write_text("test('other', async ({ page }) => {});\n")
        self.flow.spec_map = {SHEET["id"]: [self.path.name], "other": [other.name]}
        before = RunSummary(passed=1, total=2, results=[
            TestOutcome("bad", False, "failed", 1, file=self.path.name),
            TestOutcome("other", True, "passed", 1, file=other.name),
        ])
        after = RunSummary(passed=2, total=2, results=[
            TestOutcome("bad", True, "passed", 1, file=self.path.name),
            TestOutcome("other", True, "passed", 1, file=other.name),
        ])
        self.flow.run_specs.side_effect = [outcome(ok=True), after]
        observed = self.flow.audit_related_derived_specs([self.path.name, other.name], before)
        self.assertTrue(observed.all_passed)
        self.assertEqual(self.flow.run_specs.call_count, 2)
        self.assertIn("h.expectCell(page, 'A1', 'East')", self.path.read_text())

    def test_related_audit_reviews_each_failed_generated_test_in_one_feature(self):
        node = {"id": "REQ-1", "name": "Two actions", "description": "The page has Open and Save.",
                "scenarios": [{"name": name, "steps": [
                    {"keyword": "WHEN", "content": f"The visitor clicks “{action}”."},
                    {"keyword": "THEN", "content": f"The page shows “{result}”."}]}
                    for name, action, result in (("REQ-1: Open", "Open", "Opened"),
                                                 ("REQ-1: Save", "Save", "Saved"))]}
        path = self.directory / "REQ-1.spec.ts"
        path.write_text("test('REQ-1: Open [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Opened']);\n});\n"
                        "test('REQ-1: Save [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Save');\n"
                        "  await h.expectTextsVisible(page, ['Saved']);\n});\n")
        self.flow.requirement_nodes = {"REQ-1": node}
        self.flow.derived_nodes = [node]
        self.flow.spec_map = {"REQ-1": [path.name]}
        self.flow.driver = object()
        self.flow.wound_down = Mock(return_value=False)
        self.flow.remaining = Mock(return_value=1000)
        self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.audit_failed_derived_specs = Mock(return_value=None)
        self.flow.text_turn = Mock(side_effect=[
            (True, '{"verdict":"app_error","evidence":"Open action is missing","scenarios":[]}'),
            (True, '{"verdict":"oracle_dispute","evidence":"Save expectation conflicts","scenarios":[]}')])
        failed = RunSummary(passed=0, total=2, results=[
            TestOutcome("REQ-1: Open [model]", False, "failed", 1, file=path.name),
            TestOutcome("REQ-1: Save [model]", False, "failed", 1, file=path.name)])
        self.assertIs(self.flow.audit_related_derived_specs([path.name], failed), failed)
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertEqual(self.flow.disputed_generated_failures(failed),
                         [("REQ-1", "REQ-1: Save [model]")])
        self.flow.derived_failure_reviews.clear()
        self.flow.derived_spec_disputes.clear()
        self.flow.text_turn.side_effect = None
        self.flow.text_turn.return_value = (
            True, '{"verdict":"app_error","evidence":"Open action is missing","scenarios":[]}')
        self.flow.text_turn.reset_mock()
        with patch.dict("os.environ", {"OCTOS_ARC_DERIVED_FAILURE_REVIEW_PER_SUITE": "1"}):
            self.flow.audit_related_derived_specs([path.name], failed)
        self.assertEqual(self.flow.text_turn.call_count, 1)
        self.assertEqual(self.flow.disputed_generated_failures(failed),
                         [("REQ-1", "REQ-1: Save [model]")])

    def test_final_suite_repairs_uncontested_failure_while_oracle_is_disputed(self):
        self.path.unlink()
        first = self.directory / "A.spec.ts"
        second = self.directory / "B.spec.ts"
        first.write_text("test('A: disputed [model]', async ({ page }) => {});\n")
        second.write_text("test('B: broken [model]', async ({ page }) => {});\n")
        self.flow.spec_map = {"A": [first.name], "B": [second.name]}
        self.flow.derived_spec_disputes = {("A", "A: disputed [model]"): "Wrong oracle"}
        self.flow.test_verdict = {"A": None, "B": None}
        self.flow.derived_review_needed = Mock(return_value=False)
        self.flow.audit_related_derived_specs = Mock(side_effect=lambda _specs, summary: summary)
        self.flow.record_tests = Mock()
        self.flow.remember_delivery_checkpoint = Mock()
        self.flow.head = Mock(return_value="app-sha")
        self.flow.commit = Mock(return_value=True)
        self.flow.remaining = Mock(return_value=10000)
        self.flow.wound_down = Mock(return_value=False)
        self.flow.suite_repair_turn = Mock(return_value=("tools", ""))
        self.flow.repair_test_location = Mock(return_value="derived tests")
        before = RunSummary(passed=0, total=2, results=[
            TestOutcome("A: disputed [model]", False, "failed", 1, file=first.name),
            TestOutcome("B: broken [model]", False, "failed", 1, file=second.name)])
        after = RunSummary(passed=1, total=2, results=[
            TestOutcome("A: disputed [model]", False, "failed", 1, file=first.name),
            TestOutcome("B: broken [model]", True, "passed", 1, file=second.name)])
        self.flow.run_specs = Mock(return_value=after)
        with patch.dict("os.environ", {"OCTOS_FINAL_REPAIR_ROUNDS": "1",
                                    "OCTOS_ARC_FINAL_CONFIRM_RUNS": "1"}):
            self.flow.final_acceptance(initial_summary=before)
        self.flow.suite_repair_turn.assert_called_once()
        self.assertIn("B: broken", self.flow.suite_repair_turn.call_args.args[2])
        self.assertNotIn("A: disputed", self.flow.suite_repair_turn.call_args.args[2])
        self.assertIsNone(self.flow.test_verdict["A"])
        self.assertTrue(self.flow.test_verdict["B"])
        self.assertTrue(self.flow.final_spec_dispute)
        self.assertFalse(self.flow.final_suite_green)

    def test_disputed_pass_does_not_improve_trusted_score(self):
        self.flow.derived_spec_disputes = {("A", "A: disputed [model]"): "Wrong oracle"}
        rows = [TestOutcome("A: disputed [model]", True, "passed", 1, file="A.spec.ts"),
                TestOutcome("B: checked [model]", True, "passed", 1, file="B.spec.ts")]
        summary = RunSummary(passed=2, total=2, results=rows)
        trusted = self.flow.uncontested_derived_results(summary)
        self.assertEqual((trusted.passed, trusted.total), (1, 1))
        self.assertEqual((summary.passed, summary.total), (2, 2))
        self.flow.derived_as_specs = False
        self.assertIs(self.flow.uncontested_derived_results(summary), summary)

    def test_whole_app_first_suite_only_schedules_uncontested_failure(self):
        self.path.unlink()
        first = self.directory / "A.spec.ts"
        second = self.directory / "B.spec.ts"
        first.write_text("test('A: disputed [model]', async ({ page }) => {});\n")
        second.write_text("test('B: broken [model]', async ({ page }) => {});\n")
        self.flow.spec_map = {"A": [first.name], "B": [second.name]}
        self.flow.derived_spec_disputes = {("A", "A: disputed [model]"): "Wrong oracle"}
        self.flow.audit_related_derived_specs = Mock(side_effect=lambda _specs, summary: summary)
        self.flow.record_tests = Mock()
        self.flow.remember_delivery_checkpoint = Mock()
        self.flow.run_specs = Mock(return_value=RunSummary(passed=0, total=2, results=[
            TestOutcome("A: disputed [model]", False, "failed", 1, file=first.name),
            TestOutcome("B: broken [model]", False, "failed", 1, file=second.name)]))
        with patch("main.scaffold_issues", return_value=[]):
            failing = self.flow.whole_app_first_suite([{"id": "A"}, {"id": "B"}])
        self.assertEqual(failing, {"B"})
        self.assertIsNone(self.flow.test_verdict["A"])
        self.assertFalse(self.flow.test_verdict["B"])

    def test_model_review_repairs_action_order_without_weakening_oracle(self):
        node = {"id": "REQ-1", "name": "Open feature", "description": "The home page has “Open” and shows “Done”.",
                "scenarios": [{"name": "REQ-1: action", "steps": [
                    {"keyword": "GIVEN", "content": "The visitor is on the home page."},
                    {"keyword": "WHEN", "content": "The visitor clicks “Open”."},
                    {"keyword": "THEN", "content": "The page shows “Done”."}]}]}
        path = self.directory / "REQ-1.spec.ts"
        self.flow.requirement_nodes = {"REQ-1": node}
        self.flow.derived_nodes = [node]
        self.flow.driver = object()
        self.flow.wound_down = Mock(return_value=False)
        self.flow.remaining = Mock(return_value=1000)
        self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.text_turn = Mock(return_value=(True, '{"verdict":"spec_error","evidence":"WHEN clicks Open",'
                                                 '"scenarios":[{"id":"S1","title":"REQ-1: action",'
                                                 '"confidence":0.9,"signed_in":false,"steps":['
                                                 '{"op":"click","target":"Open"},'
                                                 '{"op":"expect_visible","target":"Done"}]}]}'))
        for suffix in ("model", "script"):
            with self.subTest(suffix=suffix):
                path.write_text(f"test('REQ-1: action [{suffix}]', async ({{ page }}) => {{\n"
                                "  await h.openHome(page);\n"
                                "  await h.expectTextsVisible(page, ['Done']);\n"
                                "  await h.clickNamed(page, 'Open');\n});\n")
                failed = RunSummary(passed=0, total=1, results=[TestOutcome(
                    f"REQ-1: action [{suffix}]", False, "failed", 1, file=path.name)])
                observed = self.flow.review_failed_derived_spec_with_model("REQ-1", [path.name], failed)
                self.assertTrue(observed.all_passed)
                source = path.read_text()
                self.assertLess(source.index("h.clickNamed"), source.index("h.expectTextsVisible"))
                self.assertIn("h.expectTextsVisible(page, ['Done'])", source)


if __name__ == "__main__":
    unittest.main()
