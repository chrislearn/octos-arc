"""Review of 41b6af80 / d8365870 / d4fd0cdf (2026-09-19): five P2 findings and one
efficiency note. Each test here is the finding restated as a contract."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as m  # noqa: E402
import llm_proxy  # noqa: E402
import usage_by_node  # noqa: E402
import test_main_helpers as helpers  # noqa: E402
from test_suite_repair import _app  # noqa: E402


class EvolutionDesignReuseTests(unittest.TestCase):
    """P2: app_design() could load a stored design in evolution mode, but run()
    only called it for a fresh build, so the branch was unreachable."""
    def _flow(self, evolution):
        flow = Mock(spec=m.Flow)
        flow.evolution = evolution
        flow.codegen_mode.return_value = True
        flow.skeleton_min_nodes = 4
        flow.driver = Mock()
        flow.head.return_value = "base0"
        return flow

    def test_should_load_the_design_in_evolution_mode_and_never_build_a_skeleton(self):
        flow = self._flow(True)
        with patch.dict("os.environ", {"OCTOS_SKELETON_ALWAYS": "0"}):
            m.Flow.prepare_build(flow, {"id": "ROOT"}, [{"id": "REQ-1"}] * 6)
        flow.app_design.assert_called_once()
        flow.skeleton.assert_not_called()

    def test_should_design_then_skip_the_skeleton_on_a_fresh_codegen_build(self):
        flow = self._flow(False)
        with patch.dict("os.environ", {"OCTOS_SKELETON_ALWAYS": "0"}):
            m.Flow.prepare_build(flow, {"id": "ROOT"}, [{"id": "REQ-1"}] * 6)
        flow.app_design.assert_called_once()
        flow.skeleton.assert_not_called()

    def test_should_record_the_baseline_for_the_first_suite_repair(self):
        flow = self._flow(True)
        m.Flow.prepare_build(flow, {"id": "ROOT"}, [{"id": "REQ-1"}] * 6)
        self.assertEqual(flow.last_checkpoint_sha, "base0")


class SuiteRepairReasoningTests(unittest.TestCase):
    """P2: the suite repair passed the last single node's spec size to codegen_turn,
    so a multi-node repair could run with reasoning=none."""
    def test_should_size_reasoning_by_the_aggregated_specs(self):
        flow = Mock(spec=m.Flow)
        flow.codegen_mode.return_value = True
        flow.codegen_turn.return_value = (True, "generated")
        flow.current_spec_chars = 10
        flow.suite_spec_chars = 12345
        flow.suite_repair_prompt.return_value = "codegen prompt"
        m.Flow.suite_repair_turn(flow, "checkpoint 8 repair 1/2", ["REQ-2"], "f", 300, tool_prompt="t")
        self.assertEqual(flow.codegen_turn.call_args.kwargs["spec_chars"], 12345)

    def test_should_record_the_aggregated_spec_size_when_building_the_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); _app(root); (root / "tests").mkdir()
            (root / "tests/REQ-1.spec.ts").write_text("home heading " * 40)
            (root / "tests/REQ-2.spec.ts").write_text("notes list " * 40)
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.tests_dir = root / "tests"
            flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"], "REQ-2": ["REQ-2.spec.ts"]}
            flow.requirement_nodes = {"REQ-1": {"id": "REQ-1"}, "REQ-2": {"id": "REQ-2"}}
            flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda a, check=True: SimpleNamespace(returncode=0, stdout="")))
            self.assertIsNotNone(flow.suite_repair_prompt(["REQ-1", "REQ-2"], "f"))
            self.assertGreaterEqual(flow.suite_spec_chars, len(flow.spec_bodies("REQ-1")) + len(flow.spec_bodies("REQ-2")))


class CheckpointBaselineTests(unittest.TestCase):
    """P2: the diff baseline advanced after a failed repair, so the next checkpoint
    could miss the files that introduced the regression."""
    def _flow(self, outcomes, sha):
        flow = helpers.CheckpointRepairTests()._flow(outcomes)
        flow.head = lambda: sha
        flow.last_checkpoint_sha = "green0"
        return flow

    def test_should_keep_the_baseline_while_a_regression_remains(self):
        flow = self._flow([1, 1], "later")
        with patch.dict("os.environ", {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2", "OCTOS_ARC_CHECKPOINT_REPAIRS": "1"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.last_checkpoint_sha, "green0")

    def test_should_advance_the_baseline_once_the_checkpoint_is_green(self):
        flow = self._flow([1, 2], "later")
        with patch.dict("os.environ", {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.last_checkpoint_sha, "later")
        flow = self._flow([2], "clean")
        with patch.dict("os.environ", {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.last_checkpoint_sha, "clean")


class FirstPassMetricTests(unittest.TestCase):
    """P2: 'implement without a node repair' is not 'passed first time'."""
    def _rec(self, label):
        return {"label": label, "prompt_tokens": 10, "completion_tokens": 1, "request": {"user_chars": 10}}

    def test_should_separate_no_node_repair_from_first_pass(self):
        records = [self._rec("REQ-1 implement"), self._rec("REQ-2 implement"), self._rec("REQ-3 implement"),
                   self._rec("REQ-3 repair 1/3"), self._rec("checkpoint 8 repair 1/2")]
        states = {"REQ-1": "PASSED", "REQ-2": "FAILED", "REQ-3": "PASSED"}
        nodes = usage_by_node.summarize(records, states)["nodes"]
        self.assertTrue(nodes["REQ-1"]["no_node_repair"]); self.assertTrue(nodes["REQ-1"]["first_pass"])
        self.assertTrue(nodes["REQ-2"]["no_node_repair"]); self.assertFalse(nodes["REQ-2"]["first_pass"])
        self.assertFalse(nodes["REQ-3"]["no_node_repair"]); self.assertFalse(nodes["REQ-3"]["first_pass"])

    def test_should_leave_first_pass_unknown_without_verdicts(self):
        nodes = usage_by_node.summarize([self._rec("REQ-1 implement")])["nodes"]
        self.assertTrue(nodes["REQ-1"]["no_node_repair"]); self.assertIsNone(nodes["REQ-1"]["first_pass"])

    def test_should_read_node_states_next_to_the_usage_log(self):
        with tempfile.TemporaryDirectory() as folder:
            arc = Path(folder) / ".arc"; (arc / "traceability").mkdir(parents=True)
            (arc / "llm-usage.jsonl").write_text(json.dumps(self._rec("REQ-1 implement")) + "\n")
            (arc / "traceability" / "node_states.json").write_text(json.dumps({"REQ-1": {"req_id": "REQ-1", "state": "PASSED"}}))
            self.assertEqual(usage_by_node.node_states(Path(folder)), {"REQ-1": "PASSED"})
            text = usage_by_node.render(usage_by_node.summarize(
                usage_by_node.load_records(arc / "llm-usage.jsonl"), usage_by_node.node_states(Path(folder))))
            self.assertIn("first pass: 1", text)


class LateResponseAttributionTests(unittest.TestCase):
    """P2: label, phase and the previous prompt were read when the response ended,
    so a request that outlived its turn was attributed to the next one."""
    def _proxy(self, folder):
        proxy = llm_proxy.LlmProxy("http://127.0.0.1:1/v1", "low", Path(folder) / "usage.jsonl")
        return proxy

    def test_should_attribute_by_the_turn_that_issued_the_request(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = self._proxy(folder)
            body_a = json.dumps({"model": "m", "messages": [{"role": "user", "content": "alpha " * 50}]}).encode()
            body_b = json.dumps({"model": "m", "messages": [{"role": "user", "content": "alpha " * 50 + "beta"}]}).encode()
            proxy.label, proxy.phase = "REQ-1 implement", "implement"
            meta_a = proxy.request_meta(body_a)          # issued during REQ-1
            proxy.label, proxy.phase = "REQ-2 implement", "implement"
            meta_b = proxy.request_meta(body_b)          # issued during REQ-2
            usage = json.dumps({"usage": {"prompt_tokens": 5, "completion_tokens": 2}, "choices": []}).encode()
            proxy._log(usage, 5, body_b, 1, 1, status=200, meta=meta_b)   # B returns first
            proxy._log(usage, 900, body_a, 1, 1, status=200, meta=meta_a)  # A returns late, after the turn moved on
            recs = [json.loads(l) for l in (Path(folder) / "usage.jsonl").read_text().splitlines()]
            self.assertEqual([r["label"] for r in recs], ["REQ-2 implement", "REQ-1 implement"])
            # prefix reuse follows issue order: A had no predecessor, B shares A's prefix
            self.assertEqual(recs[1]["prefix_shared_chars"], 0)
            self.assertGreater(recs[0]["prefix_shared_chars"], 200)


class MustIncludeCoverageTests(unittest.TestCase):
    """Efficiency: must_include only raises priority; a suite repair whose changed
    files cannot be quoted is a request doomed to the write guard."""
    def _flow(self, folder, changed):
        root = Path(folder); _app(root); (root / "tests").mkdir()
        (root / "tests/REQ-1.spec.ts").write_text("home heading")
        flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
        flow.tests_dir = root / "tests"
        flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"]}
        flow.requirement_nodes = {"REQ-1": {"id": "REQ-1", "description": "home"}}
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda a, check=True: SimpleNamespace(returncode=0, stdout=changed)))
        flow.last_checkpoint_sha = "green0"
        return flow

    def test_should_give_up_when_no_changed_file_fits_the_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder, "frontend/src/notes.html\n")
            (Path(folder) / "frontend/src/notes.html").write_text("x" * 200_000)
            with patch.dict("os.environ", {"OCTOS_ARC_CODEGEN_CONTEXT_CHARS": "90000"}):
                self.assertIsNone(flow.suite_repair_prompt(["REQ-1"], "f"))

    def test_should_proceed_when_the_changed_files_are_quoted(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder, "frontend/src/notes.html\n")
            prompt = flow.suite_repair_prompt(["REQ-1"], "f")
            self.assertIn("frontend/src/notes.html", m.quoted_paths(prompt))


if __name__ == "__main__":
    unittest.main()
