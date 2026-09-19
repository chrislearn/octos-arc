"""Regressions observed in temp-logs/1/keep.txt, expressed without task-specific rules."""
import argparse
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as m
from acceptance import RunSummary, TestOutcome


class KeepEfficiencyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        m.write_codegen_manifests(self.root)
        (self.root / "frontend/src").mkdir(parents=True)
        (self.root / "backend/server.js").write_text("// backend entry\n")
        (self.root / "frontend/src/index.html").write_text("<main>existing home</main>\n")
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.spec_bodies = lambda _: "public example"
        self.flow.codegen_mode = lambda: not getattr(self.flow, "codegen_blocked", False)
        self.flow.codegen_reasoning = lambda _: "none"
        self.flow.turn = Mock(return_value=(True, "tool repair"))

    def block(self, path, body):
        return f"<<<FILE {path}>>>\n{body}\n<<<END FILE>>>\n"

    def tool_prompt(self):
        return "Preserve working behavior.\n" + self.flow.sources_text()

    def test_home_navigation_quotes_large_home_page_before_unrelated_small_pages(self):
        (self.root / "frontend/src/index.html").write_text("<main>home</main>" + "x" * 60000)
        for name in ("settings", "archive", "labels"):
            (self.root / f"frontend/src/{name}.html").write_text("navigation button " * 1500)
        spec = "async function openHome(page) { await page.goto('/'); }"
        prompt = self.flow.codegen_implement_prompt({"id": "R", "description": "Toggle sidebar"}, spec)
        self.assertIn("frontend/src/index.html", m.quoted_paths(prompt))
        self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), self.flow.codegen_context_chars())

    def test_non_home_navigation_does_not_prioritize_home(self):
        files = ["frontend/src/index.html", "frontend/src/faq.html"]
        for spec in ("page.goto('/orders')", "getByText('/')", "page.goto(destination)"):
            with self.subTest(spec=spec):
                self.assertEqual(m.spec_targets(spec, files), set())
        self.assertEqual(m.spec_targets('page.goto("/?view=list", {waitUntil: "load"})', files), {files[0]})

    def test_navigation_outranks_incidental_names_in_reachable_helpers(self):
        (self.root / "frontend/src/index.html").write_text("<main>home</main>" + "x" * 60000)
        for name in ("settings", "archive", "trash", "label"):
            (self.root / f"frontend/src/{name}.html").write_text("navigation " * 1800)
        flow = self.flow
        flow.tests_dir = m.BUNDLE_DIR / "public-tests/arc-bench-web--keep"
        flow.spec_bodies = lambda node: m.Flow.spec_bodies(flow, node)
        nodes = ("REQ-2.7.6.1", "REQ-2.8.3", "REQ-3.1", "REQ-3.2", "REQ-6.1", "REQ-6.2")
        flow.spec_map = {n: [n + ".spec.ts"] for n in nodes}
        for node in nodes:
            with self.subTest(node=node):
                spec = flow.spec_bodies(node)
                prompt = flow.codegen_implement_prompt({"id": node, "description": "Preserve and extend the app"}, spec)
                self.assertIn("frontend/src/index.html", m.quoted_paths(prompt))

    def test_navigation_recognizes_nested_routes_without_inventing_dynamic_routes(self):
        files = ["frontend/src/index.html", "frontend/src/account/orders.html", "frontend/src/account/index.html"]
        self.assertEqual(m.navigation_targets("page.goto('/account/orders?sort=date');", files), {files[1]})
        self.assertEqual(m.navigation_targets("page.goto(`/account/`);", files), {files[2]})
        for url in ("${base}/", "//other.test/", "/${page}"):
            self.assertEqual(m.navigation_targets(f"page.goto(`{url}`)", files), set())

    def test_missing_backend_is_required_without_discarding_partial_frontend(self):
        (self.root / "backend/server.js").unlink()
        prompt = self.flow.codegen_implement_prompt({"id": "R", "description": "Open home"}, "page.goto('/')")
        self.assertIn("Startup prerequisite: backend/server.js is missing", prompt)
        self.assertIn("existing home", prompt)
        self.assertIn("frontend/src/index.html", m.quoted_paths(prompt))

    def test_startup_check_handles_renamed_entries_and_leaves_frameworks_alone(self):
        manifest = self.root / "backend/package.json"
        manifest.write_text(json.dumps({"scripts": {"start": "node app.cjs"}}))
        self.assertEqual(m.missing_backend_entry(self.root), "backend/app.cjs")
        (self.root / "backend/app.cjs").write_text("// entry")
        self.assertIsNone(m.missing_backend_entry(self.root))
        for command in ("next start", "npm run serve", "node ../outside.js"):
            manifest.write_text(json.dumps({"scripts": {"start": command}}))
            self.assertIsNone(m.missing_backend_entry(self.root))

    def test_repair_requotes_refused_file_even_when_it_was_refused_before(self):
        target = "frontend/src/settings.html"
        (self.root / target).write_text("<main>old settings</main>" + "s" * 50000)
        (self.root / "frontend/src/index.html").write_text("<main>large home</main>" + "h" * 60000)
        flow = self.flow
        flow.refused_paths = {target}  # previous refusal in this same node
        first = "--- backend/server.js ---\n// backend entry\n"
        original_builder = flow.codegen_repair_prompt
        prompts = []
        def build(node, prompt, failures=""):
            result = first if not prompts else original_builder(node, prompt, failures)
            prompts.append(result)
            return result
        flow.codegen_repair_prompt = build
        flow.text_turn = Mock(return_value=(True, self.block(target, "<main>fixed settings</main>")))
        self.assertTrue(flow.node_repair_turn("R", "missing setting", 300, "R repair 1/3", self.tool_prompt))
        self.assertEqual(flow.text_turn.call_count, 2)
        self.assertIn(target, m.quoted_paths(prompts[1]))
        self.assertIn("fixed settings", (self.root / target).read_text())
        flow.turn.assert_not_called()

    def test_partial_writes_are_refreshed_in_retry_prompt(self):
        flow = self.flow
        initial = "--- backend/server.js ---\n// backend entry\n"
        original_builder = flow.codegen_repair_prompt
        calls = []
        def build(node, prompt, failures=""):
            calls.append(prompt)
            return initial if len(calls) == 1 else original_builder(node, prompt, failures)
        flow.codegen_repair_prompt = build
        flow.text_turn = Mock(side_effect=[
            (True, self.block("backend/server.js", "// new entry") + self.block("frontend/src/index.html", "blind")),
            (True, self.block("frontend/src/index.html", "<main>fixed</main>")),
        ])
        self.assertTrue(flow.node_repair_turn("R", "missing control", 300, "R repair", self.tool_prompt))
        self.assertIn("// new entry", calls[1])
        self.assertNotIn("// backend entry", calls[1])
        self.assertNotIn("blind", (self.root / "frontend/src/index.html").read_text())

    def test_refused_repair_gets_tool_fallback_before_retesting_unchanged_code(self):
        flow = self.flow
        flow.runner = object()
        flow.repair_rounds = 1
        flow.min_repair_seconds = 0
        flow.head = lambda: "base"
        flow.wound_down = lambda: False
        flow.record_tests = Mock()
        flow.snapshot_sources = Mock()
        flow.commit = Mock()
        flow.codegen_repair_prompt = lambda *a, **kw: "no sources fit"
        flow.text_turn = Mock(return_value=(True, self.block("frontend/src/index.html", "blind")))
        events = []
        def accept(*args, **kwargs):
            events.append("test")
            if flow.turn.called:
                return RunSummary(passed=1, total=1)
            return RunSummary(passed=0, total=1, results=[TestOutcome(
                "control", False, "failed", 1, message="control missing")])
        flow.run_specs = accept
        flow.turn.side_effect = lambda *a, **kw: (events.append("repair") or True, "fixed")
        self.assertTrue(flow.acceptance_loop("R", ["R.spec.ts"], time.time() + 300))
        self.assertEqual(events, ["test", "repair", "test"])
        self.assertEqual(flow.text_turn.call_count, 1)
        self.assertEqual(flow.turn.call_count, 1)

    def test_refusal_retry_and_fallback_share_one_deadline(self):
        flow = self.flow
        now = [0.0]
        flow.codegen_repair_prompt = lambda *a, **kw: "no sources fit"
        def response(*args, **kw):
            now[0] += 70
            return True, self.block("frontend/src/index.html", "blind")
        flow.text_turn = response
        with patch("main.time.monotonic", side_effect=lambda: now[0]):
            self.assertTrue(flow.node_repair_turn("R", "failure", 100, "R repair", self.tool_prompt))
        self.assertEqual(flow.turn.call_args.args[1], 30)

    def test_expired_refusal_does_not_start_another_turn(self):
        flow = self.flow
        now = [0.0]
        flow.codegen_repair_prompt = lambda *a, **kw: "no sources fit"
        def response(*args, **kw):
            now[0] = 100
            return True, self.block("frontend/src/index.html", "blind")
        flow.text_turn = response
        with patch("main.time.monotonic", side_effect=lambda: now[0]):
            self.assertFalse(flow.node_repair_turn("R", "failure", 100, "R repair", self.tool_prompt))
        flow.turn.assert_not_called()

    def test_cost_guard_stops_refusal_retries(self):
        flow = self.flow
        exhausted = [False]
        flow.wound_down = lambda: exhausted[0]
        flow.codegen_repair_prompt = lambda *a, **kw: "no sources fit"
        def response(*args, **kw):
            exhausted[0] = True
            return True, self.block("frontend/src/index.html", "blind")
        flow.text_turn = Mock(side_effect=response)
        self.assertFalse(flow.node_repair_turn("R", "failure", 100, "R repair", self.tool_prompt))
        self.assertEqual(flow.text_turn.call_count, 1)
        flow.turn.assert_not_called()

    def test_truncated_frontend_node_uses_targeted_recovery_with_original_task(self):
        flow = self.flow
        flow.design_enabled = False
        flow.spec_map = {"R": ["R.spec.ts"]}
        flow.tiny_mode = lambda _: False
        flow.mark = Mock()
        flow.commit = Mock()
        flow.runtime = Mock()
        flow.runtime.traceability.list_interfaces.return_value = []
        flow.driver = Mock()
        flow.ancestors_text = lambda *_: ""
        flow.tests_prompt_for = lambda _: "public example"
        flow.perf_text = lambda: ""
        flow.ui_contract = lambda: ""
        flow.verify_text = lambda _: ""
        flow.codegen_turn = Mock(return_value=(False, "output_truncated"))
        flow.acceptance_loop = Mock(return_value=True)
        flow.node_cycle({"id": "R", "description": "Toggle the sidebar"}, [], 1, 1)
        flow.turn.assert_called_once()
        retry = flow.turn.call_args.args[0]
        self.assertIn("Toggle the sidebar", retry)
        self.assertIn("public example", retry)
        self.assertIn("smallest targeted edits", retry)
        self.assertNotIn("starting with backend/server.js", retry)
        flow.acceptance_loop.assert_called_once()

    def test_truncation_recovery_contract_matches_rust_prompt(self):
        template = (m.BUNDLE_DIR / "prompts/truncated-retry.md").read_text()
        self.assertEqual(template.format(prompt="").strip(), m.TRUNCATED_RETRY.strip())
        self.assertNotIn("starting with backend/server.js", template)
        self.assertIn("targeted edits", template)


if __name__ == "__main__":
    unittest.main()
