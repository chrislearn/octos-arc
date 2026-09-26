import json
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest import skipUnless
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from generation_checks import helper_import_errors
from llm_proxy import reserve_edit_budget
import main
import test_whole_app_v5 as whole_tests


class StartupRecoveryTests(TestCase):
    setUp = whole_tests.WholeAppTests.setUp

    def test_codegen_rejects_invalid_helper_import_before_any_file_write(self):
        f = self.flow
        library = self.root / 'backend/lib'
        library.mkdir(parents=True)
        (library / 'store.js').write_text((main.BUNDLE_DIR / 'blueprints/store.js').read_text())
        f.text_turn = Mock(return_value=(True,
            "<<<FILE backend/routes/a.js>>>\nconst {loadTable} = require('../lib/store');\n<<<END FILE>>>\n"
            "<<<FILE frontend/src/new.js>>>\nconst value = 1;\n<<<END FILE>>>"))
        ok, reason = f.codegen_turn('implement new feature', 30, 'A implement', force_files=True)
        self.assertFalse(ok)
        self.assertIn('does not export loadTable', reason)
        self.assertEqual(f.last_codegen_written, [])
        self.assertFalse((self.root / 'frontend/src/new.js').exists())

    def test_functional_failure_after_recovery_resumes_without_claiming_pass(self):
        f = self.flow
        f._unresolved_startup_error = 'TypeError: missing export'
        f.whole_app_startup_repair = Mock(return_value=True)
        f.time_up = lambda: False
        f.record_tests = Mock()
        f.metric = Mock()
        f.run_specs = Mock(return_value=RunSummary(passed=0, total=1, results=[
            TestOutcome('A', False, 'failed', 1, file='A.spec.ts', message='missing control')]))
        self.assertTrue(f.recover_sequential_startup('A'))
        f.run_specs.assert_called_once_with(['A.spec.ts'])
        self.assertFalse(f.test_verdict['A'])
        self.assertEqual(f._unresolved_startup_error, '')
        f.record_tests.assert_called_once_with('A', ['A.spec.ts'], f.run_specs.return_value)

    def test_incomplete_load_never_resumes_and_repairs_are_bounded(self):
        f = self.flow
        f._unresolved_startup_error = 'SyntaxError'
        f.whole_app_startup_repair = Mock(return_value=True)
        f.time_up = lambda: False
        f.metric = Mock()
        f.run_specs = Mock(return_value=RunSummary(error='still cannot load'))
        self.assertFalse(f.recover_sequential_startup('A'))
        self.assertEqual(f.whole_app_startup_repair.call_count, 2)
        self.assertNotIn('A', f.test_verdict)

    def test_no_write_means_no_duplicate_measurement(self):
        f = self.flow
        f._unresolved_startup_error = 'SyntaxError'
        f.whole_app_startup_repair = Mock(return_value=False)
        f.run_specs = Mock()
        self.assertFalse(f.recover_sequential_startup('A'))
        f.run_specs.assert_not_called()


class HelperContractTests(TestCase):
    def test_pristine_export_and_alias_checks_without_executing_app(self):
        sources = {'backend/lib/store.js': (main.BUNDLE_DIR / 'blueprints/store.js').read_text(),
                   'backend/routes/a.js': "const {loadTable: load, read} = require('../lib/store');"}
        errors = helper_import_errors(sources, ['backend/routes/a.js'])
        self.assertEqual(len(errors), 1)
        self.assertIn('does not export loadTable', errors[0])
        sources['backend/routes/a.js'] = "const {read: load} = require('../lib/store.js');"
        self.assertEqual(helper_import_errors(sources, sources), [])
        sources['backend/lib/undo.js'] = "const {onReset, reset} = require('./store');"
        self.assertEqual(helper_import_errors(sources, ['backend/lib/undo.js']), [])
        sources['backend/routes/a.js'] = "const {loadTable} = require('../lib/store');"
        sources['backend/lib/store.js'] = 'module.exports = {loadTable};'
        self.assertEqual(helper_import_errors(sources, sources), [])

    def test_uncertain_syntax_is_left_to_runtime(self):
        sources = {'backend/lib/store.js': (main.BUNDLE_DIR / 'blueprints/store.js').read_text(),
                   'backend/routes/a.js': "const {read = fallback} = require('../lib/store');"}
        self.assertEqual(helper_import_errors(sources, sources), [])
        for source in ("/*\nconst {bogus} = require('../lib/store');\n*/", "const doc = `\nconst {bogus} = require('../lib/store');\n`;", "// const {bogus} = require('../lib/store');"):
            sources['backend/routes/a.js'] = source
            self.assertEqual(helper_import_errors(sources, sources), [])


class RepairBudgetTests(TestCase):
    def test_implementation_notice_is_bounded_and_preserves_tool_results(self):
        data = {'messages': [{'role': 'tool', 'tool_call_id': 'edit1', 'content': 'edit succeeded'}],
                'tools': [{'type': 'function', 'function': {'name': 'edit_file'}}]}
        body = json.dumps(data).encode()
        self.assertEqual(reserve_edit_budget(body, 1, 8, 'implement'), body)
        result = reserve_edit_budget(body, 2, 8, 'implement')
        result = json.loads(reserve_edit_budget(result, 6, 8, 'implement'))
        self.assertEqual(result['messages'][0], data['messages'][0])
        self.assertEqual(result['tools'], data['tools'])
        self.assertEqual(len(result['messages']), 2)
        self.assertIn('Implementation execution budget: 2 upstream requests remain',
                      result['messages'][-1]['content'])
        self.assertEqual(reserve_edit_budget(body, 8, 8, 'implement'), body)

    def test_midpoint_notice_keeps_tools_and_does_not_accumulate(self):
        data = {'messages': [{'role': 'user', 'content': 'fix'}],
                'tools': [{'type': 'function', 'function': {'name': 'edit_file'}}]}
        body = json.dumps(data).encode()
        self.assertEqual(reserve_edit_budget(body, 1, 8), body)
        result = json.loads(reserve_edit_budget(body, 4, 8))
        self.assertEqual(result['tools'], data['tools'])
        self.assertIn('4 upstream requests remain', result['messages'][-1]['content'])
        result = json.loads(reserve_edit_budget(json.dumps(result).encode(), 5, 8))
        self.assertEqual(len(result['messages']), 2)
        self.assertIn('3 upstream requests remain', result['messages'][-1]['content'])
        self.assertIn('Do not guess', result['messages'][-1]['content'])


class RecoveryControlTests(TestCase):
    """Task-neutral recovery sequences; no application-specific fixtures."""

    def setUp(self):
        whole_tests.WholeAppTests.setUp(self)
        f = self.flow
        f.runner = SimpleNamespace(root=self.root, work_dir=self.root / 'prepared')
        f.driver = Mock()
        f.head = Mock(return_value='buildable')
        f.record_tests = Mock()
        f.remember_delivery_checkpoint = Mock()
        f.metric = Mock()
        f.restore_app = Mock()
        f.snapshot_sources = Mock()
        f.sources_text = Mock(return_value='')
        f.repair_requirements = Mock(return_value='')
        f.repair_minimum = Mock(return_value=0)
        f.time_up = Mock(return_value=False)
        f.final_phase_due = Mock(return_value=False)
        f.remaining = Mock(return_value=10000)
        f.regression_checkpoint = Mock()
        f.batch_codegen = Mock(return_value=False)

    @staticmethod
    def summary(passed=0, ids=('A', 'B', 'C')):
        return RunSummary(passed=passed, total=len(ids), results=[
            TestOutcome(n, i < passed, 'passed' if i < passed else 'failed', 1,
                        file=n + '.spec.ts', message='' if i < passed else 'missing control')
            for i, n in enumerate(ids)])

    def queue_with_startup_failure(self):
        f = self.flow
        entered = []
        def implement(node, *args, **kwargs):
            entered.append(node['id'])
            if node['id'] == 'A':
                f._unresolved_startup_error = 'missing module export'
        f.node_cycle = Mock(side_effect=implement)
        f.recover_sequential_startup = Mock(return_value=False)
        return entered

    def test_suite_recovery_resumes_pending_queue_even_when_no_feature_passes(self):
        f = self.flow
        entered = self.queue_with_startup_failure()
        f.run_specs = Mock(side_effect=[RunSummary(error='missing module export'), self.summary()])
        f.last_repair_changed = True
        f.suite_repair_turn = Mock(return_value=('tools', 'fixed import'))
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '1'}):
            f.implement_sequential(self.tree, self.nodes, set())
        self.assertEqual(entered, ['A', 'B', 'C'])
        f.suite_repair_turn.assert_not_called()  # full-suite failures cannot gate the queue
        self.assertEqual(f._unresolved_startup_error, 'missing module export')
        self.assertFalse(getattr(f, 'final_suite_green', False))

    def test_incomplete_suite_does_not_release_the_queue(self):
        f = self.flow
        entered = self.queue_with_startup_failure()
        f.run_specs = Mock(return_value=self.summary(1, ('A',)))
        f.last_repair_changed = True
        f.suite_repair_turn = Mock(return_value=('tools', 'still incomplete'))
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '1'}):
            f.implement_sequential(self.tree, self.nodes, set())
        self.assertEqual(entered, ['A', 'B', 'C'])
        self.assertFalse(getattr(f, 'final_startup_recovered', False))
        f.suite_repair_turn.assert_not_called()

    def test_deferred_recovery_obeys_budget_and_final_phase_guards(self):
        f = self.flow
        f.final_acceptance = Mock()
        for field, value in [('time_up', True), ('wound_down', True),
                             ('final_phase_due', True), ('remaining', 10)]:
            with self.subTest(field=field), patch.object(f, field, Mock(return_value=value)):
                self.assertFalse(f.recover_deferred_startup('A'))
        f.final_acceptance.assert_not_called()

    def test_queue_respects_final_reserve_after_recovery(self):
        f = self.flow
        entered = self.queue_with_startup_failure()
        def recover(node_id):
            f._unresolved_startup_error = ''
            f.final_phase_due.return_value = True
            return True
        f.recover_deferred_startup = Mock(side_effect=recover)
        f.implement_sequential(self.tree, self.nodes, set())
        self.assertEqual(entered, ['A', 'B', 'C'])

    def rollback_flow(self, restored_summary):
        f = self.flow
        f.repair_rounds = 1
        f.run_specs = Mock(side_effect=[self.summary(0, ('A',)),
                                       RunSummary(error='build failed'), restored_summary])
        f.node_repair_turn = Mock(return_value=True)
        return f

    def test_build_regression_restores_and_remeasures_zero_pass_state(self):
        f = self.rollback_flow(self.summary(0, ('A',)))
        self.assertFalse(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        f.restore_app.assert_called_once_with('buildable')
        self.assertEqual(f.run_specs.call_count, 3)
        self.assertEqual(f._unresolved_startup_error, '')
        self.assertEqual(f.record_tests.call_count, 2)
        self.assertEqual(f.record_tests.call_args.args[2].passed, 0)

    def test_failed_rollback_verification_stays_unknown(self):
        f = self.rollback_flow(RunSummary(error='still broken'))
        self.assertIsNone(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        f.restore_app.assert_called_once()
        self.assertEqual(f._unresolved_startup_error, 'still broken')
        f.record_tests.assert_called_once()

    @skipUnless(shutil.which('node') and shutil.which('git'), 'requires Node and Git')
    def test_real_import_breakage_restores_buildable_zero_pass_snapshot(self):
        from arcbench_agent_runtime.gitops import GitClient
        f = self.flow
        front = self.root / 'frontend'
        front.mkdir()
        module = front / 'helper.mjs'
        module.write_text('export default 1;\n')
        entry = front / 'main.mjs'
        entry.write_text("import value from './helper.mjs'; console.log(value);\n")
        git = GitClient(SimpleNamespace(project_dir=self.root), Mock())
        git.ensure_repo()
        f.runtime = SimpleNamespace(git=git)
        f.head = main.Flow.head.__get__(f)
        f.commit = main.Flow.commit.__get__(f)
        f.restore_app = Mock(wraps=main.Flow.restore_app.__get__(f))
        f.repair_rounds = 1
        observed = []
        def measure(*args, **kwargs):
            result = subprocess.run(['node', str(entry)], capture_output=True, text=True, timeout=10)
            observed.append(result.returncode)
            return RunSummary(error=result.stderr) if result.returncode else self.summary(0, ('A',))
        def break_import(*args):
            module.write_text('export const value = 1;\n')
            (front / 'untracked.mjs').write_text('throw Error("partial repair");')
            return True
        f.run_specs = Mock(side_effect=measure)
        f.node_repair_turn = Mock(side_effect=break_import)
        self.assertFalse(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        self.assertEqual(observed, [0, 1, 0])
        f.restore_app.assert_called_once()
        self.assertEqual(module.read_text(), 'export default 1;\n')
        self.assertFalse((front / 'untracked.mjs').exists())
        self.assertEqual(f._unresolved_startup_error, '')

    def test_rollback_without_measurement_budget_cannot_claim_recovery(self):
        f = self.rollback_flow(self.summary(1, ('A',)))
        def repair(*args):
            f.remaining.return_value = 20
            return True
        f.node_repair_turn.side_effect = repair
        self.assertIsNone(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        f.restore_app.assert_called_once()
        self.assertEqual(f.run_specs.call_count, 2)
        self.assertEqual(f._unresolved_startup_error, 'build failed')

    def test_never_restore_an_unmeasured_initial_state(self):
        f = self.flow
        f.repair_rounds = 0
        f.run_specs = Mock(return_value=RunSummary(error='initial build failed'))
        self.assertIsNone(f.acceptance_loop('A', ['A.spec.ts'], time.time() + 1000))
        f.restore_app.assert_not_called()

    def test_one_noop_can_recover_without_remeasuring_unchanged_sources(self):
        f = self.flow
        f.run_specs = Mock(side_effect=[self.summary(), self.summary(3), self.summary(3)])
        changed = iter([False, True])
        def repair(*args, **kwargs):
            f.last_repair_changed = next(changed)
            return 'tools', 'repair'
        f.suite_repair_turn = Mock(side_effect=repair)
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '1', 'OCTOS_FINAL_SUITE_PASSES': '3',
                                      'OCTOS_ARC_FINAL_CONFIRM_RUNS': '2'}):
            f.final_acceptance_passes()
        self.assertEqual(f.run_specs.call_count, 3)  # baseline + green + green confirmation
        self.assertEqual(f.suite_repair_turn.call_count, 2)
        self.assertFalse(f.suite_repair_turn.call_args.kwargs['prefer_codegen'])
        self.assertTrue(f.final_suite_green)
        self.assertTrue(any(c.kwargs.get('reused_measurement') for c in f.metric.call_args_list))

    def test_two_noops_stop_without_duplicate_measurements(self):
        f = self.flow
        f.run_specs = Mock(return_value=self.summary())
        f.last_repair_changed = False
        f.suite_repair_turn = Mock(return_value=('tools', 'no edit'))
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '3', 'OCTOS_FINAL_SUITE_PASSES': '100'}):
            f.final_acceptance_passes()
        f.run_specs.assert_called_once()
        self.assertEqual(f.suite_repair_turn.call_count, 2)
        self.assertFalse(f.final_suite_green)

    def test_progress_before_noop_does_not_discard_the_changed_approach(self):
        f = self.flow
        f.run_specs = Mock(side_effect=[self.summary(1), self.summary(2), self.summary(3), self.summary(3)])
        changes = iter([True, False, True])
        def repair(*args, **kwargs):
            f.last_repair_changed = next(changes)
            return 'tools', 'repair'
        f.suite_repair_turn = Mock(side_effect=repair)
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '3', 'OCTOS_FINAL_SUITE_PASSES': '3',
                                      'OCTOS_ARC_FINAL_CONFIRM_RUNS': '2'}):
            f.final_acceptance_passes()
        self.assertEqual(f.run_specs.call_count, 4)
        self.assertEqual(f.suite_repair_turn.call_count, 3)
        self.assertTrue(f.final_suite_green)

    def test_explicit_pass_limit_still_stops_after_one_noop(self):
        f = self.flow
        f.run_specs = Mock(return_value=self.summary())
        f.last_repair_changed = False
        f.suite_repair_turn = Mock(return_value=('tools', 'no edit'))
        with patch.dict('os.environ', {'OCTOS_FINAL_SUITE_PASSES': '1'}):
            f.final_acceptance_passes()
        f.run_specs.assert_called_once()
        f.suite_repair_turn.assert_not_called()  # default final pass observes without repair

    def test_source_changes_between_passes_invalidate_cached_measurement(self):
        f = self.flow
        f.test_verdict = {'A': False}
        summary = self.summary()
        f.app_source_digest = Mock(side_effect=['changed'])
        def final(**kwargs):
            f.final_repair_no_change = True
            f._final_retry_measurement = (summary, 'old')
        f.final_acceptance = Mock(side_effect=final)
        with patch.dict('os.environ', {'OCTOS_FINAL_SUITE_PASSES': '3'}):
            f.final_acceptance_passes()
        self.assertEqual(f.final_acceptance.call_count, 2)
        self.assertTrue(all(not c.kwargs for c in f.final_acceptance.call_args_list))
