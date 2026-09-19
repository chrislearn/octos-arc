"""Seven cloud runs (temp-logs, 2026-09-18): checkpoint regression repairs cost
0.9-1.8 h and 166-351 tool calls per big run, final-suite repairs up to 2.8 h
(keep ce54f9a57bdc, still failing), and every one of those turns went straight
to tool mode. A regression lives in the files changed since the last green
state; quote them and try one codegen repair before handing the suite to tools.
Also: the platform metered 1.2-3.2x our proxy's tokens; the proxy logged only
exchanges that returned a usage block, so nothing could be reconciled."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as m  # noqa: E402
import llm_proxy  # noqa: E402


def _app(root: Path):
    (root / "frontend/src").mkdir(parents=True); (root / "backend/routes").mkdir(parents=True)
    (root / "frontend/package.json").write_text("{}"); (root / "backend/package.json").write_text("{}")
    (root / "backend/server.js").write_text("// entry\n" + "e" * 300)
    (root / "backend/store.js").write_text("// store\n" + "s" * 300)
    (root / "frontend/src/index.html").write_text("<main>home</main>" + "i" * 300)
    (root / "frontend/src/notes.html").write_text("<main>notes</main>" + "n" * 300)


class ChangedFilesTests(unittest.TestCase):
    def test_should_list_app_files_changed_since_a_commit(self):
        flow = object.__new__(m.Flow)
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda args, check=True: SimpleNamespace(
            returncode=0, stdout="frontend/src/index.html\nbackend/store.js\n.arc/traceability/x.json\n")))
        self.assertEqual(flow.changed_files_since("abc123"), {"frontend/src/index.html", "backend/store.js"})
        self.assertEqual(flow.changed_files_since(None), set())

    def test_should_return_nothing_when_git_fails(self):
        flow = object.__new__(m.Flow)
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda args, check=True: SimpleNamespace(returncode=128, stdout="")))
        self.assertEqual(flow.changed_files_since("abc123"), set())


class SuiteRepairPromptTests(unittest.TestCase):
    def _flow(self, folder):
        root = Path(folder); _app(root)
        (root / "tests").mkdir()
        (root / "tests/REQ-1.spec.ts").write_text("await page.goto('/'); home heading")
        (root / "tests/REQ-2.spec.ts").write_text("await page.goto('/notes'); notes list")
        flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
        flow.tests_dir = root / "tests"
        flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"], "REQ-2": ["REQ-2.spec.ts"]}
        flow.requirement_nodes = {"REQ-1": {"id": "REQ-1", "description": "home"}, "REQ-2": {"id": "REQ-2", "description": "notes"}}
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda args, check=True: SimpleNamespace(returncode=0, stdout="backend/store.js\n")))
        flow.last_checkpoint_sha = "greensha"
        return flow

    def test_should_build_one_codegen_prompt_for_the_regressed_nodes_with_the_changed_files_quoted(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder)
            prompt = flow.suite_repair_prompt(["REQ-1", "REQ-2"], "- Feature: home\n  Observation: heading missing")
            self.assertIsNotNone(prompt)
            self.assertIn("--- backend/store.js ---", prompt)         # changed since the last green state
            self.assertIn("heading missing", prompt)                  # the regression evidence
            self.assertIn("home heading", prompt); self.assertIn("notes list", prompt)   # both nodes' specs
            self.assertIn("REQ-1, REQ-2", prompt)

    def test_should_give_up_without_requirement_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = self._flow(folder); flow.requirement_nodes = {}
            self.assertIsNone(flow.suite_repair_prompt(["REQ-9"], "f"))


class SuiteRepairTurnTests(unittest.TestCase):
    def _flow(self):
        flow = Mock(spec=m.Flow)
        flow.codegen_mode.return_value = True
        flow.codegen_turn.return_value = (True, "generated")
        flow.turn.return_value = (True, "tool reply")
        flow.current_spec_chars = 0
        return flow

    def test_should_try_codegen_first_and_skip_tools(self):
        flow = self._flow(); flow.suite_repair_prompt.return_value = "codegen prompt"
        mode, _ = m.Flow.suite_repair_turn(flow, "checkpoint 8 repair 1/1", ["REQ-2"], "failures", 300, tool_prompt="tool prompt")
        self.assertEqual(mode, "codegen")
        flow.codegen_turn.assert_called_once()
        self.assertEqual(flow.codegen_turn.call_args.args[0], "codegen prompt")
        flow.turn.assert_not_called()

    def test_should_fall_back_to_tools_when_no_codegen_prompt_fits_or_when_told_to(self):
        flow = self._flow(); flow.suite_repair_prompt.return_value = None
        mode, _ = m.Flow.suite_repair_turn(flow, "checkpoint 8 repair 1/1", ["REQ-2"], "f", 300, tool_prompt="tool prompt")
        self.assertEqual(mode, "tools"); flow.turn.assert_called_once(); flow.codegen_turn.assert_not_called()
        flow = self._flow(); flow.suite_repair_prompt.return_value = "codegen prompt"
        mode, _ = m.Flow.suite_repair_turn(flow, "x", ["REQ-2"], "f", 300, tool_prompt="tool prompt", prefer_codegen=False)
        self.assertEqual(mode, "tools"); flow.codegen_turn.assert_not_called()


class CheckpointRoundsTests(unittest.TestCase):
    def test_should_spend_one_codegen_round_then_one_tool_round_by_default(self):
        from unittest.mock import patch
        import test_main_helpers as helpers
        flow = helpers.CheckpointRepairTests()._flow([1, 1, 1])   # codegen round and tool round both miss
        flow.llm_proxy = object()
        flow.suite_repair_prompt = lambda ids, failures: "codegen prompt"
        flow.codegen_turn = Mock(return_value=(True, "generated"))
        flow.refused_paths = set()
        with patch.dict("os.environ", {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.codegen_turn.call_count, 1)
        self.assertEqual(flow.turn.call_count, 1)
        self.assertIn("checkpoint 2 repair 1/2", flow.codegen_turn.call_args.args[2])
        self.assertIn("checkpoint 2 repair 2/2", flow.turn.call_args.args[2])

    def test_should_stop_after_the_codegen_round_when_it_takes(self):
        from unittest.mock import patch
        import test_main_helpers as helpers
        flow = helpers.CheckpointRepairTests()._flow([1, 2])
        flow.llm_proxy = object()
        flow.suite_repair_prompt = lambda ids, failures: "codegen prompt"
        flow.codegen_turn = Mock(return_value=(True, "generated"))
        flow.refused_paths = set()
        with patch.dict("os.environ", {"OCTOS_ARC_REGRESSION_CHECKPOINT": "2"}):
            flow.regression_checkpoint(2, 8)
        self.assertEqual(flow.codegen_turn.call_count, 1)
        flow.turn.assert_not_called()
        self.assertTrue(all(flow.test_verdict.values()))


class ProxyLogsEveryExchangeTests(unittest.TestCase):
    def test_should_record_an_exchange_without_a_usage_block(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "usage.jsonl"
            proxy = llm_proxy.LlmProxy("http://127.0.0.1:1/v1", "low", log)
            proxy.label = "REQ-3 repair 1/3"; proxy.phase = "repair"
            body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}).encode()
            proxy._log(b'{"error":{"message":"upstream timeout"}}', 61000, body, len(body), 40, status=504)
            proxy._log(json.dumps({"usage": {"prompt_tokens": 5, "completion_tokens": 2}, "choices": []}).encode(), 100, body, len(body), 40, status=200)
            records = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertTrue(records[0]["no_usage"]); self.assertEqual(records[0]["status"], 504)
            self.assertEqual(records[0]["label"], "REQ-3 repair 1/3"); self.assertIn("timeout", records[0]["error"])
            self.assertEqual(records[1]["status"], 200); self.assertEqual(records[1]["prompt_tokens"], 5)

    def test_should_report_cache_misses_and_missing_usage_without_imputing_zero_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / ".arc").mkdir()
            records = [
                {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80, "completion_tokens": 10,
                 "total_tokens": 110, "request_bytes": 300, "response_bytes": 90},
                {"no_usage": True, "label": "full-suite repair 3/3", "phase": "repair",
                 "status": 504, "elapsed_ms": 1200000, "request_bytes": 500, "response_bytes": 0},
            ]
            (root / ".arc" / "llm-usage.jsonl").write_text("\n".join(json.dumps(r) for r in records))
            flow = object.__new__(m.Flow); flow.output_dir = root
            with patch.object(m, "log") as logged:
                flow.log_usage_summary()
            messages = [call.args[0] for call in logged.call_args_list]
            self.assertIn("miss=20", "\n".join(messages))
            self.assertIn("not counted as zero-cost", "\n".join(messages))
            self.assertIn("full-suite repair 3/3", "\n".join(messages))


if __name__ == "__main__":
    unittest.main()
