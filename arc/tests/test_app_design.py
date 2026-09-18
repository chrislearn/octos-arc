"""One application-level design per run, injected into every node's codegen prompt.

Codegen implements one node at a time and each node's prompt sees only its own
description and spec; upstream nodes appear as `implemented (see code)`. Nothing
tells node 40 which routes, pages and record shapes nodes 1-39 agreed on except
whatever it can infer from the quoted sources. A single request over the tree's
outline (ids, names, descriptions, dependencies -- no scenarios, they duplicate
the specs) produces routes/pages/data_model once; every node then gets the
slice that overlaps its spec, in a fixed position after the rules so the
provider's prefix cache still keys on it.
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as m  # noqa: E402

TREE = {
    "id": "ROOT", "name": "Shop", "type": "FOLDER", "description": "A shop.",
    "children": [
        {"id": "REQ-1", "name": "Accounts", "type": "FOLDER", "description": "Users register and log in.",
         "children": [
             {"id": "REQ-1.1", "name": "Register", "type": "ATOMIC", "dependencies": [],
              "description": "The register page has Email and Password fields.",
              "scenarios": [{"name": "s", "steps": [{"keyword": "GIVEN", "content": "long scenario text " * 40}]}]},
             {"id": "REQ-1.2", "name": "Login", "type": "ATOMIC", "dependencies": ["REQ-1.1"],
              "description": "The login page signs a registered user in."},
         ]},
        {"id": "REQ-2", "name": "Orders", "type": "ATOMIC", "dependencies": ["REQ-1.2"],
         "description": "A logged-in user places an order from the orders page."},
    ],
}

DESIGN = {
    "data_model": {"users": {"email": "string", "password": "string"}, "orders": {"id": "string", "userId": "string"}},
    "routes": [{"method": "POST", "path": "/api/register", "purpose": "create user"},
               {"method": "POST", "path": "/api/login", "purpose": "session"},
               {"method": "POST", "path": "/api/orders", "purpose": "place order"}],
    "pages": [{"path": "/register", "purpose": "registration form"},
              {"path": "/login", "purpose": "login form"},
              {"path": "/orders", "purpose": "order list"}],
    "notes": "sessions via cookie",
}


class TreeOutlineTests(unittest.TestCase):
    def test_should_keep_ids_names_descriptions_and_dependencies_but_not_scenarios(self):
        out = m.tree_outline(TREE)
        for token in ("REQ-1.1", "Register", "Email and Password", "REQ-1.2", "depends on REQ-1.1", "REQ-2"):
            self.assertIn(token, out)
        self.assertNotIn("long scenario text", out)
        self.assertLess(out.index("REQ-1.1"), out.index("REQ-1.2"))

    def test_should_cap_the_outline_and_say_so(self):
        out = m.tree_outline(TREE, max_chars=120)
        self.assertLessEqual(len(out), 120 + 80)
        self.assertIn("outline truncated", out)


class DesignContextTests(unittest.TestCase):
    def test_should_return_nothing_without_a_design(self):
        self.assertEqual(m.app_design_context(None, "spec", 6000), "")
        self.assertEqual(m.app_design_context({}, "spec", 6000), "")

    def test_should_quote_the_whole_design_when_it_fits(self):
        out = m.app_design_context(DESIGN, "goto('/orders')", 6000)
        self.assertIn("Application design", out)
        for token in ("/api/register", "/api/orders", "/register", "/orders", "userId", "sessions via cookie"):
            self.assertIn(token, out)

    def test_should_keep_the_data_model_and_drop_unrelated_routes_and_pages_when_over_cap(self):
        full = len(json.dumps(DESIGN, ensure_ascii=False))
        out = m.app_design_context(DESIGN, "await page.goto('/orders'); orders", full - 40)
        self.assertIn("userId", out)            # data model always
        self.assertIn("/api/orders", out)       # overlaps the spec
        self.assertIn('"/orders"', out)
        self.assertNotIn("/api/register", out)  # no overlap
        self.assertNotIn("/login", out)

    def test_should_never_exceed_the_cap_by_more_than_the_marker(self):
        big = dict(DESIGN, notes="n" * 20000)
        out = m.app_design_context(big, "orders", 500)
        self.assertLessEqual(len(out), 500 + 120)
        self.assertIn("design truncated", out)


class AppDesignTurnTests(unittest.TestCase):
    def _flow(self, folder, reply, nodes=3, evolution=False, codegen=True):
        root = Path(folder)
        flow = m.Flow(argparse.Namespace(web_port=1), root, root)
        flow.output_dir = root
        flow.evolution = evolution
        flow.codegen_mode = lambda: codegen
        flow.llm_proxy = Mock(mode="low")
        flow.driver = object.__new__(m.OctosDriver)
        flow.driver.tools_disabled = False
        flow.driver._session = None
        flow.calls = []
        def turn(prompt, timeout, label, **kw):
            flow.calls.append((prompt, label))
            return True, reply
        flow.turn = turn
        ordered = [{"id": f"REQ-{i}", "type": "ATOMIC"} for i in range(1, nodes + 1)]
        return flow, ordered

    def test_should_produce_persist_and_keep_the_design_from_one_request(self):
        with tempfile.TemporaryDirectory() as folder:
            reply = "Here is the design:\n```json\n" + json.dumps(DESIGN) + "\n```\n"
            flow, ordered = self._flow(folder, reply)
            design = flow.app_design(TREE, ordered)
            self.assertEqual(design["routes"][0]["path"], "/api/register")
            self.assertEqual(flow.app_design_doc, design)
            self.assertEqual(len(flow.calls), 1)
            prompt, label = flow.calls[0]
            self.assertIn("REQ-1.1", prompt)
            self.assertNotIn("long scenario text", prompt)
            self.assertIn("design", label)
            self.assertTrue((Path(folder) / ".arc" / "design" / "app.json").is_file())
            self.assertFalse(flow.driver.tools_disabled)   # scope restored

    def test_should_continue_without_a_design_when_the_reply_has_no_json(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, ordered = self._flow(folder, "dry run: no model call; nothing written.")
            self.assertIsNone(flow.app_design(TREE, ordered))
            self.assertIsNone(flow.app_design_doc)
            self.assertFalse((Path(folder) / ".arc" / "design" / "app.json").exists())

    def test_should_skip_small_trees_evolution_runs_tool_mode_and_the_env_switch(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            reply = "```json\n" + json.dumps(DESIGN) + "\n```"
            for kwargs in ({"nodes": 2}, {"evolution": True}, {"codegen": False}):
                flow, ordered = self._flow(folder, reply, **kwargs)
                self.assertIsNone(flow.app_design(TREE, ordered), kwargs)
                self.assertEqual(flow.calls, [], kwargs)
            flow, ordered = self._flow(folder, reply)
            with patch.dict(os.environ, {"OCTOS_ARC_APP_DESIGN": "0"}):
                self.assertIsNone(flow.app_design(TREE, ordered))
            self.assertEqual(flow.calls, [])


class PromptPlacementTests(unittest.TestCase):
    def _flow(self, folder):
        root = Path(folder)
        (root / "frontend/src").mkdir(parents=True); (root / "backend").mkdir()
        (root / "frontend/package.json").write_text("{}"); (root / "backend/package.json").write_text("{}")
        (root / "backend/server.js").write_text("// entry\n" + "s" * 300)
        (root / "frontend/src/orders.html").write_text("<h1>orders</h1>" + "p" * 300)
        flow = m.Flow(argparse.Namespace(web_port=1), root, root)
        flow.output_dir = root
        return flow

    def test_should_place_the_design_after_the_rules_and_before_the_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder)
            flow.app_design_doc = DESIGN
            node = {"id": "REQ-2", "description": "orders"}
            prompt = flow.codegen_implement_prompt(node, "await page.goto('/orders');")
            self.assertIsNotNone(prompt)
            design_at = prompt.index("Application design")
            self.assertLess(prompt.index("Files:"), design_at)                   # rules first
            self.assertLess(design_at, prompt.index("--- backend/server.js ---"))  # then sources
            self.assertLess(design_at, prompt.index("Requirement REQ-2"))          # task last

    def test_should_leave_the_prompt_unchanged_without_a_design(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder)
            flow.app_design_doc = None
            prompt = flow.codegen_implement_prompt({"id": "REQ-2", "description": "orders"}, "await page.goto('/orders');")
            self.assertNotIn("Application design", prompt)

    def test_should_count_the_design_against_the_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder)
            flow.app_design_doc = DESIGN
            flow.codegen_implement_prompt({"id": "REQ-2", "description": "o"}, "spec")
            with_design = flow.codegen_budget["room"]
            flow.app_design_doc = None
            flow.codegen_implement_prompt({"id": "REQ-2", "description": "o"}, "spec")
            self.assertLess(with_design, flow.codegen_budget["room"])


if __name__ == "__main__":
    unittest.main()
