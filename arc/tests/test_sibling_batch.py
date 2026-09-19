"""A shared generation turn must not replace per-leaf verification."""
import argparse
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import main as m


class SiblingBatchFlowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.root = root
        self.flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
        self.flow.tests_dir = root / "tests"
        self.flow.tests_dir.mkdir()
        ids = ["A", "B", "C"]
        for node_id in ids:
            (self.flow.tests_dir / f"{node_id}.spec.ts").write_text(f"test('{node_id}', () => {{ useShared(); }});")
        (self.flow.tests_dir / "helpers.ts").write_text("export function useShared() { return true; }")
        self.flow.spec_map = {node_id: [f"{node_id}.spec.ts"] for node_id in ids}
        self.flow.runner = object()
        self.flow.n_nodes = 3
        self.flow.llm_proxy = SimpleNamespace(extra_drop_tools=set())
        self.flow.codegen_mode = Mock(return_value=True)
        self.flow.codegen_turn = Mock(return_value=(True, "files"))
        self.flow.commit = Mock(return_value=True)
        self.flow.remaining = Mock(return_value=1000)
        self.flow.wound_down = Mock(return_value=False)
        self.nodes = [{"id": node_id, "name": node_id, "type": "ATOMIC", "description": node_id,
                       "dependencies": [], "scenarios": []} for node_id in ids]

    def test_quotes_shared_helper_once_and_generates_one_batch_turn(self):
        flow = self.flow
        self.assertEqual(flow.batch_spec_bodies(["A", "B", "C"]).count("--- helpers.ts ---"), 1)
        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/index.html"]
            return True, "files"
        flow.codegen_turn.side_effect = generated
        self.assertTrue(flow.batch_codegen(self.nodes))
        flow.codegen_turn.assert_called_once()
        prompt = flow.codegen_turn.call_args.args[0]
        self.assertIn("A, B, C", prompt)
        self.assertEqual(prompt.count("--- helpers.ts ---"), 1)
        flow.commit.assert_called_once()

    def test_falls_back_when_batch_cannot_fit(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value=None)
        self.assertFalse(flow.batch_codegen(self.nodes))
        flow.codegen_turn.assert_not_called()

    def test_refused_existing_file_does_not_mark_batch_complete(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(side_effect=["initial prompt", None])
        def refused(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/new.html"]
            flow.last_codegen_refused = {"frontend/src/index.html"}
            flow.refused_paths.add("frontend/src/index.html")
            return True, "partial files"
        flow.codegen_turn.side_effect = refused
        self.assertFalse(flow.batch_codegen(self.nodes))
        flow.commit.assert_not_called()

    def test_preimplemented_leaf_still_runs_acceptance_without_another_generation(self):
        flow = self.flow
        m.write_codegen_manifests(self.root)
        (self.root / "frontend/src").mkdir(parents=True)
        (self.root / "frontend/src/index.html").write_text("<main>ok</main>")
        (self.root / "backend/server.js").write_text("// server")
        flow.design_enabled = False
        flow.classify_tree({"children": self.nodes})
        flow.mark = Mock()
        flow.acceptance_loop = Mock(return_value=True)
        flow.codegen_implement_prompt = Mock(return_value="prompt")
        flow.node_cycle(self.nodes[0], self.nodes, 1, 3, preimplemented=True)
        flow.codegen_turn.assert_not_called()
        flow.acceptance_loop.assert_called_once()
        self.assertTrue(flow.test_verdict["A"])


class StableSourceOrderTests(unittest.TestCase):
    def test_orders_selected_quotes_by_churn_without_changing_selection(self):
        scored = [(0, 0, 6, Path("backend/server.js"), "server"),
                  (4, -2, 6, Path("frontend/src/index.html"), "index!"),
                  (4, -1, 7, Path("frontend/src/archive.html"), "archive")]
        baseline = m.select_source_snapshot(scored, 30, stable_order=True)
        stable = m.select_source_snapshot(scored, 30, stable_order=True,
                                          change_counts={"frontend/src/index.html": 9})
        self.assertEqual(m.quoted_paths(baseline), m.quoted_paths(stable))
        self.assertLess(stable.index("--- backend/server.js ---"), stable.index("--- frontend/src/archive.html ---"))
        self.assertLess(stable.index("--- frontend/src/archive.html ---"), stable.index("--- frontend/src/index.html ---"))

    def test_counts_app_file_edits_from_git_history(self):
        flow = object.__new__(m.Flow)
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="backend/server.js\nfrontend/src/index.html\nfrontend/src/index.html\n")))
        self.assertEqual(flow.source_change_counts(),
                         {"backend/server.js": 1, "frontend/src/index.html": 2})


if __name__ == "__main__":
    unittest.main()
