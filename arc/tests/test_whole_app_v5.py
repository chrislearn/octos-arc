"""The v5 whole-app path keeps a measured, per-leaf repair fallback."""
import argparse
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main as m
from acceptance import RunSummary, TestOutcome
from requirement_order import topo_order


class WholeAppTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.tests_dir = self.root / "tests"
        self.flow.tests_dir.mkdir()
        self.nodes = [
            {"id": node_id, "name": node_id, "type": "ATOMIC", "description": f"Feature {node_id}"}
            for node_id in ("A", "B", "C")
        ]
        self.tree = {"id": "ROOT", "name": "App", "type": "FOLDER", "children": self.nodes}
        for node in self.nodes:
            node_id = node["id"]
            (self.flow.tests_dir / f"{node_id}.spec.ts").write_text(f"test('{node_id}', () => {{ shared(); }});")
        (self.flow.tests_dir / "helpers.ts").write_text("export function shared() {}")
        self.flow.spec_map = {node["id"]: [f"{node['id']}.spec.ts"] for node in self.nodes}
        self.flow.runner = object()
        self.flow.codegen_mode = Mock(return_value=True)
        self.flow.remaining = Mock(return_value=4000)
        self.flow.wound_down = Mock(return_value=False)
        self.flow.commit = Mock()

    def test_one_generation_turn_quotes_every_leaf_and_shared_helper_once(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value="complete prompt")

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/index.html"]
            return True, "files"

        flow.codegen_turn = Mock(side_effect=generated)
        self.assertTrue(flow.whole_app_codegen(self.tree, self.nodes))
        combined, specs = flow.codegen_implement_prompt.call_args.args
        self.assertEqual(combined["id"], "whole application")
        for node in self.nodes:
            self.assertIn(node["id"], combined["description"])
            self.assertIn(f"--- {node['id']}.spec.ts ---", specs)
        self.assertEqual(specs.count("--- helpers.ts ---"), 1)
        flow.codegen_turn.assert_called_once()
        flow.commit.assert_called_once()

    def test_unfitting_prompt_and_explicit_disable_use_node_flow(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value=None)
        flow.codegen_turn = Mock()
        flow.whole_app_waves = Mock(return_value=False)
        self.assertFalse(flow.whole_app_codegen(self.tree, self.nodes))
        flow.whole_app_waves.assert_called_once_with(self.tree, self.nodes)
        flow.codegen_turn.assert_not_called()
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP": "0"}):
            self.assertFalse(flow.whole_app_codegen(self.tree, self.nodes))
        flow.codegen_implement_prompt.assert_called_once()

    def test_no_complete_file_write_falls_back(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value="prompt")
        flow.codegen_turn = Mock(return_value=(False, "output_truncated"))
        flow.whole_app_waves = Mock(return_value=False)
        self.assertFalse(flow.whole_app_codegen(self.tree, self.nodes))
        flow.whole_app_waves.assert_called_once_with(self.tree, self.nodes)
        flow.commit.assert_not_called()

    def test_oversized_whole_prompt_uses_two_generation_waves(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(side_effect=[None, "wave prompt", "wave prompt"])

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            return True, "files"

        flow.codegen_turn = Mock(side_effect=generated)
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_codegen(self.tree, self.nodes))
        self.assertEqual(flow.codegen_turn.call_count, 2)
        self.assertEqual(flow.commit.call_count, 2)

    def test_truncated_wave_is_split_before_node_fallback(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        replies = iter([(False, "output_truncated"), (True, "files"), (True, "files")])

        def generated(*args, **kwargs):
            ok, reply = next(replies)
            flow.last_codegen_written = ["frontend/src/feature.js"] if ok else []
            return ok, reply

        flow.codegen_turn = Mock(side_effect=generated)
        self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.codegen_turn.call_count, 3)
        self.assertEqual(flow.commit.call_count, 2)

    def test_later_waves_keep_the_reduced_ceiling(self):
        flow = self.flow
        nodes = [{"id": str(i), "description": "feature"} for i in range(12)]
        tree = {"id": "ROOT", "children": nodes}
        flow.batch_spec_bodies = lambda ids: "spec"
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        def generate(*args, **kwargs):
            success = flow.codegen_turn.call_count > 1
            flow.last_codegen_written = ["frontend/src/App.jsx"] if success else []
            return success, "files" if success else "output_truncated"
        flow.codegen_turn = Mock(side_effect=generate)
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "8"}):
            self.assertTrue(flow.whole_app_waves(tree, nodes))
        self.assertEqual(flow.codegen_turn.call_count, 4)  # failed 8, then 4+4+4, not 4+8
        self.assertEqual(flow.whole_app_generated_ids, {str(i) for i in range(12)})

    def test_wave_prefers_parent_boundary_without_reordering(self):
        flow = self.flow
        flow.batch_spec_bodies = Mock(return_value="spec")
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        def generate(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/App.jsx"]
            return True, "files"
        flow.codegen_turn = Mock(side_effect=generate)
        tree = {"id": "ROOT", "children": [
            {"id": "first", "children": self.nodes[:1]}, {"id": "second", "children": self.nodes[1:]}]}
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_waves(tree, self.nodes))
        self.assertEqual([call.args[0] for call in flow.batch_spec_bodies.call_args_list], [["A"], ["B", "C"]])

    def test_failed_two_leaf_wave_does_not_retry_two_on_every_later_wave(self):
        flow = self.flow
        flow.batch_spec_bodies = Mock(return_value="spec")
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        sizes = []
        def generate(*args, **kwargs):
            size = len(flow.batch_spec_bodies.call_args.args[0])
            sizes.append(size)
            flow.last_codegen_written = ["frontend/src/App.jsx"] if size == 1 else []
            return size == 1, "files" if size == 1 else "output_truncated"
        flow.codegen_turn = Mock(side_effect=generate)
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(sizes, [2, 1, 1, 1])

    def test_malformed_wave_retries_format_before_shrinking(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        replies = iter([(False, "codegen reply contained no <<<FILE>>> or <<<EDIT>>> blocks"),
                        (True, "files")])

        def generated(*args, **kwargs):
            ok, reply = next(replies)
            flow.last_codegen_written = ["frontend/src/feature.js"] if ok else []
            return ok, reply

        flow.codegen_turn = Mock(side_effect=generated)
        self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.codegen_turn.call_count, 2)
        self.assertIn("preceding answer was discarded", flow.codegen_turn.call_args.args[0])
        flow.commit.assert_called_once()

    def test_unwritable_late_wave_keeps_completed_partial_app(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        replies = iter([(True, "files"), (False, "output_truncated")])

        def generated(*args, **kwargs):
            ok, reply = next(replies)
            flow.last_codegen_written = ["frontend/src/feature.js"] if ok else []
            return ok, reply

        flow.codegen_turn = Mock(side_effect=generated)
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.commit.call_count, 1)

    def test_waves_still_have_a_global_contract_if_design_turn_failed(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            return True, "files"

        flow.codegen_turn = Mock(side_effect=generated)
        self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        combined = flow.codegen_implement_prompt.call_args.args[0]
        self.assertIn("Whole-tree requirement map", combined["description"])
        self.assertIn("Feature A", combined["description"])

    def test_first_suite_selects_only_failed_leaf(self):
        flow = self.flow
        flow.run_specs = Mock(return_value=RunSummary(passed=2, total=3, results=[
            TestOutcome(title="A", ok=True, status="passed", duration_ms=1, file="A.spec.ts"),
            TestOutcome(title="B", ok=False, status="failed", duration_ms=1, file="B.spec.ts"),
            TestOutcome(title="C", ok=True, status="passed", duration_ms=1, file="C.spec.ts"),
        ]))
        flow.record_full_suite = Mock()
        self.assertEqual(flow.whole_app_first_suite(self.nodes), {"B"})
        self.assertTrue(flow.run_specs.call_args.kwargs["grader_like"])
        flow.record_full_suite.assert_called_once()

    def test_incomplete_suite_never_marks_leaf_passed(self):
        flow = self.flow
        flow.run_specs = Mock(return_value=RunSummary(passed=1, total=1, results=[
            TestOutcome(title="A", ok=True, status="passed", duration_ms=1, file="A.spec.ts"),
        ]))
        flow.record_full_suite = Mock()
        self.assertIsNone(flow.whole_app_first_suite(self.nodes))
        flow.record_full_suite.assert_not_called()

    def test_startup_error_gets_focused_repair_then_retests(self):
        flow = self.flow
        error = "generic scaffold route checks failed: backend/routes/notes.js:4 DELETE /api/notes/trash is shadowed"
        passed = [TestOutcome(title=n["id"], ok=True, status="passed", duration_ms=1,
                              file=f"{n['id']}.spec.ts") for n in self.nodes]
        flow.run_specs = Mock(side_effect=[RunSummary(error=error),
                                           RunSummary(passed=3, total=3, results=passed)])
        flow.whole_app_startup_repair = Mock(return_value=True)
        flow.record_full_suite = Mock()
        self.assertEqual(flow.whole_app_first_suite(self.nodes), set())
        flow.whole_app_startup_repair.assert_called_once_with(error)
        self.assertEqual(flow.run_specs.call_count, 2)

    def test_route_shadow_repair_quotes_only_implicated_source(self):
        flow = self.flow
        flow.node_timeout = 1200
        route = self.root / "backend/routes/notes.js"
        route.parent.mkdir(parents=True)
        route.write_text("app.delete('/api/notes/:id', one);\n"
                         "app.delete('/api/notes/trash', two);\n")
        error = ("generic scaffold route checks failed:\nbackend/routes/notes.js:2 "
                 "DELETE /api/notes/trash is shadowed by backend/routes/notes.js:1 DELETE /api/notes/:id")

        def repaired(prompt, *args, **kwargs):
            flow.last_codegen_written = ["backend/routes/notes.js"]
            self.assertIn("--- backend/routes/notes.js ---", prompt)
            self.assertIn("literal handler first", prompt)
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=repaired)
        flow.turn = Mock()
        self.assertTrue(flow.whole_app_startup_repair(error))
        flow.turn.assert_not_called()
        flow.commit.assert_called_once()

    def test_spa_preflight_quotes_frontend_manifest_and_page(self):
        flow = self.flow
        flow.node_timeout = 1200
        page = self.root / "frontend/src/index.html"
        page.parent.mkdir(parents=True)
        page.write_text("<a href='/notes' data-link>Notes</a>")
        manifest = self.root / "frontend/package.json"
        manifest.write_text('{"scripts": {}}')

        def repaired(prompt, *args, **kwargs):
            self.assertIn("--- frontend/package.json ---", prompt)
            self.assertIn("--- frontend/src/index.html ---", prompt)
            flow.last_codegen_written = ["frontend/package.json"]
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=repaired)
        self.assertTrue(flow.whole_app_startup_repair(
            "frontend: client-side links use history.pushState but only index.html exists"))

    def test_route_preflight_repairs_before_first_full_suite(self):
        flow = self.flow
        m.write_codegen_manifests(self.root)
        m.install_generic_template(self.root, Path(m.__file__).parent, 3000, [])
        route = self.root / "backend/routes/notes.js"
        route.parent.mkdir(parents=True)
        route.write_text("app.delete('/api/notes/:id', one);\n"
                         "app.delete('/api/notes/trash', two);\n")
        passed = [TestOutcome(title=n["id"], ok=True, status="passed", duration_ms=1,
                              file=f"{n['id']}.spec.ts") for n in self.nodes]
        flow.run_specs = Mock(return_value=RunSummary(passed=3, total=3, results=passed))
        flow.whole_app_startup_repair = Mock(return_value=True)
        flow.record_full_suite = Mock()
        self.assertEqual(flow.whole_app_first_suite(self.nodes), set())
        self.assertIn("DELETE /api/notes/trash is shadowed",
                      flow.whole_app_startup_repair.call_args.args[0])
        self.assertEqual(flow.run_specs.call_count, 1)

    def test_unreliable_first_suite_does_not_restart_all_nodes(self):
        flow = self.flow
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_first_suite = Mock(return_value=None)
        flow.mark = Mock()
        flow.node_cycle = Mock()
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        flow.node_cycle.assert_not_called()
        self.assertEqual([call.args[1] for call in flow.mark.call_args_list
                          if call.args[0] == "test_failed"], ["A", "B", "C"])
        self.assertTrue(all(flow.test_verdict[node["id"]] is False for node in self.nodes))

    def test_partial_waves_only_generate_unreached_nodes_if_suite_unavailable(self):
        flow = self.flow
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_generated_ids = {"A", "B"}
        flow.whole_app_first_suite = Mock(return_value=None)
        flow.mark = Mock()
        flow.node_cycle = Mock()
        flow.time_up = Mock(return_value=False)
        flow.driver = SimpleNamespace(end_scope=Mock())
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        flow.node_cycle.assert_called_once_with(self.nodes[2], self.nodes, 3, 3)
        self.assertEqual([call.args[1] for call in flow.mark.call_args_list
                          if call.args[0] == "implementation_done"], ["A", "B"])

    def test_failed_unreached_node_is_not_treated_as_preimplemented(self):
        flow = self.flow
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_generated_ids = {"A", "B"}
        flow.whole_app_first_suite = Mock(return_value={"C"})
        flow.mark = Mock()
        flow.node_cycle = Mock()
        flow.time_up = Mock(return_value=False)
        flow.driver = SimpleNamespace(end_scope=Mock())
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        flow.node_cycle.assert_called_once_with(self.nodes[2], self.nodes, 3, 3,
                                                preimplemented=False)

    def test_only_failing_leaf_receives_a_node_repair_turn(self):
        flow = self.flow
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_first_suite = Mock(return_value={"B"})
        flow.mark = Mock()
        flow.node_cycle = Mock()
        flow.time_up = Mock(return_value=False)
        flow.driver = SimpleNamespace(end_scope=Mock())
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        flow.node_cycle.assert_called_once_with(self.nodes[1], self.nodes, 2, 3, preimplemented=True)
        flow.driver.end_scope.assert_called_once_with("node")
        self.assertEqual([call.args[1] for call in flow.mark.call_args_list
                          if call.args[0] == "test_passed"], ["A", "C"])

    def test_real_keep_whole_prompt_fits_default_budget(self):
        # Keep is the first v5 experiment, but the generator remains task-neutral.
        bundle = Path(m.__file__).parent
        tree = m.load_requirement_tree(bundle / "tasks/arc-bench-web--keep")
        nodes = topo_order(tree)
        flow = self.flow
        flow.tests_dir = bundle / "public-tests/arc-bench-web--keep"
        flow.spec_map = {str(node["id"]): [f"{node['id']}.spec.ts"] for node in nodes}
        flow.codegen_context_chars = Mock(return_value=90000)
        flow.codegen_reasoning = Mock(return_value="low")
        flow.codegen_ports_clause = Mock(return_value="")
        m.write_codegen_manifests(self.root)
        m.install_generic_template(self.root, bundle, 3000, [])
        flow.generic_template_installed = True
        flow.codegen_turn = Mock(return_value=(False, "output_truncated"))
        flow.whole_app_waves = Mock(return_value=False)
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_MAX_NODES": "64"}):
            self.assertFalse(flow.whole_app_codegen(tree, nodes))
        self.assertEqual(flow.codegen_turn.call_count, 1)
        prompt = flow.codegen_turn.call_args.args[0]
        self.assertIn("REQ-6.2", prompt)
        self.assertIn("frontend/src/index.html", m.quoted_paths(prompt))
        self.assertIn("frontend/src/app.js", m.quoted_paths(prompt))
        self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 90000)

    def test_large_tree_defaults_to_waves_without_spending_a_one_shot_turn(self):
        bundle = Path(m.__file__).parent
        tree = m.load_requirement_tree(bundle / "tasks/arc-bench-web--keep")
        nodes = topo_order(tree)
        flow = self.flow
        flow.tests_dir = bundle / "public-tests/arc-bench-web--keep"
        flow.spec_map = {str(node["id"]): [f"{node['id']}.spec.ts"] for node in nodes}
        flow.whole_app_waves = Mock(return_value=True)
        flow.codegen_turn = Mock()
        self.assertTrue(flow.whole_app_codegen(tree, nodes))
        flow.whole_app_waves.assert_called_once_with(tree, nodes)
        flow.codegen_turn.assert_not_called()

    def test_all_six_web_tasks_can_be_partitioned_into_bounded_prompts(self):
        bundle = Path(m.__file__).parent
        for requirement_dir in sorted((bundle / "tasks").glob("arc-bench-web--*")):
            with self.subTest(task=requirement_dir.name):
                tree = m.load_requirement_tree(requirement_dir)
                nodes = topo_order(tree)
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                root = Path(temp.name)
                flow = m.Flow(argparse.Namespace(web_port=3000), root, requirement_dir)
                flow.tests_dir = bundle / "public-tests" / requirement_dir.name
                specs = sorted(str(path.relative_to(flow.tests_dir))
                               for path in flow.tests_dir.rglob("*.spec.ts"))
                flow.spec_map, _ = m.map_specs_to_nodes(specs, [str(node["id"]) for node in nodes])
                flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
                flow.codegen_context_chars = Mock(return_value=90000)
                flow.codegen_reasoning = Mock(return_value="low")
                flow.codegen_ports_clause = Mock(return_value="")
                flow.remaining = Mock(return_value=10000)
                flow.wound_down = Mock(return_value=False)
                flow.commit = Mock()
                m.write_codegen_manifests(root)
                m.install_generic_template(root, bundle, 3000, [])
                flow.generic_template_installed = True
                prompts = []

                def generated(prompt, *args, **kwargs):
                    prompts.append(prompt)
                    flow.last_codegen_written = ["frontend/src/feature.js"]
                    return True, "files"

                flow.codegen_turn = Mock(side_effect=generated)
                self.assertTrue(flow.whole_app_waves(tree, nodes))
                self.assertGreater(len(prompts), 1)
                self.assertLessEqual(len(prompts), 12)
                for prompt in prompts:
                    self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 90000)


if __name__ == "__main__":
    unittest.main()
