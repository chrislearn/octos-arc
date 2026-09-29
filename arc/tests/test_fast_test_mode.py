"""Fast generated-test admission and its buildable-repair boundary."""
import json
import argparse
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from main import Flow
from scenario_review import review_targets, validate_proposal
from scenario_tests import Fixtures


def result(ok=False, *, error=None):
    rows = [] if error else [TestOutcome(title='A [model]', ok=ok,
                                         status='passed' if ok else 'failed',
                                         duration_ms=1, file='A.spec.ts', message='missing button')]
    return RunSummary(results=rows, total=len(rows), passed=sum(row.ok for row in rows), error=error)


class FastModeTests(unittest.TestCase):
    def test_default_and_full_switch(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(Flow.fast_test_mode())
        with patch.dict(os.environ, {'OCTOS_ARC_TEST_MODE': 'full'}):
            self.assertFalse(Flow.fast_test_mode())
        with patch.dict(os.environ, {'OCTOS_ARC_TEST_MODE': 'fast'}):
            self.assertTrue(Flow.fast_test_mode())

    def test_structural_case_enters_skip_review_without_model_request(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'OCTOS_ARC_TEST_MODE': 'fast'}):
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_tests_dir = root / 'tests'
            flow.derived_tests_dir.mkdir()
            flow.tests_dir = flow.derived_tests_dir
            flow.derived_as_specs = True
            node = {'id': 'A', 'name': 'Create',
                    'description': 'A created record shows “Done” after “Create”.',
                    'scenarios': [{'name': 'Create', 'steps': [
                        {'keyword': 'WHEN', 'content': 'Click “Create”.'},
                        {'keyword': 'THEN', 'content': 'A created record shows “Done”.'}]}]}
            flow.derived_nodes = [node]
            flow.derived_case_reviews = {}
            target = review_targets([node], Fixtures(), include_all=True)[0]
            case = validate_proposal({'confidence': 1, 'steps': [
                {'op': 'click', 'target': 'Create'}, {'op': 'expect_visible', 'target': 'Done'}]},
                target, Fixtures())
            path = flow.derived_tests_dir / 'A.spec.ts'
            path.write_text(case)
            flow.text_turn = Mock(side_effect=AssertionError('pre-run model review must be skipped'))
            flow.metric = Mock()
            flow.review_derived_cases({'A'})
            title = target['title'] + ' [model]'
            self.assertEqual(flow.derived_case_reviews[('A', title)]['status'], 'skip_review')
            self.assertTrue(flow.trusted_derived_case('A', title))
            path.write_text(case + '\n// changed\n')
            self.assertFalse(flow.trusted_derived_case('A', title))

    def flow(self, root, repaired):
        source = "test('A [model]', async () => { expect(true).toBe(true); });\n"
        (root / 'A.spec.ts').write_text(source)
        policy = Mock()
        flow = SimpleNamespace(
            tests_dir=root, requirement_nodes={'A': {'id': 'A', 'description': 'Show a button'}},
            requirement_tree={}, node_timeout=300, smoke_port=3100, web_port=3000,
            derived_has_runnable_cases=Mock(return_value=True),
            derived_review_needed=Mock(return_value=False),
            run_specs=Mock(return_value=repaired), suite_is_measured=Mock(side_effect=[True, not bool(repaired.error)]),
            record_tests=Mock(), commit=Mock(), metric=Mock(), snapshot_protected=Mock(),
            generated_test_policy=Mock(return_value=policy), trusted_derived_case=Mock(return_value=True),
            repair_requirements=Mock(return_value='Show a button'), sources_text=Mock(return_value='app source'),
            codegen_context_chars=Mock(return_value=100000),
            oracle_review_turn=Mock(return_value=(True, json.dumps({
                'verdict': 'app_error', 'evidence': 'The application omits the required button.',
                'reason_code': None, 'requirement_quote': '', 'test_quote': '', 'scenarios': []}))),
            remaining=Mock(return_value=1000), final_phase_reserve=Mock(return_value=0),
            repair_minimum=Mock(return_value=10), wound_down=Mock(return_value=False),
            head=Mock(return_value='base'), node_repair_turn=Mock(return_value=True),
            app_source_digest=Mock(return_value='before'),
            app_repair_prompt=Mock(return_value='repair'), corrections_text=Mock(return_value=''),
            repair_test_location=Mock(return_value='A.spec.ts'), restore_app=Mock(),
            flag_derived_spec_dispute=Mock(), pending_corrections=[])
        return flow, policy

    def test_systemic_error_after_one_repair_restores_measured_source(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, policy = self.flow(Path(temp), result(error='frontend build failed'))
            verdict = Flow.fast_derived_acceptance(flow, 'A', ['A.spec.ts'], time.time() + 500, result())
            self.assertIsNone(verdict)
            flow.node_repair_turn.assert_called_once()
            flow.restore_app.assert_called_once_with('base')
            flow.commit.assert_not_called()
            self.assertEqual(policy.decide.call_args.args[3], 'disputed')

    def test_interrupted_repair_restores_measured_source(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, _ = self.flow(Path(temp), result())
            flow.node_repair_turn.side_effect = RuntimeError('partial edit interrupted')
            self.assertIsNone(Flow.fast_derived_acceptance(
                flow, 'A', ['A.spec.ts'], time.time() + 500, result()))
            flow.restore_app.assert_called_once_with('base')

    def test_buildable_unsolved_repair_is_retained_and_only_case_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, policy = self.flow(Path(temp), result())
            verdict = Flow.fast_derived_acceptance(flow, 'A', ['A.spec.ts'], time.time() + 500, result())
            self.assertIsNone(verdict)
            flow.restore_app.assert_not_called()
            flow.commit.assert_called_once()
            policy.decide.assert_called_once()
            self.assertEqual(policy.decide.call_args.args[3], 'disputed')
            flow.flag_derived_spec_dispute.assert_called_once()

    def test_uncertain_failure_skips_only_its_case_not_passing_sibling(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, policy = self.flow(Path(temp), result())
            (Path(temp) / 'A.spec.ts').write_text(
                "test('A [model]', async () => { expect(false).toBe(true); });\n"
                "test('B [model]', async () => { expect(true).toBe(true); });\n")
            passing = TestOutcome(title='B [model]', ok=True, status='passed',
                                  duration_ms=1, file='A.spec.ts')
            failing = TestOutcome(title='A [model]', ok=False, status='failed',
                                  duration_ms=1, file='A.spec.ts', message='missing button')
            initial = RunSummary(results=[failing, passing], total=2, passed=1)
            flow.oracle_review_turn.return_value = (True, json.dumps({
                'verdict': 'uncertain', 'evidence': 'The observation does not separate code and test faults.'}))
            self.assertIsNone(Flow.fast_derived_acceptance(
                flow, 'A', ['A.spec.ts'], time.time() + 500, initial))
            flow.node_repair_turn.assert_not_called()
            policy.decide.assert_called_once()
            self.assertEqual(policy.decide.call_args.args[1], 'A [model]')

    def test_passing_candidate_needs_no_review_or_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            flow, _ = self.flow(Path(temp), result(ok=True))
            verdict = Flow.fast_derived_acceptance(flow, 'A', ['A.spec.ts'], time.time() + 500,
                                                   result(ok=True))
            self.assertTrue(verdict)
            flow.oracle_review_turn.assert_not_called()
            flow.node_repair_turn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
