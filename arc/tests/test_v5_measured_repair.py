"""Repair admission, complete verdicts and bounded request contracts."""
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import main as m
from acceptance import RunSummary, TestOutcome
from web_stack import REACT_CONTRACT
import test_whole_app_v5 as fixtures


class MeasuredRepairTests(TestCase):
    setUp = fixtures.WholeAppTests.setUp

    def summary(self):
        return RunSummary(passed=2, total=3, results=[
            TestOutcome(n, n != 'C', 'passed' if n != 'C' else 'failed', 1, file=f'{n}.spec.ts')
            for n in ('A', 'B', 'C')])

    def test_all_passed_rejects_infrastructure_errors(self):
        for extra in ({'error': 'build'}, {'load_errors': ['import']}, {'killed': True}):
            self.assertFalse(RunSummary(passed=1, total=1, **extra).all_passed)

    def test_complete_suite_requires_every_relative_spec_and_terminal_result(self):
        f = self.flow
        specs = ['A.spec.ts', 'B.spec.ts', 'C.spec.ts']
        self.assertTrue(f.suite_is_measured(self.summary(), specs))
        for change in ('missing', 'skipped', 'load'):
            s = self.summary()
            if change == 'missing':
                s.results[-1].file = 'A.spec.ts'
            elif change == 'skipped':
                s.results[-1].status = 'skipped'
            else:
                s.load_errors = ['missing import']
            self.assertFalse(f.suite_is_measured(s, specs))
        self.assertFalse(f.suite_is_measured(self.summary(), ['subdir/A.spec.ts']))

    def test_missing_node_is_not_marked_passed_by_absence_from_failure_group(self):
        f = self.flow
        f.record_tests = Mock()
        s = self.summary()
        s.results = s.results[:2]
        s.total = 2
        f.record_full_suite(s, {})
        self.assertEqual(f.test_verdict, {'A': True, 'B': True, 'C': None})

    def test_fatal_response_still_restores_tests_and_records_turn(self):
        f = self.flow
        f.driver = SimpleNamespace(run=lambda *a: (False, 'HTTP 402 insufficient_balance'))
        f.restore_protected = Mock(return_value=[])
        f.metric = Mock()
        with self.assertRaises(m.PermanentProviderError):
            f.turn('prompt', 60, 'repair')
        f.restore_protected.assert_called_once()
        f.metric.assert_called_once()
        self.assertFalse(f.metric.call_args.kwargs['ok'])

    def test_existing_failure_is_not_retested_before_first_repair(self):
        f = self.flow
        f.head = lambda: 'before'
        f.repair_rounds = 0
        f.record_tests = Mock()
        f.run_specs = Mock()
        self.assertFalse(f.acceptance_loop('C', ['C.spec.ts'], time.time() + 60,
                                          initial_summary=RunSummary(passed=0, total=1)))
        f.run_specs.assert_not_called()

    def test_local_token_guard_winds_down_without_skipping_final_measurement(self):
        f = self.flow
        f.driver = SimpleNamespace(run=lambda *a: (False, 'HTTP 402 local_token_budget_exhausted'))
        f.restore_protected = Mock(return_value=[])
        f.metric = Mock()
        ok, _ = f.turn('prompt', 60, 'repair')
        self.assertFalse(ok)
        self.assertTrue(f.local_budget_exhausted)
        self.assertTrue(m.Flow.wound_down(f))
        f.final_acceptance = Mock()
        f.driver = None
        f.remaining = lambda: 180
        f.final_acceptance_passes()
        f.final_acceptance.assert_not_called()  # estimated full suite exceeds remaining measurement budget

    def test_large_unentered_suite_keeps_a_bounded_delivery_checkpoint(self):
        f = self.flow
        for i in range(4, 34):
            name = f'N{i}'
            (f.tests_dir / f'{name}.spec.ts').write_text('test("pending", () => {});')
            f.spec_map[name] = [f'{name}.spec.ts']
        f.test_verdict = {'A': True, 'B': True}
        f.runner = SimpleNamespace(timeout_ms=30000)
        f.remaining = Mock(return_value=350)
        f.run_specs = Mock(return_value=RunSummary(passed=2, total=2, results=[
            TestOutcome(n, True, 'passed', 1, file=f'{n}.spec.ts') for n in ('A', 'B')]))
        f.record_tests = Mock()
        f.metric = Mock()
        f.final_acceptance = Mock()
        f.final_acceptance_passes()
        f.run_specs.assert_called_once()
        self.assertEqual(set(f.run_specs.call_args.args[0]), {'A.spec.ts', 'B.spec.ts'})
        f.final_acceptance.assert_not_called()
        self.assertTrue(f.test_verdict['A'] and f.test_verdict['B'])

    def test_timeout_only_full_suite_preserves_earlier_node_verdicts(self):
        f = self.flow
        f.run_specs = Mock(return_value=RunSummary(error='playwright run exceeded 300s'))
        f.metric = Mock()
        f.test_verdict = {'A': True, 'B': False, 'C': None}
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '0'}):
            f.final_acceptance()
        self.assertEqual(f.test_verdict, {'A': True, 'B': False, 'C': None})

    def test_initial_phase_caps_leave_generation_and_thinking_unchanged(self):
        f = self.flow
        proxy = SimpleNamespace(mode='none', codegen_max_tokens=77)
        f.llm_proxy = proxy
        f.driver = SimpleNamespace(without_tools=nullcontext)
        observed = []
        f.turn = lambda *a, **k: observed.append((proxy.codegen_max_tokens, f.base_reasoning_mode)) or (True, '')
        f.base_reasoning_mode = 'none'
        with patch.dict('os.environ', {}, clear=True):
            for label in ('application design', 'A implement', 'A repair'):
                f.text_turn('', 30, label)
        self.assertEqual(observed, [(32768, 'none'), (0, 'none'), (32768, 'medium')])
        self.assertEqual(proxy.codegen_max_tokens, 77)
        with patch.dict('os.environ', {'OCTOS_ARC_REPAIR_MAX_TOKENS': '4096'}):
            f.text_turn('', 30, 'A repair')
        self.assertEqual(observed[-1][0], 4096)
        f.n_nodes = 125
        with patch.dict('os.environ', {}, clear=True):
            f.text_turn('', 30, 'application design')
        self.assertEqual(observed[-1][0], 32768)  # 256 tokens per leaf, capped

    def test_reasoning_off_for_all_implementation_by_default(self):
        f = self.flow
        proxy = SimpleNamespace(mode='low', codegen_max_tokens=0)
        f.llm_proxy = proxy
        f.driver = SimpleNamespace(without_tools=nullcontext)
        f.base_reasoning_mode = 'low'
        seen = []
        f.turn = lambda *a, **kw: seen.append(f.base_reasoning_mode) or (True, '')
        with patch.dict('os.environ', {}, clear=True):
            f.text_turn('', 30, 'A implement')
            f.text_turn('', 30, 'A repair')
        self.assertEqual(seen, ['none', 'low'])
        self.assertEqual(f.base_reasoning_mode, 'low')

    def test_contracts_describe_generic_invariants_not_fixture_values(self):
        for invariant in ('<Outlet/>', 'opacity:0 alone', 'onOpenChange(false)', 'owning record ID'):
            self.assertIn(invariant, REACT_CONTRACT)
        for fixture in ('note-archive', 'Garden tasks', 'REQ-2.7'):
            self.assertNotIn(fixture, REACT_CONTRACT)

    def test_unknown_full_suite_preserves_unknown_counts_and_no_checkpoint(self):
        f = self.flow
        f.run_specs = Mock(return_value=RunSummary(error='build failed'))
        f.metric = Mock()
        f.remember_delivery_checkpoint = Mock()
        f.record_tests = Mock()
        f.head = Mock()
        f.test_verdict = {'A': True, 'B': True, 'C': True}
        with patch.dict('os.environ', {'OCTOS_FINAL_REPAIR_ROUNDS': '0'}):
            f.final_acceptance()
        self.assertEqual(f.test_verdict, {'A': None, 'B': None, 'C': None})
        f.head.assert_not_called()
        f.commit.assert_not_called()
        self.assertEqual(f.metric.call_args.kwargs['total'], 0)
        self.assertEqual(f.metric.call_args.kwargs['verdict'], 'unknown')

    def test_rehearsal_never_uses_negative_time_for_a_model_repair(self):
        f = self.flow
        f.remaining = lambda: -1
        server = SimpleNamespace(build=lambda: 'build failed', stop=Mock())
        f.app_server = lambda **kw: server
        f.turn = Mock()
        self.assertFalse(f.rehearsal())
        f.turn.assert_not_called()

    def test_early_system_check_keeps_review_and_final_repair_time(self):
        f = self.flow
        f.derived_as_specs = True
        f.final_measurement_reserve = Mock(return_value=120)
        f.repair_minimum = Mock(return_value=60)
        f.remaining = Mock(return_value=239)
        f.rehearsal = Mock(return_value=True)
        f.metric = Mock()
        f.pre_review_derived_system_check()
        f.rehearsal.assert_not_called()
        f.remaining.return_value = 500
        f.pre_review_derived_system_check()
        f.rehearsal.assert_called_once_with(preserve_seconds=180, restore_on_failure=False)

    def test_early_rehearsal_repair_turn_cannot_borrow_preserved_time(self):
        f = self.flow
        f.remaining = lambda: 240
        f.repair_minimum = lambda: 60
        f.node_timeout = 1200
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: 'build failed', stop=Mock())
        f.turn = Mock()
        f.commit = Mock()
        f.last_turn_changed = False
        f.restore_startable_commit = Mock(return_value=False)
        f.whole_app_startup_repair = Mock(return_value=False)
        f.derived_as_specs = True
        self.assertFalse(f.rehearsal(preserve_seconds=180, restore_on_failure=False))
        f.turn.assert_not_called()
        f.remaining = lambda: 300
        self.assertFalse(f.rehearsal(preserve_seconds=180, restore_on_failure=False))
        self.assertAlmostEqual(f.turn.call_args.args[1], 120, delta=1)
        self.assertIn('do not read, search, run, or modify generated tests', f.turn.call_args.args[0])
        f.restore_startable_commit.assert_not_called()

    def test_rehearsal_continues_past_three_distinct_source_errors(self):
        f = self.flow
        version = [0]
        f.remaining = Mock(return_value=3600)
        f.repair_minimum = Mock(return_value=60)
        f.wound_down = Mock(return_value=False)
        f.app_source_digest = Mock(side_effect=lambda: str(version[0]))
        f.measure_rehearsal_server = Mock(side_effect=[
            'frontend/src/A.jsx: SyntaxError', 'frontend/src/B.jsx: SyntaxError',
            'backend/routes/auth.js: ReferenceError', 'Undefined frontend bindings', None])
        f.repair_spa_entry_from_blueprint = Mock(return_value=False)
        f.restore_startable_commit = Mock(return_value=False)
        f.test_verdict = {'A': True}
        f.commit = Mock()

        def repair(*args, **kwargs):
            version[0] += 1
            f.last_turn_changed = True
            return True, 'edited'

        f.turn = Mock(side_effect=repair)
        self.assertTrue(f.rehearsal())
        self.assertEqual(f.turn.call_count, 4)
        self.assertEqual(f.measure_rehearsal_server.call_count, 5)
        self.assertEqual(f.turn.call_args.kwargs['request_budget'], 32)
        self.assertEqual(f.test_verdict, {'A': None})

    def test_rehearsal_stops_after_action_limit_even_when_source_keeps_changing(self):
        f = self.flow
        version = [0]
        f.remaining = Mock(return_value=3600)
        f.repair_minimum = Mock(return_value=60)
        f.wound_down = Mock(return_value=False)
        f.app_source_digest = Mock(side_effect=lambda: str(version[0]))
        f.measure_rehearsal_server = Mock(return_value='frontend/src/A.jsx: SyntaxError')
        f.repair_spa_entry_from_blueprint = Mock(return_value=False)
        f.restore_startable_commit = Mock(return_value=False)
        f.commit = Mock()

        def repair(*args, **kwargs):
            version[0] += 1
            f.last_turn_changed = True
            return True, 'edited'

        f.turn = Mock(side_effect=repair)
        with patch.dict('os.environ', {'OCTOS_ARC_REHEARSAL_REPAIR_ACTIONS': '4'}):
            self.assertFalse(f.rehearsal())
        self.assertEqual(f.turn.call_count, 4)
        self.assertEqual(f.measure_rehearsal_server.call_count, 5)

    def test_rehearsal_time_limit_zero_admits_no_repair(self):
        f = self.flow
        f.remaining = Mock(return_value=3600)
        f.measure_rehearsal_server = Mock(return_value='frontend/src/A.jsx: SyntaxError')
        f.repair_spa_entry_from_blueprint = Mock(return_value=False)
        f.restore_startable_commit = Mock(return_value=False)
        f.turn = Mock()
        with patch.dict('os.environ', {'OCTOS_ARC_REHEARSAL_REPAIR_SECONDS': '0'}):
            self.assertFalse(f.rehearsal())
        f.turn.assert_not_called()
        f.repair_spa_entry_from_blueprint.assert_not_called()

    def test_blueprint_repair_invalidates_previous_acceptance_verdicts(self):
        f = self.flow
        f.measure_rehearsal_server = Mock(side_effect=[
            'SPA entry frontend/dist/index.html is missing', None])
        f.repair_spa_entry_from_blueprint = Mock(return_value=True)
        f.test_verdict = {'A': True, 'B': False}
        self.assertTrue(f.rehearsal())
        self.assertEqual(f.test_verdict, {'A': None, 'B': None})

    def test_rehearsal_regenerates_a_stalled_source_then_remeasures(self):
        f = self.flow
        version = [0]
        f.remaining = Mock(return_value=3600)
        f.repair_minimum = Mock(return_value=60)
        f.wound_down = Mock(return_value=False)
        f.app_source_digest = Mock(side_effect=lambda: str(version[0]))
        f.measure_rehearsal_server = Mock(side_effect=['Undefined frontend bindings'] * 2 + [None])
        f.repair_spa_entry_from_blueprint = Mock(return_value=False)
        f.turn = Mock(return_value=(False, 'local_turn_budget_exhausted'))
        f.last_turn_changed = False
        f.commit = Mock()
        f.test_verdict = {'A': True}

        def regenerate(*args, **kwargs):
            version[0] += 1
            return True

        f.whole_app_startup_repair = Mock(side_effect=regenerate)
        self.assertTrue(f.rehearsal())
        f.whole_app_startup_repair.assert_called_once()
        self.assertEqual(f.turn.call_count, 1)
        self.assertEqual(f.test_verdict, {'A': None})

    def test_rehearsal_stops_after_tools_and_regeneration_make_no_progress(self):
        f = self.flow
        f.remaining = Mock(return_value=3600)
        f.repair_minimum = Mock(return_value=60)
        f.wound_down = Mock(return_value=False)
        f.app_source_digest = Mock(return_value='unchanged')
        f.measure_rehearsal_server = Mock(return_value='Undefined frontend bindings')
        f.repair_spa_entry_from_blueprint = Mock(return_value=False)
        f.turn = Mock(return_value=(False, 'no edit'))
        f.last_turn_changed = False
        f.commit = Mock()
        f.whole_app_startup_repair = Mock(return_value=False)
        f.restore_startable_commit = Mock(return_value=False)
        self.assertFalse(f.rehearsal())
        self.assertEqual(f.measure_rehearsal_server.call_count, 4)
        self.assertEqual(f.turn.call_count, 2)
        f.whole_app_startup_repair.assert_called_once()

    def test_source_changed_by_final_rehearsal_reopens_one_measured_suite(self):
        f = self.flow
        f.runner = Mock()
        f.test_verdict = {'A': True}
        f._final_suite_attempted = True
        f.app_source_digest = Mock(return_value='after-repair')
        f.final_acceptance_passes = Mock()
        f.rehearsal = Mock(return_value=True)
        self.assertTrue(f.remeasure_after_rehearsal('before-repair', True))
        self.assertFalse(f._final_suite_attempted)
        self.assertIsNone(f.test_verdict['A'])
        f.final_acceptance_passes.assert_called_once()
        f.rehearsal.assert_not_called()
        f._final_suite_attempted = True
        self.assertTrue(f.remeasure_after_rehearsal('after-repair', True))
        self.assertTrue(f._final_suite_attempted)
        f.rehearsal.assert_not_called()

    def test_final_suite_source_repair_must_pass_another_startup_check(self):
        f = self.flow
        f.runner = Mock()
        f.test_verdict = {'A': None}
        f.app_source_digest = Mock(side_effect=['same', 'changed'])
        f.final_acceptance_passes = Mock()
        f.rehearsal = Mock(return_value=False)
        self.assertFalse(f.remeasure_after_rehearsal('same', True))
        f.final_acceptance_passes.assert_called_once()
        f.rehearsal.assert_called_once_with(repair_on_failure=False)

    def test_final_suite_reverting_startup_repair_still_needs_startup_check(self):
        f = self.flow
        f.runner = Mock()
        f.test_verdict = {'A': True}
        f.app_source_digest = Mock(side_effect=['after-startup', 'before-startup'])
        f.final_acceptance_passes = Mock()
        f.rehearsal = Mock(return_value=False)
        self.assertFalse(f.remeasure_after_rehearsal('before-startup', True))
        f.final_acceptance_passes.assert_called_once()
        f.rehearsal.assert_called_once_with(repair_on_failure=False)

    def test_final_startup_check_does_not_launch_another_repair_turn(self):
        f = self.flow
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: 'build failed', stop=Mock())
        f.rehearsal_browser_error = Mock()
        f.turn = Mock()
        f.restore_startable_commit = Mock(return_value=False)
        self.assertFalse(f.rehearsal(repair_on_failure=False))
        f.turn.assert_not_called()
        f.restore_startable_commit.assert_called_once()

    def test_failed_rehearsal_ships_the_last_startable_commit_instead_of_as_is(self):
        f = self.flow
        f.remaining = lambda: -1
        f.last_startable_sha = 'good1234'
        f.rehearsal_browser_error = Mock(return_value=None)
        f.head = Mock(return_value='broken99')
        f.restore_app = Mock()
        f.runtime = SimpleNamespace(git=SimpleNamespace(
            run=Mock(return_value=SimpleNamespace(returncode=0, stdout=''))))
        f.commit = Mock()
        f.test_verdict = {'A': True}
        builds = iter(['start failed', 'start failed', None])
        server = SimpleNamespace(build=lambda: next(builds), start=lambda: None, stop=Mock())
        f.app_server = lambda **kw: server
        f.turn = Mock()
        self.assertTrue(f.rehearsal())
        f.restore_app.assert_called_once_with('good1234')
        self.assertEqual(f.test_verdict, {'A': None})
        f.turn.assert_not_called()

    def test_transient_rehearsal_failure_keeps_the_current_tree(self):
        f = self.flow
        f.remaining = lambda: -1
        f.last_startable_sha = 'good1234'
        f.rehearsal_browser_error = Mock(return_value=None)
        f.head = Mock(return_value='current9')
        f.restore_app = Mock()
        f.runtime = SimpleNamespace(git=SimpleNamespace(
            run=Mock(return_value=SimpleNamespace(returncode=0, stdout=''))))
        builds = iter(['port busy', None])
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: next(builds), start=lambda: None, stop=Mock())
        f.turn = Mock()
        self.assertTrue(f.rehearsal())
        f.restore_app.assert_not_called()

    def test_startable_commit_is_recorded_only_when_the_tree_equals_head(self):
        f = self.flow
        f.head = Mock(return_value='abc')
        f.app_source_digest = Mock(return_value='source-abc')
        f.note_startable_commit(lambda args: SimpleNamespace(returncode=0, stdout=' M frontend/src/App.jsx'), 'passed')
        self.assertIsNone(getattr(f, 'last_startable_sha', None))
        f.note_startable_commit(lambda args: SimpleNamespace(returncode=0, stdout=''), 'unknown')
        self.assertIsNone(getattr(f, 'last_startable_sha', None))
        f.note_startable_commit(lambda args: SimpleNamespace(returncode=0, stdout=''), 'passed')
        self.assertEqual(f.last_startable_sha, 'abc')
        self.assertEqual(f.last_startable_source_hash, 'source-abc')
        f.head.return_value = 'changed-head'
        f.note_startable_commit(lambda args: SimpleNamespace(returncode=0, stdout=''),
                                'passed', 'earlier-source')
        self.assertEqual(f.last_startable_sha, 'abc')

    def test_rehearsal_measurement_promotes_only_a_clean_browser_verified_head(self):
        f = self.flow
        f.head = Mock(return_value='verified-head')
        f.app_source_digest = Mock(return_value='verified-source')
        f.runtime = SimpleNamespace(git=SimpleNamespace(run=Mock(
            return_value=SimpleNamespace(returncode=0, stdout=''))))
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: None, start=lambda: None, stop=Mock())
        f.rehearsal_browser_error = Mock(return_value=None)
        self.assertIsNone(f.measure_rehearsal_server())
        self.assertEqual(f.last_startable_sha, 'verified-head')
        f.runtime.git.run.return_value = SimpleNamespace(returncode=0, stdout=' M frontend/src/App.jsx')
        f.head.return_value = 'dirty-head'
        self.assertIsNone(f.measure_rehearsal_server())
        self.assertEqual(f.last_startable_sha, 'verified-head')

    def test_failed_restore_candidate_returns_to_current_commit_without_committing(self):
        f = self.flow
        f.last_startable_sha = 'good1234'
        f.head = Mock(return_value='current9')
        f.runtime = SimpleNamespace(git=SimpleNamespace(
            run=Mock(return_value=SimpleNamespace(returncode=0, stdout=''))))
        f.restore_app = Mock()
        f.commit = Mock()
        f.test_verdict = {'A': True}
        builds = iter(['broken app', 'broken candidate'])
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: next(builds), start=lambda: None, stop=Mock())
        self.assertFalse(f.restore_startable_commit())
        self.assertEqual([call.args[0] for call in f.restore_app.call_args_list], ['good1234', 'current9'])
        f.commit.assert_not_called()
        self.assertEqual(f.test_verdict, {'A': True})

    def test_uncommitted_app_is_never_destroyed_by_rollback(self):
        f = self.flow
        f.last_startable_sha = 'good1234'
        f.head = Mock(return_value='current9')
        f.runtime = SimpleNamespace(git=SimpleNamespace(
            run=Mock(return_value=SimpleNamespace(returncode=0, stdout=' M frontend/src/App.jsx'))))
        f.restore_app = Mock()
        f.app_server = lambda **kw: SimpleNamespace(build=lambda: 'build failed', stop=Mock())
        self.assertFalse(f.restore_startable_commit())
        f.restore_app.assert_not_called()

    def test_measurement_reserve_adapts_to_observed_suite_cost(self):
        f = self.flow
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(f.final_measurement_reserve(), 120)
            f.last_suite_seconds = 200
            self.assertEqual(f.final_measurement_reserve(), 260)
        with patch.dict('os.environ', {'OCTOS_ARC_FINAL_MEASUREMENT_SECONDS': '180'}):
            self.assertEqual(f.final_measurement_reserve(), 180)
