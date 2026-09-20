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
        f.final_acceptance.assert_called_once()

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
        self.assertEqual(observed, [(4096, 'none'), (0, 'none'), (8192, 'none')])
        self.assertEqual(proxy.codegen_max_tokens, 77)
        with patch.dict('os.environ', {'OCTOS_ARC_REPAIR_MAX_TOKENS': '4096'}):
            f.text_turn('', 30, 'A repair')
        self.assertEqual(observed[-1][0], 4096)
        f.n_nodes = 125
        with patch.dict('os.environ', {}, clear=True):
            f.text_turn('', 30, 'application design')
        self.assertEqual(observed[-1][0], 16000)

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

    def test_measurement_reserve_adapts_to_observed_suite_cost(self):
        f = self.flow
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(f.final_measurement_reserve(), 120)
            f.last_suite_seconds = 200
            self.assertEqual(f.final_measurement_reserve(), 260)
        with patch.dict('os.environ', {'OCTOS_ARC_FINAL_MEASUREMENT_SECONDS': '180'}):
            self.assertEqual(f.final_measurement_reserve(), 180)
