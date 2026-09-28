import io
import json
import tempfile
import time
import unittest
import argparse
from unittest.mock import patch
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
        self.assertFalse(validate_review(row, decision), 'a setup assertion is not an outcome')
        row['case'] = "await h.resetState(page);\nawait h.expectAbsent(page, 'invalid');"
        self.assertFalse(validate_review(row, decision), 'fixture reset is not a feature action')
        row['case'] = "await h.clickNamed(page, 'submit');\nawait h.expectAbsent(page, 'invalid');"
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

    def test_download_helper_is_an_action_and_oracle_in_one_call(self):
        row = {'status': 'unreviewed', 'outcome': 'The user downloads a CSV with the saved Region value.',
               'case': "await h.expectDownload(page, 'Export CSV', '.csv', ['Region']);"}
        verdict = {'status': 'approved_behavior',
                   'requirement_quote': row['outcome'],
                   'test_quote': row['case'],
                   'reason': 'The helper clicks the export control and inspects the downloaded file.'}
        self.assertTrue(validate_review(row, verdict))


class DerivedPreflightTests(unittest.TestCase):
    def test_review_queue_reserves_a_cross_leaf_final_measurement(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / 'derived-tests'
            tests.mkdir()
            for node_id in 'ABC':
                (tests / f'{node_id}.spec.ts').write_text(f"test('{node_id}', () => {{}});\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.tests_dir = tests
            flow.runner = SimpleNamespace(timeout_ms=30000)
            flow.final_measurement_reserve = lambda: 120
            flow.repair_minimum = lambda: 60
            flow._derived_post_code_review_active = True
            self.assertEqual(flow.final_phase_reserve(), 390)
            flow._in_final_repair = True  # completeness uses this lower generic reserve
            self.assertEqual(flow.final_phase_reserve(), 120)
            self.assertEqual(flow.derived_review_reserve(), 390)

    def test_final_rehearsal_reserves_rerun_only_for_reviewed_derived_specs(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from acceptance import RunSummary, TestOutcome
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / 'derived-tests'
            tests.mkdir()
            for node_id in 'AB':
                (tests / f'{node_id}.spec.ts').write_text(f"test('{node_id}', () => {{}});\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.tests_dir = tests
            flow.runner = SimpleNamespace(timeout_ms=30000)
            flow.final_measurement_reserve = lambda: 120
            flow.repair_minimum = lambda: 60
            flow.derived_review_needed = lambda node_id: node_id != 'A'
            self.assertEqual(flow.derived_review_reserve(), 330)  # both files need review time
            self.assertEqual(flow.final_rehearsal_reserve(), 270)  # only A can rerun
            flow.remaining = Mock(return_value=270)
            flow.metric = Mock()
            flow.record_full_suite = Mock()
            flow.app_source_digest = Mock(return_value='same-source')
            flow.run_specs = Mock(return_value=RunSummary(
                results=[TestOutcome('A', True, 'passed', 1, file='A.spec.ts')], passed=1, total=1))
            flow.final_acceptance_passes()
            flow.run_specs.assert_called_once_with(['A.spec.ts'], workers=1, grader_like=True)
            flow.derived_review_needed = lambda node_id: True
            self.assertEqual(flow.final_rehearsal_reserve(), 120)
            flow.derived_as_specs = False
            self.assertEqual(flow.final_rehearsal_reserve(), 120)

    def test_final_stage_corrected_case_gets_one_bounded_independent_rereview(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            ready = {'A': False}
            flow.derived_review_needed = lambda node_id: not ready[node_id]
            flow.remaining = Mock(return_value=1000)
            flow.final_measurement_reserve = lambda: 120
            flow.repair_minimum = lambda: 60
            flow.metric = Mock()
            flow.write_derived_handoff = Mock()
            flow.snapshot_protected = Mock()
            flow.review_derived_cases = Mock(side_effect=lambda nodes: ready.__setitem__('A', True))
            self.assertTrue(flow.rereview_corrected_derived_leaf('A'))
            flow.review_derived_cases.assert_called_once_with({'A'})
            # One measurement plus repair is insufficient: correction needs
            # a validation run and still leaves a final measurement window.
            flow.remaining.return_value = 320
            ready['A'] = False
            self.assertFalse(flow.rereview_corrected_derived_leaf('A'))
            flow.review_derived_cases.assert_called_once()

    def test_final_derived_acceptance_rechecks_corrected_spec_before_repair(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from acceptance import RunSummary, TestOutcome
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / 'derived-tests'
            tests.mkdir()
            spec = tests / 'A.spec.ts'
            spec.write_text("test('case', () => { oldOracle(); });\n")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.tests_dir = tests
            flow.runner = SimpleNamespace(timeout_ms=30000)
            flow.spec_map = {'A': ['A.spec.ts']}
            flow.requirement_nodes = {'A': {'description': 'Save state'}}
            flow.remaining = Mock(return_value=1000)
            flow.final_measurement_reserve = lambda: 120
            flow.repair_minimum = lambda: 60
            flow.final_retry_admission = lambda: 300
            flow.wound_down = Mock(return_value=False)
            flow.metric = Mock()
            flow.app_source_digest = Mock(return_value='same-source')
            flow.record_full_suite = Mock()
            ready = {'A': True}
            flow.derived_review_needed = lambda node_id: not ready[node_id]
            failed = RunSummary(results=[TestOutcome('case', False, 'failed', 1, file='A.spec.ts')],
                                passed=0, total=1)
            passed = RunSummary(results=[TestOutcome('case', True, 'passed', 1, file='A.spec.ts')],
                                passed=1, total=1)
            flow.run_specs = Mock(side_effect=[failed, passed])
            def accept(*args, **kwargs):
                if flow.acceptance_loop.call_count == 1:
                    spec.write_text("test('case', () => { correctedOracle(); });\n")
                    ready['A'] = False
                    return None
                return True
            flow.acceptance_loop = Mock(side_effect=accept)
            flow.rereview_corrected_derived_leaf = Mock(side_effect=lambda node_id: ready.__setitem__(node_id, True) or True)
            flow.final_acceptance_passes()
            self.assertEqual(flow.acceptance_loop.call_count, 2)
            flow.rereview_corrected_derived_leaf.assert_called_once_with('A')
            self.assertEqual(flow.run_specs.call_count, 2)
            self.assertEqual(flow.run_specs.call_args.args[0], ['A.spec.ts'])

    def test_failed_implementation_waits_behind_delivered_leaf_review(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.impl_failed = ['A']
            flow.runner = Mock()
            flow.spec_map = {'A': ['A.spec.ts'], 'B': ['B.spec.ts']}
            flow.remaining = Mock(return_value=5000)
            flow.final_phase_reserve = lambda: 300
            flow.derived_review_needed = lambda node_id: False
            flow.metric = Mock()
            flow.write_derived_handoff = Mock()
            flow.snapshot_protected = Mock()
            flow.driver = Mock()
            events = []
            flow.preflight_derived_specs = lambda nodes: events.append(('preflight', [n['id'] for n in nodes]))
            flow.prepare_derived_build_batch = lambda nodes: events.append(('batch', [n['id'] for n in nodes]))
            flow.acceptance_loop = lambda node_id, *_args: events.append(('accept', node_id)) or True
            flow.derived_completeness_pass = lambda nodes: events.append(('completeness', [n['id'] for n in nodes]))
            flow.review_derived_after_implementation([{'id': 'A'}, {'id': 'B'}])
            self.assertEqual(events, [('preflight', ['B']), ('batch', ['B']),
                                      ('accept', 'B'), ('completeness', ['B', 'A'])])
            flow.driver.end_scope.assert_called_once_with('node')

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
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_PREFLIGHT_CATEGORIES': '0'}):
                flow.preflight_derived_specs([{'id': 'a1'}, {'id': 'b1'}, {'id': 'a2'}])
            self.assertEqual(batches, [['a1', 'a2'], ['b1']])
            self.assertFalse(flow.derived_specs_frozen)

    def test_first_category_receives_only_its_time_slice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.phase_plan = {'phases': [{'id': 'A'}, {'id': 'B'}, {'id': 'C'}],
                               'leaf_phase': {'a': 'A', 'b': 'B', 'c': 'C'}}
            flow.budget = 6000
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 600
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            deadlines = []
            flow.prepare_derived_spec_batch = lambda nodes: deadlines.append(flow.derived_preflight_deadline)
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_PREFLIGHT_CATEGORIES': '0'}):
                flow.preflight_derived_specs([{'id': key} for key in 'abc'])
            self.assertEqual(len(deadlines), 3)
            self.assertLess(deadlines[0], deadlines[1])
            self.assertLess(deadlines[1], deadlines[2])

    def test_unused_preflight_time_revisits_only_partially_covered_category(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_tests_dir = root
            flow.phase_plan = {'phases': [{'id': 'A'}, {'id': 'B'}],
                               'leaf_phase': {'a': 'A', 'b': 'B'}}
            flow.budget = 6000
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 600
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            flow.derived_augmentation_attempts = {}
            coverage = {'a': [0, 2], 'b': [0, 1]}
            flow.derived_scenario_coverage = lambda node_id: dict(zip(('covered', 'total'), coverage[node_id]))
            calls = []
            def prepare(nodes):
                node_id = nodes[0]['id']
                calls.append(node_id)
                flow.derived_augmentation_attempts[node_id] = flow.derived_augmentation_attempts.get(node_id, 0) + 1
                coverage[node_id][0] += 1
            flow.prepare_derived_spec_batch = prepare
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_PREFLIGHT_CATEGORIES': '0'}):
                flow.preflight_derived_specs([{'id': 'a'}, {'id': 'b'}])
            self.assertEqual(calls, ['a', 'b', 'a'])

    def test_default_preflight_starts_code_after_first_leaf_and_jit_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.phase_plan = {'phases': [{'id': 'A'}, {'id': 'B'}],
                               'leaf_phase': {'a': 'A', 'a2': 'A', 'b': 'B'}}
            flow.budget = 10000
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 600
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            calls = []
            flow.prepare_derived_spec_batch = lambda nodes: calls.append(
                ([node['id'] for node in nodes], flow.derived_preflight_deadline - time.monotonic()))
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_PREFLIGHT_CATEGORIES': '1',
                                            'OCTOS_ARC_DERIVED_FIRST_CODE_SECONDS': '120',
                                            'OCTOS_ARC_DERIVED_CODE_BATCH_SPEC_SECONDS': '45'}):
                flow.preflight_derived_specs([{'id': 'a'}, {'id': 'a2'}, {'id': 'b'}])
                self.assertEqual([ids for ids, _ in calls], [['a']])
                self.assertLessEqual(calls[0][1], 121)
                flow.prepare_derived_build_batch([{'id': 'a'}])
                flow.prepare_derived_build_batch([{'id': 'a2'}])
                flow.prepare_derived_build_batch([{'id': 'a2'}])
            self.assertEqual([ids for ids, _ in calls], [['a'], ['a2']])
            self.assertLessEqual(calls[1][1], 46)

    def test_startup_follows_implementation_order_when_phase_plan_differs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.phase_plan = {'phases': [{'id': 'B'}, {'id': 'A'}],
                               'leaf_phase': {'a': 'A', 'b': 'B'}}
            flow.budget = 5000
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 300
            flow.wound_down = lambda: False
            flow.metric = lambda *args, **kwargs: None
            calls = []
            flow.prepare_derived_spec_batch = lambda nodes: calls.append([n['id'] for n in nodes])
            flow.preflight_derived_specs([{'id': 'a'}, {'id': 'b'}])
            self.assertEqual(calls, [['a']])
            self.assertEqual(flow._derived_preflight_node_ids, {'a'})

    def test_per_leaf_handoff_status_does_not_claim_pending_review_is_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_tests_dir = root / 'derived-tests'
            flow.derived_tests_dir.mkdir()
            flow.derived_nodes = [{'id': 'a'}, {'id': 'b'}]
            (flow.derived_tests_dir / 'a.spec.ts').write_text('test("a", () => {});')
            flow._derived_preflight_node_ids = {'a'}
            flow.derived_scenario_coverage = lambda node_id: {
                'covered': 1 if node_id == 'a' else 0, 'total': 1}
            flow.derived_review_needed = lambda node_id: node_id == 'b'
            flow.derived_obligation_status = {'b': {'status': 'incomplete', 'attempts': 2,
                                                    'candidate_obligations': 3,
                                                    'errors': ['missing inherited source ROOT']}}
            flow.write_derived_handoff()
            target = flow.derived_tests_dir / 'review' / 'spec-handoff.json'
            rows = {row['node_id']: row for row in json.loads(target.read_text())['nodes']}
            self.assertEqual(rows['a']['status'], 'reviewed')
            self.assertEqual(rows['b']['status'], 'not_generated')
            self.assertFalse(rows['b']['reviewed'])
            self.assertEqual(rows['b']['implementation_admission'], 'allowed')
            self.assertEqual(rows['b']['test_admission'], 'waiting_for_review')
            self.assertEqual(rows['b']['obligation_attempts'], 2)
            self.assertEqual(rows['b']['candidate_obligations'], 3)
            self.assertEqual(rows['b']['obligation_errors'], ['missing inherited source ROOT'])
            flow._derived_build_spec_attempted_ids = {'b'}
            flow.write_derived_handoff()
            rows = {row['node_id']: row for row in json.loads(target.read_text())['nodes']}
            self.assertEqual(rows['b']['status'], 'review_pending')

    def test_code_waves_do_not_wait_for_derived_spec_review(self):
        from unittest.mock import Mock
        from test_whole_app_v5 import WholeAppTests
        case = WholeAppTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        flow = case.flow
        flow.derived_as_specs = True
        flow._derived_preflight_node_ids = {'A'}
        flow.derived_review_needed = Mock(return_value=True)
        flow.final_phase_reserve = lambda: 300
        flow.derived_build_spec_seconds = 0
        events = []
        flow.prepare_derived_build_batch = lambda nodes: events.append(('spec', [n['id'] for n in nodes]))
        flow.batch_spec_bodies = lambda ids: events.append(('body', ids)) or 'spec'
        flow.codegen_implement_prompt = Mock(return_value='wave prompt')
        def generate(*args, **kwargs):
            flow.last_codegen_written = ['frontend/src/App.jsx']
            events.append(('code', None))
            return True, 'files'
        flow.codegen_turn = Mock(side_effect=generate)
        with patch.dict('os.environ', {'OCTOS_ARC_WHOLE_APP_WAVE_NODES': '3',
                                        'OCTOS_ARC_CODEGEN_OUTPUT_TOKENS': '999999'}):
            self.assertTrue(flow.whole_app_waves(case.tree, case.nodes))
        self.assertEqual([item for item in events if item[0] == 'spec'], [])
        self.assertEqual(flow.codegen_turn.call_count, 1)
        self.assertEqual(flow.whole_app_generated_ids, {'A', 'B', 'C'})

    def test_candidate_tests_cannot_run_as_application_acceptance(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_review_needed = Mock(return_value=True)
            flow.metric = Mock()
            flow.runner = Mock()
            summary = flow.run_specs(['A.spec.ts'])
            self.assertIn('await complete independent review', summary.error)
            self.assertIn('no fully reviewed', flow.run_specs([]).error)
            flow.runner.run.assert_not_called()
            self.assertIsNone(flow.acceptance_loop('A', ['A.spec.ts'], time.time() + 120))
            flow.runner.run.assert_not_called()

    def test_after_code_queue_accepts_one_reviewed_leaf_without_waiting_for_siblings(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.runner = Mock()
            flow.spec_map = {'A': ['A.spec.ts'], 'B': ['B.spec.ts']}
            flow.node_timeout = 120
            flow.remaining = Mock(return_value=5000)
            flow.final_measurement_reserve = Mock(return_value=100)
            flow.metric = Mock()
            flow.write_derived_handoff = Mock()
            flow.snapshot_protected = Mock()
            events, ready = [], set()
            def first(nodes):
                events.append('review_A')
                flow._derived_preflight_node_ids = {'A'}
                ready.add('A')
            def later(nodes):
                events.append('review_B')
                ready.add('B')
            flow.preflight_derived_specs = first
            flow.prepare_derived_build_batch = later
            flow.derived_review_needed = lambda node_id: node_id not in ready
            flow.acceptance_loop = lambda node_id, *_args: events.append('accept_' + node_id) or True
            flow.derived_completeness_pass = lambda nodes: events.append('completeness')
            flow.review_derived_after_implementation([{'id': 'A'}, {'id': 'B'}])
            self.assertEqual(events, ['review_A', 'accept_A', 'review_B', 'accept_B', 'completeness'])
            self.assertFalse(flow._derived_post_code_review_active)

    def test_code_prompt_uses_requirements_instead_of_candidate_test(self):
        from requirement_contracts import compile_contracts
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / 'derived-tests'
            tests.mkdir()
            (tests / 'A.spec.ts').write_text("test('WRONG_ORACLE', () => {});")
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.tests_dir = tests
            flow.spec_map = {'A': ['A.spec.ts']}
            flow.requirement_contracts = compile_contracts([{
                'id': 'A', 'name': 'Save item', 'description': 'Saving shows Saved.',
                'scenarios': [{'steps': [{'keyword': 'GIVEN', 'content': 'the form is open'},
                                         {'keyword': 'WHEN', 'content': 'Save is clicked'},
                                         {'keyword': 'THEN', 'content': 'Saved is visible'}]}]}])
            flow._generation_active = True
            self.assertIn('Saved', flow.spec_bodies('A'))
            self.assertIn('Saved', flow.batch_spec_bodies(['A']))
            self.assertIn('Saved', flow.tests_prompt_for('A'))
            self.assertNotIn('WRONG_ORACLE', flow.spec_bodies('A'))
            self.assertNotIn('WRONG_ORACLE', flow.batch_spec_bodies(['A']))
            self.assertNotIn('WRONG_ORACLE', flow.tests_prompt_for('A'))
            stable_code_inputs = (flow.spec_bodies('A'), flow.batch_spec_bodies(['A']),
                                  flow.tests_prompt_for('A'))
            (tests / 'A.spec.ts').write_text("test('CHANGED_CANDIDATE', () => {});")
            self.assertEqual(stable_code_inputs, (flow.spec_bodies('A'),
                                                  flow.batch_spec_bodies(['A']),
                                                  flow.tests_prompt_for('A')))
            from unittest.mock import Mock
            flow.turn = Mock(return_value=(False, ''))
            node = {'id': 'A', 'name': 'Save item', 'description': 'Saving shows Saved.'}
            flow.design(node, [node], time.time() + 60)
            design_prompt = flow.turn.call_args.args[0]
            self.assertIn('Do not read or run generated test files', design_prompt)
            self.assertNotIn('Read the acceptance spec files', design_prompt)
            self.assertNotIn('WRONG_ORACLE', design_prompt)
            self.assertIn('do not read generated test files', flow.inline_design_instruction('A'))
            flow._generation_active = False
            self.assertIn('CHANGED_CANDIDATE', flow.spec_bodies('A'))

    def test_jit_spec_exception_and_zero_budget_do_not_withhold_implementation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.budget = 10000
            flow.t_start = time.time()
            flow.final_phase_reserve = lambda: 600
            metrics = []
            flow.metric = lambda name, **kwargs: metrics.append((name, kwargs))
            calls = []
            def failed(nodes):
                calls.append([node['id'] for node in nodes])
                raise RuntimeError('test planner unavailable')
            flow.prepare_derived_spec_batch = failed
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_CODE_BATCH_SPEC_SECONDS': '45',
                                            'OCTOS_ARC_DERIVED_CODE_TOTAL_SPEC_SECONDS': '45'}):
                flow.prepare_derived_build_batch([{'id': 'a'}])
                flow.prepare_derived_build_batch([{'id': 'a'}])
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_CODE_TOTAL_SPEC_SECONDS': '0'}):
                flow.prepare_derived_build_batch([{'id': 'b'}])
            self.assertEqual(calls, [['a']])
            self.assertEqual(metrics[0][0], 'derived_build_spec')
            self.assertEqual(flow.derived_preflight_deadline, float('inf'))

    def test_partial_leaf_is_planned_again_even_after_one_accepted_script(self):
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.derived_as_specs = True
            flow.derived_tests_dir = root
            flow.derived_nodes = [{'id': 'a'}]
            flow.derived_augmented_nodes = {'a'}
            flow.derived_augmentation_attempts = {'a': 1}
            flow.derived_scenario_coverage = Mock(return_value={'covered': 1, 'total': 2})
            flow.augment_derived_tests = Mock()
            flow.review_derived_cases = Mock()
            flow.adopt_derived_specs = Mock()
            flow.snapshot_protected = Mock()
            flow.metric = Mock()
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_LLM': '1',
                                            'OCTOS_ARC_DERIVED_CASE_CORRECTION_REQUESTS': '0'}):
                flow.prepare_derived_spec_batch(flow.derived_nodes)
            flow.augment_derived_tests.assert_called_once_with(flow.derived_nodes)

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
            self.assertFalse(flow.derived_specs_frozen)

    def test_explicit_token_limit_leaves_later_category_for_code(self):
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
            from unittest.mock import patch
            with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_PREFLIGHT_TOKENS': '100'}):
                flow.preflight_derived_specs([{'id': 'a'}, {'id': 'b'}])
            self.assertEqual(batches, ['a'])
            self.assertFalse(flow.derived_specs_frozen)


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
                                                      'whole application implement'))['reasoning_effort'], 'medium')
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
