import io
import json
import tempfile
import time
import unittest
import argparse
from pathlib import Path

from derived_case_review import parse_review_decisions, review_request_admissible, validate_review
from generation_checks import check_batch, missing_backend_module_errors, preflight_failure_evidence
from llm_proxy import LlmProxy, collect_codegen_stream, usage_record
from scenario_review import build_prompt, proposal_problems, review_targets, validate_proposal
from scenario_tests import suite_fixtures
from main import Flow


class ReviewBoundaryTests(unittest.TestCase):
    def test_one_fence_and_exact_outcome_quotes(self):
        decision = {'id': 'a', 'status': 'approved_behavior',
                    'requirement_quote': 'The application rejects the invalid input.',
                    'test_quote': "await h.expectAbsent(page, 'invalid');",
                    'reason': 'The absence proves the negative outcome.'}
        wrapped = '```json\n' + json.dumps([decision]) + '\n```'
        self.assertEqual(parse_review_decisions(wrapped, {'a'}), ([decision], None))
        self.assertEqual(parse_review_decisions(wrapped + '\nApproved.', {'a'})[1], 'format_invalid')
        self.assertEqual(parse_review_decisions(json.dumps([decision, decision]), {'a'})[1], 'schema_invalid')
        row = {'status': 'unreviewed', 'outcome': 'The application rejects the invalid input.',
               'case': "await h.expectAbsent(page, 'invalid');\nawait h.clickNamed(page, 'submit');"}
        self.assertTrue(validate_review(row, decision))
        decision['requirement_quote'] = 'The user clicked submit.'
        self.assertFalse(validate_review(row, decision))
        decision['requirement_quote'] = row['outcome']
        decision['test_quote'] = "await h.clickNamed(page, 'submit');"
        self.assertFalse(validate_review(row, decision))

    def test_six_requests_leave_one_for_each_of_six_categories(self):
        phases = [str(n) for n in range(6)]
        counts = {}
        spent = 0
        for phase in phases:
            self.assertTrue(review_request_admissible(phase, phases, counts, spent, 6))
            counts[phase] = 1
            spent += 1
            if phase != phases[-1]:
                self.assertFalse(review_request_admissible(phase, phases, counts, spent, 6))
        self.assertFalse(review_request_admissible(phases[-1], phases, counts, spent, 6))


class DerivedPreflightTests(unittest.TestCase):
    def test_category_context_is_shared_but_assertions_stay_local(self):
        target = {'id': 'S1', 'title': 'Sign in', 'node_id': 'a1', 'name': 'Authentication',
                  'description': 'Sign in shows Home.', 'steps': ['WHEN: Sign in.', 'THEN: Show Home.'],
                  'allowed': ['Home']}
        fixtures = suite_fixtures([])
        prompt = build_prompt([target], fixtures, '{"category":"Accounts","requirements":["a1","a2"]}')
        self.assertIn('TOP-LEVEL CATEGORY CONTRACT', prompt)
        self.assertIn('"a2"', prompt)
        self.assertIn('each assertion must still be grounded in its own scenario', prompt)

    def test_categories_are_prepared_before_code_and_frozen(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.phase_plan = {'phases': [{'id': 'A'}, {'id': 'B'}],
                               'leaf_phase': {'a1': 'A', 'b1': 'B', 'a2': 'A'}}
            flow.budget = 3600
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 300
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            batches = []
            flow.prepare_derived_spec_batch = lambda nodes: batches.append([n['id'] for n in nodes])
            flow.preflight_derived_specs([{'id': 'a1'}, {'id': 'b1'}, {'id': 'a2'}])
            self.assertEqual(batches, [['a1', 'a2'], ['b1']])
            self.assertTrue(flow.derived_specs_frozen)

    def test_no_preflight_time_never_blocks_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.budget = 600
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 300
            flow.metric = lambda *args, **kwargs: None
            flow.prepare_derived_spec_batch = lambda nodes: self.fail('should not spend test time')
            flow.preflight_derived_specs([{'id': 'a1'}])
            self.assertTrue(flow.derived_specs_frozen)

    def test_token_limit_leaves_later_category_for_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.phase_plan = {'phases': [{'id': 'A'}, {'id': 'B'}],
                               'leaf_phase': {'a': 'A', 'b': 'B'}}
            flow.budget = 3600
            flow.t_start = time.time()
            flow.max_total_tokens = 1000
            flow.llm_proxy = argparse.Namespace(total_tokens=100)
            flow.final_phase_reserve = lambda: 300
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            batches = []
            def prepare(nodes):
                batches.append(nodes[0]['id'])
                flow.llm_proxy.total_tokens += 100
            flow.prepare_derived_spec_batch = prepare
            flow.preflight_derived_specs([{'id': 'a'}, {'id': 'b'}])
            self.assertEqual(batches, ['a'])
            self.assertTrue(flow.derived_specs_frozen)


class InvalidCsvFixtureTests(unittest.TestCase):
    def test_negative_import_requires_rejection_and_no_partial_workbook(self):
        node = {'id': 'REQ-1-3-1', 'name': 'CSV import', 'children': [],
                'description': ('The page has controls "Import CSV", "CSV file", "Confirm import". '
                                'Invalid CSV with unclosed quote must show "Invalid CSV file format. Import failed." '
                                'and not create a workbook.'),
                'scenarios': [{'name': 'bad CSV', 'steps': [
                    {'keyword': 'GIVEN', 'content': 'The visitor starts at home.'},
                    {'keyword': 'WHEN', 'content': 'Upload invalid CSV and confirm import.'},
                    {'keyword': 'THEN', 'content': 'Invalid CSV file format. Import failed. and no workbook remains.'}]}]}
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        steps = [{'op': 'click', 'target': 'Import CSV'},
                 {'op': 'upload', 'target': 'CSV file', 'value': '$INVALID_CSV'},
                 {'op': 'click', 'target': 'Confirm import'},
                 {'op': 'expect_visible', 'target': 'Invalid CSV file format. Import failed.'},
                 {'op': 'open', 'target': 'home'},
                 {'op': 'expect_absent', 'target': '$INVALID_CSV_NAME'}]
        proposal = {'confidence': 0.9, 'steps': steps}
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("'derived-invalid.csv'", source)
        self.assertIn("h.expectAbsent(page, 'derived-invalid')", source)
        for omitted in (2, 3, 4, 5):
            bad = {**proposal, 'steps': [step for i, step in enumerate(steps) if i != omitted]}
            self.assertTrue(proposal_problems(bad, target, fixtures), omitted)
        target['seed_kinds'] = [('workbook', 'Q3 Sales'), ('cell A1 value', 'Region')]
        self.assertTrue(proposal_problems(proposal, target, fixtures))
        retained = {**proposal, 'steps': steps + [{'op': 'open', 'target': 'Q3 Sales'},
                                                  {'op': 'expect_cell', 'target': 'A1', 'value': 'Region'}]}
        target['allowed'].extend(['Q3 Sales', 'A1', 'Region'])
        self.assertEqual(proposal_problems(retained, target, fixtures), [])
        target['description'] = 'There is no invalid CSV contract.'
        target['steps'] = ['WHEN: Open the import page.', 'THEN: Show the import controls.']
        self.assertTrue(proposal_problems(proposal, target, fixtures))


class ModuleAndStreamTests(unittest.TestCase):
    def test_unstartable_partial_snapshot_is_not_called_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.tests_dir = None
            flow.has_app = lambda: True
            flow.last_codegen_written = ['backend/routes/auth.js']
            flow._generation_gate_result = {'errors': [], 'checked': ['syntax backend/routes/auth.js'],
                                            'deferred': ['backend module: missing ../lib/session']}
            self.assertFalse(flow.retain_safe_no_spec_partial('REQ-1'))

    def test_glm53_route_default_effort_respects_explicit_override(self):
        from llm_proxy import inject_reasoning, route_request
        from unittest.mock import patch
        body = json.dumps({'model': 'base', 'messages': []}).encode()
        rules = [{'model': 'glm-5.3-flash', 'phases': ['implement']}]
        with patch.dict('os.environ', {}, clear=True):
            routed = json.loads(route_request(body, rules, 'implement'))
            self.assertEqual(routed['reasoning_effort'], 'medium')
            self.assertEqual(json.loads(route_request(body, rules, 'implement', 'low',
                                                      'whole application implement'))['reasoning_effort'], 'low')
            self.assertEqual(json.loads(inject_reasoning(body.replace(b'base', b'glm-5.3-flash'), 'medium'))
                             ['reasoning_effort'], 'medium')
            for model in ('glm-5.3-flash', 'qwen3.7-plus'):
                kernel = json.dumps({'model': model, 'messages': [], 'reasoning_effort': 'medium'}).encode()
                lowered = json.loads(inject_reasoning(kernel, 'low', force=True))
                self.assertEqual(lowered['reasoning_effort'], 'low')
                self.assertEqual(json.loads(inject_reasoning(kernel, 'low'))['reasoning_effort'], 'medium')
        with patch.dict('os.environ', {'OCTOS_ARC_REASONING': 'low'}):
            self.assertEqual(json.loads(route_request(body, rules, 'implement'))['reasoning_effort'], 'low')
        rules[0]['parameters'] = {'reasoning_effort': 'high'}
        self.assertEqual(json.loads(route_request(body, rules, 'implement'))['reasoning_effort'], 'high')

    def test_backend_missing_edge_is_deferred_then_resolves(self):
        source = "const session = require('../lib/session');\nimport x from '../lib/other.js';\n"
        sources = {'backend/routes/auth.js': source}
        self.assertEqual(len(missing_backend_module_errors(sources, sources)), 2)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = check_batch(root, [], sources=sources)
            self.assertEqual(result['readiness'], 'build_deferred')
            self.assertFalse(result['errors'])
            self.assertEqual(sum(x.startswith('backend module:') for x in result['deferred']), 2)
            sources['backend/lib/session.js'] = 'module.exports = {};'
            sources['backend/lib/other.js'] = 'export default {};'
            self.assertFalse(missing_backend_module_errors(sources, sources))
        self.assertFalse(missing_backend_module_errors(
            {'backend/routes/a.js': "// require('../lib/missing')\nconst x = require(path);"},
            ['backend/routes/a.js']))

    def test_incomplete_provider_stream_cannot_be_salvaged_or_precisely_billed(self):
        event = {'choices': [{'index': 0, 'delta': {'content': '<<<FILE a.js>>>\nx\n<<<END FILE>>>'},
                              'finish_reason': 'stop'}]}
        payload, stop = collect_codegen_stream(io.BytesIO(('data: ' + json.dumps(event) + '\n').encode()))
        self.assertEqual(stop, 'incomplete_stream')
        data = json.loads(payload)
        self.assertEqual(data['arc_stream_integrity'], 'upstream_incomplete')
        self.assertEqual(data['arc_stream_events'], 1)
        self.assertIsNone(usage_record(payload, 1, 'low'))
        proxy = LlmProxy('http://127.0.0.1:1/v1', 'low')
        proxy.turn_serial = 1
        proxy.capture_truncated_reply(payload, {'turn_serial': 1, 'label': 'wave'})
        self.assertIsNone(proxy.take_truncated_reply('wave'))

    def test_preflight_excerpts_redact_credentials(self):
        evidence = preflight_failure_evidence('npm ERR! Authorization: Bearer abc123veryprivate '
                                              'https://user:pass@example.test/path?key=hidden')
        self.assertEqual(evidence['cause_class'], 'dependency_install')
        self.assertNotIn('abc123veryprivate', evidence['error_excerpt'])
        self.assertNotIn('hidden', evidence['error_excerpt'])
        self.assertNotIn('user:pass', evidence['error_excerpt'])


if __name__ == '__main__':
    unittest.main()
