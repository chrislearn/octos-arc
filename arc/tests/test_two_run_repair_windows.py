"""Captured repair/context failures: real Flow boundaries, no model/network."""
import argparse
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from main import Flow
from quality_control import context_evidence, RepeatedContextRequest
from repair_control import seconds_available
from test_codegen_recovery import request, file_block
import test_diagnostic_repairs as fixtures
import test_joint_regression_repair as joint


class ContextWindows(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.FlowRegression(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow, self.root = fixture.flow, fixture.root
        self.path = 'frontend/src/App.jsx'
        source = self.root / self.path; source.parent.mkdir(parents=True)
        self.original = 'export default function App(){return null;}\n' + '// existing source\n' * 270
        source.write_text(self.original)
        f = self.flow
        f.use_structured_edits = Mock(return_value=False)
        f.codegen_context_chars = Mock(return_value=10000)
        f.llm_proxy = SimpleNamespace(turn_upstream_requests=1)
        f.text_turn = Mock(return_value=(True, request([self.path])))
        def edit(*args, **kwargs):
            (self.root / self.path).write_text('export default function App(){return <main>Ready</main>;}')
            f.last_codegen_written = [self.path]; f.last_codegen_outcome = 'applied'
            return True, ''
        f.structured_edit_turn = Mock(side_effect=edit)

    def quoted(self, source=None):
        return 'Current source:\n--- ' + self.path + ' ---\n' + (source or self.original)

    def test_current_whole_quote_is_not_appended_again_and_edits_on_first_request(self):
        f = self.flow
        self.assertTrue(f.codegen_turn(self.quoted(), 600, 'A implement', request_budget=8)[0])
        self.assertEqual(f.text_turn.call_count, 1)
        f.structured_edit_turn.assert_called_once()
        self.assertEqual(f.structured_edit_turn.call_args.kwargs['request_budget'], 7)
        self.assertEqual(f.last_codegen_request_count, 2)
        self.assertIn('Ready', (self.root / self.path).read_text())
        prompt = f.structured_edit_turn.call_args.args[0]
        self.assertEqual(prompt.count(self.original), 1)
        self.assertIn('already supplied', prompt)

    def test_unquoted_large_file_uses_tools_when_context_cannot_fit(self):
        f = self.flow
        f.codegen_context_chars.return_value = 2500
        self.assertTrue(f.codegen_turn('Implement the member form', 600, 'A implement', request_budget=8)[0])
        self.assertEqual(f.text_turn.call_count, 1)
        self.assertIn('Read current ranges', f.structured_edit_turn.call_args.args[0])
        self.assertNotIn('already supplied', f.structured_edit_turn.call_args.args[0])
        metric = next(c for c in f.metric.call_args_list if c.args[0] == 'codegen_context_fallback')
        self.assertEqual(metric.kwargs['context_outcome'], 'needs_context')
        self.assertIn('Ready', (self.root / self.path).read_text())

    def test_stale_or_outline_snapshot_does_not_count_as_current_evidence(self):
        for prompt in (self.quoted('export default function App(){return "stale";}\n'),
                       self.quoted().replace('---\n', '--- (outline)\n')):
            with self.subTest(prompt=prompt[:90]):
                evidence, _ = context_evidence(self.root, {'paths': [self.path]}, {self.path}, {}, supplied=prompt)
                self.assertIn(self.original, evidence)
        with self.assertRaises(RepeatedContextRequest):
            context_evidence(self.root, {'paths': [self.path]}, {self.path}, {}, supplied=self.quoted())

    def test_mixed_request_keeps_new_dependency_without_duplicating_supplied_file(self):
        other = 'backend/model.js'; (self.root / 'backend').mkdir()
        (self.root / other).write_text('module.exports = {};\n')
        evidence, versions = context_evidence(self.root, {'paths': [self.path, other]},
                                              {self.path, other}, {}, supplied=self.quoted())
        self.assertNotIn(self.original, evidence)
        self.assertIn('--- backend/model.js ---', evidence)
        self.assertEqual(set(versions), {self.path, other})

    def test_request_exhaustion_zero_tools_and_disabled_tools_do_not_recover(self):
        f = self.flow
        f.codegen_context_chars.return_value = 2500
        for budget, env in ((1, {}), (8, {'OCTOS_ARC_EDIT_REQUESTS': '0'}),
                            (8, {'OCTOS_ARC_STRUCTURED_EDITS': '0'})):
            with self.subTest(budget=budget, env=env), patch.dict(os.environ, env):
                self.assertFalse(f.codegen_turn('implement', 600, 'A implement', request_budget=budget)[0])
                f.structured_edit_turn.assert_not_called()
                self.assertEqual((self.root / self.path).read_text(), self.original)

    def test_expired_node_cannot_borrow_global_run_time_for_context_tools(self):
        f = self.flow
        now = [1000.0]
        f._node_deadline = 1020.0
        def reply(*args, **kwargs):
            now[0] += 2
            return True, request([self.path])
        f.text_turn.side_effect = reply
        with patch('main.time.monotonic', side_effect=lambda: now[0]):
            self.assertFalse(f.codegen_turn(self.quoted(), 600, 'A implement', request_budget=8)[0])
        f.structured_edit_turn.assert_not_called()
        self.assertLessEqual(f.text_turn.call_args.args[1], 20)

    def test_context_tool_window_is_clamped_to_node_and_partial_writes_are_retained(self):
        f = self.flow
        f._node_deadline = 1045.0
        with patch('main.time.monotonic', return_value=1000.0):
            self.assertTrue(f.codegen_turn(self.quoted(), 600, 'A implement', request_budget=8)[0])
        self.assertLessEqual(f.structured_edit_turn.call_args.args[1], 45)
        f.structured_edit_turn.reset_mock()
        def partial(*args, **kwargs):
            f.last_codegen_written = [self.path]; f.last_codegen_outcome = 'needs_context'
            f.last_codegen_request_count = 1
            return False, 'other file needed after partial edit'
        f._codegen_attempt = Mock(side_effect=partial)
        f._node_deadline = None
        self.assertFalse(f.codegen_turn('implement', 600, 'A implement', request_budget=8)[0])
        f.structured_edit_turn.assert_not_called()
        self.assertEqual(f.last_codegen_written, [self.path])


class MeasurementHistory(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.flow = f = Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        f.tests_dir = self.root / 'tests'; f.tests_dir.mkdir()
        (f.tests_dir / 'A.spec.ts').write_text("test('one',()=>{}); test.setTimeout(60_000);")
        f.runner = SimpleNamespace(timeout_ms=10000, workers=1)
        f.metric = Mock()

    def measured(self, passed):
        return RunSummary(total=1, passed=int(passed), results=[TestOutcome(
            'one', passed, 'passed' if passed else 'failed', 1000, file='A.spec.ts')])

    def test_complete_failed_measurement_trains_window_but_partial_does_not(self):
        f = self.flow; now = [1000.0]
        def run(*args, **kwargs):
            now[0] += 80
            return self.measured(False)
        f._run_specs = Mock(side_effect=run)
        with patch('main.time.monotonic', side_effect=lambda: now[0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 115)
        f._run_specs.return_value = RunSummary(total=0, error='acceptance time budget exhausted')
        f._run_specs.side_effect = lambda *a, **k: f._run_specs.return_value
        f.run_specs(['A.spec.ts'])
        self.assertEqual(len(f._acceptance_timings), 1)
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 115)

    def test_changed_spec_or_worker_uses_cold_forecast_instead_of_old_fast_measurement(self):
        f = self.flow; f._run_specs = Mock(return_value=self.measured(True))
        with patch('main.time.monotonic', side_effect=[1000.0, 1020.0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 40)
        f.runner.workers = 2
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 67.5)
        f.runner.workers = 1
        with (f.tests_dir / 'A.spec.ts').open('a') as out:
            out.write("\ntest('two',()=>{});")
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 90)

    def test_generated_case_selection_and_grader_environment_invalidate_fast_history(self):
        f = self.flow
        f.derived_as_specs = True
        f.derived_case_selection = Mock(return_value=(1, {'A.spec.ts': {'two'}}))
        f._run_specs = Mock(return_value=self.measured(True))
        with patch('main.time.monotonic', side_effect=[1000.0, 1020.0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 40)
        self.assertEqual(f.node_measurement_window(['A.spec.ts'], grader_like=True), 75)
        f.derived_case_selection.return_value = (2, {})
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)

    def test_layered_selected_case_identity_invalidates_history_without_mutating_selection(self):
        f = self.flow
        old = {'previous.spec.ts': [{'title': 'unchanged'}]}
        f.layered = SimpleNamespace(case_inclusions=old)
        chosen = [{'title': 'one', 'line': 2}]
        def selected(specs):
            f.layered.case_inclusions = {'A.spec.ts': list(chosen)}
            return len(chosen), {}
        f.layered.selected = selected
        f._run_specs = Mock(return_value=self.measured(True))
        with patch('main.time.monotonic', side_effect=[1000.0, 1020.0]):
            f.run_specs(['A.spec.ts'])
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 40)
        self.assertIs(f.layered.case_inclusions, old)
        chosen.append({'title': 'two', 'line': 4})
        self.assertEqual(f.node_measurement_window(['A.spec.ts']), 75)
        self.assertIs(f.layered.case_inclusions, old)


class NodeWindows(unittest.TestCase):
    def setUp(self):
        fixture = joint.JointRepairTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow, self.root, self.editor = fixture.flow, fixture.root, fixture.editor
        self.target, self.good, self.bad = fixture.target, fixture.good, fixture.bad
        self.now = [1000.0]
        self.clock = patch('main.time.monotonic', side_effect=lambda: self.now[0])
        self.wall = patch('main.time.time', side_effect=lambda: self.now[0])
        self.clock.start(); self.wall.start()
        self.addCleanup(self.clock.stop); self.addCleanup(self.wall.stop)
        f = self.flow
        f._node_deadline = 2039.0
        f.node_timeout = 1200
        f.node_measurement_window = Mock(side_effect=lambda specs, **kwargs: 200 if 'csv.spec.ts' in specs else 100)
        f.snapshot_sources = Mock(side_effect=lambda *a: self.now.__setitem__(0, self.now[0] + 17))

    def test_1039_seconds_keeps_target_and_regression_window_after_full_repair(self):
        f = self.flow
        def repair(node, failures, timeout, label, build):
            self.assertEqual(f._node_deadline, 1739)
            self.assertLessEqual(timeout, 722)
            build()  # Real prompt construction also lives inside the cutoff.
            self.now[0] += timeout
            self.editor.write_text('target and csv repaired')
            return True
        f._node_repair_turn = Mock(side_effect=repair)
        def measure(specs, **kwargs):
            self.assertEqual(f._node_deadline, 2039)
            self.assertGreaterEqual(seconds_available(f), 100)
            if len(specs) == 1:
                self.now[0] += 100; return self.target
            self.now[0] += 200; return self.good
        f.run_specs = Mock(side_effect=[self.bad])
        # The first regression belongs to the old patch; do not consume the
        # post-repair window with a fabricated old timing in this clock test.
        calls = [0]
        def runs(specs, **kwargs):
            calls[0] += 1
            return self.bad if calls[0] == 1 else measure(specs, **kwargs)
        f.run_specs.side_effect = runs
        self.assertTrue(f.acceptance_loop('rename', ['rename.spec.ts'], 2039,
                        initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        f._node_repair_turn.assert_called_once()
        self.assertEqual(f._node_deadline, 2039)
        self.assertEqual(self.now[0], 2039)

    def test_insufficient_measurement_and_repair_time_never_starts_writing(self):
        f = self.flow; f._node_deadline = 1300
        f.run_specs = Mock(return_value=self.bad); f.node_repair_turn = Mock()
        self.assertFalse(f.acceptance_loop('rename', ['rename.spec.ts'], 1300,
                         initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        f.node_repair_turn.assert_not_called(); f.snapshot_sources.assert_not_called()
        self.assertEqual(f._node_deadline, 1300)

    def test_exception_restores_node_deadline_for_later_measurement(self):
        f = self.flow; f.run_specs = Mock(return_value=self.bad)
        def fail(*args):
            self.assertEqual(f._node_deadline, 1739)
            raise RuntimeError('cancelled')
        f._node_repair_turn = Mock(side_effect=fail)
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            f.acceptance_loop('rename', ['rename.spec.ts'], 2039, initial_summary=self.target,
                              source_versions={'frontend/src/Editor.jsx': 'before'})
        self.assertEqual(f._node_deadline, 2039)

    def test_unapplied_rewrite_and_tool_fallback_share_cutoff(self):
        f = self.flow
        f.test_verdict = {}; f.can_rewrite_from_scratch = Mock(return_value=True)
        failed = joint.measured(joint.outcome('rename', False, 'value mismatch'))
        f.run_specs = Mock(return_value=self.target)
        def rewrite(*args, **kwargs):
            self.assertEqual(f._node_deadline, 1939)
            self.now[0] += 300; f.last_codegen_written = []
            return False, 'no writes'
        f.codegen_turn = Mock(side_effect=rewrite)
        def tools(node, failures, timeout, label, build):
            self.assertEqual(f._node_deadline, 1939)
            self.assertLessEqual(timeout, 622)
            self.now[0] += timeout
            return True
        f._node_repair_turn = Mock(side_effect=tools)
        self.assertTrue(f.acceptance_loop('rename', ['rename.spec.ts'], 2039,
                                         rebuild_prompt=lambda _: 'rewrite', initial_summary=failed))
        f._node_repair_turn.assert_called_once()
        self.assertEqual(f._node_deadline, 2039)

    def test_global_final_reserve_can_block_repair_with_long_node_deadline(self):
        f = self.flow
        f.remaining = Mock(return_value=400)
        f.final_phase_reserve = Mock(return_value=150)
        f.run_specs = Mock(return_value=self.bad); f.node_repair_turn = Mock()
        self.assertFalse(f.acceptance_loop('rename', ['rename.spec.ts'], 2039,
                         initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        f.node_repair_turn.assert_not_called()
        f.snapshot_sources.assert_not_called()

    def test_real_node_segments_and_unapplied_tool_continuation_share_measurement_cutoff(self):
        f = self.flow
        f.test_verdict = {}
        f.codegen_mode = Mock(return_value=True)
        f.codegen_repair_prompt = Mock(return_value='quoted sources')
        f.llm_proxy = SimpleNamespace(turn_upstream_requests=0)
        def generate(*args, **kwargs):
            self.assertEqual(f._node_deadline, 1939)
            self.now[0] += 200
            f.last_codegen_written = []
            f.last_codegen_request_count = 1
            f.last_codegen_outcome = 'needs_context'
            return False, 'whole-source capacity exhausted'
        f.codegen_turn = Mock(side_effect=generate)
        calls = [0]
        def tool(prompt, timeout, label, **kwargs):
            calls[0] += 1
            self.assertEqual(f._node_deadline, 1939)
            self.assertLessEqual(timeout, 722 if calls[0] == 1 else 422)
            f.llm_proxy.turn_upstream_requests = 1
            f.last_turn_changed = calls[0] == 2
            self.now[0] += 300 if calls[0] == 1 else timeout
            if calls[0] == 2:
                self.editor.write_text('applied by continuation')
            return True, 'read source; implement the fix next'
        f.repair_tool_turn = Mock(side_effect=tool)
        f.run_specs = Mock(return_value=self.target)
        failed = joint.measured(joint.outcome('rename', False, 'value mismatch'))
        self.assertTrue(f.acceptance_loop('rename', ['rename.spec.ts'], 2039, initial_summary=failed))
        self.assertEqual(f.repair_tool_turn.call_count, 2)
        self.assertEqual(f._node_deadline, 2039)
        self.assertEqual(self.now[0], 1939)
        self.assertEqual(self.editor.read_text(), 'applied by continuation')


if __name__ == '__main__':
    unittest.main()
