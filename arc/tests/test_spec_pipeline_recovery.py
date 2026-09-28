"""Regressions for 91ab7ba9457b and 0fc38614be28, across product domains."""
import argparse
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from main import Flow, salvage_app_design, app_design_coverage
from scenario_tests import Fixtures, spec_header
from scenario_review import compile_reply, proposal_problems, retry_prompt, validate_proposal
from obligation_planning import source_scope, parse_obligations, prepare_obligations, applicable_obligations, reviewed_obligations_intact
from derived_case_review import collect_cases, outcome_text, validate_review
from quality_control import blocked_design_owners, recovery_budget


def target():
    return dict(id='S1', node_id='A', title='A: workflow', name='Show result',
                description='Press "Run" to show "Completed result".', allowed=['Run', 'Completed result'],
                controls=['Run'], steps=['WHEN: Click Run', 'THEN: Show Completed result'])


def case():
    return {'confidence': .9, 'steps': [{'op': 'click', 'target': 'Run'},
                                      {'op': 'expect_visible', 'target': 'Completed result'}]}


class PipelineRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.metric = Mock(); self.flow.snapshot_protected = Mock()
        self.flow.start_derived_designs = Mock()
        self.flow.wound_down = Mock(return_value=False)
        self.flow.remaining = Mock(return_value=20000)
        self.flow.final_phase_reserve = Mock(return_value=600)
        self.flow.derived_preflight_tokens_spent = Mock(return_value=False)
        self.flow.codegen_context_chars = Mock(return_value=200000)
        self.tree = {'id': 'ROOT', 'description': 'Committed data must survive refresh.', 'children': [
            {'id': 'A', 'description': 'Press Run to show Completed result.'}]}
        self.flow.requirement_tree = self.tree

    def reply(self):
        return json.dumps({'obligations': [
            dict(requirement_id=n['id'], quote=n['description'], applies_to=['A'], branch='success',
                 outcome=n['description']) for n in [self.tree, self.tree['children'][0]]], 'gaps': []})

    def test_empty_ledger_and_missing_parent_never_mean_complete(self):
        sources, ancestry = source_scope(self.tree, ['A'])
        self.assertTrue(parse_obligations('{"obligations":[]}', sources, ancestry)[1])
        body = json.loads(self.reply()); body['obligations'] = body['obligations'][1:]
        self.assertTrue(any('inherited' in e for e in parse_obligations(json.dumps(body), sources, ancestry)[1]))

    def test_single_complete_json_fence_is_accepted_without_prose(self):
        sources, ancestry = source_scope(self.tree, ['A'])
        rows, errors = parse_obligations('```json\n' + self.reply() + '\n```', sources, ancestry)
        self.assertEqual(len(rows), 2)
        self.assertEqual(errors, [])
        self.assertTrue(parse_obligations('```json\n' + self.reply() + '\n```\nApproved.', sources, ancestry)[1])

    def test_missing_gap_disclosure_cannot_approve_ledger(self):
        sources, ancestry = source_scope(self.tree, ['A'])
        proposal = json.loads(self.reply())
        del proposal['gaps']
        rows, errors = parse_obligations(json.dumps(proposal), sources, ancestry)
        self.assertEqual(len(rows), 2)
        self.assertIn('gaps must be an array', errors)

    def test_fake_quote_or_cross_leaf_applicability_is_rejected(self):
        sources, ancestry = source_scope(self.tree, ['A'])
        for key, value in [('quote', 'Made up outcome not in requirement'), ('applies_to', ['B'])]:
            body = json.loads(self.reply()); body['obligations'][1][key] = value
            self.assertTrue(parse_obligations(json.dumps(body), sources, ancestry)[1])

    def test_shared_parent_scope_outside_batch_keeps_current_leaf_reviewable(self):
        self.tree['children'].append({'id': 'C', 'description': 'Delete a record and show its removal.'})
        reply = json.loads(self.reply())
        reply['obligations'][0]['applies_to'] = ['A', 'C']
        reply['gaps'] = [{'applies_to': ['C'], 'reason': 'Deletion permission is unresolved'}]
        sources, ancestry = source_scope(self.tree, ['A'])
        rows, errors = parse_obligations(json.dumps(reply), sources, ancestry)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual({tuple(row['applies_to']) for row in rows}, {('A',)})
        self.flow.text_turn = Mock(return_value=(True, json.dumps(reply)))
        prepare_obligations(self.flow, [self.tree['children'][0]])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertNotIn('C', self.flow.derived_obligation_status)
        self.assertTrue(reviewed_obligations_intact(self.flow, 'A'))

    def test_two_independent_turns_feed_parent_and_leaf_obligations_to_tests(self):
        self.flow.text_turn = Mock(return_value=(True, self.reply()))
        prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertEqual(len(applicable_obligations(self.flow, 'A')), 2)
        saved = json.loads((self.root/'derived-tests/review/obligations.json').read_text())
        self.assertEqual(len(saved['obligations']), 2)
        prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.text_turn.call_count, 2)

    def test_failed_independent_review_retains_gap_and_never_approves_proposal(self):
        self.flow.text_turn = Mock(side_effect=[(True, self.reply()), (False, 'timeout')])
        prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.derived_obligations, [])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')

    def test_partial_independent_review_keeps_valid_sourced_candidates_as_debt(self):
        proposal = json.loads(self.reply())
        proposal['gaps'] = ['unresolved status for malformed request']
        self.flow.text_turn = Mock(side_effect=[(True, self.reply()), (True, json.dumps(proposal))])
        prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(len(self.flow.derived_obligations), 2)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.assertIn('semantic gap', self.flow.derived_obligation_status['A']['errors'][0])

    def test_bad_sibling_does_not_veto_reviewed_leaf_or_change_its_ids_on_retry(self):
        tree = {'id': 'ROOT', 'description': 'Every saved record survives a page refresh.', 'children': [
            {'id': 'A', 'description': 'Creating a record shows it in the list.'},
            {'id': 'B', 'description': 'Deleting a record removes it from the list.'}]}
        self.flow.requirement_tree = tree
        def ledger(bad_b=False, only_b=False):
            rows = [
                {'requirement_id': 'ROOT', 'applies_to': ['A', 'B'],
                 'quote': tree['description'], 'branch': 'success', 'outcome': tree['description']},
                {'requirement_id': 'A', 'applies_to': ['A'],
                 'quote': tree['children'][0]['description'], 'branch': 'success',
                 'outcome': tree['children'][0]['description']},
                {'requirement_id': 'B', 'applies_to': ['B'],
                 'quote': 'Invented result' if bad_b else tree['children'][1]['description'],
                 'branch': 'success', 'outcome': tree['children'][1]['description']}]
            if only_b:
                rows = [{**rows[0], 'applies_to': ['B']}, rows[2]]
            return json.dumps({'obligations': rows, 'gaps': []})
        self.flow.text_turn = Mock(side_effect=[(True, ledger()), (True, ledger(True)),
                                                (True, ledger(only_b=True)), (True, ledger(only_b=True))])
        prepare_obligations(self.flow, tree['children'])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertEqual(self.flow.derived_obligation_status['B']['status'], 'incomplete')
        a_ids = {row['id'] for row in applicable_obligations(self.flow, 'A')}
        self.assertEqual(len(a_ids), 2)
        prepare_obligations(self.flow, tree['children'])
        self.assertEqual(self.flow.derived_obligation_status['B']['status'], 'reviewed')
        self.assertEqual({row['id'] for row in applicable_obligations(self.flow, 'A')}, a_ids)
        self.assertEqual(len(applicable_obligations(self.flow, 'B')), 2)
        self.assertEqual(self.flow.text_turn.call_count, 4)

    def test_leaf_scoped_gap_does_not_block_unrelated_leaf(self):
        tree = {'id': 'ROOT', 'description': 'Every saved record survives a page refresh.', 'children': [
            {'id': 'A', 'description': 'Creating a record shows it in the list.'},
            {'id': 'B', 'description': 'Deleting a record removes it from the list.'}]}
        self.flow.requirement_tree = tree
        reply = json.dumps({'obligations': [
            {'requirement_id': n['id'], 'applies_to': ['A', 'B'] if n['id'] == 'ROOT' else [n['id']],
             'quote': n['description'], 'branch': 'success', 'outcome': n['description']}
            for n in [tree, *tree['children']]],
            'gaps': [{'applies_to': ['B'], 'reason': 'Unresolved deletion permission behavior'}]})
        self.flow.text_turn = Mock(return_value=(True, reply))
        prepare_obligations(self.flow, tree['children'])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertEqual(self.flow.derived_obligation_status['B']['status'], 'incomplete')
        self.assertTrue(any('semantic gap' in error for error in self.flow.derived_obligation_status['B']['errors']))

    def test_missing_tree_leaf_cannot_inherit_siblings_review(self):
        self.flow.text_turn = Mock(return_value=(True, self.reply()))
        prepare_obligations(self.flow, [self.tree['children'][0], {'id': 'Z'}])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertEqual(self.flow.derived_obligation_status['Z']['status'], 'incomplete')
        self.assertIn('missing from requirement tree', self.flow.derived_obligation_status['Z']['errors'][0])

    def test_row_merge_failure_cannot_publish_reviewed_status(self):
        self.flow.derived_obligation_status = {'A': {'status': 'incomplete', 'errors': [], 'attempts': 0}}
        self.flow.derived_obligations = [{'broken': 'prior artifact'}]
        self.flow.text_turn = Mock(return_value=(True, self.reply()))
        with self.assertRaises(KeyError):
            prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')

    def test_reviewed_flag_without_source_rows_does_not_open_test_gate(self):
        self.flow.derived_as_specs = True
        self.flow.derived_nodes = self.tree['children']
        self.flow.planned_derived_scenarios = Mock(return_value=[])
        self.flow.derived_obligations = []
        self.flow.derived_obligation_status = {'A': {'status': 'reviewed'}}
        self.assertTrue(self.flow.derived_scenario_coverage('A')['obligation_plan_incomplete'])
        sources, ancestry = source_scope(self.tree, ['A'])
        self.flow.derived_obligations = parse_obligations(self.reply(), sources, ancestry)[0]
        self.assertFalse(self.flow.derived_scenario_coverage('A')['obligation_plan_incomplete'])

    def test_generated_suite_initializes_unreviewed_obligation_gate(self):
        self.flow.derived_as_specs = True
        self.flow.prepare_derived_tests(self.tree['children'])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.assertEqual(self.flow.derived_obligations, [])
        self.assertTrue(self.flow.derived_scenario_coverage('A')['obligation_plan_incomplete'])

    def test_zero_budget_marks_missing_plan_without_model_call(self):
        self.flow.text_turn = Mock()
        with patch.dict(os.environ, {'OCTOS_ARC_OBLIGATION_SECONDS': '0'}):
            prepare_obligations(self.flow, self.tree['children'])
        self.flow.text_turn.assert_not_called()
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')

    def test_obligation_retry_is_bounded_and_debt_remains_visible(self):
        self.flow.text_turn = Mock(return_value=(True, '{"obligations":[],"gaps":[]}'))
        for _ in range(3):
            prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.text_turn.call_count, 4)
        self.assertEqual(self.flow.derived_obligation_status['A']['attempts'], 2)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.flow._completeness_active = True
        prepare_obligations(self.flow, self.tree['children'])
        self.assertEqual(self.flow.text_turn.call_count, 6)
        self.assertEqual(self.flow.derived_obligation_status['A']['attempts'], 3)

    def test_valid_sibling_retained_but_partial_scenario_never_covers(self):
        t = target(); proposal = {'id': 'S1', 'cases': [case(), {'skip': 'missing fixture'}]}
        scripts, errors, retry = compile_reply(json.dumps({'scenarios': [proposal]}), [t], Fixtures(), True)
        self.assertEqual(len(scripts['A']), 1); self.assertTrue(errors)
        self.assertEqual(retry[0]['previous_proposal'], proposal)
        directory = self.root/'derived-tests'; directory.mkdir()
        (directory/'A.spec.ts').write_text(spec_header('A') + scripts['A'][0])
        self.flow.derived_tests_dir = directory
        self.flow._derived_scenario_targets = [t]
        self.flow.derived_nodes = [{'id': 'A', 'description': t['description']}]
        self.flow.derived_scenario_gaps = {'S1': errors}
        coverage = self.flow.derived_scenario_coverage('A')
        self.assertEqual(coverage['covered'], 0)
        self.assertEqual(coverage['scenarios'][0]['status'], 'partial')

    def test_retry_preserves_shared_context_and_original_case_order(self):
        t = target(); previous = {'id': 'S1', 'cases': [case(), {'skip': 'missing fixture'}]}
        prompt = retry_prompt([{'id': 'S1', 'title': t['title'], 'reasons': ['case 2 failed'],
                               'previous_proposal': previous}], [t], Fixtures(), 'one authoritative identity store')
        self.assertIn('one authoritative identity store', prompt)
        self.assertIn(json.dumps(previous), prompt)
        self.assertIn('case order', prompt)
        self.assertNotIn('copy every target and value verbatim', prompt)

    def test_retry_cannot_clear_gap_by_omitting_a_previously_failed_case(self):
        t = dict(target(), minimum_case_count=2)
        scripts, errors = compile_reply(json.dumps({'scenarios': [{'id': 'S1', 'cases': [case()]}]}), [t], Fixtures())
        self.assertEqual(len(scripts['A']), 1)
        self.assertIn('missing previously proposed cases', errors[0])

    def test_correction_preserves_approved_sibling_and_persists_remaining_gaps(self):
        t = target(); directory = self.root/'derived-tests'; directory.mkdir()
        other = case(); other['steps'].insert(0, {'op': 'click', 'target': 'Run'})
        tests, _ = compile_reply(json.dumps({'scenarios': [{'id': 'S1', 'cases': [case(), other]}]}), [t], Fixtures())
        path = directory/'A.spec.ts'; path.write_text(spec_header('A') + '\n' + '\n'.join(tests['A']))
        self.flow.derived_tests_dir = directory; self.flow._derived_scenario_targets = [t]
        self.flow.derived_nodes = [{'id': 'A', 'description': t['description']}]
        self.flow.derived_case_reviews = {('A', 'bad'): dict(node_id='A', scenario_id='S1', status='needs_correction', reason='incomplete state assertions')}
        self.flow.derived_scenario_gaps = {'S1': ['case 2: previous compilation failure']}
        self.flow.trusted_derived_case = Mock(side_effect=lambda _, title: '[case 1]' in title)
        # Even a valid replacement for case 1 may not overwrite its approved source.
        self.flow.text_turn = Mock(return_value=(True, json.dumps({'scenarios': [{'id': 'S1', 'cases': [other]}]})))
        self.flow.correct_derived_cases({'A'})
        self.assertIn(tests['A'][0], path.read_text())
        self.assertTrue(self.flow.derived_scenario_gaps['S1'])
        self.assertEqual(json.loads((directory/'review/plan.json').read_text())['targets'][0]['status'], 'partial')
        # Returning the complete, valid case set clears only the compilation gap.
        self.flow.derived_case_correction_attempted = set()
        self.flow.text_turn.return_value = (True, json.dumps({'scenarios': [{'id': 'S1', 'cases': [case(), other]}]}))
        self.flow.correct_derived_cases({'A'})
        self.assertEqual(self.flow.derived_scenario_gaps['S1'], [])
        self.assertEqual(self.flow.derived_case_reviews[('A', 'bad')]['status'], 'needs_correction')

    def test_review_count_budget_can_audit_all_branches_but_honors_explicit_cap(self):
        self.flow.derived_as_specs = True; self.flow.max_turns = 188
        self.flow.planned_derived_scenarios = Mock(return_value=[target()] * 89)
        self.assertGreaterEqual(self.flow.case_review_cap(), 89 * 8 * 2)
        self.flow.review_turn_count = 188
        self.assertFalse(self.flow.review_budget_spent())
        with patch.dict(os.environ, {'OCTOS_ARC_REVIEW_TURNS': '188'}):
            self.assertTrue(self.flow.review_budget_spent())
        with patch.dict(os.environ, {'OCTOS_ARC_DERIVED_CASE_REVIEW_REQUESTS': '5'}):
            self.assertEqual(self.flow.case_review_cap(), 5)
        self.assertLessEqual(self.flow.case_review_seconds(), 10800)

    def test_reviewed_rejection_only_ledger_does_not_demand_invented_success_branch(self):
        sources, ancestry = source_scope(self.tree, ['A'])
        reply = json.dumps({'obligations': [
            {'requirement_id': item['id'], 'quote': item['description'], 'applies_to': ['A'],
             'branch': 'rejection', 'outcome': item['description']}
            for item in [self.tree, self.tree['children'][0]]], 'gaps': []})
        self.flow.derived_obligation_status = {'A': {'status': 'reviewed'}}
        self.flow.derived_obligations = parse_obligations(reply, sources, ancestry)[0]
        self.assertFalse(self.flow.success_branch_required('A'))
        self.flow.derived_obligations = []
        self.assertTrue(self.flow.success_branch_required('A'))
        self.flow.derived_obligation_status['A']['status'] = 'incomplete'
        self.assertTrue(self.flow.success_branch_required('A'))

    def test_missing_reply_scenario_remains_retryable(self):
        _, errors, retry = compile_reply('{"scenarios":[]}', [target()], Fixtures(), True)
        self.assertIn('omitted', errors[0]); self.assertEqual(retry[0]['id'], 'S1')

    def test_drag_coordinates_compile_to_accessible_gridcell_not_visible_text(self):
        t = target(); p = {'confidence': .9, 'steps': [
            {'op': 'drag', 'target': 'A1', 'destination': 'B2'},
            {'op': 'expect_selected', 'target': 'A1:B2'}]}
        source = validate_proposal(p, t, Fixtures())
        self.assertIsNotNone(source, proposal_problems(p, t, Fixtures()))
        self.assertIn("h.dragNamed(page, 'A1', 'B2', 'gridcell')", source)

    def test_generic_drag_supports_role_without_inventing_names(self):
        t = target(); t['allowed'] += ['Todo', 'Done']
        p = {'confidence': .9, 'steps': [{'op': 'drag', 'role': 'button', 'target': 'Todo', 'destination': 'Done'},
                                       {'op': 'expect_visible', 'target': 'Completed result'}]}
        self.assertIn("'button')", validate_proposal(p, t, Fixtures()))
        p['steps'][0]['role'] = 'invented'; self.assertIsNone(validate_proposal(p, t, Fixtures()))

    def test_dependency_enum_requires_source_quote_and_free_input_uses_typed_data(self):
        t = target(); t['controls'] += ['Priority', 'Limit']
        t['source_contracts'] = {'DEPENDENCY': 'The "Priority" options include "Critical".'}
        p = {'confidence': .9, 'test_data': {'$DATA_LIMIT': {'type': 'number', 'value': 100}},
             'source_values': [{'value': 'Critical', 'requirement_id': 'DEPENDENCY',
                               'quote': t['source_contracts']['DEPENDENCY']}],
             'steps': [{'op': 'select_option', 'target': 'Priority', 'value': 'Critical'},
                       {'op': 'fill', 'target': 'Limit', 'value': '$DATA_LIMIT'},
                       {'op': 'expect_visible', 'target': 'Completed result'}]}
        self.assertIsNotNone(validate_proposal(p, t, Fixtures()), proposal_problems(p, t, Fixtures()))
        p['source_values'][0]['quote'] = 'Invented: choose Critical here'
        self.assertIsNone(validate_proposal(p, t, Fixtures()))

    def test_parent_outcome_can_be_audited_but_not_invented_outcome(self):
        t = target(); t['obligations'] = [{'id': 'O1', 'quote': self.tree['description']}]
        text = validate_proposal(case(), t, Fixtures())
        row = {'status': 'unreviewed', 'obligations': t['obligations'], 'outcome': outcome_text(t), 'case': text}
        decision = dict(status='approved_behavior', obligation_ids=['O1'], requirement_quote=self.tree['description'],
                        test_quote="await h.expectTextsVisible(page, ['Completed result']);", reason='The assertion proves the claimed outcome.',
                        obligation_evidence=[{'obligation_id':'O1','requirement_quote':self.tree['description'],
                                              'test_quote':"await h.expectTextsVisible(page, ['Completed result']);"}])
        self.assertTrue(validate_review(row, decision))
        decision['requirement_quote'] = 'Invented expectation without source.'
        self.assertFalse(validate_review(row, decision))

    def test_incomplete_design_does_not_drop_all_implementation_nodes(self):
        self.flow._design_blocked = blocked_design_owners(self.tree, {'data_model': {'items': {'id': 'string'}}}, {'A'}, False)
        self.assertEqual(self.flow._design_blocked, {'A'})
        self.flow.self_audit_node = Mock(); self.flow.pending_dependencies = Mock(return_value=[])
        self.assertTrue(self.flow.admit_node({'id': 'A'}))
        self.assertIsNot(self.flow.test_verdict.get('A'), True)

    def test_missing_shared_contracts_trigger_design_recovery_review(self):
        self.flow.text_turn = Mock(return_value=(False, 'unavailable'))
        design = {'data_model': {'items': {'id': 'string'}}}
        self.assertEqual(self.flow.review_domain_design(self.tree, design), design)
        self.flow.text_turn.assert_called_once()
        self.assertIn('Complete missing domain_contracts', self.flow.text_turn.call_args.args[0])
        self.assertFalse(self.flow._design_semantics_reviewed)

    def test_design_salvage_retains_valid_items_and_correction_uses_pointer_errors(self):
        accepted = {'data_model': {'items': {'id': 'string'}}, 'routes': [], 'pages': [],
                    'modules': [], 'contracts': [], 'domain_contracts': [], 'commands': [], 'notes': ''}
        bad = {**accepted, 'routes': [
            {'method': 'GET', 'path': '/api/items', 'requirements': ['A']},
            {'method': 'GET', 'path': 'api/broken', 'requirements': ['A']}]}
        partial = salvage_app_design(accepted, bad)
        self.assertEqual(len(partial['routes']), 1)
        self.assertEqual(partial['routes'][0]['path'], '/api/items')
        self.assertEqual(accepted['routes'], [])
        corrected = {**partial, 'routes': [partial['routes'][0],
                    {'method': 'POST', 'path': '/api/items', 'requirements': ['A']}]}
        self.flow.text_turn = Mock(side_effect=[(True, json.dumps(bad)), (True, json.dumps(corrected))])
        self.flow.save_rejected_reply = Mock()
        with patch.dict(os.environ, {'OCTOS_ARC_DESIGN_RECOVERY_SECONDS': '600',
                                      'OCTOS_ARC_DESIGN_CATEGORY_SECONDS': '300'}):
            result = self.flow.recover_category_design(self.tree, self.tree['children'], accepted=accepted)
        self.assertEqual(len(result['routes']), 2)
        self.assertIn('A', app_design_coverage(result))
        correction_prompt = self.flow.text_turn.call_args_list[1].args[0]
        self.assertIn('/routes/1/path', correction_prompt)
        self.assertIn('ACCEPTED DESIGN', correction_prompt)

    def test_recovery_restores_cumulative_obligation_budget(self):
        self.flow.derived_obligation_seconds = 2400
        with recovery_budget(self.flow):
            self.assertEqual(self.flow.derived_obligation_seconds, 0)
            self.flow.derived_obligation_seconds = 100
        self.assertEqual(self.flow.derived_obligation_seconds, 2500)

    def test_late_completeness_reuses_obligation_and_case_review_pipeline(self):
        node = self.tree['children'][0]
        self.flow.derived_as_specs = True
        self.flow.weak_derived_leaves = Mock(return_value=['A'])
        self.flow.final_measurement_reserve = Mock(return_value=600)
        self.flow.prepare_derived_spec_batch = Mock()
        self.flow.derived_review_needed = Mock(return_value=True)
        self.flow.self_audit_node = Mock()
        self.flow.spec_map = {}
        self.flow.runner = None
        self.flow._derived_completeness_work([node])
        self.flow.prepare_derived_spec_batch.assert_called_once_with([node])
        queue = json.loads((self.root/'diagnostics/recovery-queue.json').read_text())
        self.assertEqual(queue[0]['status'], 'unverified')

    def test_late_completeness_batches_weak_leaves_by_category(self):
        nodes = [{'id': key} for key in ('A', 'B', 'C')]
        self.flow.derived_as_specs = True
        self.flow.phase_plan = {'leaf_phase': {'A': 'one', 'B': 'one', 'C': 'two'}}
        self.flow.weak_derived_leaves = Mock(return_value=['A', 'B', 'C'])
        self.flow.final_measurement_reserve = Mock(return_value=600)
        self.flow.prepare_derived_spec_batch = Mock()
        self.flow.derived_review_needed = Mock(return_value=True)
        self.flow.self_audit_node = Mock()
        self.flow.spec_map = {}
        self.flow.runner = None
        self.flow._derived_completeness_work(nodes)
        self.assertEqual([call.args[0] for call in self.flow.prepare_derived_spec_batch.call_args_list],
                         [nodes[:2], nodes[2:]])

    def test_whole_app_queue_keeps_all_nodes_with_incomplete_design(self):
        nodes = [{'id': key} for key in ('A', 'B', 'C')]
        self.flow._design_blocked = {'A', 'B', 'C'}
        self.flow.tests_dir = None; self.flow.evolution = False
        self.flow.codegen_mode = Mock(return_value=True)
        self.flow.requirement_contracts = {'nodes': nodes}
        self.flow.batch_spec_bodies = Mock(return_value='original business requirements')
        self.flow.whole_app_waves = Mock(return_value=True)
        with patch.dict(os.environ, {'OCTOS_ARC_WHOLE_APP': 'auto'}):
            self.assertTrue(self.flow.whole_app_codegen({'id': 'ROOT', 'children': nodes}, nodes))
        self.assertEqual(self.flow.whole_app_waves.call_args.args[1], nodes)

    def test_no_spec_or_unapproved_dependency_does_not_cancel_node_development(self):
        self.flow.self_audit_node = Mock()
        self.flow.pending_dependencies = Mock(return_value=['missing-test-dependency'])
        self.flow.spec_map = {}; self.flow.runner = None
        self.assertTrue(self.flow.admit_node({'id': 'A'}))
        self.assertIsNot(self.flow.test_verdict.get('A'), True)

    def test_obligation_planner_exception_does_not_cancel_generation(self):
        self.tree['children'].append({'id': 'B', 'description': 'Show the saved record.'})
        nodes = self.tree['children']
        self.flow.derived_as_specs = True; self.flow.derived_nodes = nodes
        self.flow.derived_obligation_status = {'B': {'status': 'reviewed', 'attempts': 1, 'errors': []}}
        sources, ancestry = source_scope(self.tree, ['B'])
        reviewed = {'obligations': [
            {'requirement_id': item['id'], 'applies_to': ['B'], 'quote': item['description'],
             'branch': 'success', 'outcome': item['description']}
            for item in [self.tree, nodes[1]]], 'gaps': []}
        self.flow.derived_obligations = parse_obligations(json.dumps(reviewed), sources, ancestry)[0]
        self.assertTrue(reviewed_obligations_intact(self.flow, 'B'))
        self.flow.derived_tests_dir = self.root/'derived-tests'
        self.flow.augment_derived_tests = Mock(); self.flow.review_derived_cases = Mock()
        self.flow.correct_derived_cases = Mock(return_value=set()); self.flow.adopt_derived_specs = Mock()
        with patch('main.prepare_obligations', side_effect=RuntimeError('unavailable planner')), \
                patch.dict(os.environ, {'OCTOS_ARC_DRYRUN': '0', 'OCTOS_ARC_DERIVED_LLM': '1'}):
            self.flow.prepare_derived_spec_batch(nodes)
        self.flow.augment_derived_tests.assert_called_once_with(nodes)
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'incomplete')
        self.assertEqual(self.flow.derived_obligation_status['B']['status'], 'reviewed')
        self.assertTrue(self.flow.admit_node(nodes[0]))
        self.flow.derived_obligation_status['B']['status'] = 'incomplete'
        if hasattr(self.flow, 'derived_obligations'):
            del self.flow.derived_obligations
        self.assertFalse(reviewed_obligations_intact(self.flow, 'B'))
        self.flow.text_turn = Mock(return_value=(True, self.reply()))
        prepare_obligations(self.flow, [nodes[0]])
        self.assertEqual(self.flow.derived_obligation_status['A']['status'], 'reviewed')
        self.assertEqual(self.flow.derived_obligation_status['B']['status'], 'incomplete')

    def test_initial_audit_leaves_time_for_correction_and_reaudit(self):
        nodes = self.tree['children']; observed = []
        self.flow.derived_as_specs = True; self.flow.derived_nodes = nodes
        self.flow.derived_tests_dir = self.root/'derived-tests'
        deadline = time.monotonic() + 1000
        self.flow.derived_preflight_deadline = deadline
        self.flow.augment_derived_tests = Mock()
        self.flow.adopt_derived_specs = Mock()
        self.flow.review_derived_cases = Mock(side_effect=lambda *a, **k: observed.append(self.flow.derived_preflight_deadline))
        self.flow.correct_derived_cases = Mock(side_effect=lambda *a: observed.append(self.flow.derived_preflight_deadline) or {'A'})
        with patch('main.prepare_obligations'), patch.dict(os.environ, {'OCTOS_ARC_DRYRUN': '0', 'OCTOS_ARC_DERIVED_LLM': '1'}):
            self.flow.prepare_derived_spec_batch(nodes)
        self.assertEqual(len(observed), 3)
        self.assertLess(observed[0], deadline - 400)
        self.assertLess(observed[1], deadline - 300)
        self.assertEqual(observed[2], deadline)
        self.assertEqual(self.flow.derived_preflight_deadline, deadline)


@unittest.skipUnless(os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT'), 'requires Playwright and Chromium')
class BrowserDragRecovery(unittest.TestCase):
    def test_drag_uses_accessible_name_when_visible_content_is_business_data(self):
        from acceptance import AcceptanceRunner
        install = Path(os.environ['OCTOS_TEST_PLAYWRIGHT_ROOT'])
        with tempfile.TemporaryDirectory(dir=install, prefix='drag-contract-') as directory:
            root = Path(directory); specs = root/'specs'; specs.mkdir()
            (specs/'helpers.ts').write_text((Path(__file__).parents[1]/'blueprints/derived-helpers.ts').read_text())
            (specs/'drag.spec.ts').write_text('''import {test,expect} from '@playwright/test';
import * as h from './helpers';
test('accessible grid coordinates', async ({page})=>{
  await page.setContent(`<div role="grid" aria-label="Worksheet grid">
    <div draggable="true" role="gridcell" aria-label="A1" ondragstart="event.dataTransfer.setData('text/plain','selected')">Region</div>
    <div role="gridcell" aria-label="B2" ondragover="event.preventDefault()" ondrop="this.setAttribute('aria-selected','true')">1200</div>
  </div>`);
  await h.dragNamed(page,'A1','B2','gridcell');
  await expect(page.getByRole('gridcell',{name:'B2',exact:true})).toHaveAttribute('aria-selected','true');
});
test('generic named role drag', async ({page})=>{
  // Homogeneous role drag has names independent of visible captions.
  await page.setContent(`<button draggable="true" aria-label="First" ondragstart="event.dataTransfer.setData('text/plain','task')">Card title</button>
    <button aria-label="Second" ondragover="event.preventDefault()" ondrop="this.textContent='Task moved'">Drop here</button>`);
  await h.dragNamed(page,'First','Second','button');
  await expect(page.getByRole('button',{name:'Second'})).toHaveText('Task moved');
});
''')
            runner = AcceptanceRunner(install, specs, root/'prepared', lambda *_: None, workers=1)
            result = runner.run(['drag.spec.ts'], 'http://127.0.0.1:9', wall_timeout=35)
            self.assertTrue(result.all_passed, (result.error, [(r.title, r.message) for r in result.results]))
            self.assertEqual(result.total, 2)
