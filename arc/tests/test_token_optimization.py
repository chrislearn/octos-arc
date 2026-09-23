"""Check complete prompt budgets, stable prefixes and preservation of contracts."""
import argparse
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main as m
import tests.test_main_helpers as helpers


class TokenOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.spec_bodies = lambda _: "public example"
        self.flow.codegen_ports_clause = lambda: ""
        self.flow.codegen_reasoning = lambda _: "none"
        self.flow.codegen_context_chars = lambda: 90000

    def app(self, server="const http = require('http');", page="<p>Page</p>"):
        m.write_codegen_manifests(self.root)
        (self.root / "frontend/src").mkdir(parents=True, exist_ok=True)
        (self.root / "backend/server.js").write_text(server)
        (self.root / "frontend/src/index.html").write_text(page)

    def test_same_sources_keep_a_long_prefix_across_nodes_and_corrections(self):
        self.app(server="// stable entry\n" + "e" * 600, page="<h1>Notes</h1>" + "p" * 600)
        (self.root / "frontend/src/settings.html").write_text("<h1>Settings</h1>" + "s" * 600)
        a = self.flow.codegen_implement_prompt(helpers.node("REQ-1", "Notes"), "notes", "Fix notes\n")
        b = self.flow.codegen_implement_prompt(helpers.node("REQ-2", "Settings"), "settings", "Fix settings\n")
        common = os.path.commonprefix([a, b])
        self.assertIn("--- frontend/src/settings.html ---", common)
        self.assertGreater(len(common), 3000)
        self.assertLess(a.index("Rules:"), a.index("--- backend/server.js ---"))
        self.assertLess(a.index("--- frontend/src/settings.html ---"), a.index("Fix notes"))
        self.assertLess(a.index("Fix notes"), a.index("Requirement REQ-1"))

    def test_path_order_does_not_change_relevance_selection(self):
        self.app(server="entry", page="note-list " + "n" * 300)
        (self.root / "frontend/src/settings.html").write_text("settings " + "s" * 300)
        spec = "await page.getByTestId('note-list');"
        scored = m.scored_sources(self.root, spec)
        ranked = m.select_source_snapshot(scored, 400)
        stable = m.select_source_snapshot(scored, 400, stable_order=True)
        self.assertEqual(m.quoted_paths(ranked), m.quoted_paths(stable))
        self.assertIn("frontend/src/index.html", m.quoted_paths(stable))
        self.assertNotIn("frontend/src/settings.html", m.quoted_paths(stable))

    def test_budget_includes_rules_corrections_headings_and_format(self):
        self.app(server="e" * 3000, page="p" * 3000)
        self.flow.codegen_context_chars = lambda: 6600
        correction = "Keep previous behavior. " * 20
        prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-1", "Add search"), "search", correction)
        self.assertIsNotNone(prompt)
        self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 6600)
        self.assertIn(correction, prompt)
        self.assertIn("backend/server.js", m.quoted_paths(prompt))
        self.assertNotIn("frontend/src/index.html", m.quoted_paths(prompt))
        self.assertIn("frontend/src/index.html (", prompt)

    def test_backend_entry_must_fit_the_complete_prompt_not_only_content_budget(self):
        # The entry fits the content budget on its own (4,500 < 6,000) and the spec
        # is far below 60%; only the serialized message pushes this over.
        self.app(server="e" * 4500)
        self.flow.codegen_context_chars = lambda: 6000
        self.assertIsNone(self.flow.codegen_implement_prompt(helpers.node("REQ-1", "Search"), "search"))
        self.assertEqual(self.flow.codegen_budget["reason"],
                         "fixed_prompt_entry_or_critical_corrections_exceed_budget")

    def test_unabridged_evidence_that_exceeds_budget_uses_tools(self):
        self.flow.codegen_context_chars = lambda: 6000
        self.assertIsNone(self.flow.codegen_implement_prompt(
            helpers.node("REQ-1", "Search"), "search", "failure evidence " * 600))

    def test_tiny_text_retains_scenario_only_constraints_and_dependencies(self):
        requirement = helpers.node("REQ-1", "Reject invalid search", ["REQ-0"])
        requirement["scenarios"] = [{"name": "Same city", "steps": [
            {"keyword": "THEN", "content": "Show 同城错误 and block navigation"}]}]
        self.flow.runner = object()
        self.flow.codegen_turn = Mock(return_value=(False, ""))
        self.flow.tiny_turn("REQ-1", ["REQ-1.spec.ts"], 60, requirement)
        prompt = self.flow.codegen_turn.call_args.args[0]
        self.assertIn(m.describe_node(requirement), prompt)
        self.assertIn("THEN Show 同城错误 and block navigation", prompt)
        self.assertIn("Depends on: REQ-0", prompt)
        self.assertIn("public example", prompt)
        self.assertNotIn('"scenarios":', prompt)

    def node_flow(self):
        self.app(server="// OBSOLETE_SOURCE\n", page="<p>Existing page</p>")
        flow = self.flow
        flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"]}
        flow.llm_proxy = SimpleNamespace()
        flow.design_enabled = False
        flow.tiny_mode = lambda _: False
        flow.mark = Mock()
        flow.commit = Mock(return_value=True)
        flow.runtime = Mock()
        flow.runtime.traceability.list_interfaces.return_value = []
        flow.ancestors_text = lambda *_: ""
        flow.tests_prompt_for = lambda _: ""
        flow.perf_text = lambda: ""
        flow.ui_contract = lambda: ""
        flow.verify_text = lambda _: ""
        flow.turn = Mock(return_value=(True, "tool implementation"))
        return flow

    def test_rewrite_quotes_only_current_sources_once(self):
        flow = self.node_flow()
        rebuilt = []
        def implement(*args, **kwargs):
            (self.root / "backend/server.js").write_text("// CURRENT_SOURCE\n")
            return True, "implemented"
        flow.codegen_turn = Mock(side_effect=implement)
        def accept(node_id, specs, deadline, rebuild_prompt, source_versions=None):
            rebuilt.append(rebuild_prompt("current failure"))
            return False
        flow.acceptance_loop = accept
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        self.assertIn("OBSOLETE_SOURCE", flow.codegen_turn.call_args.args[0])
        self.assertNotIn("OBSOLETE_SOURCE", rebuilt[0])
        self.assertIn("CURRENT_SOURCE", rebuilt[0])
        self.assertEqual(rebuilt[0].count("--- backend/server.js ---"), 1)
        self.assertIn("current failure", rebuilt[0])
        self.assertLessEqual(len(rebuilt[0] + "\n" + m.FORMAT_INSTRUCTIONS), 90000)

    def test_initial_shared_helper_refusal_waits_for_acceptance(self):
        flow = self.node_flow()
        flow.generic_template_installed = True
        def partial(*args, **kwargs):
            self.assertTrue(kwargs["defer_shared_refusals"])
            flow.refused_paths.add("backend/lib/store.js")
            flow.last_codegen_deferred = {"backend/lib/store.js"}
            flow.last_codegen_written = ["backend/routes/items.js"]
            return True, "generated application route"
        flow.codegen_turn = Mock(side_effect=partial)
        flow.acceptance_loop = Mock(return_value=True)
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        flow.codegen_turn.assert_called_once()
        flow.acceptance_loop.assert_called_once()

    def test_truncated_generation_probes_existing_app_before_spending_more_tokens(self):
        flow = self.node_flow()
        flow.runner = object()
        flow.codegen_turn = Mock(return_value=(False, "output_truncated: max_tokens"))
        flow.run_specs = Mock(return_value=m.RunSummary(passed=1, total=1))
        flow.acceptance_loop = Mock(return_value=True)
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        flow.run_specs.assert_called_once_with(["REQ-1.spec.ts"])
        flow.codegen_turn.assert_called_once()
        flow.turn.assert_not_called()
        flow.acceptance_loop.assert_called_once()

    def test_truncated_generation_uses_one_compact_codegen_retry_when_app_fails(self):
        flow = self.node_flow()
        flow.runner = object()
        flow.codegen_turn = Mock(side_effect=[(False, "output_truncated: max_tokens"),
                                              (True, "<<<NO CHANGE>>>")])
        flow.run_specs = Mock(return_value=m.RunSummary(passed=0, total=1))
        flow.acceptance_loop = Mock(return_value=True)
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        self.assertEqual(flow.codegen_turn.call_count, 2)
        retry = flow.codegen_turn.call_args.args[0]
        self.assertIn("previous codegen reply exceeded its output limit", retry)
        self.assertIn("OBSOLETE_SOURCE", retry)
        flow.turn.assert_not_called()

    def test_oversized_rewrite_evidence_switches_to_tools(self):
        flow = self.node_flow()
        flow.codegen_context_chars = lambda: 6000
        flow.codegen_turn = Mock(return_value=(True, "implemented"))
        def accept(node_id, specs, deadline, rebuild_prompt, source_versions=None):
            prompt = rebuild_prompt("oversized failure " * 500)
            self.assertIn("oversized failure", prompt)
            self.assertFalse(flow.codegen_mode())
            return False
        flow.acceptance_loop = accept
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)

    def test_oversized_non_checkpoint_correction_falls_back_to_tools(self):
        flow = self.node_flow()
        flow.codegen_context_chars = lambda: 6000
        flow.pending_corrections = ["oversized evidence " * 500]
        flow.codegen_turn = Mock(return_value=(True, "implemented"))
        flow.acceptance_loop = Mock(return_value=True)
        flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        flow.codegen_turn.assert_not_called()
        self.assertIn("oversized evidence", flow.turn.call_args.args[0])


class RepairContractTests(unittest.TestCase):
    def ctrip_requirements(self):
        req_dir = Path(m.__file__).parent / "tasks/arc-bench-web--ctrip"
        return {str(n["id"]): n for n in m.topo_order(m.load_requirement_tree(req_dir))}

    def assert_original_constraints(self, prompt):
        for text in ["用户名或密码错误", "请先阅读并勾选协议", "出发城市和到达城市不能相同", "navigation is blocked"]:
            self.assertIn(text, prompt)

    def test_full_suite_preserves_constraints_found_only_in_other_nodes_scenarios(self):
        flow = helpers.FinalSuiteBestRoundTests()._flow([1, 2])
        flow.requirement_nodes = self.ctrip_requirements()
        flow.turn = Mock(return_value=(True, "repaired"))
        with patch.dict(os.environ, {"OCTOS_FINAL_REPAIR_ROUNDS": "1"}):
            flow.final_acceptance()
        self.assert_original_constraints(flow.turn.call_args.args[0])

    def test_checkpoint_preserves_constraints_found_only_in_other_nodes_scenarios(self):
        flow = helpers.CheckpointRepairTests()._flow([1, 2])
        flow.requirement_nodes = self.ctrip_requirements()
        with patch.dict(os.environ, {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assert_original_constraints(flow.turn.call_args.args[0])

    def checkpoint_flow(self, outcomes):
        flow = helpers.CheckpointRepairTests()._flow(outcomes)
        flow.corrections_text = lambda: m.Flow.corrections_text(flow)
        return flow

    def test_residual_failures_survive_for_next_node_without_initial_duplicate(self):
        flow = self.checkpoint_flow([1, 1])
        run = flow.run_specs
        messages = iter(["stale failure", "latest failure"])
        def observe(*args, **kwargs):
            summary = run(*args, **kwargs)
            summary.results[-1].message = next(messages)
            return summary
        flow.run_specs = observe
        with patch.dict(os.environ, {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2", "OCTOS_ARC_CHECKPOINT_REPAIRS": "1"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(len(flow.pending_corrections), 1)
        self.assertIn("latest failure", flow.pending_corrections[0])
        self.assertNotIn("stale failure", flow.pending_corrections[0])
        self.assertIn("REQ-2", flow.corrections_text())
        self.assertEqual(flow.pending_corrections, [])

    def test_fixed_failures_leave_no_stale_evidence(self):
        flow = self.checkpoint_flow([1, 2])
        with patch.dict(os.environ, {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.pending_corrections, [])

    def test_budget_stop_between_repairs_keeps_latest_residual_evidence(self):
        flow = self.checkpoint_flow([1, 1])
        remaining = iter([10000, 10000, 10000, 0])
        flow.remaining = lambda: next(remaining)
        with patch.dict(os.environ, {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2", "OCTOS_ARC_CHECKPOINT_REPAIRS": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(len(flow.pending_corrections), 1)
        self.assertIn("REQ-2", flow.pending_corrections[0])

    def test_repair_prefix_contains_full_requirements_before_changing_failures(self):
        requirements = self.ctrip_requirements()
        originals = "\n\n".join(m.describe_node(n) for n in requirements.values())
        def prompt(node_id, failures, corrections):
            return m.REPAIR_PROMPT.format(node_id=node_id, passed=1, total=2,
                failures=failures, corrections=corrections, slow="", sources=originals,
                test_location="read-only tests", smoke=3100, port=3000)
        a = prompt("REQ-2.4.1", "login failure", "fix login")
        b = prompt("REQ-3.2.3", "search failure", "fix search")
        common = os.path.commonprefix([a, b])
        self.assertIn(originals, common)
        self.assert_original_constraints(common)

    def test_unreliable_post_repair_run_preserves_last_known_failure_evidence(self):
        from acceptance import RunSummary
        for error, killed in [("build failed", False), ("", True)]:
            with self.subTest(error=error, killed=killed):
                flow = self.checkpoint_flow([1])
                run = flow.run_specs
                calls = []
                def observe(*args, **kwargs):
                    calls.append(True)
                    return run(*args, **kwargs) if len(calls) == 1 else RunSummary(error=error, killed=killed)
                flow.run_specs = observe
                with patch.dict(os.environ, {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
                    flow.regression_checkpoint(2, 8)
                self.assertEqual(len(flow.pending_corrections), 1)
                self.assertIn("REQ-2", flow.pending_corrections[0])
                # Historical failure evidence survives, but changed sources
                # with an incomplete report have no current verified verdict.
                self.assertIsNone(flow.test_verdict["REQ-1"])
                self.assertIsNone(flow.test_verdict["REQ-2"])


class PrefixAndCorrectionBudgetTests(unittest.TestCase):
    setUp = TokenOptimizationTests.setUp
    app = TokenOptimizationTests.app
    node_flow = TokenOptimizationTests.node_flow
    def test_cross_threshold_prefix_keeps_identical_source_blocks(self):
        self.app(server="// shared entry\n" + "e" * 1500, page="<p>Shared page</p>" + "p" * 4000)
        del self.flow.codegen_reasoning
        with patch.dict(os.environ, {"OCTOS_ARC_REASONING": "auto", "OCTOS_ARC_CODEGEN_REASONING_CHARS": "5000"}):
            a = self.flow.codegen_implement_prompt(helpers.node("REQ-1", "Small"), "a" * 4999)
            b = self.flow.codegen_implement_prompt(helpers.node("REQ-2", "Large"), "b" * 5000)
        common = os.path.commonprefix([a, b])
        self.assertIn("--- frontend/src/index.html ---", common)
        self.assertIn("p" * 4000, common)
        self.assertNotIn(m.CODEGEN_SIZE_SMALL, common)
        self.assertNotIn(m.CODEGEN_SIZE_FULL, common)
        self.assertIn(m.CODEGEN_SIZE_SMALL, a)
        self.assertIn(m.CODEGEN_SIZE_FULL, b)

    def checkpoint_corrections(self, critical="Keep the restored file unchanged."):
        from acceptance import RunSummary, TestOutcome
        self.flow.tests_dir = self.root
        self.flow.spec_map = {"REQ-OLD": ["old.spec.ts"]}
        summary = RunSummary(passed=0, total=1, results=[TestOutcome(
            title="Old requirement", ok=False, status="failed", duration_ms=1,
            file="old.spec.ts", message="HEAD_EXPECTED_VALUE " + "failure context " * 1000 + " TAIL_OBSERVATION")])
        self.flow.pending_corrections = [critical]
        with patch.object(m, "failure_source_context", return_value="HEAD_EXPECTED_VALUE " + "context " * 3000 + " TAIL_OBSERVATION"):
            self.flow.queue_checkpoint_evidence(summary)
        return self.flow.corrections_text()

    def test_trim_checkpoint_evidence_before_abandoning_codegen(self):
        self.app(server="e" * 28000)
        self.flow.codegen_reasoning = lambda _: None
        corrections = self.checkpoint_corrections()
        self.flow.codegen_context_chars = lambda: 90000
        prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-NEW", "New feature"), "s" * 50000, corrections)
        self.assertIsNotNone(prompt)
        self.assertIn("backend/server.js", m.quoted_paths(prompt))
        self.assertNotIn(str(corrections), prompt)
        self.assertIn("Keep the restored file unchanged.", prompt)
        self.assertIn("REQ-OLD", prompt)
        self.assertIn("elided", prompt)
        self.assertIn("HEAD_EXPECTED_VALUE", prompt)
        self.assertIn("TAIL_OBSERVATION", prompt)
        self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 90000)

    def test_budget_fit_keeps_all_corrections_without_truncation(self):
        self.app(server="entry")
        corrections = self.checkpoint_corrections()
        prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-NEW", "New feature"), "small spec", corrections)
        self.assertIn(corrections, prompt)

    def test_all_critical_corrections_are_preserved_if_checkpoint_is_trimmed(self):
        self.app(server="e" * 25000)
        critical = "Never overwrite the restored backend/routes/old.js. " * 200
        corrections = self.checkpoint_corrections(critical)
        prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-NEW", "New feature"), "s" * 50000, corrections)
        self.assertIsNotNone(prompt)
        self.assertIn(critical, prompt)
        self.assertIn("elided", prompt)

    def test_critical_corrections_alone_exceeding_budget_still_uses_tools(self):
        self.app(server="e" * 25000)
        critical = "Never overwrite the restored backend/routes/old.js. " * 400
        corrections = self.checkpoint_corrections(critical)
        prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-NEW", "New feature"), "s" * 50000, corrections)
        self.assertIsNone(prompt)
        self.assertIn(critical, corrections)

    def test_budget_failure_log_contains_spec_entry_room_and_reason(self):
        flow = self.node_flow()
        flow.codegen_context_chars = lambda: 6000
        flow.pending_corrections = ["critical correction " * 500]
        flow.codegen_turn = Mock(return_value=(True, "implemented"))
        flow.acceptance_loop = Mock(return_value=True)
        with patch.object(m, "log") as logged:
            flow.node_cycle(helpers.node("REQ-1", "Search"), [], 1, 1)
        lines = [str(c.args[0]) for c in logged.call_args_list if "tool mode" in str(c.args[0])]
        self.assertEqual(len(lines), 1)
        for field in ["spec=", "entry=", "room=", "limit=", "reason="]:
            self.assertIn(field, lines[0])

    def test_budget_render_reads_each_source_file_once(self):
        self.app(server="e" * 3000, page="p" * 3000)
        self.flow.codegen_context_chars = lambda: 6500
        read = Path.read_text
        calls = []
        def recorded(path, *args, **kwargs):
            calls.append(path)
            return read(path, *args, **kwargs)
        with patch.object(Path, "read_text", recorded):
            prompt = self.flow.codegen_implement_prompt(helpers.node("REQ-1", "Search"), "search")
        self.assertIsNotNone(prompt)
        self.assertEqual(calls.count(self.root / "backend/server.js"), 1)
        self.assertEqual(calls.count(self.root / "frontend/src/index.html"), 1)
