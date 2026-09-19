"""Cloud fcec6ac02a95 (12306, 135/135, ¥119.68): 93% of the 1,154 requests and
3.8 of 6.2 hours went to 32 tool-mode turns. 28 nodes got there because the
codegen reply rewrote the page the spec is about, that page had not been quoted
whole (44 files, noisy spec-term ranking, small files filling the budget first),
the write guard refused it, the repair got the same selection and was refused
again, and "identical failure twice" switched the node to tools. The refused
path names the file the node needs; quote it and retry once instead.
"""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as m  # noqa: E402


def _app(root: Path, pages: dict[str, str]):
    (root / "frontend/src").mkdir(parents=True, exist_ok=True)
    (root / "backend/routes").mkdir(parents=True, exist_ok=True)
    (root / "frontend/package.json").write_text("{}"); (root / "backend/package.json").write_text("{}")
    (root / "backend/server.js").write_text("// entry\n" + "e" * 400)
    for name, body in pages.items():
        (root / name).write_text(body)


class SpecTargetTests(unittest.TestCase):
    def test_should_name_the_page_whose_stem_the_spec_mentions_in_any_casing(self):
        files = ["frontend/src/ticket-orders.html", "frontend/src/login.html", "frontend/src/index.html"]
        spec = "import { openTicketOrders } from './helpers';\ntest('x', async ({ page }) => { await openTicketOrders(page); });"
        self.assertEqual(m.spec_targets(spec, files), {"frontend/src/ticket-orders.html"})

    def test_should_not_match_short_or_absent_stems(self):
        files = ["frontend/src/index.html", "frontend/src/faq.html", "backend/routes/orders.js"]
        self.assertEqual(m.spec_targets("await page.goto('/orders'); expect(orders)", files), {"backend/routes/orders.js"})


class MustIncludeRankingTests(unittest.TestCase):
    def test_should_quote_a_large_must_include_page_before_small_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            big = "<h1>Ticket orders</h1>" + "order center my 12306 login " * 1500   # ~42k, many nav words
            _app(root, {"frontend/src/ticket-orders.html": big,
                        "frontend/src/login.html": "login order center my 12306 " * 40,
                        "frontend/src/index.html": "index order center my 12306 " * 40,
                        "backend/routes/orders.js": "// orders order center " * 40})
            spec = "order center my 12306; openTicketOrders"   # names no other page
            scored = m.scored_sources(root, spec, must_include={"frontend/src/ticket-orders.html"})
            rels = [str(row[3]) for row in scored]
            self.assertEqual(rels[0], "backend/server.js")
            self.assertEqual(rels[1], "frontend/src/ticket-orders.html")
            out = m.select_source_snapshot(scored, 50_000, stable_order=True, max_output_chars=52_000)
            self.assertIn("--- frontend/src/ticket-orders.html ---", out)

    def test_should_rank_a_spec_target_after_the_entry_even_without_must_include(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {"frontend/src/security.html": "s" * 30_000,
                        "frontend/src/index.html": "index " * 200,
                        "frontend/src/login.html": "login " * 200})
            scored = m.scored_sources(root, "await openAccountSecurity(page);")
            self.assertEqual([str(r[3]) for r in scored][:2], ["backend/server.js", "frontend/src/security.html"])


class RefusalRetryTests(unittest.TestCase):
    def _flow(self, root):
        flow = Mock(spec=m.Flow)
        flow.output_dir = root; flow.req_dir = root
        flow.spec_map = {"REQ-9": ["REQ-9.spec.ts"]}
        flow.node_budget_cap = 300; flow.remaining.return_value = 600
        flow.design_enabled = False; flow.evolution = False
        flow.has_app.return_value = True
        flow.codegen_mode.return_value = True
        flow.tiny_mode.return_value = False
        flow.node_timeout = 300; flow.implement_fraction = .7; flow.smoke_port = 3001; flow.web_port = 3000
        flow.runner = Mock(); flow.impl_failed = []; flow.pending_corrections = []; flow.test_verdict = {}
        flow.refused_paths = set(); flow.app_design_doc = None
        flow.acceptance_loop.return_value = True
        for method in ["ancestors_text", "tests_prompt_for", "perf_text", "ui_contract", "verify_text",
                       "corrections_text", "codegen_ports_clause"]:
            getattr(flow, method).return_value = ""
        flow.spec_bodies.return_value = "await openTicketOrders(page); orders"
        flow.codegen_reasoning.return_value = "none"
        flow.codegen_context_chars.return_value = 90_000
        flow.codegen_implement_prompt.side_effect = lambda *a, **kw: m.Flow.codegen_implement_prompt(flow, *a, **kw)
        flow.runtime = Mock(); flow.runtime.traceability.list_interfaces.return_value = []
        return flow

    def test_should_retry_codegen_once_with_the_refused_file_quoted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # The target page is bigger than what greedy selection left for it.
            _app(root, {"frontend/src/ticket-orders.html": "<main>orders</main>" + "x" * 60_000,
                        "frontend/src/index.html": "orders " * 3000,
                        "frontend/src/login.html": "orders " * 3000})
            flow = self._flow(root)
            prompts = []
            def codegen_turn(prompt, *a, **kw):
                prompts.append(prompt)
                if len(prompts) == 1:
                    flow.refused_paths.add("frontend/src/ticket-orders.html")
                    return False, "codegen reply only rewrote files it was not shown: frontend/src/ticket-orders.html"
                return True, "generated"
            flow.codegen_turn.side_effect = codegen_turn
            m.Flow.node_cycle(flow, {"id": "REQ-9", "description": "orders"}, [], 1, 1)
            self.assertEqual(len(prompts), 2, "one retry, no more")
            self.assertIn("--- frontend/src/ticket-orders.html ---", prompts[1])
            self.assertIn("retry", flow.codegen_turn.call_args.args[2])
            self.assertTrue(flow.acceptance_loop.called)

    def test_should_not_retry_when_the_refused_file_cannot_be_quoted_whole(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {"frontend/src/ticket-orders.html": "x" * 120_000})   # over the whole budget
            flow = self._flow(root)
            calls = []
            def codegen_turn(prompt, *a, **kw):
                calls.append(prompt)
                flow.refused_paths.add("frontend/src/ticket-orders.html")
                return False, "codegen reply only rewrote files it was not shown: frontend/src/ticket-orders.html"
            flow.codegen_turn.side_effect = codegen_turn
            m.Flow.node_cycle(flow, {"id": "REQ-9", "description": "orders"}, [], 1, 1)
            self.assertEqual(len(calls), 1)

    def test_should_reset_refused_paths_per_node_and_record_them_from_the_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {"frontend/src/index.html": "<main>v1</main>"})
            flow = object.__new__(m.Flow)
            flow.output_dir = root; flow.llm_proxy = Mock(mode="low")
            flow.driver = object.__new__(m.OctosDriver); flow.driver.tools_disabled = False; flow.driver._session = None
            flow.codegen_reasoning = lambda _: None; flow.pending_corrections = []; flow.refused_paths = set()
            flow.turn = lambda *a, **k: (True, "<<<FILE frontend/src/index.html>>>\nblind\n<<<END FILE>>>\n")
            ok, _ = flow.codegen_turn("Requirement REQ-9\nOther files: frontend/src/index.html (15 chars)\n", 60, "REQ-9 implement")
            self.assertFalse(ok)
            self.assertEqual(flow.refused_paths, {"frontend/src/index.html"})


class RepairFallbackTests(unittest.TestCase):
    def test_should_rebuild_a_repair_through_the_budgeted_builder_when_the_patched_prompt_cannot_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {"frontend/src/orders.html": "<h1>orders</h1>" + "o" * 2000})
            (root / "tests").mkdir(); (root / "tests/REQ-9.spec.ts").write_text("await page.goto('/orders'); orders")
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.tests_dir = root / "tests"; flow.spec_map = {"REQ-9": ["REQ-9.spec.ts"]}
            flow.requirement_nodes = {"REQ-9": {"id": "REQ-9", "description": "orders page"}}
            sources = flow.sources_text()
            # A tool-mode repair prompt whose non-source part alone exceeds the room the patch route needs.
            prompt = "failure evidence " * 6000 + sources
            full = flow.codegen_repair_prompt("REQ-9", prompt, failures="- Feature: orders\n  Observation: button missing")
            self.assertIsNotNone(full)
            self.assertIn("--- backend/server.js ---", full)
            self.assertIn("button missing", full)
            self.assertLessEqual(len(full) + len(m.FORMAT_INSTRUCTIONS) + 1, flow.codegen_context_chars())

    def test_should_still_give_up_when_even_the_builder_cannot_fit_the_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {})
            (root / "backend/server.js").write_text("e" * 95_000)   # the entry alone exceeds the budget
            (root / "tests").mkdir(); (root / "tests/REQ-9.spec.ts").write_text("spec")
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.tests_dir = root / "tests"; flow.spec_map = {"REQ-9": ["REQ-9.spec.ts"]}
            flow.requirement_nodes = {"REQ-9": {"id": "REQ-9", "description": "d"}}
            # A prompt that carries no requotable source block and is itself over the limit.
            self.assertIsNone(flow.codegen_repair_prompt("REQ-9", "x" * 95_000, failures="f"))

    def test_should_prefer_a_refused_path_over_a_spec_named_page(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _app(root, {"frontend/src/login.html": "l" * 100, "frontend/src/ticket-orders.html": "t" * 100})
            scored = m.scored_sources(root, "login page", must_include={"frontend/src/ticket-orders.html"})
            self.assertEqual([str(r[3]) for r in scored][:3],
                             ["backend/server.js", "frontend/src/ticket-orders.html", "frontend/src/login.html"])


if __name__ == "__main__":
    unittest.main()
