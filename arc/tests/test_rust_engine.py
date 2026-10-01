import json
import unittest

from rust_engine import Translator, parse_event, write_runner_spec


class Calls:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return []
        return record


class Runtime:
    def __init__(self):
        self.events = Calls()
        self.traceability = Calls()


class ParseTests(unittest.TestCase):
    def test_should_only_accept_prefixed_json_objects(self):
        self.assertEqual(parse_event('@@arc-event {"event": "x"}'), {"event": "x"})
        self.assertIsNone(parse_event("[flow] plain log"))
        self.assertIsNone(parse_event("@@arc-event not json"))
        self.assertIsNone(parse_event("@@arc-event [1]"))


class TranslatorTests(unittest.TestCase):
    def test_should_mirror_requirement_states_onto_aliases_and_record_tests(self):
        runtime = Runtime()
        t = Translator(runtime, lambda m: None)
        t.handle({"event": "requirement_state", "node_id": "REQ-1", "phase": "test", "status": "passed",
                  "message": "ok", "aliases": ["REQ-1.1"]})
        t.handle({"event": "test_result", "node_id": "REQ-1", "test_id": "REQ-1-increments", "title": "REQ-1: increments",
                  "file": "REQ-1.spec.ts", "ok": True, "type": "e2e"})
        t.handle({"event": "commit", "message": "m", "sha": "abc"})
        t.handle({"event": "run_completed", "message": "all requirement nodes implemented and verified"})
        names = [c[0] for c in runtime.events.calls]
        self.assertEqual(names[:2], ["mark_test_passed", "mark_test_passed"])
        self.assertEqual(runtime.events.calls[1][1], ("REQ-1.1", "ok"))
        self.assertIn("notify_commit_history_changed", names)
        self.assertEqual(runtime.traceability.calls[0][0], "list_interfaces")
        upsert = next(c for c in runtime.traceability.calls if c[0] == "upsert_test")
        self.assertEqual(upsert[2]["req_id"], "REQ-1")
        self.assertTrue(upsert[2]["passed"])
        self.assertEqual(t.final["event"], "run_completed")

    def test_should_ignore_unknown_states(self):
        runtime = Runtime()
        t = Translator(runtime, lambda m: None)
        t.handle({"event": "requirement_state", "node_id": "REQ-1", "phase": "design", "status": "weird"})
        t.handle({"event": "usage", "prompt_tokens": 1})
        self.assertEqual(runtime.events.calls, [])


class RunnerSpecTests(unittest.TestCase):
    def test_should_write_the_kernel_contract(self):
        import os, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MODEL"] = "deepseek-v4-flash"
            os.environ["OPENAI_BASE_URL"] = "https://api.arc-bench.com/v1"
            path = Path(tmp) / ".arc" / "runner-spec.json"
            spec = write_runner_spec(path, req_dir=Path(tmp) / "req", output_dir=Path(tmp), web_port=3000, tests_dir=None)
            data = json.loads(path.read_text())
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["web_port"], 3000)
            self.assertIsNone(data["tests_dir"])
            self.assertEqual(data["model"]["model"], "deepseek-v4-flash")
            self.assertEqual(spec["model"]["api_key_env"], "OPENAI_API_KEY")
            self.assertNotIn("sk-", path.read_text())
            self.assertIsNone(data["previous_requirements"])

    def test_should_snapshot_the_template_requirement_table_before_it_is_overwritten(self):
        import tempfile
        from pathlib import Path
        from rust_engine import snapshot_previous_requirements
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            empty = snapshot_previous_requirements(out)  # no template table: an empty snapshot, never None
            self.assertEqual(json.loads(empty.read_text()), {})
            table = out / ".arc" / "traceability" / "requirements.json"
            table.parent.mkdir(parents=True)
            table.write_text(json.dumps({"REQ-1": {"id": "REQ-1", "description": "old"}, "ROOT": {"id": "ROOT"}}))
            copy = snapshot_previous_requirements(out)
            self.assertEqual(copy, out / ".arc" / "previous-requirements.json")
            self.assertEqual(json.loads(copy.read_text())["REQ-1"]["description"], "old")
            path = out / ".arc" / "runner-spec.json"
            write_runner_spec(path, req_dir=out / "req", output_dir=out, web_port=3000, tests_dir=None,
                              previous_requirements=copy)
            self.assertEqual(json.loads(path.read_text())["previous_requirements"], str(copy))


class RustTerminalTests(unittest.TestCase):
    def test_requirements_setup_failure_records_terminal_state(self):
        import argparse
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from rust_engine import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req = root / 'task'
            req.mkdir()
            output = root / 'output'
            args = argparse.Namespace(requirement_path=str(req), output_dir=str(output), web_port=3000)
            with patch.dict('sys.modules', {'arcbench_agent_runtime': SimpleNamespace(AgentRuntime=object)}), \
                    patch('rust_engine.shutil.copytree', side_effect=OSError('copy failed')):
                self.assertEqual(main(args), 0)
            state = json.loads((output / '.arc/terminal-state.json').read_text())
            self.assertEqual(state['state'], 'completed_with_issues')
            self.assertEqual(state['pending_usage_status'], 'unknown')

    def test_kernel_exit_and_final_event_must_both_succeed(self):
        import argparse
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from rust_engine import main
        for rc, event, expected in ((1, 'run_failed', 'completed_with_issues'),
                                    (0, 'run_failed', 'completed_with_issues'),
                                    (0, 'run_completed', 'completed'),
                                    (None, None, 'interrupted_by_user'),
                                    ('SIGTERM', None, 'completed_with_issues'),
                                    ('internal_exit', None, 'completed_with_issues')):
            with self.subTest(rc=rc, event=event), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                req = root / 'task'
                req.mkdir()
                output = root / 'output'
                args = argparse.Namespace(requirement_path=str(req), output_dir=str(output), web_port=3000)
                runtime = Runtime()
                runtime.git = Calls()
                agent = SimpleNamespace(from_env=lambda **_: runtime)
                def kernel(_bin, _spec, _policy, translator, _log, _env):
                    if rc is None:
                        raise KeyboardInterrupt
                    if rc == 'SIGTERM':
                        import signal
                        signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                    if rc == 'internal_exit': raise SystemExit(1)
                    translator.final = {'event': event, 'message': 'kernel result'}
                    return rc
                with patch.dict('sys.modules', {'arcbench_agent_runtime': SimpleNamespace(AgentRuntime=agent)}), \
                        patch('rust_engine.snapshot_previous_requirements', return_value=output / 'previous.json'), \
                        patch('rust_engine.write_runner_spec'), \
                        patch('rust_engine.run_kernel', side_effect=kernel), \
                        patch('main.load_requirement_tree', return_value={}), \
                        patch('main.locate_acceptance_tests', return_value=None), \
                        patch('main.find_octos', return_value='octos'), \
                        patch('main._reap_stray_processes') as reap, \
                        patch('main._postflight_structure_check'), \
                        patch('main._free_web_port') as free_port:
                    self.assertEqual(main(args), 130 if expected == 'interrupted_by_user' else 0)
                    reap.assert_called_once_with('postflight', output)
                    free_port.assert_called_once_with(3000, output)
                state = json.loads((output / '.arc/terminal-state.json').read_text())
                self.assertEqual(state['state'], expected)
                if rc == 1:
                    self.assertIn('exited 1', state['reason'])
                calls=[name for name, _, _ in runtime.events.calls]
                self.assertNotIn('mark_run_failed',calls)
                if expected != 'interrupted_by_user': self.assertIn('mark_run_completed',calls)

    def test_legacy_entry_and_cleanup_failures_still_handoff(self):
        import argparse,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from rust_engine import main
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);(output/'backend').mkdir();entry=output/'backend/server.js'
            entry.write_text('retained application')
            args=argparse.Namespace(output_dir=str(output))
            with patch('rust_engine.coordinated_main',side_effect=SystemExit(1)):
                self.assertEqual(main(args),0)
            self.assertEqual(entry.read_text(),'retained application')
            self.assertEqual(json.loads((output/'.arc/terminal-state.json').read_text())['state'],'completed_with_issues')


if __name__ == "__main__":
    unittest.main()


class ModelRouteCommandTests(unittest.TestCase):
    def test_routes_are_explicit_kernel_argument(self):
        import io
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from rust_engine import run_kernel
        proc = MagicMock()
        proc.stdout = io.StringIO('')
        proc.wait.return_value = 0
        rules = '[{"model":"small","phases":["implement"]}]'
        with patch('rust_engine.subprocess.Popen', return_value=proc) as launch:
            run_kernel('octos', Path('spec.json'), Path('policy.toml'), None,
                       lambda _: None, {'OCTOS_ARC_MODEL_ROUTES': rules})
        args = launch.call_args.args[0]
        self.assertEqual(args[args.index('--model-routes-json') + 1], rules)

    def test_interrupted_kernel_stream_stops_its_process_group(self):
        import signal
        from pathlib import Path
        from unittest.mock import MagicMock, patch
        from rust_engine import run_kernel
        proc = MagicMock()
        proc.pid = 12345
        def lines():
            yield '[engine] started\n'
            raise KeyboardInterrupt
        proc.stdout.__iter__.side_effect = lines
        with patch('rust_engine.subprocess.Popen', return_value=proc) as launch, \
                patch('rust_engine.os.killpg') as kill_group:
            with self.assertRaises(KeyboardInterrupt):
                run_kernel('octos', Path('spec.json'), Path('policy.toml'), None,
                           lambda _: None, {})
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        kill_group.assert_called_once_with(12345, signal.SIGTERM)
        proc.wait.assert_called_once_with(timeout=5)
        proc.stdout.close.assert_called_once()
