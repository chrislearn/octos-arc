"""Review report items 1 (attributable measurement), 2 (core + catalog design)
and 7 (design metadata and reuse)."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as m  # noqa: E402
import llm_proxy  # noqa: E402
import usage_by_node  # noqa: E402

DESIGN = {"data_model": {"users": {"email": "string"}, "orders": {"id": "string", "userId": "string"}},
          "routes": [{"method": "POST", "path": "/api/register", "purpose": "create user"},
                     {"method": "POST", "path": "/api/login", "purpose": "session"},
                     {"method": "POST", "path": "/api/orders", "purpose": "place order"}],
          "pages": [{"path": "/register", "purpose": "registration form"},
                    {"path": "/login", "purpose": "login form"},
                    {"path": "/orders", "purpose": "order list"}],
          "notes": "sessions via cookie"}


class PromptFingerprintTests(unittest.TestCase):
    def _body(self, *contents):
        return json.dumps({"model": "m", "messages": [{"role": "user", "content": c} for c in contents]}).encode()

    def test_should_hash_the_messages_and_measure_the_prefix_shared_with_the_previous_request(self):
        sha1, shared1, text1 = llm_proxy.prompt_fingerprint(self._body("RULES " * 100, "node A"), "")
        sha2, shared2, text2 = llm_proxy.prompt_fingerprint(self._body("RULES " * 100, "node B"), text1)
        self.assertEqual(len(sha1), 64); self.assertNotEqual(sha1, sha2)
        self.assertEqual(shared1, 0)
        self.assertGreaterEqual(shared2, 600)            # the rules prefix is shared
        self.assertLess(shared2, len(text2))             # the node text is not

    def test_should_tolerate_bodies_that_are_not_chat_requests(self):
        self.assertEqual(llm_proxy.prompt_fingerprint(b"not json", "x"), ("", 0, ""))


class UsageByNodeTests(unittest.TestCase):
    def _rec(self, label, prompt, hit, completion, reasoning=0, ms=1000, shared=0):
        return {"label": label, "prompt_tokens": prompt, "prompt_cache_hit_tokens": hit, "completion_tokens": completion,
                "reasoning_tokens": reasoning, "elapsed_ms": ms, "prefix_shared_chars": shared, "request": {"user_chars": 1000}}

    def test_should_aggregate_per_node_and_phase_and_flag_first_pass(self):
        records = [self._rec("application design", 14000, 0, 3000),
                   self._rec("REQ-1 implement", 20000, 15000, 800),
                   self._rec("REQ-2 implement", 22000, 18000, 900),
                   self._rec("REQ-2 repair 1/3", 24000, 20000, 700, reasoning=200),
                   self._rec("REQ-2 repair 2/3", 30000, 2000, 300),   # tool mode, little cache
                   self._rec("checkpoint 8 repair 1/1", 26000, 20000, 500)]
        summary = usage_by_node.summarize(records)
        nodes = summary["nodes"]
        self.assertEqual(nodes["REQ-1"]["requests"], 1)
        self.assertTrue(nodes["REQ-1"]["no_node_repair"])
        self.assertFalse(nodes["REQ-2"]["no_node_repair"])
        self.assertEqual(nodes["REQ-2"]["requests"], 3)
        self.assertEqual(nodes["REQ-2"]["prompt_tokens"], 76000)
        self.assertEqual(nodes["REQ-2"]["cache_miss_tokens"], 76000 - 40000)
        self.assertEqual(nodes["REQ-2"]["by_phase"]["repair"]["requests"], 2)
        self.assertEqual(summary["run"]["design"]["requests"], 1)
        self.assertEqual(summary["run"]["checkpoint"]["requests"], 1)
        self.assertEqual(summary["totals"]["requests"], 6)
        self.assertIn("REQ-2", usage_by_node.render(summary))

    def test_should_account_for_shared_batch_once_at_run_level(self):
        records = [self._rec("sibling batch REQ-1, REQ-2 implement", 30000, 25000, 1000)]
        summary = usage_by_node.summarize(records)
        self.assertEqual(summary["run"]["batch"]["requests"], 1)
        self.assertEqual(summary["totals"]["prompt_tokens"], 30000)


class TwoLayerDesignTests(unittest.TestCase):
    def test_should_keep_a_small_design_whole_before_the_sources(self):
        stable, node_slice = m.app_design_blocks(DESIGN, "orders", 6000)
        self.assertIn("/api/login", stable); self.assertEqual(node_slice, "")

    def test_should_split_a_large_design_into_stable_core_plus_catalog_and_a_node_slice(self):
        full = len(json.dumps(DESIGN))
        stable_a, slice_a = m.app_design_blocks(DESIGN, "await page.goto('/orders'); orders", full - 40)
        stable_b, slice_b = m.app_design_blocks(DESIGN, "await page.goto('/login'); login", full - 40)
        self.assertEqual(stable_a, stable_b, "core + catalog are the same for every node")
        self.assertIn("userId", stable_a)                       # core: data model
        self.assertIn("design truncated", stable_a)             # omissions are explicit under the combined cap
        self.assertIn("POST /api/login", stable_a)              # catalog: every route, one line each
        self.assertIn("/register", stable_a)                    # catalog: every page
        self.assertNotIn("registration form", stable_a)         # catalog carries no detail text
        self.assertIn("place order", slice_a); self.assertNotIn("session", slice_a)
        self.assertIn("session", slice_b); self.assertNotIn("place order", slice_b)

    def test_should_normalise_key_order_so_equal_designs_render_identically(self):
        a = {"routes": [{"path": "/x", "method": "GET"}], "data_model": {}}
        b = {"data_model": {}, "routes": [{"method": "GET", "path": "/x"}]}
        self.assertEqual(m.app_design_blocks(a, "x", 6000), m.app_design_blocks(b, "x", 6000))

    def test_should_cap_both_layers(self):
        big = dict(DESIGN, notes="n" * 20000, routes=[{"method": "GET", "path": f"/api/r{i}"} for i in range(400)])
        stable, node_slice = m.app_design_blocks(big, "r1", 1500)
        self.assertLessEqual(len(stable) + len(node_slice), 1500)


class DesignReuseTests(unittest.TestCase):
    TREE = {"id": "ROOT", "type": "FOLDER", "children": [
        {"id": f"REQ-{i}", "type": "ATOMIC", "description": f"feature {i}"} for i in range(1, 4)]}

    def _flow(self, folder, reply="```json\n" + json.dumps(DESIGN) + "\n```", evolution=False):
        root = Path(folder)
        flow = m.Flow(argparse.Namespace(web_port=1), root, root)
        flow.output_dir = root; flow.evolution = evolution
        flow.codegen_mode = lambda: True
        flow.llm_proxy = Mock(mode="low")
        flow.driver = object.__new__(m.OctosDriver); flow.driver.tools_disabled = False; flow.driver._session = None
        flow.calls = []
        def turn(prompt, timeout, label, **kw):
            flow.calls.append(label); return True, reply
        flow.turn = turn
        return flow, [{"id": f"REQ-{i}"} for i in range(1, 4)]

    def test_should_write_metadata_beside_the_design(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, ordered = self._flow(folder)
            flow.app_design(self.TREE, ordered)
            meta = json.loads((Path(folder) / ".arc/design/app.meta.json").read_text())
            for key in ("tree_sha256", "prompt_version", "model", "design_sha256"):
                self.assertIn(key, meta)
            self.assertEqual(meta["prompt_version"], m.APP_DESIGN_PROMPT_VERSION)

    def test_should_reuse_a_compatible_design_without_a_request(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, ordered = self._flow(folder)
            flow.app_design(self.TREE, ordered)
            again, _ = self._flow(folder)
            self.assertEqual(again.app_design(self.TREE, ordered), DESIGN)
            self.assertEqual(again.calls, [])

    def test_should_regenerate_when_the_tree_or_prompt_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, ordered = self._flow(folder)
            flow.app_design(self.TREE, ordered)
            changed = json.loads(json.dumps(self.TREE)); changed["children"][0]["description"] = "different"
            again, _ = self._flow(folder)
            again.app_design(changed, ordered)
            self.assertEqual(again.calls, ["application design"])

    def test_omitted_scenario_changes_still_invalidate_cached_design(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder, patch.dict(
                "os.environ", {"OCTOS_ARC_APP_DESIGN_OUTLINE_CHARS": "100"}):
            flow, ordered = self._flow(folder)
            flow.app_design(self.TREE, ordered)
            changed = json.loads(json.dumps(self.TREE))
            changed["children"][-1]["scenarios"] = [{"steps": [{"keyword": "THEN", "content": "new rule"}]}]
            self.assertEqual(m.tree_outline(self.TREE, 100), m.tree_outline(changed, 100))
            again, _ = self._flow(folder)
            again.app_design(changed, ordered)
            self.assertEqual(again.calls, ["application design"])

    def test_should_load_a_compatible_design_in_evolution_mode_but_not_generate_one(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, ordered = self._flow(folder)
            flow.app_design(self.TREE, ordered)
            evo, _ = self._flow(folder, evolution=True)
            self.assertEqual(evo.app_design(self.TREE, ordered), DESIGN)
            self.assertEqual(evo.calls, [])
            (Path(folder) / ".arc/design/app.meta.json").unlink()
            evo2, _ = self._flow(folder, evolution=True)
            self.assertIsNone(evo2.app_design(self.TREE, ordered))
            self.assertEqual(evo2.calls, [])


if __name__ == "__main__":
    unittest.main()
