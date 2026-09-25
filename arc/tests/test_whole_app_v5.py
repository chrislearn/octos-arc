"""The v5 whole-app path keeps a measured, per-leaf repair fallback."""
import argparse
import os
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
        experimental = patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP": "1"})
        experimental.start()
        self.addCleanup(experimental.stop)
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
        self.flow.events = Mock()  # a real run always has the platform event client
        # Generation tests below mock the list of written paths rather than
        # writing those files. Batch-check behavior has dedicated tests; do not
        # run a real scaffold build against a fictional mock write here.
        self.flow.generation_batch_check = Mock()

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

    def test_explicit_no_change_advances_wave_but_still_requires_suite_verification(self):
        flow = self.flow
        flow.codegen_implement_prompt = Mock(return_value="prompt")
        def satisfied(*args, **kwargs):
            flow.last_codegen_no_change = True
            flow.last_codegen_written = []
            return True, "<<<NO CHANGE>>>"
        flow.codegen_turn = Mock(side_effect=satisfied)
        self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        flow.codegen_turn.assert_called_once()
        self.assertEqual(flow.whole_app_generated_ids, {'A', 'B', 'C'})
        self.assertEqual(flow.test_verdict, {})  # a model's claim is not a passing test

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
        with patch.dict("os.environ", {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "8",
                                       "OCTOS_ARC_CODEGEN_OUTPUT_TOKENS": "32768"}):
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

    def test_no_spec_generation_stays_pending_until_final_contract_review(self):
        flow = self.flow
        flow.tests_dir = None
        flow.runner = None
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_generated_ids = {"A", "B", "C"}
        flow.whole_app_first_suite = Mock(return_value=None)
        flow.mark = Mock()
        flow.node_cycle = Mock()
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        flow.node_cycle.assert_not_called()
        self.assertFalse(any(call.args[0] == "test_failed" for call in flow.mark.call_args_list))
        self.assertTrue(all(flow.test_verdict[node["id"]] is None for node in self.nodes))

    def test_auto_whole_app_is_no_spec_only_and_uses_derived_contract(self):
        from requirement_contracts import compile_contracts
        flow = self.flow
        flow.tests_dir = None
        flow.runner = None
        flow.requirement_contracts = compile_contracts(self.nodes)
        flow.codegen_implement_prompt = Mock(return_value="complete prompt")

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/index.html"]
            return True, "files"

        flow.codegen_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP": "auto"}):
            self.assertTrue(flow.whole_app_codegen(self.tree, self.nodes))
        _, contract = flow.codegen_implement_prompt.call_args.args
        self.assertIn("not official Playwright tests", contract)

        flow.tests_dir = self.root / "tests"
        flow.runner = object()
        flow.codegen_turn.reset_mock()
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP": "auto"}):
            self.assertFalse(flow.whole_app_codegen(self.tree, self.nodes))
        flow.codegen_turn.assert_not_called()

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

    def test_should_implement_partial_leaves_again_when_official_specs_are_absent(self):
        flow = self.flow
        flow.tests_dir = None
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_generated_ids = {"A"}
        flow.whole_app_partial_ids = {"B"}
        flow.whole_app_first_suite = Mock(return_value=None)
        flow.mark = Mock()
        flow.node_cycle = Mock()
        flow.time_up = Mock(return_value=False)
        flow.driver = SimpleNamespace(end_scope=Mock())
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        partial_call = flow.node_cycle.call_args_list[0]
        self.assertEqual(partial_call.args[0], self.nodes[1])
        self.assertFalse(partial_call.kwargs.get("preimplemented", False))

    def test_should_keep_preimplemented_partial_leaves_when_official_specs_decide(self):
        flow = self.flow
        flow.whole_app_codegen = Mock(return_value=True)
        flow.whole_app_generated_ids = {"A"}
        flow.whole_app_partial_ids = {"B"}
        flow.whole_app_first_suite = Mock(return_value=None)
        flow.mark = Mock()
        flow.node_cycle = Mock()
        flow.time_up = Mock(return_value=False)
        flow.driver = SimpleNamespace(end_scope=Mock())
        self.assertTrue(flow.whole_app_experiment(self.tree, self.nodes))
        self.assertTrue(flow.node_cycle.call_args_list[0].kwargs.get("preimplemented"))

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

    def test_real_keep_whole_prompt_fits_input_but_exceeds_output_budget(self):
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
        flow.codegen_turn.assert_not_called()
        flow.whole_app_waves.assert_called_once_with(tree, nodes)
        prompt = flow.codegen_implement_prompt(
            {"id": "whole application", "description": m.tree_outline(tree)},
            flow.batch_spec_bodies([str(node['id']) for node in nodes]))
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

    def test_hyphenated_requirement_id_selects_its_design_slice(self):
        design = {
            "data_model": {},
            "routes": [],
            "pages": [{"path": "/access", "purpose": "manage access",
                       "requirements": ["REQ-2-3"]}],
        }
        rendered = m.app_design_context(design, "[REQ-2-3] Grant repository access", 6000)
        self.assertIn('/access', rendered)

    def test_wave_targets_include_shared_composition_and_related_modules(self):
        flow = self.flow
        files = {
            "frontend/src/App.jsx": "export default function App() {}",
            "frontend/src/style.css": ".app {}",
            "backend/routes/repositories.js": "module.exports = app => {};",
            "backend/lib/accessGrants.js": "module.exports = {};",
        }
        for rel, source in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        flow.app_design_doc = {
            "data_model": {},
            "routes": [{"method": "POST", "path": "/api/repositories/:owner/:repo/access",
                        "purpose": "grant repository access", "requirements": ["REQ-2-3"]}],
            "pages": [{"path": "/:owner/:repo/settings/access", "purpose": "repository access",
                       "requirements": ["REQ-2-3"]}],
            "modules": [{"path": "backend/lib/accessGrants.js", "owns": ["repository access grants"]}],
        }
        flow.refused_paths = {"backend/routes/repositories.js"}
        targets = flow.whole_app_wave_targets(
            ["REQ-2-3"], "[REQ-2-3] grant repository access", "repository access grants")
        self.assertTrue({"frontend/src/App.jsx", "frontend/src/style.css",
                         "backend/routes/repositories.js", "backend/lib/accessGrants.js"} <= targets)

    def test_wave_guard_requires_owned_design_routes_and_pages(self):
        flow = self.flow
        app = self.root / "frontend/src/App.jsx"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text('<Routes><Route path="/" element={<Home />} /></Routes>')
        route = self.root / "backend/routes/repositories.js"
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text("module.exports = app => { app.get('/api/repositories', list); };")
        flow.app_design_doc = {
            "data_model": {},
            "routes": [{"method": "POST", "path": "/api/repositories/:owner/:repo/access",
                        "requirements": ["REQ-2-3"]}],
            "pages": [{"path": "/:owner/:repo/settings/access", "requirements": ["REQ-2-3"]}],
        }
        flow.last_codegen_refused = set()
        flow._generation_gate_result = None
        gaps = flow.whole_app_wave_gaps(["REQ-2-3"])
        self.assertTrue(any("design route missing" in gap for gap in gaps))
        self.assertTrue(any("design page route missing" in gap for gap in gaps))
        route.write_text("module.exports = app => { app.post('/api/repositories/:owner/:repo/access', grant); };")
        app.write_text('<Routes><Route path="/:owner/:repo/settings/access" element={<Access />} /></Routes>')
        self.assertEqual(flow.whole_app_wave_gaps(["REQ-2-3"]), [])

    def test_wave_guard_requires_explicit_scenario_seed_literals(self):
        from requirement_contracts import compile_contracts
        flow = self.flow
        flow.tests_dir = None
        flow.requirement_contracts = compile_contracts([{
            "id": "REQ-SEED", "name": "Existing note", "type": "ATOMIC",
            "description": 'The system contains a note titled “Project ideas” with initial content “Draft”.',
            "scenarios": [{"name": "Open", "steps": [
                {"keyword": "GIVEN", "content": "The user is on the home page."},
                {"keyword": "WHEN", "content": "The user opens the note."},
                {"keyword": "THEN", "content": "The editor displays the initial content."},
            ]}],
        }])
        path = self.root / "backend/seed.js"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('module.exports = [{ title: "Project ideas" }];')
        flow.last_codegen_refused = set()
        flow._generation_gate_result = None
        gaps = flow.whole_app_wave_gaps(["REQ-SEED"])
        self.assertTrue(any("SEED_DATA" in gap and '"Draft"' in gap for gap in gaps))
        path.write_text('module.exports = [{ title: "Project ideas", content: "Draft" }];')
        self.assertEqual(flow.whole_app_wave_gaps(["REQ-SEED"]), [])

    def test_clean_no_spec_feature_review_costs_no_second_model_turn(self):
        from requirement_contracts import compile_contracts
        flow = self.flow
        flow.tests_dir = None
        node = {"id": "REQ-1", "name": "Home", "type": "ATOMIC",
                "description": "Show the home page", "scenarios": [{"name": "Open", "steps": [
                    {"keyword": "GIVEN", "content": "The user opens the application."},
                    {"keyword": "THEN", "content": "The home page is visible."}]}]}
        flow.requirement_contracts = compile_contracts([node])
        flow.whole_app_wave_gaps = Mock(return_value=[])
        flow.codegen_turn = Mock()
        self.assertEqual(flow.no_spec_feature_review(node, 10**12), [])
        flow.codegen_turn.assert_not_called()

    def test_seed_gap_triggers_one_focused_no_spec_repair(self):
        from requirement_contracts import compile_contracts
        flow = self.flow
        flow.tests_dir = None
        node = {"id": "REQ-1", "name": "Seed", "type": "ATOMIC",
                "description": 'The system contains a note titled “Project ideas”.',
                "scenarios": []}
        flow.requirement_contracts = compile_contracts([node])
        flow.whole_app_wave_gaps = Mock(side_effect=[["SEED_DATA REQ-1 missing Project ideas"], []])
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.codegen_implement_prompt = Mock(return_value="repair prompt")
        flow.codegen_turn = Mock(return_value=(True, "files"))
        flow.codegen_context_chars = Mock(return_value=90000)
        flow.remaining = Mock(return_value=4000)
        flow.wound_down = Mock(return_value=False)
        self.assertEqual(flow.no_spec_feature_review(node, 10**12), [])
        flow.codegen_turn.assert_called_once()
        self.assertIn("requirement contract repair", flow.codegen_turn.call_args.args[2])

    def test_incomplete_group_is_split_instead_of_marked_complete(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(side_effect=[["missing access route"], [], []])

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "3"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.whole_app_generation_turn.call_count, 3)
        self.assertEqual(flow.whole_app_generated_ids, {"A", "B", "C"})
        self.assertIn("missing access route", "\n".join(map(str, flow.pending_corrections)))

    def test_should_keep_generating_later_leaves_when_single_leaves_stay_partial(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(return_value=["incomplete feature contract"])

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            flow.last_codegen_outcome = "applied"
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.whole_app_generation_turn.call_count, 3)
        self.assertEqual(flow.whole_app_partial_ids, {"A", "B", "C"})
        self.assertEqual(flow.whole_app_deferred_ids, {"A", "B", "C"})

    def test_should_roll_back_only_the_capped_leaf_and_continue_with_later_leaves(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(return_value=[])
        flow.head = Mock(return_value="clean-sha")
        flow.restore_app = Mock()
        calls = []

        def generated(*args, **kwargs):
            calls.append(args)
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            if len(calls) == 1:
                flow.last_codegen_outcome = "tool_incomplete"
                return False, "local_turn_budget_exhausted"
            flow.last_codegen_outcome = "applied"
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        flow.restore_app.assert_called_once_with("clean-sha")
        self.assertEqual(flow.whole_app_deferred_ids, {"A"})
        self.assertEqual(flow.whole_app_generated_ids, {"B", "C"})

    def test_should_retain_clean_capped_leaf_when_official_specs_are_absent(self):
        flow = self.flow
        flow.tests_dir = None
        flow.batch_spec_bodies = Mock(return_value="derived contract")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(return_value=[])
        flow.head = Mock(return_value="clean-sha")
        flow.restore_app = Mock()
        flow.retain_safe_no_spec_partial = Mock(return_value=True)

        def capped(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            flow.last_codegen_outcome = "tool_incomplete"
            return False, "local_turn_budget_exhausted"

        flow.whole_app_generation_turn = Mock(side_effect=capped)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        flow.restore_app.assert_not_called()
        self.assertEqual(flow.whole_app_partial_ids, {"A", "B", "C"})
        self.assertEqual(flow.whole_app_generation_turn.call_count, 3)
        self.assertTrue(flow.commit.called)

    def test_should_requote_refused_files_once_within_the_same_wave(self):
        flow = self.flow
        for rel in ("backend/routes/orgs.js", "frontend/src/NewOrg.jsx"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// existing")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        refusal = "write guard refused required existing file(s): backend/routes/orgs.js"
        flow.whole_app_wave_gaps = Mock(side_effect=[[refusal], [], [], []])
        calls = []

        def generated(*args, **kwargs):
            calls.append(args)
            flow.last_codegen_written = ["frontend/src/NewOrg.jsx"]
            flow.last_codegen_no_change = False
            flow.last_codegen_outcome = "applied"
            flow.last_codegen_refused = {"backend/routes/orgs.js"} if len(calls) == 1 else set()
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(flow.whole_app_generation_turn.call_count, 4)
        self.assertEqual(flow.whole_app_generated_ids, {"A", "B", "C"})
        retry_targets = flow.codegen_implement_prompt.call_args_list[1].kwargs["must_include"]
        self.assertTrue({"backend/routes/orgs.js", "frontend/src/NewOrg.jsx"} <= retry_targets)
        later_targets = flow.codegen_implement_prompt.call_args_list[2].kwargs["must_include"]
        self.assertNotIn("frontend/src/NewOrg.jsx", later_targets)

    def test_should_quote_files_written_by_the_previous_attempt_when_splitting(self):
        flow = self.flow
        path = self.root / "frontend/src/Forgot.jsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// written by the two-leaf attempt")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(side_effect=[["design page route missing: /forgot"], [], [], []])

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/Forgot.jsx"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            flow.last_codegen_outcome = "applied"
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        split_targets = flow.codegen_implement_prompt.call_args_list[1].kwargs["must_include"]
        self.assertIn("frontend/src/Forgot.jsx", split_targets)

    def test_should_retry_with_minimal_closure_before_node_flow(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.whole_app_wave_targets = Mock(return_value={"frontend/src/App.jsx", "backend/routes/big.js"})
        flow.whole_app_wave_gaps = Mock(return_value=[])
        prompts = iter([None, "wave prompt", "wave prompt", "wave prompt"])
        flow.codegen_implement_prompt = Mock(side_effect=lambda *a, **k: next(prompts))

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            flow.last_codegen_outcome = "applied"
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        minimal = flow.codegen_implement_prompt.call_args_list[1].kwargs["must_include"]
        self.assertEqual(minimal, {"frontend/src/App.jsx"})
        self.assertEqual(flow.whole_app_generated_ids, {"A", "B", "C"})
        self.assertEqual(flow.whole_app_deferred_ids, set())

    def test_should_use_measured_wave_budgets_and_no_short_turn_cap_by_default(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_context_chars = Mock(return_value=200000)
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(return_value=[])
        flow.remaining = Mock(return_value=20000)

        def generated(*args, **kwargs):
            flow.last_codegen_written = ["frontend/src/feature.js"]
            flow.last_codegen_no_change = False
            flow.last_codegen_refused = set()
            flow.last_codegen_outcome = "applied"
            return True, "files"

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        keys = ("OCTOS_ARC_WHOLE_APP_PROMPT_CHARS", "OCTOS_ARC_WHOLE_APP_SOURCE_CHARS",
                "OCTOS_ARC_WHOLE_APP_TURN_SECONDS", "OCTOS_ARC_WHOLE_APP_TIMEOUT")
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "3"}):
            for key in keys:
                os.environ.pop(key, None)
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        kwargs = flow.codegen_implement_prompt.call_args.kwargs
        self.assertEqual(kwargs["context_limit"], 60000)
        self.assertEqual(kwargs["source_limit"], 36000)
        self.assertGreaterEqual(flow.whole_app_generation_turn.call_args.args[1], 600)

    def test_should_not_block_api_call_planned_for_a_later_leaf(self):
        flow = self.flow
        flow.last_codegen_refused = set()
        flow.requirement_contracts = None
        flow.whole_app_generated_ids = set()
        flow.last_codegen_written = ["frontend/src/Orgs.jsx"]
        flow.app_design_doc = {"data_model": {}, "pages": [], "routes": [
            {"method": "POST", "path": "/api/orgs/:org/teams", "requirements": ["LATER"]}]}
        flow._generation_gate_result = {"errors": [], "warnings": [
            "API_CALL (heuristic): frontend/src/Orgs.jsx calls POST /api/orgs/${org}/teams, "
            "but no Express route has a matching method and /api path."]}
        self.assertEqual(flow.whole_app_wave_gaps(["A"]), [])
        flow.app_design_doc["routes"][0]["requirements"] = ["A"]
        self.assertTrue(any(gap.startswith("API_CALL") for gap in flow.whole_app_wave_gaps(["A"])))

    def test_should_block_route_conflict_touching_the_current_write(self):
        flow = self.flow
        flow.last_codegen_refused = set()
        flow.requirement_contracts = None
        flow.last_codegen_written = ["backend/routes/repos.js"]
        flow._generation_gate_result = {"errors": [], "warnings": [
            "ROUTE_CONFLICT: GET /api/repos/:owner/:repo is registered in backend/routes/orgs.js and "
            "backend/routes/repos.js; Express serves only the first."]}
        gaps = flow.whole_app_wave_gaps(["A"])
        self.assertEqual(len(gaps), 1)
        self.assertTrue(gaps[0].startswith("ROUTE_CONFLICT"))

    def _applied(self, written=("frontend/src/feature.js",), refused=()):
        flow = self.flow
        flow.last_codegen_written = list(written)
        flow.last_codegen_no_change = False
        flow.last_codegen_refused = set(refused)
        flow.last_codegen_outcome = "applied"
        return True, "files"

    def test_should_report_node_progress_while_waves_run(self):
        flow = self.flow
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        flow.whole_app_wave_gaps = Mock(side_effect=[[], ["incomplete"], []])
        flow.mark = Mock()
        seen = []

        def generated(*args, **kwargs):
            seen.append([call.args[:2] for call in flow.mark.call_args_list])
            return self._applied()

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertIn(("implementation_started", "A"), seen[0])
        marks = [call.args[:2] for call in flow.mark.call_args_list]
        self.assertIn(("implementation_done", "A"), marks)
        self.assertIn(("implementation_done", "C"), marks)
        self.assertIn(("implementation_started", "B"), marks)
        self.assertNotIn(("implementation_done", "B"), marks)

    def test_should_not_require_files_the_previous_attempt_wrote_in_the_minimal_closure(self):
        flow = self.flow
        big = self.root / "frontend/src/Big.jsx"
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_text("// written by the two-leaf attempt")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.whole_app_wave_targets = Mock(return_value={"frontend/src/App.jsx"})
        flow.whole_app_wave_gaps = Mock(side_effect=[["incomplete group"]] + [[]] * 6)
        prompts = iter(["group prompt", None, "leaf prompt", "leaf prompt", "leaf prompt", "leaf prompt"])
        flow.codegen_implement_prompt = Mock(side_effect=lambda *a, **k: next(prompts))
        flow.whole_app_generation_turn = Mock(side_effect=lambda *a, **k: self._applied(["frontend/src/Big.jsx"]))
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "2"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        minimal = flow.codegen_implement_prompt.call_args_list[2].kwargs["must_include"]
        self.assertEqual(minimal, {"frontend/src/App.jsx"})
        self.assertNotIn("A", flow.whole_app_deferred_ids)

    def test_should_quote_files_with_source_check_errors_until_fixed(self):
        flow = self.flow
        broken = self.root / "frontend/src/pages/Repos.jsx"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text("import {requestJson} from '../../shared/request.js';")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.whole_app_wave_targets = Mock(return_value={"frontend/src/App.jsx", "frontend/src/Big.jsx"})
        flow.whole_app_wave_gaps = Mock(return_value=[])
        prompts = iter(["p", None, "p", None, "p"])
        flow.codegen_implement_prompt = Mock(side_effect=lambda *a, **k: next(prompts))
        calls = []

        def generated(*args, **kwargs):
            calls.append(1)
            flow._generation_gate_result = {"errors": [
                "frontend/src/pages/Repos.jsx: relative import ../../shared/request.js resolves to missing "
                "frontend/shared/request.js."] if len(calls) == 1 else [], "warnings": []}
            return self._applied()

        flow.whole_app_generation_turn = Mock(side_effect=generated)
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        second_leaf_minimal = flow.codegen_implement_prompt.call_args_list[2].kwargs["must_include"]
        self.assertIn("frontend/src/pages/Repos.jsx", second_leaf_minimal)
        third_leaf_minimal = flow.codegen_implement_prompt.call_args_list[4].kwargs["must_include"]
        self.assertNotIn("frontend/src/pages/Repos.jsx", third_leaf_minimal)

    def test_should_keep_quoting_a_file_refused_in_two_waves(self):
        flow = self.flow
        hot = self.root / "backend/lib/auth.js"
        hot.parent.mkdir(parents=True, exist_ok=True)
        hot.write_text("module.exports = {};")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.codegen_implement_prompt = Mock(return_value="wave prompt")
        flow.whole_app_wave_targets = Mock(return_value=set())
        refusal = "write guard refused required existing file(s): backend/lib/auth.js"
        flow.whole_app_wave_gaps = Mock(side_effect=[[refusal], [], [refusal], [], []])
        replies = iter([["backend/lib/auth.js"], [], ["backend/lib/auth.js"], [], []])
        flow.whole_app_generation_turn = Mock(side_effect=lambda *a, **k: self._applied(refused=next(replies)))
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        first_c_prompt = flow.codegen_implement_prompt.call_args_list[4].kwargs["must_include"]
        self.assertIn("backend/lib/auth.js", first_c_prompt)

    def test_should_not_require_hot_files_in_the_minimal_closure(self):
        flow = self.flow
        hot = self.root / "backend/lib/auth.js"
        hot.parent.mkdir(parents=True, exist_ok=True)
        hot.write_text("module.exports = {};")
        flow.app_design_doc = {"data_model": {}, "routes": [], "pages": [{"path": "/"}]}
        flow.whole_app_wave_targets = Mock(return_value={"frontend/src/App.jsx"})
        refusal = "write guard refused required existing file(s): backend/lib/auth.js"
        flow.whole_app_wave_gaps = Mock(side_effect=[[refusal], [], [refusal], [], []])
        # A (2 prompts) and B (2 prompts) fit; C's full closure with the hot
        # file does not, and its minimal closure must not insist on it.
        prompts = iter(["p", "p", "p", "p", None, "p"])
        flow.codegen_implement_prompt = Mock(side_effect=lambda *a, **k: next(prompts))
        replies = iter([["backend/lib/auth.js"], [], ["backend/lib/auth.js"], [], []])
        flow.whole_app_generation_turn = Mock(side_effect=lambda *a, **k: self._applied(refused=next(replies)))
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP_WAVE_NODES": "1"}):
            self.assertTrue(flow.whole_app_waves(self.tree, self.nodes))
        self.assertIn("backend/lib/auth.js", flow.codegen_implement_prompt.call_args_list[4].kwargs["must_include"])
        self.assertEqual(flow.codegen_implement_prompt.call_args_list[5].kwargs["must_include"],
                         {"frontend/src/App.jsx"})
        self.assertNotIn("C", flow.whole_app_deferred_ids)

    def test_should_retry_no_spec_review_with_minimal_closure(self):
        from requirement_contracts import compile_contracts
        flow = self.flow
        flow.tests_dir = None
        node = {"id": "REQ-1", "name": "Seed", "type": "ATOMIC",
                "description": 'The system contains a note titled “Project ideas”.', "scenarios": []}
        flow.requirement_contracts = compile_contracts([node])
        flow.whole_app_wave_gaps = Mock(side_effect=[
            ["source check: backend/routes/notes.js: missing import"], []])
        flow.whole_app_wave_targets = Mock(return_value={"frontend/src/App.jsx", "frontend/src/Big.jsx",
                                                         "backend/routes/notes.js"})
        flow.codegen_implement_prompt = Mock(side_effect=[None, "repair prompt"])
        flow.codegen_turn = Mock(return_value=(True, "files"))
        flow.codegen_context_chars = Mock(return_value=90000)
        flow.remaining = Mock(return_value=4000)
        flow.wound_down = Mock(return_value=False)
        self.assertEqual(flow.no_spec_feature_review(node, 10**12), [])
        self.assertEqual(flow.codegen_implement_prompt.call_args_list[1].kwargs["must_include"],
                         {"frontend/src/App.jsx", "backend/routes/notes.js"})
        flow.codegen_turn.assert_called_once()

    def test_should_not_treat_a_timed_out_final_check_as_failure(self):
        self.assertIsNone(m.Flow.final_check_verdict(False, "octos turn timed out"))
        self.assertIsNone(m.Flow.final_check_verdict(False, "local_turn_budget_exhausted: partial edits"))
        self.assertFalse(m.Flow.final_check_verdict(False, "startup failed: port in use"))
        self.assertTrue(m.Flow.final_check_verdict(True, "all checks pass"))

    def test_should_discard_the_scaffold_runtime_store_before_grading(self):
        data = self.root / "backend/data"
        data.mkdir(parents=True)
        (data / "repositories.json").write_text('{"items": [{"id": "self-test-fork"}]}')
        (self.root / "backend/server.js").write_text("'use strict';\n// Generic web entry (Express).\n")
        self.assertTrue(self.flow.discard_runtime_store())
        self.assertFalse(data.exists())
        data.mkdir()
        (self.root / "backend/server.js").write_text("// user application entry\n")
        self.assertFalse(self.flow.discard_runtime_store())
        self.assertTrue(data.exists())

    def test_should_retry_format_once_when_a_reply_has_an_incomplete_block(self):
        flow = self.flow
        replies = iter([(False, "Incomplete FILE/EDIT output: no changes were applied. Return complete "
                                "blocks with exact terminators; never nest FILE headers."),
                        (True, "files")])

        def turn(*args, **kwargs):
            ok, text = next(replies)
            flow.last_codegen_written = ["frontend/src/feature.js"] if ok else []
            flow.last_codegen_no_change = False
            return ok, text

        flow.codegen_turn = Mock(side_effect=turn)
        flow.codegen_context_chars = Mock(return_value=90000)
        ok, _ = flow.whole_app_generation_turn("prompt", 600, "whole application wave 1", spec_chars=10)
        self.assertTrue(ok)
        self.assertEqual(flow.codegen_turn.call_count, 2)
        self.assertIn("format retry", flow.codegen_turn.call_args.args[2])

    def _derived_nodes(self):
        seed = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
                "The seeded data is account `alice-dev`, email `a@example.test`, password `Pw-123456789!`.")
        for node in self.nodes:
            node["scenarios"] = [{"name": f"{node['id']}: Scenario 1", "steps": [
                {"keyword": "GIVEN", "content": seed},
                {"keyword": "WHEN", "content": f"The visitor clicks “Open {node['id']}”."},
                {"keyword": "THEN", "content": f"The page shows “Done {node['id']}”."}]}]
        return self.nodes

    def test_should_compile_static_derived_tests_once_when_official_specs_are_absent(self):
        flow = self.flow
        flow.tests_dir = None
        self.assertTrue(flow.prepare_derived_tests(self._derived_nodes()))
        directory = self.root / ".arc" / "derived-tests"
        self.assertEqual(sorted(p.name for p in directory.iterdir()),
                         ["A.spec.ts", "B.spec.ts", "C.spec.ts", "helpers.ts"])
        self.assertEqual(flow.derived_spec_map["B"], ["B.spec.ts"])
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_TESTS": "0"}):
            self.assertFalse(flow.prepare_derived_tests(self.nodes))
        flow.tests_dir = self.root / "tests"
        self.assertFalse(flow.prepare_derived_tests(self.nodes))

    def test_should_report_derived_check_results_in_the_no_spec_verdict(self):
        passed, detail = m.Flow.no_spec_node_verdict("B", True, True, {}, {"B": False})
        self.assertFalse(passed)
        self.assertIn("derived scenario checks", detail)
        passed, detail = m.Flow.no_spec_node_verdict("A", True, True, {}, {"A": True})
        self.assertTrue(passed)
        self.assertIn("derived scenario checks pass", detail)

    def test_should_fail_only_the_node_that_owns_a_final_seed_gap(self):
        flow = self.flow
        seeds = {"B": ["SEED_DATA B: required initial literal \"Acme\" is absent"]}
        passed, _ = flow.no_spec_node_verdict("A", True, True, seeds)
        self.assertTrue(passed)
        passed, detail = flow.no_spec_node_verdict("B", True, True, seeds)
        self.assertFalse(passed)
        self.assertIn("Acme", detail)
        passed, _ = flow.no_spec_node_verdict("A", False, True, seeds)
        self.assertFalse(passed)
        passed, _ = flow.no_spec_node_verdict("A", True, False, {})
        self.assertFalse(passed)

    def test_wave_wiring_warnings_are_current_change_scoped(self):
        flow = self.flow
        flow.last_codegen_refused = set()
        flow.requirement_contracts = None
        flow.last_codegen_written = ["frontend/src/Current.jsx"]
        flow._generation_gate_result = {
            "errors": [],
            "warnings": [
                "API_CALL (heuristic): frontend/src/Old.jsx calls POST /api/x, but no route matches.",
                "ROUTE_LINK (heuristic): frontend/src/Current.jsx links to /future, but no route matches.",
            ],
        }
        self.assertEqual(flow.whole_app_wave_gaps(["A"]), [])
        flow._generation_gate_result["warnings"].append(
            "API_CALL (heuristic): frontend/src/Current.jsx calls POST /api/x, but no route matches.")
        gaps = flow.whole_app_wave_gaps(["A"])
        self.assertEqual(len(gaps), 1)
        self.assertIn("API_CALL", gaps[0])

    def test_focused_source_budget_lists_but_does_not_quote_unrelated_large_file(self):
        flow = self.flow
        files = {
            "backend/server.js": "module.exports = {};",
            "frontend/src/App.jsx": "export default function App() { return null; }",
            "frontend/src/style.css": ".app {}",
            "frontend/src/Unrelated.jsx": "x" * 50000,
        }
        for rel, source in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        (self.root / "backend/package.json").write_text('{"scripts":{"start":"node server.js"}}')
        (self.root / "frontend/package.json").write_text('{"scripts":{"build":"vite build"}}')
        flow.app_design_doc = None
        flow.codegen_context_chars = Mock(return_value=90000)
        prompt = flow.codegen_implement_prompt(
            {"id": "wave", "description": "Update the application route"}, "route contract",
            must_include={"frontend/src/App.jsx", "frontend/src/style.css"},
            context_limit=30000, source_limit=12000)
        self.assertIsNotNone(prompt)
        self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 30000)
        self.assertNotIn("frontend/src/Unrelated.jsx", m.quoted_paths(prompt))
        self.assertIn("frontend/src/Unrelated.jsx", prompt)

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
                flow.events = Mock()
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
                # Output-safe batches may need more than twelve waves on large
                # trees. Still never lose leaves or exceed a per-leaf turn count.
                self.assertLessEqual(len(prompts), len(nodes))
                self.assertEqual(flow.whole_app_generated_ids, {str(node['id']) for node in nodes})
                for prompt in prompts:
                    self.assertLessEqual(len(prompt + "\n" + m.FORMAT_INSTRUCTIONS), 90000)


if __name__ == "__main__":
    unittest.main()


class DerivedSpecsAsAcceptanceTests(WholeAppTests):
    """Without official specs, the derived specs ARE the acceptance suite: the
    measured per-node flow, startup recovery and final passes apply unchanged.
    v9.0 (run 1b0211e3caef) never measured anything because the no-spec path
    only ran a separate static review."""

    def _derived(self):
        seed = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
                "The seeded data is account `alice-dev`, email `a@example.test`, password `Pw-123456789!`.")
        for node in self.nodes:
            node["scenarios"] = [{"name": f"{node['id']}: Scenario 1", "steps": [
                {"keyword": "GIVEN", "content": seed},
                {"keyword": "WHEN", "content": f"The visitor clicks “Open {node['id']}”."},
                {"keyword": "THEN", "content": f"The page shows “Done {node['id']}”."}]}]
        self.flow.tests_dir = None
        self.flow.spec_map = {}
        return self.nodes

    def test_derived_specs_become_the_acceptance_suite(self):
        flow = self.flow
        nodes = self._derived()
        self.assertTrue(flow.prepare_derived_tests(nodes))
        flow.adopt_derived_specs(["A", "B", "C"])
        self.assertEqual(flow.tests_dir, self.root / ".arc" / "derived-tests")
        self.assertTrue(flow.derived_as_specs)
        self.assertEqual(flow.spec_map["B"], ["B.spec.ts"])
        prompt = flow.tests_prompt_for("B")
        self.assertIn("derived from requirements.yaml", prompt)
        self.assertIn("B.spec.ts", prompt)
        self.assertIn("derived from requirements.yaml", flow.spec_bodies("B"))
        self.assertIn("h.clickNamed(page, 'Open B')", flow.spec_bodies("B"))
        # The whole-app wave experiment stays off by default: the normal measured flow runs.
        with patch.dict(os.environ, {"OCTOS_ARC_WHOLE_APP": "auto"}):
            flow.runner = object()
            flow.requirement_contracts = {"nodes": []}
            self.assertFalse(flow.whole_app_experiment(self.tree, nodes))

    def test_model_review_adds_validated_scripts_before_the_suite_is_adopted(self):
        flow = self.flow
        nodes = self._derived()
        nodes[1]["scenarios"][0]["steps"][1]["content"] = "The visitor opens B somehow and clicks “Open B”."
        nodes[1]["description"] = "Feature B shows Done B."
        flow.prepare_derived_tests(nodes)
        before = (flow.derived_tests_dir / "B.spec.ts").read_text()
        self.assertNotIn("[script]", before)
        reply = ('{"scenarios": [{"title": "B: Scenario 1", "signed_in": false, "confidence": 0.9, "steps": ['
                 '{"op": "click", "target": "Open B"}, {"op": "expect_visible", "target": "Done B"}]},'
                 '{"title": "B: Scenario 1", "signed_in": false, "confidence": 0.9, "steps": ['
                 '{"op": "click", "target": "Invented"}, {"op": "expect_visible", "target": "Done B"}]}]}')
        flow.text_turn = Mock(return_value=(True, reply))
        flow.remaining = Mock(return_value=4000)
        flow.final_phase_reserve = Mock(return_value=0)
        self.assertEqual(flow.augment_derived_tests(nodes), 1)
        flow.adopt_derived_specs(["A", "B", "C"])
        after = (flow.tests_dir / "B.spec.ts").read_text()
        self.assertIn("[model]", after)
        self.assertIn("h.clickNamed(page, 'Open B')", after)
        self.assertNotIn("Invented", after)
        prompt = flow.text_turn.call_args.args[0]
        self.assertIn("B: Scenario 1", prompt)
        self.assertNotIn("A: Scenario 1", prompt)  # A compiled mechanically; no tokens spent on it
        with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_LLM": "0"}):
            self.assertEqual(flow.augment_derived_tests(nodes), 0)


class HubSplitTests(WholeAppTests):
    """When a hub file has outgrown every budget, one bounded refactor turn splits
    it by feature; build errors or a measured regression roll it back."""

    def _hub(self):
        hub = self.root / "frontend/src/pages/Repository.jsx"
        hub.parent.mkdir(parents=True, exist_ok=True)
        hub.write_text("export default function Repository() {}\n" + "// x\n" * 7000)
        (self.root / "frontend/package.json").write_text("{}")
        (self.root / "backend").mkdir(exist_ok=True)
        (self.root / "backend/package.json").write_text("{}")
        (self.root / "backend/server.js").write_text("// entry\n")
        return "frontend/src/pages/Repository.jsx"

    def test_should_split_commit_and_remember_the_hub(self):
        flow = self.flow
        rel = self._hub()
        flow.head = Mock(return_value="before")
        flow.restore_app = Mock()
        flow.codegen_context_chars = Mock(return_value=90_000)

        def turn(prompt, timeout, label, **kwargs):
            self.assertIn("split", label)
            self.assertIn(rel, prompt)
            flow.last_codegen_written = [rel, "frontend/src/pages/repository/Overview.jsx"]
            return True, "files"
        flow.codegen_turn = Mock(side_effect=turn)
        flow.generation_batch_check = Mock(side_effect=lambda label: setattr(
            flow, "_generation_gate_result", {"errors": [], "warnings": []}))
        flow.runner = None
        self.assertTrue(flow.split_oversized_hub(rel, "closure did not fit"))
        flow.commit.assert_called()
        flow.restore_app.assert_not_called()
        # Once per file per run.
        self.assertFalse(flow.split_oversized_hub(rel, "again"))
        self.assertEqual(flow.codegen_turn.call_count, 1)

    def test_should_roll_back_a_split_that_breaks_the_build_or_regresses(self):
        flow = self.flow
        rel = self._hub()
        flow.head = Mock(return_value="before")
        flow.restore_app = Mock()
        flow.codegen_context_chars = Mock(return_value=90_000)

        def turn(prompt, timeout, label, **kwargs):
            flow.last_codegen_written = [rel]
            return True, "files"
        flow.codegen_turn = Mock(side_effect=turn)
        gate = {"errors": ["frontend build failed"], "warnings": []}
        flow.generation_batch_check = Mock(side_effect=lambda label: setattr(flow, "_generation_gate_result", gate))
        self.assertFalse(flow.split_oversized_hub(rel, "closure did not fit"))
        flow.restore_app.assert_called_once_with("before")
        # A second file: build clean but a previously passing spec regresses.
        other = self.root / "frontend/src/pages/Issues.jsx"
        other.write_text("export default function Issues() {}\n" + "// y\n" * 7000)
        gate = {"errors": [], "warnings": []}
        flow.test_verdict = {"A": True}
        flow.run_specs = Mock(return_value=RunSummary(passed=0, total=1, results=[
            TestOutcome(title="A", ok=False, status="failed", duration_ms=1, file="A.spec.ts")]))
        flow.restore_app.reset_mock()
        self.assertFalse(flow.split_oversized_hub("frontend/src/pages/Issues.jsx", "closure did not fit"))
        flow.restore_app.assert_called_once_with("before")

    def test_split_does_not_trust_a_stale_gate_result(self):
        flow = self.flow
        rel = self._hub()
        flow.head = Mock(return_value="before")
        flow.restore_app = Mock()
        flow.codegen_context_chars = Mock(return_value=90_000)
        flow.codegen_turn = Mock(side_effect=lambda *a, **k: (setattr(flow, "last_codegen_written", [rel]), (True, "f"))[1])
        flow._generation_gate_result = {"errors": ["old error from an earlier turn"], "warnings": []}
        flow.generation_batch_check = Mock()  # skipped: leaves no result
        flow.app_server = Mock(return_value=Mock(build=Mock(return_value=None)))
        flow.runner = None
        self.assertTrue(flow.split_oversized_hub(rel, "x"))
        flow.restore_app.assert_not_called()

    def test_small_or_unknown_files_are_never_split(self):
        flow = self.flow
        (self.root / "frontend/src").mkdir(parents=True, exist_ok=True)
        (self.root / "frontend/src/Small.jsx").write_text("export default 1;\n")
        flow.codegen_turn = Mock()
        self.assertFalse(flow.split_oversized_hub("frontend/src/Small.jsx", "x"))
        self.assertFalse(flow.split_oversized_hub("frontend/src/Missing.jsx", "x"))
        flow.codegen_turn.assert_not_called()


class DerivedSuiteVerificationTests(WholeAppTests):
    """Every generated spec must load in Playwright before it is the acceptance
    suite; a file that does not is repaired deterministically (model additions
    dropped, then the leaf recompiled), never left to poison the suite."""

    def _derived(self):
        seed = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
                "The seeded data is account `alice-dev`, email `a@example.test`, password `Pw-123456789!`.")
        for node in self.nodes:
            node["scenarios"] = [{"name": f"{node['id']}: Scenario 1", "steps": [
                {"keyword": "GIVEN", "content": seed},
                {"keyword": "WHEN", "content": f"The visitor clicks “Open {node['id']}”."},
                {"keyword": "THEN", "content": f"The page shows “Done {node['id']}”."}]}]
        self.flow.tests_dir = None
        self.flow.spec_map = {}
        self.flow.prepare_derived_tests(self.nodes)
        return self.nodes

    def _runner(self):
        runner = Mock()
        runner.list_specs = Mock(side_effect=lambda rels: next(
            ((False, f"SyntaxError in {rel}") for rel in rels
             if "BROKEN" in (self.flow.derived_tests_dir / rel).read_text()), (True, "")))
        return runner

    def test_model_additions_that_do_not_load_are_dropped_and_the_file_kept(self):
        flow = self.flow
        self._derived()
        flow.runner = self._runner()
        path = flow.derived_tests_dir / "B.spec.ts"
        path.write_text(path.read_text() + "\ntest('B: x [model]', async ({ page }) => { BROKEN (\n});\n")
        flow.adopt_derived_specs(["A", "B", "C"])
        self.assertNotIn("BROKEN", path.read_text())
        self.assertIn("h.clickNamed(page, 'Open B')", path.read_text())
        self.assertEqual(flow.spec_map["B"], ["B.spec.ts"])
        self.assertTrue(flow.derived_suite_verified)

    def test_a_file_that_still_fails_after_recompilation_is_excluded(self):
        flow = self.flow
        nodes = self._derived()
        flow.runner = self._runner()
        nodes[1]["scenarios"][0]["steps"][1]["content"] = "The visitor clicks “BROKEN”."  # mechanical output itself fails
        flow.derived_nodes = nodes
        path = flow.derived_tests_dir / "B.spec.ts"
        path.write_text(path.read_text().replace("Open B", "BROKEN"))
        flow.adopt_derived_specs(["A", "B", "C"])
        self.assertFalse(path.exists())
        self.assertEqual(flow.spec_map["B"], [])
        self.assertEqual(flow.spec_map["A"], ["A.spec.ts"])

    def test_model_review_retries_a_rejected_proposal_once_with_the_reason(self):
        flow = self.flow
        nodes = self._derived()
        nodes[1]["scenarios"][0]["steps"][1]["content"] = "The visitor opens B somehow and clicks “Open B”."
        nodes[1]["description"] = "Feature B shows Done B."
        flow.prepare_derived_tests(nodes)
        bad = ('{"scenarios": [{"title": "B: Scenario 1", "signed_in": false, "confidence": 0.9, "steps": ['
               '{"op": "click", "target": "Invented"}, {"op": "expect_visible", "target": "Done B"}]}]}')
        good = ('{"scenarios": [{"title": "B: Scenario 1", "signed_in": false, "confidence": 0.9, "steps": ['
                '{"op": "click", "target": "Open B"}, {"op": "expect_visible", "target": "Done B"}]}]}')
        flow.text_turn = Mock(side_effect=[(True, bad), (True, good)])
        flow.remaining = Mock(return_value=4000)
        flow.final_phase_reserve = Mock(return_value=0)
        self.assertEqual(flow.augment_derived_tests(nodes), 1)
        self.assertEqual(flow.text_turn.call_count, 2)
        retry = flow.text_turn.call_args.args[0]
        self.assertIn("Invented", retry)
        self.assertIn("not an allowed literal", retry)
        self.assertIn("[model]", (flow.derived_tests_dir / "B.spec.ts").read_text())


class RollbackAttributionTests(WholeAppTests):
    """v9.1 run 2a839b37d3e8: REQ-1-1-2 passed 2/2, a proven REQ-1-1-1 check failed
    in the combined run, the node's work was rolled back -- and REQ-1-1-1 still
    failed on the restored source. A prior that fails without the node's changes
    is not a regression of the node; its work must be kept."""

    def test_rollback_is_undone_when_the_prior_fails_on_the_restored_source_too(self):
        flow = self.flow
        flow.head = Mock(side_effect=["after-node"])
        flow.restore_app = Mock()
        flow.run_specs = Mock(return_value=RunSummary(passed=1, total=2, results=[
            TestOutcome(title="A ok", ok=True, status="passed", duration_ms=1, file="A.spec.ts"),
            TestOutcome(title="A flaky", ok=False, status="failed", duration_ms=1, file="A.spec.ts")]))
        flow.test_verdict = {"A": False, "B": True}
        flow.final_measurement_reserve = Mock(return_value=0)
        kept = flow.settle_failed_extension("B", before_sha="before-node", regressed_proven=["A"], node_passed=True)
        self.assertTrue(kept)
        self.assertEqual(flow.restore_app.call_args_list[0].args, ("before-node",))
        self.assertEqual(flow.restore_app.call_args_list[-1].args, ("after-node",))
        self.assertTrue(flow.test_verdict["B"])
        self.assertFalse(flow.test_verdict["A"])

    def test_rollback_stands_when_the_prior_passes_again_on_the_restored_source(self):
        flow = self.flow
        flow.head = Mock(side_effect=["after-node"])
        flow.restore_app = Mock()
        flow.run_specs = Mock(return_value=RunSummary(passed=1, total=1, results=[
            TestOutcome(title="A ok", ok=True, status="passed", duration_ms=1, file="A.spec.ts")]))
        flow.test_verdict = {"A": False, "B": False}
        flow.final_measurement_reserve = Mock(return_value=0)
        kept = flow.settle_failed_extension("B", before_sha="before-node", regressed_proven=["A"], node_passed=False)
        self.assertFalse(kept)
        self.assertEqual(flow.restore_app.call_count, 1)
        self.assertTrue(flow.test_verdict["A"])
        self.assertFalse(flow.test_verdict["B"])


class CompletenessPassTests(WholeAppTests):
    """hackathon--sheet run ef2ab916a57d: 24 reach checks passed, the run ended after
    91 of 1175 available minutes, the grader passed 0/100. Leaves whose derived spec
    carries no scenario-specific script get a bounded requirement-driven tool turn
    with the remaining budget, gated by the full suite."""

    def _prepare(self):
        seed = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
                "The seeded data is account `alice-dev`, email `a@example.test`, password `Pw-123456789!`.")
        for node in self.nodes:
            node["scenarios"] = [{"name": f"{node['id']}: Scenario 1", "steps": [
                {"keyword": "GIVEN", "content": seed},
                {"keyword": "WHEN", "content": f"The visitor clicks “Open {node['id']}”."},
                {"keyword": "THEN", "content": f"The page shows “Done {node['id']}”."}]}]
        # B is weak: its scenario cannot be scripted (only a reach check).
        self.nodes[1]["scenarios"][0]["steps"][1]["content"] = "The visitor somehow reaches “Open B”."
        self.flow.tests_dir = None
        self.flow.spec_map = {}
        self.flow.prepare_derived_tests(self.nodes)
        self.flow.adopt_derived_specs(["A", "B", "C"])
        self.flow.requirement_contracts = m.compile_contracts(self.nodes)
        self.flow.runner = object()
        self.flow.test_verdict = {"A": True, "B": True, "C": True}
        return self.nodes

    def test_only_weak_leaves_get_a_completeness_turn_and_regressions_roll_back(self):
        flow = self.flow
        nodes = self._prepare()
        self.assertEqual(flow.weak_derived_leaves(nodes), ["B"])
        flow.turn = Mock(return_value=(True, "verified"))
        flow.head = Mock(return_value="before-pass")
        flow.restore_app = Mock()
        flow.remaining = Mock(return_value=9000)
        flow.final_phase_reserve = Mock(return_value=0)
        flow.run_specs = Mock(return_value=RunSummary(passed=3, total=3, results=[
            TestOutcome(title=n, ok=True, status="passed", duration_ms=1, file=f"{n}.spec.ts") for n in "ABC"]))
        flow.suite_is_measured = Mock(return_value=True)
        flow.derived_completeness_pass(nodes)
        self.assertEqual(flow.turn.call_count, 1)
        prompt, _, label = flow.turn.call_args.args[:3]
        self.assertIn("B", label)
        self.assertIn("Open B", prompt)
        flow.restore_app.assert_not_called()
        # A regression of the full suite restores the tree taken before the pass.
        flow.turn.reset_mock()
        flow.run_specs = Mock(return_value=RunSummary(passed=2, total=3, results=[
            TestOutcome(title="A", ok=False, status="failed", duration_ms=1, file="A.spec.ts"),
            TestOutcome(title="B", ok=True, status="passed", duration_ms=1, file="B.spec.ts"),
            TestOutcome(title="C", ok=True, status="passed", duration_ms=1, file="C.spec.ts")]))
        flow.derived_completeness_pass(nodes)
        flow.restore_app.assert_called_once_with("before-pass")

    def test_pass_is_skipped_without_time(self):
        flow = self.flow
        nodes = self._prepare()
        flow.turn = Mock()
        flow.remaining = Mock(return_value=100)
        flow.derived_completeness_pass(nodes)
        flow.turn.assert_not_called()


class DerivedWorkersTests(WholeAppTests):
    def test_derived_suites_run_sequentially_by_default(self):
        flow = self.flow
        flow.derived_as_specs = True
        flow.time_up = Mock(return_value=False)
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=Mock(return_value=SimpleNamespace(stdout=""))))
        server = SimpleNamespace(build=Mock(return_value=None), start=Mock(return_value=None), stop=Mock(),
                                 tail=Mock(return_value=""))
        flow.app_server = Mock(return_value=server)
        captured = {}
        runner = SimpleNamespace(run=lambda specs, url, workers=None, wall_timeout=None: (
            captured.update(workers=workers), RunSummary(passed=1, total=1, results=[
                TestOutcome(title="A", ok=True, status="passed", duration_ms=1, file="A.spec.ts")]))[1])
        with patch.object(m, "snapshot_worktree"), patch.object(m, "restore_worktree"), \
                patch.object(m, "mutated_by_tests", return_value=[]), patch.object(m, "store_changes_by_tests", return_value=[]):
            flow.run_specs(["A.spec.ts"], workers=2, runner=runner)
            self.assertEqual(captured["workers"], 1)
            with patch.dict(os.environ, {"OCTOS_ARC_DERIVED_WORKERS": "2"}):
                flow.run_specs(["A.spec.ts"], workers=2, runner=runner)
            self.assertEqual(captured["workers"], 2)
            flow.derived_as_specs = False
            flow.run_specs(["A.spec.ts"], workers=2, runner=runner)
            self.assertEqual(captured["workers"], 2)
