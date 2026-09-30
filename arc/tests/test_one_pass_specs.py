"""One-pass derived-spec planning keeps rejection as explicit coverage debt."""
import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from main import Flow, OctosDriver
from obligation_planning import prepare_obligations, reviewed_obligations_intact


class OnePassObligations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.flow = Flow(argparse.Namespace(web_port=3000), root, root)
        self.flow.metric = Mock()
        self.flow.snapshot_protected = Mock()
        self.flow.start_derived_designs = Mock()
        self.flow.remaining = Mock(return_value=10000)
        self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.wound_down = Mock(return_value=False)
        self.flow.review_budget_spent = Mock(return_value=False)
        self.flow.derived_preflight_tokens_spent = Mock(return_value=False)
        self.flow.codegen_context_chars = Mock(return_value=200000)
        self.flow.text_turn = Mock()

    def test_simple_source_compiles_without_model_and_still_needs_case_audit(self):
        leaf = {'id': 'A', 'description': 'The item shows Done.'}
        self.flow.requirement_tree = {'id': 'ROOT', 'description': 'Records are visible.',
                                      'children': [leaf]}
        prepare_obligations(self.flow, [leaf])
        self.flow.text_turn.assert_not_called()
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'source_grounded')
        self.assertEqual(self.flow.derived_obligation_status['A']['method'], 'mechanical')
        self.assertTrue(reviewed_obligations_intact(self.flow, 'A'))
        self.assertEqual(len(self.flow.derived_obligations), 2)

    def test_complex_source_uses_one_model_turn_without_retry(self):
        leaf = {'id': 'A', 'description': 'If saving fails, the saved item remains unchanged.'}
        root = {'id': 'ROOT', 'description': 'Records are visible.', 'children': [leaf]}
        self.flow.requirement_tree = root
        reply = json.dumps({'obligations': [
            {'requirement_id': 'ROOT', 'applies_to': ['A'], 'quote': root['description'],
             'branch': 'success', 'outcome': root['description']},
            {'requirement_id': 'A', 'applies_to': ['A'], 'quote': leaf['description'],
             'branch': 'rejection', 'outcome': leaf['description']}], 'gaps': []})
        self.flow.text_turn.return_value = (True, reply)
        prepare_obligations(self.flow, [leaf])
        prepare_obligations(self.flow, [leaf])
        self.assertEqual(self.flow.text_turn.call_count, 1)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'source_grounded')
        self.assertEqual(self.flow.derived_obligation_status['A']['method'], 'model_once')

    def test_failed_complex_source_stays_incomplete_without_retry(self):
        leaf = {'id': 'A', 'description': 'If saving fails, the saved item remains unchanged.'}
        self.flow.requirement_tree = {'id': 'ROOT', 'description': 'Records are visible.',
                                      'children': [leaf]}
        self.flow.text_turn.return_value = (False, 'provider unavailable')
        prepare_obligations(self.flow, [leaf])
        prepare_obligations(self.flow, [leaf])
        self.assertEqual(self.flow.text_turn.call_count, 1)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.assertFalse(reviewed_obligations_intact(self.flow, 'A'))

    def test_negative_declarative_source_is_not_mechanically_a_success(self):
        for description in ('Only owners can delete records.', 'Saving fails with HTTP 403.',
                            'A deleted item cannot be opened.'):
            with self.subTest(description=description):
                leaf = {'id': 'A', 'description': description}
                self.flow.requirement_tree = leaf
                self.flow.derived_obligations = []
                self.flow.derived_obligation_status = {}
                self.flow.text_turn.reset_mock()
                self.flow.text_turn.return_value = (False, 'provider unavailable')
                prepare_obligations(self.flow, [leaf])
                self.flow.text_turn.assert_called_once()
                self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')

    def test_obligation_artifacts_follow_the_selected_suite_directory(self):
        leaf = {'id': 'A', 'description': 'The item shows Done.'}
        self.flow.requirement_tree = leaf
        self.flow.derived_tests_dir = self.flow.output_dir / 'derived-tests-owned'
        prepare_obligations(self.flow, [leaf])
        self.assertTrue((self.flow.derived_tests_dir / 'review/obligations.json').is_file())
        self.assertFalse((self.flow.output_dir / 'derived-tests').exists())

    def test_omitted_source_clause_remains_explicit_debt(self):
        leaf = {'id': 'A', 'description': ('If saving fails, the saved item remains unchanged. '
                                          'After refresh, the same item is visible.')}
        root = {'id': 'ROOT', 'description': 'Records are visible.', 'children': [leaf]}
        self.flow.requirement_tree = root
        self.flow.text_turn.return_value = (True, json.dumps({'obligations': [
            {'requirement_id': 'ROOT', 'applies_to': ['A'], 'quote': root['description'],
             'branch': 'success', 'outcome': root['description']},
            {'requirement_id': 'A', 'applies_to': ['A'],
             'quote': 'If saving fails, the saved item remains unchanged.',
             'branch': 'rejection', 'outcome': 'If saving fails, the saved item remains unchanged.'}],
            'gaps': []}))
        prepare_obligations(self.flow, [leaf])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.assertTrue(any('source clause not represented' in issue
                            for issue in self.flow.derived_obligation_status['A']['errors']))


class OnePassRequestLimits(unittest.TestCase):
    def test_driver_single_attempt_does_not_replay_a_provider_failure(self):
        driver = object.__new__(OctosDriver)
        driver.mode, driver.session_scope = 'stdio', 'turn'
        driver.tools_disabled = True
        driver.retry_attempts = 1
        driver.progress_deadline = None
        driver._run_stdio = Mock(return_value=(False, 'HTTP 503 temporarily unavailable'))
        driver._run_with_heartbeat = lambda run: run()
        driver.close = Mock()
        with patch('main.time.sleep'):
            self.assertFalse(driver.run('proposal', 300)[0])
        driver._run_stdio.assert_called_once()

    def test_serial_spec_request_restores_transport_policy_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
            flow.llm_proxy = SimpleNamespace(mode='none', no_tools=False, system_override=None,
                                             codegen_max_tokens=0, single_attempt=False)
            driver = object.__new__(OctosDriver)
            driver.retry_attempts = 3
            driver.tools_disabled = False
            driver.close = Mock()
            flow.driver = driver
            def turn(*args, **kwargs):
                self.assertTrue(flow.llm_proxy.single_attempt)
                self.assertEqual(driver.retry_attempts, 1)
                self.assertEqual(kwargs['request_budget'], 1)
                return False, 'HTTP 503 temporarily unavailable'
            flow.turn = Mock(side_effect=turn)
            self.assertFalse(flow.text_turn('proposal', 300, 'derived scenario review')[0])
            self.assertFalse(flow.llm_proxy.single_attempt)
            self.assertEqual(driver.retry_attempts, 3)


if __name__ == '__main__':
    unittest.main()
