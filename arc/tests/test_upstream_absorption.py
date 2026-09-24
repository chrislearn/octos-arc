"""Selected upstream mechanisms adapted to the whole-app/codegen workflow."""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile

import main as m
from acceptance import RunSummary, TestOutcome, startup_error_digest
from flow_policy import node_seconds, phase_for_label, repair_seconds
from codegen import incomplete_blocks
from llm_proxy import LlmProxy, open_upstream, routed_model_missing


class ProxyCompatibilityTests(unittest.TestCase):
    def test_custom_api_roots_and_segment_boundaries(self):
        for base, expected in (("https://example.test", "/v1/chat/completions"),
                               ("https://example.test/v1", "/chat/completions"),
                               ("https://example.test/api/coding/paas/v4/", "/chat/completions")):
            proxy = object.__new__(LlmProxy)
            proxy.upstream = base.rstrip("/")
            self.assertEqual(proxy.forward_path("/v1/chat/completions"), expected)
            self.assertEqual(proxy.forward_path("/v10/models"), "/v10/models")
            self.assertEqual(proxy.forward_path("/health"), "/health")
        self.assertEqual(proxy.forward_path("/v1/models?limit=1"), "/models?limit=1")
        self.assertEqual(proxy.forward_path("/v1?x=1"), "/?x=1")

    def test_only_loopback_bypasses_environment_proxy(self):
        with patch("llm_proxy.urllib.request.build_opener") as builder, \
                patch("llm_proxy.urllib.request.urlopen") as remote:
            for host in ("localhost", "test.localhost", "127.0.0.8", "[::1]", "0.0.0.0"):
                open_upstream(urllib.request.Request(f"http://{host}:9999/models"), timeout=2)
            self.assertEqual(builder.call_count, 5)
            remote.assert_not_called()
            self.assertEqual(builder.call_args.args[0].proxies, {})
            for host in ("localhost.evil.test", "192.168.1.3", "example.test"):
                open_upstream(urllib.request.Request(f"https://{host}/v1/models"), timeout=2)
            self.assertEqual(remote.call_count, 3)

    def test_only_explicit_model_404_is_eligible(self):
        payload = json.dumps({"error": {"message": "Model 'chosen' not found"}}).encode()
        self.assertTrue(routed_model_missing(404, payload, "chosen"))
        for status in (400, 401, 403, 429, 500):
            self.assertFalse(routed_model_missing(status, payload, "chosen"))
        self.assertFalse(routed_model_missing(404, payload, "different"))
        for payload in (b"<html>model not found</html>", b"[]", b'{"error":"not found"}',
                        b'{"error":{"message":"route not found"}}'):
            self.assertFalse(routed_model_missing(404, payload, "chosen"))

    def test_wire_fallback_restores_parameters_and_accounts_both_exchanges(self):
        received = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, body))
                missing = body["model"] == "unavailable"
                response = ({"error": {"code": "model_not_found", "message": "Model 'unavailable' not found"}}
                            if missing else {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                                             "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
                payload = json.dumps(response).encode()
                self.send_response(404 if missing else 200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        routes = [{"model": "unavailable", "parameters": {"temperature": 0.1, "thinking": {"type": "disabled"}}}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
                "OCTOS_ARC_MODEL_ROUTES": json.dumps(routes), "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}):
            logfile = Path(tmp) / "usage.jsonl"
            proxy = LlmProxy(f"http://127.0.0.1:{server.server_port}/custom/v4", "passthrough",
                             log_path=logfile, trim=False, min_max_tokens=0).start()
            try:
                original = {"model": "original", "temperature": 0.7, "thinking": {"type": "enabled"},
                            "messages": [{"role": "user", "content": "hello"}], "stream": True}
                for _ in range(2):
                    req = urllib.request.Request(proxy.base_url + "/chat/completions", data=json.dumps(original).encode())
                    with open_upstream(req, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(b"data:", response.read())
                self.assertEqual(proxy.routes, [])
                self.assertEqual(proxy.total_requests, 3)
                self.assertGreater(proxy.estimated_tokens, 0)
                self.assertEqual(proxy.total_tokens, 8 + proxy.estimated_tokens)
            finally:
                proxy.stop()
            records = [json.loads(line) for line in logfile.read_text().splitlines()]
            self.assertEqual([r["status"] for r in records], [404, 200, 200])
            self.assertEqual([r["model"] for r in records], ["unavailable", "original", "original"])
            self.assertEqual(records[0]["guard_token_estimate"], proxy.estimated_tokens)
        self.assertEqual([p for p, _ in received], ["/custom/v4/chat/completions"] * 3)
        self.assertEqual(received[1][1]["thinking"], {"type": "enabled"})
        self.assertEqual(received[1][1]["temperature"], 0.7)


class SchedulingTests(unittest.TestCase):
    def test_whole_app_repair_uses_failed_job_count_not_original_node_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
            nodes = [{"id": name} for name in ("a", "b", "c", "d")]
            flow.whole_app_codegen = Mock(return_value=True)
            flow.whole_app_first_suite = Mock(return_value={"b", "d"})
            flow.whole_app_shared_repair = lambda ordered, failing: failing
            flow.mark = Mock()
            flow.time_up = lambda: False
            flow.remaining = lambda: 900
            flow.driver = SimpleNamespace(end_scope=Mock())
            stages = []
            flow.node_cycle = lambda *a, **kw: stages.append(flow._repair_stage)
            flow.whole_app_experiment({}, nodes)
            self.assertEqual(stages, [(900, 2, 0), (900, 2, 1)])
            self.assertIsNone(flow._repair_stage)

    def test_surplus_is_earned_not_borrowed_and_explicit_cap_is_hard(self):
        args = dict(phase_budget=6000, total_jobs=4, completed=0, burst_cap=3000)
        self.assertEqual(node_seconds(6000, 4, 1500, **args), 1500)
        args["completed"] = 1
        self.assertEqual(node_seconds(4500, 3, 1500, **args), 1500)
        self.assertEqual(node_seconds(5500, 3, 1500, **args), 2000)
        args["burst_cap"] = None
        self.assertEqual(node_seconds(5500, 3, 1500, **args), 1500)

    def test_short_budget_and_final_reserve_never_overspent(self):
        for left in (-10, 0, 20, 199, 500, 5000):
            allocated = node_seconds(left, 2, 1500, phase_budget=5000, total_jobs=2, completed=0, reserve=200)
            self.assertLessEqual(allocated, max(0, left - 200))
            self.assertGreaterEqual(allocated, 0)

    def test_large_task_reserves_final_suite_capacity_without_extending_budget(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.n_nodes = 32
            flow.runner = object()
            flow.tests_dir = root
            flow.codegen_mode = lambda **kw: True
            self.assertEqual(flow.final_phase_reserve(), 600)
            self.assertEqual(flow.final_phase_reserve(900), 225)
            flow.n_nodes = 2
            self.assertEqual(flow.final_phase_reserve(), 0)

    def test_final_phase_reserve_can_be_explicitly_tuned(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"OCTOS_ARC_FINAL_PHASE_SECONDS": "750"}, clear=True):
            root = Path(tmp)
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.n_nodes = 10
            flow.runner = object()
            flow.tests_dir = root
            self.assertEqual(flow.final_phase_reserve(), 750)

    def test_final_phase_starts_when_remaining_time_reaches_the_reserve(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"OCTOS_ARC_FINAL_PHASE_SECONDS": "600"}, clear=True):
            root = Path(tmp)
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            flow.n_nodes = 10
            flow.runner = object()
            flow.tests_dir = root
            flow.remaining = lambda: 601
            self.assertFalse(flow.final_phase_due())
            flow.remaining = lambda: 600
            self.assertTrue(flow.final_phase_due())

    def test_measured_duration_median_and_phase_classification(self):
        self.assertEqual(repair_seconds([], 300), 300)
        self.assertEqual(repair_seconds([80, 100, 110], 300), 300)
        self.assertAlmostEqual(repair_seconds([500, 600, 5000], 300), 660)
        self.assertEqual(repair_seconds([10000] * 12 + [50] * 12, 300), 300)
        self.assertEqual(phase_for_label("REQ rewrite"), "repair")
        self.assertEqual(phase_for_label("whole-app design"), "design")


class RepairOutcomeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.codegen_mode = lambda **kw: True
        self.flow.codegen_repair_prompt = lambda *a, **kw: "quoted sources"
        self.flow.suite_repair_prompt = lambda *a: "quoted sources"
        self.flow.wound_down = lambda: False
        self.flow.text_turn = Mock(return_value=(True, "<<<NO CHANGE>>>"))
        def tool_noop(*a, **kw):
            self.flow.last_turn_changed = False
            return True, "no edit"
        self.flow.turn = Mock(side_effect=tool_noop)

    def prepare_final_suite(self):
        (self.root / 'R.spec.ts').touch()
        self.flow.tests_dir = self.root
        self.flow.runner = SimpleNamespace(timeout_ms=30000)
        self.flow.spec_map = {'R': ['R.spec.ts']}

    def test_noop_node_repair_falls_back_then_stops_without_retesting(self):
        self.assertFalse(self.flow.node_repair_turn("R", "missing control", 300, "R repair", lambda: "repair"))
        self.flow.turn.assert_called_once()
        self.assertEqual(self.flow.last_codegen_outcome, "unchanged")
        self.assertIn("unchanged", " ".join(self.flow.pending_corrections))

    def test_startup_repair_uses_file_protocol_even_when_tools_would_be_selected(self):
        self.flow.use_structured_edits = Mock(return_value=True)
        self.flow.structured_edit_turn = Mock()
        self.flow.text_turn.return_value = True, '<<<FILE backend/new.js>>>\nmodule.exports = 1;\n<<<END FILE>>>'
        self.assertTrue(self.flow.node_repair_turn('R', 'Failed at: build/start\nSyntaxError',
                                                  60, 'R repair', lambda: 'repair'))
        self.flow.structured_edit_turn.assert_not_called()
        self.flow.text_turn.assert_called_once()

    def test_suite_noop_is_not_an_applied_repair(self):
        self.assertEqual(self.flow.suite_repair_turn("suite repair", ["R"], "missing control", 300,
                                                   tool_prompt="repair")[0], "tools")
        self.assertIs(self.flow.last_repair_changed, False)

    def test_partial_codegen_changes_are_kept_when_tool_fallback_is_noop(self):
        (self.root / "backend").mkdir()
        (self.root / "backend/existing.js").write_text("old\n")
        self.flow.text_turn.return_value = (True, "<<<FILE backend/new.js>>>\nnew\n<<<END FILE>>>\n"
                                                 "<<<FILE backend/existing.js>>>\nblind\n<<<END FILE>>>")
        self.flow.suite_repair_turn("suite repair", ["R"], "failure", 300, tool_prompt="repair")
        self.assertTrue(self.flow.last_repair_changed)
        self.assertEqual((self.root / "backend/existing.js").read_text(), "old\n")

    def test_codegen_outcomes_are_logged_without_source_or_prompt_contents(self):
        for reply, outcome in (("I will fix it", "no_blocks"),
                               ("<<<FILE backend/x.js>>>\nunfinished", "incomplete_blocks"),
                               ("<<<NO CHANGE>>>", "unchanged"),
                               ("<<<FILE backend/x.js>>>\nsecret-body\n<<<END FILE>>>", "applied")):
            self.flow.text_turn.return_value = True, reply
            self.flow.codegen_turn("secret-prompt", 60, "R repair")
            self.assertEqual(self.flow.last_codegen_outcome, outcome)
        records = (self.root / ".arc/flow-metrics.jsonl").read_text()
        self.assertNotIn("secret", records)
        self.assertEqual(sum(json.loads(line)['kind'] == 'codegen' for line in records.splitlines()), 4)

    def test_completed_reply_with_unclosed_block_is_rejected_before_any_write(self):
        reply = ("<<<FILE backend/one.js>>>\ncomplete\n<<<END FILE>>>\n"
                 "<<<FILE backend/two.js>>>\nunfinished")
        self.flow.text_turn.return_value = True, reply
        ok, message = self.flow.codegen_turn("new app", 60, "R repair")
        self.assertFalse(ok)
        self.assertEqual(self.flow.last_codegen_outcome, "incomplete_blocks")
        self.assertEqual(self.flow.last_codegen_written, [])
        self.assertFalse((self.root / "backend/one.js").exists())
        self.assertFalse((self.root / "backend/two.js").exists())
        self.assertIn("no changes were applied", message)
        self.assertTrue(incomplete_blocks("<<<FILE backend/example.js>>>\nconst example = `\n"
                                           "<<<FILE literal-inside-string>>>\n`;\n<<<END FILE>>>"))

    def test_protocol_retry_is_bounded_and_does_not_run_acceptance_between_attempts(self):
        self.flow.text_turn.side_effect = [(True, "I will fix it"),
                                           (True, "<<<FILE backend/one.js>>>\nfixed\n<<<END FILE>>>")]
        self.assertTrue(self.flow.node_repair_turn("R", "failed", 300, "R repair", lambda: "repair"))
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.flow.turn.assert_not_called()
        self.assertIn("Previous repair was not applied", self.flow.text_turn.call_args.args[0])

    def test_startup_protocol_and_tool_fallback_share_one_deadline(self):
        now = [0.0]
        self.flow.node_timeout = 360
        self.flow.remaining = lambda: 1000
        (self.root / "backend").mkdir()
        (self.root / "backend/server.js").write_text("bad syntax")
        def generate(*a, **kw):
            now[0] += 330
            return False, "no patch"
        self.flow.whole_app_generation_turn = generate
        self.flow.commit = Mock(return_value=True)  # metadata commits are not source changes
        with patch("main.time.monotonic", side_effect=lambda: now[0]):
            self.assertFalse(self.flow.whole_app_startup_repair("backend/server.js: SyntaxError: bad syntax"))
        self.assertEqual(self.flow.turn.call_args.args[1], 30)

    def test_failed_noop_does_not_consume_another_acceptance_run(self):
        flow = self.flow
        flow.runner = object()
        flow.repair_rounds = 3
        flow.head = lambda: "base"
        flow.record_tests = Mock()
        flow.snapshot_sources = Mock()
        flow.run_specs = Mock(return_value=RunSummary(passed=0, total=1, results=[
            TestOutcome("control", False, "failed", 1, message="control missing")]))
        self.assertFalse(flow.acceptance_loop("R", ["R.spec.ts"], time.time() + 900))
        flow.run_specs.assert_called_once()

    def test_leaf_repair_cannot_borrow_the_large_tasks_final_reserve(self):
        flow = self.flow
        flow.runner = object()
        flow.tests_dir = self.root
        flow.n_nodes = 32
        flow.budget = 3600
        flow.remaining = lambda: 600
        flow.repair_rounds = 3
        flow.head = lambda: "base"
        flow.record_tests = Mock()
        flow.run_specs = Mock(return_value=RunSummary(passed=0, total=1, results=[
            TestOutcome("control", False, "failed", 1, message="control missing")]))
        flow.node_repair_turn = Mock(return_value=True)
        self.assertFalse(flow.acceptance_loop("R", ["R.spec.ts"], time.time() + 900))
        flow.node_repair_turn.assert_not_called()
        flow.run_specs.assert_called_once()

    def test_real_tool_turn_measures_effective_sources_not_attempted_writes(self):
        flow = self.flow
        flow.protected_prefixes = lambda: []
        flow.restore_protected = lambda: []
        (self.root / "frontend/public").mkdir(parents=True)
        asset = self.root / "frontend/public/icon.png"
        asset.write_bytes(b"first image")
        metadata = self.root / ".arc"
        metadata.mkdir(exist_ok=True)
        def run(prompt, timeout, monitor):
            self.assertEqual(timeout, 7)  # the shared remainder must not grow to 60s
            monitor.wrote_files = True
            (metadata / "notes.txt").write_text(prompt)
            if prompt == "asset repair":
                asset.write_bytes(b"different image")
            return True, "done"
        flow.driver = SimpleNamespace(run=run)
        m.Flow.turn(flow, "metadata only", 7, "R repair")
        self.assertFalse(flow.last_turn_changed)
        m.Flow.turn(flow, "asset repair", 7, "R repair")
        self.assertTrue(flow.last_turn_changed)
        self.assertEqual(len(flow.repair_durations["tools"]), 1)
        self.assertEqual(flow.repair_durations["codegen"], [])

    def test_noop_final_pass_allows_only_one_changed_approach(self):
        self.prepare_final_suite()
        flow = self.flow
        flow.remaining = lambda: 10000
        flow.time_up = lambda: False
        flow.test_verdict = {"R": False}
        def unchanged():
            flow.final_repair_no_change = True
        flow.final_acceptance = Mock(side_effect=unchanged)
        with patch.dict("os.environ", {"OCTOS_FINAL_SUITE_PASSES": "3"}):
            flow.final_acceptance_passes()
        self.assertEqual(flow.final_acceptance.call_count, 2)
        self.assertTrue(flow._force_final_tool_repair)

    def test_noop_final_pass_stops_when_another_complete_attempt_will_not_fit(self):
        self.prepare_final_suite()
        flow = self.flow
        flow.remaining = lambda: 250
        flow.time_up = lambda: False
        flow.test_verdict = {"R": False}
        flow.final_acceptance = Mock(side_effect=lambda: setattr(flow, "final_repair_no_change", True))
        with patch.dict("os.environ", {"OCTOS_FINAL_SUITE_PASSES": "3"}):
            flow.final_acceptance_passes()
        flow.final_acceptance.assert_called_once()

    def test_final_passes_stop_after_two_stalls_even_with_source_changes(self):
        self.prepare_final_suite()
        flow = self.flow
        flow.remaining = lambda: 50000
        flow.time_up = lambda: False
        flow.test_verdict = {"R": False}
        flow.final_suite_progress = False
        flow.final_repair_no_change = False
        flow.final_acceptance = Mock()
        with patch.dict("os.environ", {"OCTOS_FINAL_SUITE_PASSES": "136"}):
            flow.final_acceptance_passes()
        self.assertEqual(flow.final_acceptance.call_count, 2)

    def test_default_final_pass_cap_does_not_scale_with_tree(self):
        self.prepare_final_suite()
        flow = self.flow
        flow.remaining = lambda: 50000
        flow.time_up = lambda: False
        flow.test_verdict = {"R": False}
        flow.max_turns = 136
        flow.final_suite_progress = True
        flow.final_repair_no_change = False
        flow.final_acceptance = Mock()
        with patch.dict("os.environ", {}, clear=True):
            flow.final_acceptance_passes()
        self.assertEqual(flow.final_acceptance.call_count, 3)

    def test_final_pass_progress_resets_stall_counter(self):
        self.prepare_final_suite()
        flow = self.flow
        flow.remaining = lambda: 50000
        flow.time_up = lambda: False
        flow.test_verdict = {"R": False}
        flow.final_repair_no_change = False
        progress = iter([False, True, False, False])
        flow.final_acceptance = Mock(side_effect=lambda: setattr(flow, "final_suite_progress", next(progress)))
        with patch.dict("os.environ", {"OCTOS_FINAL_SUITE_PASSES": "10"}):
            flow.final_acceptance_passes()
        self.assertEqual(flow.final_acceptance.call_count, 4)


class StartupDigestTests(unittest.TestCase):
    def test_vite_js_parse_error_preserves_location_and_conditional_jsx_advice(self):
        error = 'vite building...\nsrc/hooks/useAuth.js (47:4): Expression expected\n' + 'stack\n' * 250
        digest = startup_error_digest(error)
        self.assertIn('useAuth.js (47:4)', digest)
        self.assertIn('If this module contains JSX', digest)
        self.assertIn('do not replace', digest)
        self.assertLessEqual(len(digest), 700)
        self.assertLessEqual(len(startup_error_digest(error, 30)), 30)

    def test_long_module_warning_does_not_hide_actual_exception(self):
        log = ("server exited early\nWarning: Failed to load the ES module. " + "advice " * 300 +
               "\n(Use node --trace-warnings ...)\n/app/backend/server.js:4\nconst __dirname = 'x';\n"
               "SyntaxError: Identifier '__dirname' has already been declared\n" + "stack\n" * 200)
        digest = startup_error_digest(log, 600)
        self.assertIn("SyntaxError", digest)
        self.assertIn("server.js:4", digest)
        self.assertNotIn("Failed to load", digest)
        self.assertLessEqual(len(digest), 600)

    def test_digest_limits_even_for_tiny_limits_and_unrecognized_errors(self):
        for limit in (0, 1, 2, 3, 4, 50):
            for text in ("header\nSyntaxError: bad syntax", "noise " * 300 + "custom error"):
                self.assertLessEqual(len(startup_error_digest(text, limit)), limit)


class BundleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("zip") and shutil.which("shasum"), "zip and shasum required")
    def test_pack_excludes_public_tests_and_imports_in_isolated_directory(self):
        bundle = Path(m.__file__).parent
        script = (bundle / "pack.sh").read_text()
        command = next(line for line in script.splitlines() if line.startswith("zip -qr "))
        items = shlex.split(command)
        paths = items[3:items.index("-x")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "arc"
            stage.mkdir()
            for rel in [*paths, "pack.sh", "pack_kernel.py"]:
                source = bundle / rel
                if source.is_dir():
                    shutil.copytree(source, stage / rel, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(source, stage / rel)
            (stage / "public-tests").mkdir()
            (stage / "public-tests/private-to-bundle.spec.ts").write_text("must not be packed")
            env = {**os.environ, "ARC_PACK_KERNEL": "0"}
            result = subprocess.run(["sh", str(stage / "pack.sh")], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with ZipFile(root / "octos-arc-bundle.zip") as archive:
                self.assertIn("flow_policy.py", archive.namelist())
                self.assertFalse(any(name.startswith("public-tests/") for name in archive.namelist()))
                archive.extractall(root / "unpacked")
            result = subprocess.run([sys.executable, "main.py", "--help"], cwd=root / "unpacked",
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
