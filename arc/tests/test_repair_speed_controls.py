"""Failure-driven controls for scheduling, evidence and source context."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acceptance import AppServer, RunSummary, TestOutcome, completed_step_prefix
from guard import TurnMonitor
from main import Flow, write_codegen_manifests, quoted_paths
from repair_control import isolated_node_deadline, measured_progress, progress_snapshot, seconds_available, run_owned_process
from source_index import SourceIndex
from verify_app import verify


class VerificationControls(unittest.TestCase):
    def test_failed_unfinished_and_unidentified_commands_do_not_verify(self):
        for completion in (None, {'success': False}, {}, {'success': True, 'tool_call_id': 'other'}):
            monitor = TurnMonitor([])
            monitor.observe('tool/started', {'tool_name': 'write_file', 'tool_call_id': 'write', 'arguments': {'path': 'a.js'}})
            monitor.observe('tool/started', {'tool_name': 'exec_command', 'tool_call_id': 'check', 'arguments': {'cmd': 'npm run build'}})
            if completion is not None:
                monitor.observe('tool/completed', {'tool_call_id': 'check', **completion})
            monitor.finish('implemented and verified')
            self.assertTrue(monitor.verification_attempted)
            self.assertFalse(monitor.verified)
            self.assertTrue(monitor.corrections())

    def test_inherited_data_is_never_used_and_private_data_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app, specs = root / 'app', root / 'tests'
            app.mkdir(); specs.mkdir()
            (app / 'a.js').write_text('source')
            (specs / 'a.spec.ts').write_text('frozen')
            dirty = root / 'dirty'; dirty.mkdir()
            (dirty / 'state.json').write_text('user data')
            private_paths = []
            def server_factory(copy, port, log, **kwargs):
                private = Path(kwargs['env_extra']['ARC_DATA_DIR'])
                self.assertNotEqual(private, dirty)
                self.assertFalse(private.exists())
                private.mkdir(); (private / 'state.json').write_text('mutated')
                private_paths.append(private)
                return Mock(build=Mock(return_value=None), start=Mock(return_value=None), time_left=Mock(return_value=50))
            runner = Mock(run=Mock(return_value=RunSummary(passed=1, total=1)))
            with patch.dict(os.environ, {'ARC_DATA_DIR': str(dirty)}), patch('verify_app.AppServer', side_effect=server_factory), patch('verify_app.AcceptanceRunner', return_value=runner):
                for _ in range(2):
                    self.assertEqual(verify(app, specs, root, root / 'report', ['a.spec.ts']), 0)
            self.assertNotEqual(private_paths[0], private_paths[1])
            self.assertTrue(all(not p.exists() for p in private_paths))
            self.assertEqual((dirty / 'state.json').read_text(), 'user data')
            self.assertEqual((app / 'a.js').read_text(), 'source')
            report = json.loads((root / 'report/summary.json').read_text())
            self.assertEqual(report['specs'], ['a.spec.ts'])

    def test_exception_stops_server_and_removes_private_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'app').mkdir(); (root / 'tests').mkdir()
            (root / 'tests/a.spec.ts').write_text('test')
            server = Mock(build=Mock(side_effect=RuntimeError('build exception')))
            with patch('verify_app.AppServer', return_value=server), patch('verify_app.AcceptanceRunner'):
                with self.assertRaisesRegex(RuntimeError, 'build exception'):
                    verify(root / 'app', root / 'tests', root, root / 'report', ['a.spec.ts'])
            server.stop.assert_called_once()


class SchedulingControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.flow = Flow(argparse.Namespace(web_port=3000), root, root)
        f = self.flow
        f.metric = Mock(); f.remaining = Mock(return_value=5000); f.wound_down = Mock(return_value=False)
        f.codegen_mode = Mock(return_value=True); f.codegen_repair_prompt = Mock(return_value=None)
        f.with_preservation_context = Mock(side_effect=lambda prompt, *a: prompt)
        f.compact_tool_repair_prompt = Mock(side_effect=lambda prompt, *a: prompt)
        f.llm_proxy = SimpleNamespace(hard_budget_exhausted=True, turn_upstream_requests=0)
        def tools(*args, **kwargs):
            f.last_turn_changed = False
            f.llm_proxy.turn_upstream_requests = 1
            return True, ''
        f.repair_tool_turn = Mock(side_effect=tools)

    def test_previous_segment_exhaustion_does_not_block_fresh_round(self):
        self.assertFalse(self.flow.node_repair_turn('A', 'failure', 100, 'A repair', lambda: 'prompt'))
        self.flow.repair_tool_turn.assert_called_once()
        self.assertEqual(self.flow.repair_tool_turn.call_args.kwargs['request_budget'], 36)
        report = self.flow.metric.call_args.kwargs
        self.assertEqual(report['upstream_requests'], 1)

    def test_segment_exhaustion_uses_remaining_round_but_whole_round_does_not_reset(self):
        for spent, expected in ((12, 24), (36, None)):
            f = self.flow; f.repair_tool_turn.reset_mock()
            f.codegen_repair_prompt.return_value = 'compact'
            def generation(*args, **kwargs):
                f.last_codegen_request_count = spent; f.last_codegen_written = []
                f.last_codegen_refused = set(); f.last_codegen_context_requested = set()
                f.last_codegen_degenerated = True; f.last_codegen_outcome = 'generation_failed'
                return False, 'segment exhausted'
            f.codegen_turn = Mock(side_effect=generation)
            f.node_repair_turn('A', 'failure', 100, 'A repair', lambda: 'prompt')
            if expected is None:
                f.repair_tool_turn.assert_not_called()
            else:
                self.assertEqual(f.repair_tool_turn.call_args.kwargs['request_budget'], expected)

    def test_expired_node_does_not_start_a_repair(self):
        self.flow._node_deadline = time.monotonic() - 1
        self.assertFalse(self.flow.node_repair_turn('A', 'failure', 100, 'A repair', lambda: 'prompt'))
        self.flow.repair_tool_turn.assert_not_called()

    def test_node_deadline_is_restored_after_exception(self):
        f = SimpleNamespace(_node_deadline=100, remaining=lambda: 500)
        @isolated_node_deadline
        def run(flow):
            flow._node_deadline = time.monotonic() - 1
            self.assertLess(seconds_available(flow), 0)
            raise RuntimeError('failed')
        with self.assertRaises(RuntimeError):
            run(f)
        self.assertEqual(f._node_deadline, 100)

    def test_build_command_cannot_start_after_deadline(self):
        server = AppServer(Path(self.temp.name), 0, lambda _: None)
        server.deadline = time.monotonic() - 1
        with patch('acceptance.run_owned_process') as command:
            self.assertEqual(server._run(['npm', 'install'], server.project, 600)[0], 124)
        command.assert_not_called()

    def test_timeout_stops_owned_grandchild(self):
        root = Path(self.temp.name)
        child = "import pathlib,time,os; pathlib.Path('child.pid').write_text(str(os.getpid())); time.sleep(60)"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(60)"
        with self.assertRaises(subprocess.TimeoutExpired):
            run_owned_process([sys.executable, '-c', parent, child], cwd=root, env=dict(os.environ), timeout=0.5)
        pid = int((root / 'child.pid').read_text())
        # An unreaped orphan may briefly remain a zombie; it cannot run/write.
        stat = Path(f'/proc/{pid}/stat')
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')

    def test_backend_refactor_rejects_duplicate_actual_registration(self):
        f = self.flow; root = Path(self.temp.name)
        route = root / 'backend/routes/items.js'; route.parent.mkdir(parents=True)
        route.write_text('module.exports=app=>{};\n' + '// x\n' * 7000)
        (root / 'backend/server.js').write_text("require('./routes/items')(app);\n")
        f.head = Mock(return_value='before'); f.restore_app = Mock(); f.commit = Mock()
        f.codegen_context_chars = Mock(return_value=90000); f.runner = None
        f.generation_batch_check = Mock(side_effect=lambda _: setattr(f, '_generation_gate_result', {'errors': []}))
        def split(prompt, *args, **kwargs):
            self.assertIn('--- backend/server.js ---', prompt)
            self.assertIn('child directory', prompt)
            f.last_codegen_written = ['backend/routes/items.js', 'backend/routes/items/filter.js']
            return True, 'split'
        f.codegen_turn = Mock(side_effect=split)
        rows = [{'method': 'GET', 'path': '/api/items'}]
        with patch('web_checks.runtime_route_report', side_effect=[{'routes': rows}, {'routes': rows * 2}]):
            self.assertFalse(f.split_oversized_hub('backend/routes/items.js', 'too large'))
        f.restore_app.assert_called_once_with('before'); f.commit.assert_not_called()

    def test_unknown_backend_loader_never_runs_a_refactor(self):
        f = self.flow; root = Path(self.temp.name)
        route = root / 'backend/routes/items.js'; route.parent.mkdir(parents=True)
        route.write_text('// x\n' * 7000); (root / 'backend/server.js').write_text('unknownLoader()')
        f.codegen_context_chars = Mock(return_value=90000); f.codegen_turn = Mock()
        with patch('web_checks.runtime_route_report', return_value=None):
            self.assertFalse(f.split_oversized_hub('backend/routes/items.js', 'too large'))
        f.codegen_turn.assert_not_called()

    def test_partial_or_cancelled_refactor_restores_uncommitted_files(self):
        f = self.flow; root = Path(self.temp.name)
        page = root / 'frontend/src/pages/Editor.jsx'; page.parent.mkdir(parents=True)
        original = 'export default function Editor() {}\n' + '// pending feature\n' * 3000
        page.write_text(original)
        pending = root / 'frontend/src/pages/Pending.jsx'; pending.write_text('uncommitted new feature')
        helper = root / 'frontend/src/pages/feature/Helper.jsx'
        f.head = Mock(return_value='old-head'); f.codegen_context_chars = Mock(return_value=196608)
        def restore_head(_):
            page.write_text('old committed version'); pending.unlink(missing_ok=True)
        f.restore_app = Mock(side_effect=restore_head)
        for cancelled in (False, True):
            f.hub_splits_attempted = set()
            def generation(*args, **kwargs):
                page.write_text('incomplete refactor'); helper.parent.mkdir(exist_ok=True)
                helper.write_text('new refactor module')
                f.last_codegen_written = [str(page.relative_to(root)), str(helper.relative_to(root))]
                if cancelled:
                    raise RuntimeError('cancelled')
                return False, 'partial'
            f.codegen_turn = Mock(side_effect=generation)
            if cancelled:
                with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                    f.split_oversized_hub(str(page.relative_to(root)), 'context')
            else:
                self.assertFalse(f.split_oversized_hub(str(page.relative_to(root)), 'context'))
            self.assertEqual(page.read_text(), original)
            self.assertEqual(pending.read_text(), 'uncommitted new feature')
            self.assertFalse(helper.exists())

    def test_context_rebuild_keeps_original_owner_with_current_version(self):
        f = self.flow; root = Path(self.temp.name)
        write_codegen_manifests(root)
        (root / 'frontend/src').mkdir(parents=True, exist_ok=True)
        (root / 'backend/server.js').write_text('const entry = true;')
        editor = root / 'frontend/src/Editor.jsx'
        editor.write_text('export default function Editor(){return <div data-testid="filter-range"/>;}')
        (root / 'frontend/src/App.jsx').write_text("import Editor from './Editor'; export default Editor;")
        node = {'id': 'A', 'name': 'filter', 'type': 'ATOMIC', 'description': 'Apply filter'}
        f.codegen_context_chars = Mock(return_value=90000)
        original = f.codegen_implement_prompt(node, "await page.getByTestId('filter-range');",
                                              must_include={'frontend/src/Editor.jsx'})
        self.assertIn('frontend/src/Editor.jsx', quoted_paths(original))
        editor.write_text(editor.read_text() + '\n// new current version')
        recovered = f.codegen_implement_prompt(node, 'backend operation')
        self.assertIn('frontend/src/Editor.jsx', quoted_paths(recovered))
        self.assertIn('// new current version', recovered)
        manifest = f.metric.call_args.kwargs['closure_versions']
        self.assertEqual(manifest['frontend/src/Editor.jsx'], SourceIndex({'frontend/src/Editor.jsx': editor.read_text()}).versions['frontend/src/Editor.jsx'])

    def test_direct_native_fallback_does_not_require_shell(self):
        f = self.flow
        # Exercise the real dispatch method, rather than the setUp scheduler stub.
        f.use_structured_edits = Mock(return_value=True)
        f.structured_edit_turn = Mock(return_value=(True, ''))
        f.turn = Mock()
        f.codegen_context_chars = Mock(return_value=90000)
        f.generation_batch_check = Mock(); f.remember_repair = Mock()
        Flow.repair_tool_turn(f, 'focused prompt', 100, 'A repair', request_budget=24)
        f.structured_edit_turn.assert_called_once()
        f.turn.assert_not_called()

    def test_repair_memory_preserves_bound_native_scope_and_is_added_once(self):
        f = self.flow; root = Path(self.temp.name)
        path = root / 'frontend/src/Editor.jsx'; path.parent.mkdir(parents=True)
        path.write_text('function helper() {}\n' * 100 + 'const applyFilter = () => {};\n')
        prompt, evidence = 'Repair the current failing operation.', 'apply filter'
        f.bind_edit_scope(prompt, evidence, {'frontend/src/Editor.jsx'})
        f.repair_memory_context = Mock(return_value='\nPrevious bounded repair: unchanged.\n')
        f.codegen_context_chars = Mock(return_value=90000)
        f.turn = Mock(return_value=(True, 'done'))
        f.generation_batch_check = Mock(); f.remember_repair = Mock()
        Flow.repair_tool_turn(f, prompt, 100, 'A repair', request_budget=24)
        delivered = f.turn.call_args.args[0]
        self.assertIn('Source relationships', delivered)
        self.assertIn('applyFilter', delivered)
        self.assertEqual(delivered.count('Previous bounded repair: unchanged.'), 1)
        self.assertIn('(structured edits)', f.turn.call_args.args[2])

    def test_post_refactor_verification_exception_restores_pending_sources(self):
        f = self.flow; root = Path(self.temp.name)
        path = root / 'frontend/src/Editor.jsx'; path.parent.mkdir(parents=True)
        original = 'export default function Editor() {}\n' + '// pending feature\n' * 3000
        path.write_text(original)
        helper = path.parent / 'feature/Helper.jsx'
        f.head = Mock(return_value='before'); f.restore_app = Mock(); f.commit = Mock()
        f.codegen_context_chars = Mock(return_value=196608)
        def split(*args, **kwargs):
            path.write_text('refactored entry'); helper.parent.mkdir(exist_ok=True)
            helper.write_text('new refactor helper')
            f.last_codegen_written = ['frontend/src/Editor.jsx', 'frontend/src/feature/Helper.jsx']
            return True, 'split'
        f.codegen_turn = Mock(side_effect=split)
        for phase in ('fallback_build', 'regression'):
            with self.subTest(phase=phase):
                f.hub_splits_attempted = set(); path.write_text(original); helper.unlink(missing_ok=True)
                f.generation_batch_check = Mock(side_effect=lambda _: setattr(
                    f, '_generation_gate_result', None if phase == 'fallback_build' else {'errors': []}))
                f.app_server = Mock(return_value=Mock(build=Mock(side_effect=RuntimeError('cancelled verification'))))
                f.test_verdict = {'old': True}; f.spec_map = {'old': ['old.spec.ts']}; f.runner = Mock()
                f.run_specs = Mock(side_effect=RuntimeError('cancelled verification'))
                with self.assertRaisesRegex(RuntimeError, 'cancelled verification'):
                    f.split_oversized_hub('frontend/src/Editor.jsx', 'context')
                self.assertEqual(path.read_text(), original)
                self.assertFalse(helper.exists())
                f.commit.assert_not_called()

    def test_refactor_rejects_passing_counts_with_a_missing_proven_spec(self):
        f = self.flow; root = Path(self.temp.name)
        path = root / 'frontend/src/Editor.jsx'; path.parent.mkdir(parents=True)
        original = 'export default function Editor() {}\n' + '// pending feature\n' * 3000
        path.write_text(original)
        f.head = Mock(return_value='before'); f.restore_app = Mock(); f.commit = Mock()
        f.codegen_context_chars = Mock(return_value=196608)
        def split(*args, **kwargs):
            path.write_text('refactored entry')
            f.last_codegen_written = ['frontend/src/Editor.jsx']
            return True, 'split'
        f.codegen_turn = Mock(side_effect=split)
        f.generation_batch_check = Mock(side_effect=lambda _: setattr(f, '_generation_gate_result', {'errors': []}))
        f.test_verdict = {'A': True, 'B': True}; f.spec_map = {'A': ['A.spec.ts'], 'B': ['B.spec.ts']}
        f.runner = Mock()
        f.run_specs = Mock(return_value=RunSummary(passed=2, total=2, results=[
            TestOutcome('A first', True, 'passed', 1, file='A.spec.ts'),
            TestOutcome('A second', True, 'passed', 1, file='A.spec.ts')]))
        self.assertFalse(f.split_oversized_hub('frontend/src/Editor.jsx', 'context'))
        self.assertEqual(path.read_text(), original)
        f.commit.assert_not_called()

    def test_request_attribution_survives_a_later_turn(self):
        import threading
        from llm_proxy import LlmProxy
        proxy = object.__new__(LlmProxy)
        proxy._lock = threading.Lock(); proxy.phase = 'repair'; proxy.mode = 'low'
        proxy.no_tools = False; proxy.turn_serial = 2
        proxy.repair_round_id = 'A:1'; proxy.executor = 'structured_tools'
        captured = proxy.request_meta(json.dumps({'messages': [{'role': 'user', 'content': 'source'}]}).encode())
        proxy.repair_round_id = 'B:2'; proxy.turn_serial = 3
        self.assertEqual(captured['repair_round_id'], 'A:1')
        self.assertEqual(captured['turn_serial'], 2)
        self.assertEqual(captured['executor'], 'structured_tools')

    def test_acceptance_links_only_matching_source_and_complete_scope(self):
        f = self.flow
        f._last_repair_round = {'round_id': 'A:1', 'source_after': f.app_source_digest()}
        f._run_specs = Mock(return_value=RunSummary(passed=0, total=0))
        f.suite_is_measured = Mock(return_value=False)
        f.run_specs(['A.spec.ts'])
        self.assertEqual(f.metric.call_args.kwargs['repair_round_id'], 'A:1')
        self.assertFalse(f.metric.call_args.kwargs['all_passed'])
        f._last_repair_round['source_after'] = 'stale source'
        f.run_specs(['A.spec.ts'])
        self.assertIsNone(f.metric.call_args.kwargs['repair_round_id'])


class EvidenceControls(unittest.TestCase):
    def row(self, title='sort', ok=False, steps=(), **kwargs):
        return TestOutcome(title, ok, 'passed' if ok else 'failed', 1, file='A.spec.ts', completed_steps=list(steps), **kwargs)

    def test_line_and_message_changes_do_not_earn_extra_rounds(self):
        old = progress_snapshot(RunSummary(results=[self.row(line=10, message='click missing')]))
        new = progress_snapshot(RunSummary(results=[self.row(line=99, message='click missing changed')]))
        self.assertEqual(measured_progress(old, new), 'unchanged')

    def test_completed_action_prefix_can_advance_without_passing_yet(self):
        old = progress_snapshot(RunSummary(results=[self.row(steps=['Open'])]))
        new = progress_snapshot(RunSummary(results=[self.row(steps=['Open', 'Select range'])]))
        self.assertEqual(measured_progress(old, new), 'advanced')
        new[('A.spec.ts', 'sort', None)] = (False, ('Different open', 'Select range'))
        self.assertEqual(measured_progress(old, new), 'unknown')

    def test_swapped_passes_are_a_regression_not_equal_quality(self):
        old = progress_snapshot(RunSummary(results=[self.row('A', True), self.row('B')]))
        new = progress_snapshot(RunSummary(results=[self.row('A'), self.row('B', True)]))
        self.assertEqual(measured_progress(old, new), 'regression')

    def test_duplicate_ambiguous_titles_cannot_buy_progress(self):
        summary = RunSummary(results=[self.row('same', True), self.row('same')])
        self.assertEqual(progress_snapshot(summary), {})
        summary.results[0].spec_line = 1; summary.results[1].spec_line = 2
        self.assertEqual(len(progress_snapshot(summary)), 2)

    def test_trace_parser_excludes_failed_action_and_unknown_timeouts(self):
        trace = [{'title': 'Before Hooks'}, {'title': 'Open'}, {'title': 'Sort', 'steps': [
            {'title': 'Select range'}, {'title': 'Click sort', 'error': {'message': 'missing'}}]}]
        self.assertEqual(completed_step_prefix(trace), ['Open', 'Select range'])
        self.assertEqual(completed_step_prefix([{'title': 'Click sort'}]), [])

    def test_late_arrow_function_and_request_json_survive_local_noise(self):
        source = 'export default function Editor() {\n' + ''.join(f'  const state{i} = 0;\n' for i in range(1500))
        source += '  const applyFilter = async (columnId) => {\n    return requestJson(`/api/sheets/${id}/filters`, {method:"POST"});\n  };\n}\n'
        index = SourceIndex({'frontend/src/Editor.jsx': source})
        display = index.render(['frontend/src/Editor.jsx'], evidence='Apply filter to column')
        self.assertIn('L1502 applyFilter(columnId)', display)
        self.assertIn('requestJson', display); self.assertIn('method=POST', display)
        self.assertNotIn('state999', display)
        self.assertIn(index.versions['frontend/src/Editor.jsx'], display)
        self.assertLessEqual(len(display), 5000)

    def test_evidence_prioritizes_a_late_handler_over_early_helpers(self):
        source = ''.join(f'function helper{i}() {{}}\n' for i in range(40)) + 'const sortRange = (range) => {};\n'
        index = SourceIndex({'a.js': source})
        self.assertIn('sortRange', index.render(['a.js'], evidence='sort range'))
        self.assertNotEqual(index.versions, SourceIndex({'a.js': source + '// update'}).versions)
