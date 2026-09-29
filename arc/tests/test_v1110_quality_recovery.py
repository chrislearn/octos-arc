"""8ea2 regressions: read-only workflow review, obligations, health routes and budgets."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from main import Flow
from obligation_planning import source_scope, parse_obligation_details, applicable_obligations, obligation_kind
from quality_control import dynamic_health_patterns
from scenario_review import transition_contract, proposal_transition_problems, proposal_problems, review_targets
from scenario_tests import Fixtures


class LiveRunRecoveryTests(unittest.TestCase):
    def test_read_only_open_does_not_require_a_commit_and_accepts_grid_attribute(self):
        node = {'id': 'A', 'name': 'View and Open a Workbook', 'type': 'ATOMIC',
                'description': ('Users view workbooks. Each record displays "Last updated: <last updated value>". '
                                'After the user clicks the link, the editor shows the workbook.'),
                'scenarios': [{'name': 'A: the requested workflow', 'steps': [
                    {'keyword': 'WHEN', 'content': 'Open the workbook and the requested workflow.'},
                    {'keyword': 'THEN', 'content': 'The observable result for the requested workflow appears.'}]}]}
        target = review_targets([node], Fixtures(), context={'A': 'The grid has accessible name "Worksheet grid" and aria-multiselectable="true".'},
                                include_all=True)[0]
        self.assertEqual(transition_contract(target)['kind'], '')
        proposal = {'confidence': .9, 'steps': [
            {'op': 'click', 'target': 'Worksheet grid'},
            {'op': 'expect_attribute', 'role': 'grid', 'target': 'Worksheet grid',
             'attribute': 'aria-multiselectable', 'value': 'true'}]}
        self.assertNotIn('attribute must be an explicit supported state attribute',
                         ' | '.join(proposal_problems(proposal, target, Fixtures())))

    def test_real_update_still_requires_commit(self):
        target = {'name': 'Rename workbook', 'title': 'Rename workbook',
                  'description': 'Rename a workbook and show the updated name.',
                  'steps': ['WHEN: the requested workflow', 'THEN: observable result for the requested workflow']}
        self.assertEqual(transition_contract(target)['kind'], 'update')
        self.assertIn('no commit action', ' | '.join(proposal_transition_problems(
            [{'op': 'expect_visible', 'target': 'New name'}], target)))

    def test_duplicate_template_gap_is_warning_but_real_conflict_blocks(self):
        repeated = 'After refresh, the saved result and all existing records remain unchanged.'
        tree = {'id': 'ROOT', 'description': 'Saved results persist after refresh.', 'children': [
            {'id': 'A', 'description': 'Open the saved record.', 'scenarios': [
                {'steps': [{'keyword': 'THEN', 'content': repeated}]},
                {'steps': [{'keyword': 'THEN', 'content': repeated}]}]}]}
        sources, ancestry = source_scope(tree, ['A'])
        rows = [{'requirement_id': owner, 'applies_to': ['A'], 'quote': quote,
                 'outcome': quote, 'branch': 'success'} for owner, quote in
                [('ROOT', tree['description']), ('A', tree['children'][0]['description'])]]
        body = {'obligations': rows, 'gaps': [{'applies_to': ['A'],
                 'reason': 'An exact duplicate outcome appears twice verbatim.'}]}
        self.assertEqual(parse_obligation_details(json.dumps(body), sources, ancestry)[1]['A'], [])
        body['gaps'][0]['reason'] = 'These requirements conflict about whether the saved result persists.'
        self.assertTrue(parse_obligation_details(json.dumps(body), sources, ancestry)[1]['A'])
        body['gaps'][0]['reason'] = 'Exact duplicate entries have different status codes.'
        self.assertTrue(parse_obligation_details(json.dumps(body), sources, ancestry)[1]['A'])

    def test_scope_and_category_list_do_not_become_leaf_oracles(self):
        source = {'ROOT': 'Sharing is outside the core scope.',
                  'GROUP': 'Supports viewing, opening, creating, renaming, importing and exporting workbooks.',
                  'A': 'Open a workbook and show the stored cells.'}
        ancestry = {'A': ['ROOT', 'GROUP', 'A']}
        body = {'obligations': [{'requirement_id': key, 'quote': quote, 'outcome': quote,
                                'branch': 'success', 'applies_to': ['A']} for key, quote in source.items()],
                'gaps': []}
        rows, errors, global_errors = parse_obligation_details(json.dumps(body), source, ancestry)
        self.assertFalse(errors['A'] or global_errors)
        self.assertEqual({row.get('kind', 'test') for row in rows}, {'context', 'summary', 'test'})
        tree = {'id': 'ROOT', 'children': [{'id': 'GROUP', 'children': [
            {'id': 'A', 'name': 'View and Open records'},
            {'id': 'B', 'name': 'Create and Rename records'},
            {'id': 'C', 'name': 'Import and Export records'}]}]}
        flow = Mock(derived_obligations=rows, requirement_tree=tree)
        self.assertEqual([row['requirement_id'] for row in applicable_obligations(flow, 'A')], ['A'])
        tree['children'][0]['children'].pop()
        self.assertEqual([row['requirement_id'] for row in applicable_obligations(flow, 'A')], ['GROUP', 'A'])
        self.assertEqual(obligation_kind('ROOT', 'A',
                         'Records must persist after refresh; sharing is outside the core scope.'), 'test')
        self.assertEqual(obligation_kind('GROUP', 'A',
                         'Supports viewing, opening and creating records. Every saved change must persist.'), 'test')

    def test_dynamic_health_paths_only_use_declared_parameterized_pages(self):
        design = {'pages': [{'path': '/'}, {'path': '/workbook/:id'}, {'path': '/users/:userId'},
                            {'path': 'https://other.test/x'}, {'path': '/search?term=:query'}]}
        self.assertEqual(dynamic_health_patterns(design), ['/workbook/:id', '/users/:userId'])

    def test_post_code_review_window_scales_with_leaf_count_and_preserves_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_nodes = [{'id': str(i)} for i in range(24)]
            flow.remaining = Mock(return_value=30000)
            flow.final_phase_reserve = Mock(return_value=1000)
            self.assertEqual(flow.derived_build_spec_window(), 720)
            flow.derived_build_spec_seconds = 720 * 23
            self.assertEqual(flow.derived_build_spec_window(), 720)
            flow.derived_build_spec_seconds = 720 * 24
            self.assertEqual(flow.derived_build_spec_window(), 0)
            flow.derived_build_spec_seconds = 0
            flow.remaining = Mock(return_value=1050)
            self.assertEqual(flow.derived_build_spec_window(), 0)

    def test_same_category_review_batches_three_leaves_with_independent_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.runner = Mock()
            flow.phase_plan = {'leaf_phase': {key: 'P' for key in 'ABCD'}}
            flow.spec_map = {key: [f'{key}.spec.ts'] for key in 'ABCD'}
            flow.remaining = Mock(return_value=30000)
            flow.final_phase_reserve = Mock(return_value=1000)
            flow.metric = Mock()
            flow.write_derived_handoff = Mock()
            flow.snapshot_protected = Mock()
            flow.preflight_derived_specs = Mock(side_effect=lambda _nodes: setattr(flow, '_derived_preflight_node_ids', {'A'}))
            batches = []
            def prepare(nodes):
                keys = [node['id'] for node in nodes]
                batches.append(keys)
                flow._derived_build_spec_attempted_ids = set(keys)
            flow.prepare_derived_build_batch = prepare
            flow.derived_review_needed = Mock(return_value=False)
            flow.derived_has_runnable_cases = Mock(return_value=True)
            accepted = []
            flow.acceptance_loop = Mock(side_effect=lambda node_id, *_args: accepted.append(node_id) or True)
            flow.derived_completeness_pass = Mock()
            flow.review_derived_after_implementation([{'id': key} for key in 'ABCD'])
            self.assertEqual(batches, [['B', 'C', 'D']])
            self.assertEqual(accepted, list('ABCD'))


if __name__ == '__main__':
    unittest.main()
