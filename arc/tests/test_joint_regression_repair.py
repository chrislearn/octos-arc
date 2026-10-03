"""A feature is accepted only with its previously verified dependencies intact."""
import argparse
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main as m
from acceptance import RunSummary, SharedFailureTracker, TestOutcome, alternative_text_locator_conflict


def measured(*rows):
    return RunSummary(results=list(rows), total=len(rows), passed=sum(row.ok for row in rows))


def outcome(spec, ok, message=''):
    return TestOutcome(spec, ok, 'passed' if ok else 'failed', 1000,
                       file=spec + '.spec.ts', message=message)


class JointRepairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.flow = f = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        f.tests_dir = self.root / 'tests'; f.tests_dir.mkdir()
        f.spec_map = {'rename': ['rename.spec.ts'], 'csv': ['csv.spec.ts']}
        for name in f.spec_map:
            (f.tests_dir / (name + '.spec.ts')).write_text('test("' + name + '");')
        self.editor = self.root / 'frontend/src/Editor.jsx'
        self.editor.parent.mkdir(parents=True); self.editor.write_text('extension with CSV regression')
        f.runner = SimpleNamespace(root=self.root, env_extra={}, workers=1)
        f.repair_rounds = 2
        f.test_verdict = {'csv': True}
        f.requirement_nodes = {name: {'id': name, 'description': name + ' requirement'}
                               for name in f.spec_map}
        for name, value in {'remaining': 3000, 'wound_down': False, 'time_up': False,
                            'final_phase_reserve': 0, 'final_measurement_reserve': 120,
                            'repair_minimum': 60, 'head': 'source', 'codegen_mode': True,
                            'slow_test_ms': 30000, 'perf_text': ''}.items():
            setattr(f, name, Mock(return_value=value))
        f.commit = Mock(); f.restore_app = Mock(); f.record_tests = Mock()
        f.metric = Mock(); f.mark = Mock()
        self.target = measured(outcome('rename', True))
        self.bad = measured(outcome('rename', True), outcome('csv', False, 'CSV newline was lost'))
        self.good = measured(outcome('rename', True), outcome('csv', True))

    def test_green_target_repairs_red_prior_with_both_contracts_and_retests_it(self):
        f = self.flow
        prompts = []
        def repair(node, failures, timeout, label, build):
            prompts.append(build())
            self.editor.write_text('extension and CSV both repaired')
            return True
        f.node_repair_turn = Mock(side_effect=repair)
        f.run_specs = Mock(side_effect=[self.bad, self.target, self.good])
        verdict = f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000,
                    initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'})
        self.assertTrue(verdict)
        f.node_repair_turn.assert_called_once()
        self.assertIn('CSV newline was lost', f.node_repair_turn.call_args.args[1])
        self.assertIn('csv requirement', prompts[0])
        self.assertIn('csv.spec.ts', prompts[0])
        self.assertTrue(f.test_verdict['csv'])
        self.assertEqual(f.run_specs.call_args.args[0], ['csv.spec.ts', 'rename.spec.ts'])
        f.restore_app.assert_not_called()

    def test_persistent_regression_stops_after_first_nonprogressing_repair(self):
        f = self.flow
        def repair(*args):
            self.editor.write_text(self.editor.read_text() + ' unsuccessful edit')
            return True
        f.node_repair_turn = Mock(side_effect=repair)
        f.run_specs = Mock(side_effect=[self.bad, self.target, self.bad, self.target, self.bad])
        self.assertFalse(f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000,
                  initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        self.assertEqual(f.node_repair_turn.call_count, 1)
        self.assertFalse(f.test_verdict['csv'])
        self.assertFalse(any('accepted)' in str(call) for call in f.commit.call_args_list))

    def test_regressed_prior_remains_protected_and_prevents_whole_app_rewrite(self):
        f = self.flow
        f.affected_regression_specs({'frontend/src/Editor.jsx'}, ['rename.spec.ts'])
        f.test_verdict['csv'] = False
        self.assertNotIn('csv.spec.ts', f.affected_regression_specs(
            {'frontend/src/Editor.jsx'}, ['rename.spec.ts'], baseline_failed_nodes={'csv'}))
        self.assertIn('csv', f.proven_behavior)
        self.assertFalse(f.can_rewrite_from_scratch())

    def test_no_regression_measurement_budget_cannot_accept_green_target(self):
        f = self.flow
        f.remaining.return_value = 100
        f.run_specs = Mock()
        f.node_repair_turn = Mock()
        self.assertIsNone(f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000,
               initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        f.run_specs.assert_not_called(); f.node_repair_turn.assert_not_called()

    def test_corrections_are_invalidated_by_source_change_without_losing_guard_rules(self):
        f = self.flow
        f.pending_corrections = [m.RegressionEvidence('CSV red', ['csv.spec.ts'], f.app_source_digest()),
                                 'Do not edit protected requirements']
        self.editor.write_text('rolled back to good source')
        text = f.corrections_text()
        self.assertNotIn('CSV red', text)
        self.assertIn('Do not edit protected requirements', text)

    def test_green_rollback_retires_only_its_resolved_regression_evidence(self):
        f = self.flow
        f.test_verdict['csv'] = False
        f.pending_corrections = [m.RegressionEvidence('CSV red', ['csv.spec.ts'], 'bad'),
                                 m.RegressionEvidence('other red', ['other.spec.ts'], 'bad'),
                                 'Preserve shared interfaces']
        f.run_specs = Mock(return_value=measured(outcome('csv', True)))
        f.settle_failed_extension('rename', 'before', ['csv'], node_passed=True)
        self.assertTrue(f.test_verdict['csv'])
        self.assertEqual([str(c) for c in f.pending_corrections],
                         ['Related regression checks after the targeted repair:\nother red', 'Preserve shared interfaces'])

    def test_counterfactual_retains_concurrent_actor_and_workers_on_both_sources(self):
        f = self.flow
        scope = ['csv.spec.ts', 'rename.spec.ts']
        f._regression_controls = {'rename': {'specs': scope, 'workers': 2}}
        f.run_specs = Mock(side_effect=[self.bad, self.bad, self.target])
        self.assertTrue(f.settle_failed_extension('rename', 'before', ['csv'], node_passed=True))
        calls = f.run_specs.call_args_list
        self.assertEqual([c.args[0] for c in calls], [scope, scope, ['rename.spec.ts']])
        self.assertTrue(all(c.kwargs == {'workers': 2, 'grader_like': True} for c in calls))
        self.assertTrue(f.test_verdict['rename'])
        self.assertIsNone(f.test_verdict['csv'])

    def test_missing_control_cannot_keep_extension_from_failed_prior_only_recheck(self):
        f = self.flow
        f.run_specs = Mock(return_value=measured(outcome('csv', False)))
        self.assertFalse(f.settle_failed_extension('rename', 'before', ['csv'], node_passed=True))
        f.restore_app.assert_called_once_with('before')

    def test_incomplete_counterfactual_cannot_keep_extension(self):
        f = self.flow
        f._regression_controls = {'rename': {'specs': ['csv.spec.ts', 'rename.spec.ts'], 'workers': 2}}
        f.run_specs = Mock(side_effect=[self.bad, measured(outcome('csv', False))])
        self.assertFalse(f.settle_failed_extension('rename', 'before', ['csv'], node_passed=True))
        self.assertIsNone(f.test_verdict['csv'])
        f.restore_app.assert_called_once_with('before')

    def test_kept_extension_requires_fresh_target_pass_on_selected_source(self):
        f = self.flow
        f._regression_controls = {'rename': {'specs': ['csv.spec.ts', 'rename.spec.ts'], 'workers': 2}}
        f.run_specs = Mock(side_effect=[self.bad, self.bad, measured(outcome('rename', False))])
        self.assertFalse(f.settle_failed_extension('rename', 'before', ['csv'], node_passed=True))
        self.assertEqual([c.args[0] for c in f.restore_app.call_args_list], ['before', 'source', 'before'])
        self.assertIsNone(f.test_verdict['rename'])

    def test_internal_concurrency_defaults_to_one_and_preserves_operator_override(self):
        f = self.flow
        f.runner.workers = 2
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(f.spec_workers(), 2)
            f.frozen_suite = {'name': 'reviewed'}
            self.assertEqual(f.spec_workers(), 1)
            self.assertEqual(f.spec_workers(3), 3)
        with patch.dict(os.environ, {'OCTOS_ARC_TEST_WORKERS': '2'}):
            self.assertEqual(f.spec_workers(), 2)

    def test_invalidated_generated_oracle_does_not_leave_a_repair_obligation(self):
        f = self.flow
        approved = {'rename', 'csv'}
        f.derived_as_specs = True
        f.derived_has_runnable_cases = Mock(side_effect=lambda owner: owner in approved)
        f.derived_review_needed = Mock(return_value=False)
        f.audit_related_derived_specs = Mock(side_effect=lambda specs, summary, **kw: summary)
        f.disputed_generated_failures = Mock(return_value=[])
        f.uncontested_derived_results = Mock(side_effect=lambda summary: summary)
        def repair(*args):
            approved.remove('csv')
            f.test_verdict['csv'] = None
            self.editor.write_text('new source; CSV oracle review withdrawn')
            return True
        f.node_repair_turn = Mock(side_effect=repair)
        f.run_specs = Mock(side_effect=[self.bad, self.target, self.target])
        self.assertTrue(f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000,
            initial_summary=self.target, source_versions={'frontend/src/Editor.jsx': 'before'}))
        f.node_repair_turn.assert_called_once()
        self.assertIsNone(f.test_verdict['csv'])
        f.pending_corrections = [m.RegressionEvidence('withdrawn CSV oracle', ['csv.spec.ts'],
                                 f.app_source_digest()), 'Keep protected sources unchanged']
        self.assertNotIn('withdrawn CSV oracle', f.corrections_text())

    def test_nonprogressing_repair_restores_best_state_without_extra_turns(self):
        f = self.flow
        f.repair_rounds = 3
        f.codegen_mode.return_value = False
        self.editor.write_text('baseline')
        events, prompts = [], []
        def run(specs, **kw):
            state = self.editor.read_text()
            events.append(('measure', state, tuple(specs)))
            target = [outcome('rename', state != 'rejected'),
                      outcome('rename', state == 'fixed',
                              'Missing dismissal handler' if state == 'baseline' else
                              'Duplicate rejected control' if state == 'rejected' else 'Missing entry')]
            prior = [outcome('csv', state in {'baseline', 'fixed'}, 'Rejected shared-file behavior')]
            return measured(*(target if specs == ['rename.spec.ts'] else
                              prior if specs == ['csv.spec.ts'] else target + prior))
        f.run_specs = Mock(side_effect=run)
        def restore(sha):
            events.append(('rollback', sha))
            self.editor.write_text('baseline')
        f.restore_app.side_effect = restore
        def repair(node, failures, timeout, label, build):
            events.append(('repair', self.editor.read_text()))
            prompts.append((failures, build(), label))
            self.editor.write_text(['partial', 'rejected', 'fixed'][len(prompts) - 1])
            return True
        f.node_repair_turn = Mock(side_effect=repair)
        baseline = run(['rename.spec.ts'])
        self.assertFalse(f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000,
                                         initial_summary=baseline))
        self.assertEqual(len(prompts), 1)
        self.assertIn('repair 1/1', prompts[0][2])
        self.assertEqual(self.editor.read_text(), 'baseline')
        self.assertEqual(len([event for event in events if event[0] == 'repair']), 1)


class SharedFailureEvidenceTests(unittest.TestCase):
    def test_generic_timeouts_do_not_establish_a_shared_cause(self):
        tracker = SharedFailureTracker()
        for name in ('register', 'recover', 'logout'):
            self.assertEqual(tracker.note(name, measured(outcome(name, False,
                'Error: locator.click: Test timeout of 60000ms exceeded.'))), '')

    def test_distinct_locators_are_not_merged_and_healed_nodes_are_retired(self):
        tracker = SharedFailureTracker(min_nodes=2)
        def failed(name):
            return measured(outcome('feature', False,
                "Error: locator.click: Test timeout of 60000ms exceeded.\nLocator: getByRole('link', { name: '" + name + "' })"))
        self.assertEqual(tracker.note('A', failed('Create account')), '')
        self.assertEqual(tracker.note('B', failed('Sign out')), '')
        self.assertIn('possible shared cause', tracker.note('C', failed('Sign out')))
        tracker.note('B', measured(outcome('feature', True)))
        self.assertEqual(tracker.note('C', failed('Sign out')), '')


class FixtureDeliveryTests(unittest.TestCase):
    def test_text_codegen_gets_complete_public_seed_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {'workbooks': [{'name': 'Row operations seed', 'cells': {'A1': 'Label', 'A2': 'first'}}],
                        'private_api_required': False}
            (root / 'fixtures.json').write_text(json.dumps(document))
            f = Mock(); f.tests_dir = root; f.frozen_suite = {'name': 'reviewed'}
            text = m.fixture_context(f, 'Row operations seed')
            self.assertIn('"A1":"Label"', text)
            self.assertIn('"A2":"first"', text)
            self.assertIn('no private test API', text)
            f.frozen_suite = None
            self.assertEqual(m.fixture_context(f, 'Row operations seed'), '')

    def test_large_fixture_keeps_active_record_and_its_relations_without_truncating_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {'records': [{'name': 'active', 'owner': 'alice'},
                                    {'name': 'future', 'text': 'x' * 1000}],
                        'accounts': [{'username': 'alice', 'role': 'owner'}, {'username': 'bob'}]}
            (root / 'fixtures.json').write_text(json.dumps(document))
            f = Mock(); f.tests_dir = root; f.frozen_suite = {'name': 'reviewed'}
            with patch.dict(os.environ, {'OCTOS_ARC_FIXTURE_CONTEXT_CHARS': '250'}):
                text = m.fixture_context(f, 'Open active')
            self.assertIn('"name":"active"', text)
            self.assertIn('"username":"alice"', text)
            self.assertNotIn('future', text)
            self.assertNotIn('bob', text)


class OracleConflictTests(unittest.TestCase):
    setUp = JointRepairTests.setUp
    def ambiguity(self):
        return TestOutcome('field validation', False, 'failed', 1000, file='rename.spec.ts',
            message=('Error: strict mode violation: getByText(/Current password is incorrect|Password confirmation does not match/) resolved to 2 elements:\n'
                     '1) <span>Current password is incorrect</span>\n'
                     '2) <span>Password confirmation does not match</span>'),
            rendered_page='Current password is incorrect\nPassword confirmation does not match')

    def test_valid_required_messages_are_not_removed_to_satisfy_an_ambiguous_oracle(self):
        f = self.flow
        requirement = 'Errors: Current password is incorrect; Password confirmation does not match.'
        row = self.ambiguity()
        self.assertIn('case remains unverified', alternative_text_locator_conflict(row, requirement))
        f.frozen_suite = {'name': 'reviewed'}
        f.requirement_nodes['rename']['description'] = requirement
        f.run_specs = Mock(return_value=measured(row)); f.node_repair_turn = Mock()
        f.self_audit_node = Mock()
        self.assertIsNone(f.acceptance_loop('rename', ['rename.spec.ts'], time.time() + 1000))
        f.node_repair_turn.assert_not_called()
        self.assertEqual(self.editor.read_text(), 'extension with CSV regression')

    def test_duplicate_control_or_unrequired_message_remains_a_product_failure(self):
        row = self.ambiguity()
        self.assertEqual(alternative_text_locator_conflict(row, 'Only Current password is incorrect is required'), '')
        row.rendered_page = 'Current password is incorrect'
        self.assertEqual(alternative_text_locator_conflict(row,
            'Current password is incorrect; Password confirmation does not match'), '')

    def test_final_suite_records_real_results_and_leaves_conflicted_case_unverified(self):
        f = self.flow
        f.frozen_suite = {'name': 'reviewed'}
        f.requirement_nodes['rename']['description'] = ('Current password is incorrect; '
                                                       'Password confirmation does not match')
        summary = measured(self.ambiguity(), outcome('csv', True))
        f.run_specs = Mock(return_value=summary)
        f.final_workers = Mock(return_value=1)
        f.self_audit_node = Mock()
        f.record_full_suite = Mock()
        f.suite_repair_turn = Mock()
        with patch.dict(os.environ, {'OCTOS_FINAL_REPAIR_ROUNDS': '2'}):
            f.final_acceptance()
        f.record_full_suite.assert_called_once()
        self.assertEqual(f.record_full_suite.call_args.args[0].passed, 1)
        self.assertFalse(f.final_suite_green)
        self.assertTrue(f.final_spec_dispute)
        self.assertIsNone(f.test_verdict['rename'])
        f.suite_repair_turn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
