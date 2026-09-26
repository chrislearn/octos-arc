import argparse
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from acceptance import AcceptanceRunner, RunSummary, TestOutcome
from main import Flow
from test_policy import TestPolicy, grounded_verdict, test_block
from generation_checks import missing_export_errors, placeholder_overwrites
from llm_proxy import context_limit_error, LlmProxy

SOURCE = "import { test, expect } from '@playwright/test';\ntest('wrong', async () => { expect(1).toBe(2); });\ntest('valid', async () => { expect(1).toBe(1); });\n"

class TestPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / '.arc' / 'derived-tests'
        self.directory.mkdir(parents=True)
        (self.directory / 'A.spec.ts').write_text(SOURCE)
        self.policy = TestPolicy(self.directory, {'description': 'The result must equal one.'}, 'helper-v1')

    def decide(self):
        return self.policy.decide('A.spec.ts', 'wrong', SOURCE, 'invalid', 'Two independent evidence-backed reviews', [{}, {}])

    def test_decision_is_bound_to_requirements_helpers_and_entire_file(self):
        self.decide()
        self.assertEqual(set(self.policy.quarantines()), {'A.spec.ts'})
        self.assertEqual(TestPolicy(self.directory, {}, 'helper-v1').quarantines(), {})
        self.assertEqual(TestPolicy(self.directory, {'description': 'The result must equal one.'}, 'helper-v2').quarantines(), {})
        (self.directory / 'A.spec.ts').write_text(SOURCE + '// changed\n')
        self.assertEqual(self.policy.quarantines(), {})
        self.assertTrue((self.policy.control / 'test-decisions.jsonl').exists())

    def test_duplicate_titles_and_path_escape_are_not_filterable(self):
        with self.assertRaises(ValueError):
            self.policy.decide('A.spec.ts', 'wrong', SOURCE + SOURCE, 'invalid', 'e')
        self.decide()['file'] = '../outside.spec.ts'
        self.assertEqual(self.policy.quarantines(), {})
        self.policy.records['malformed'] = {'context': self.policy.context, 'title': None, 'file': None}
        self.assertEqual(self.policy.quarantines(), {})

    def test_unresolved_and_valid_are_never_skipped(self):
        self.policy.decide('A.spec.ts', 'wrong', SOURCE, 'unresolved', 'Reviewers disagree')
        self.assertEqual(self.policy.quarantines(), {})
        self.policy.decide('A.spec.ts', 'wrong', SOURCE, 'valid', 'Application must be repaired')
        self.assertEqual(self.policy.quarantines(), {})

    def test_no_confidence_only_or_unquoted_verdict(self):
        review = {'verdict': 'oracle_dispute', 'reason_code': 'requirement_conflict',
                  'requirement_quote': 'The result must equal one.', 'test_quote': 'expect(1).toBe(2)',
                  'evidence': 'Test expects two although requirement explicitly requires one.'}
        self.assertTrue(grounded_verdict(review, 'The result must equal one.', test_block(SOURCE, 'wrong')))
        self.assertFalse(grounded_verdict({**review, 'reason_code': 'app_timeout'}, 'The result must equal one.', SOURCE))
        self.assertFalse(grounded_verdict({**review, 'requirement_quote': 'Invented requirement text'}, 'The result must equal one.', SOURCE))

    def test_runner_injects_only_into_copy_and_never_public_specs(self):
        self.decide()
        runner = AcceptanceRunner(self.root, self.directory, self.root / 'work', lambda *_: None)
        runner.derived_policy = self.policy
        runner._prepare()
        copy = (self.root / 'work/tests/A.spec.ts').read_text()
        self.assertIn('test.skip(["wrong"].includes(info.title)', copy)
        self.assertEqual((self.directory / 'A.spec.ts').read_text(), SOURCE)
        public = self.root / 'public'
        public.mkdir(); (public / 'A.spec.ts').write_text(SOURCE)
        runner.tests_dir = public
        runner._prepare()
        self.assertNotIn('test.skip(', (self.root / 'work/tests/A.spec.ts').read_text())
        self.assertEqual(runner._quarantined, {})

    def test_all_quarantined_is_measured_but_never_a_pass(self):
        row = TestOutcome('wrong', False, 'quarantined', 0, file='A.spec.ts')
        summary = RunSummary(total=1, results=[row])
        self.assertTrue(Flow.suite_is_measured(summary, ['A.spec.ts']))
        self.assertFalse(summary.all_passed)
        self.assertFalse(Flow.suite_is_measured(RunSummary(total=1, results=[TestOutcome('wrong', False, 'skipped', 0, file='A.spec.ts')]), ['A.spec.ts']))

    def test_snapshot_refresh_keeps_harness_additions_and_rejects_model_overwrite(self):
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root / 'requirements')
        flow.tests_dir = self.directory
        flow.snapshot_protected()
        path = self.directory / 'A.spec.ts'
        path.write_text(SOURCE + '// harness addition\n')
        self.decide()
        flow.snapshot_protected()
        path.write_text('// unauthorized model overwrite')
        self.policy.path.write_text('{}')
        flow.restore_protected()
        self.assertEqual(path.read_text(), SOURCE + '// harness addition\n')
        self.assertIn('records', json.loads(self.policy.path.read_text()))
        for _, snapshot, _ in flow.protected_snapshots:
            import shutil
            shutil.rmtree(snapshot.parent)

class GenerationRegressionTests(unittest.TestCase):
    def test_default_export_loss_detected_from_unchanged_caller(self):
        files = {'frontend/src/App.jsx': "import Home from './Home'; export default Home;",
                 'frontend/src/Home.jsx': '// unchanged marker'}
        self.assertTrue(missing_export_errors(files, ['frontend/src/Home.jsx']))
        self.assertTrue(placeholder_overwrites({'frontend/src/Home.jsx': 'export default function Home(){}'},
                                              {'frontend/src/Home.jsx': '// unchanged marker'}))
        files['frontend/src/Home.jsx'] = 'const Home=()=>null; export { Home as default };'
        self.assertFalse(missing_export_errors(files, ['frontend/src/Home.jsx']))

    def test_final_serialized_context_includes_tools_history_output_and_route(self):
        body = json.dumps({'model': 'small', 'max_tokens': 100,
                           'messages': [{'role': 'user', 'content': '中文' * 20}],
                           'tools': [{'description': 'x' * 300}]}).encode()
        self.assertIsNotNone(context_limit_error(body, {'small': 500}))
        self.assertIsNone(context_limit_error(body, {'other': 500}))
        self.assertIsNone(context_limit_error(body, {'small': 10000}))

    def test_request_extension_requires_effective_edit_and_is_once_only(self):
        proxy = object.__new__(LlmProxy)
        proxy.turn_budget = 8; proxy.turn_extension_limit = 12
        proxy.turn_budget_extended = False; proxy.turn_upstream_requests = 6
        proxy.turn_progress = Mock(return_value=False); proxy.log = Mock()
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 8)
        proxy.turn_progress.return_value = True
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 12)
        proxy.turn_extension_limit = 20
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 12)

class OracleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / '.arc/derived-tests'; self.directory.mkdir(parents=True)
        self.title = 'REQ-1: action [model]'
        self.source = "import {test} from '@playwright/test';\ntest('REQ-1: action [model]', async ({page}) => {\n await h.clickNamed(page, 'Open');\n await h.expectTextsVisible(page, ['Wrong']);\n});\ntest('REQ-1: valid [script]', async ({page}) => { await h.expectTextsVisible(page, ['Done']); });\n"
        self.path = self.directory / 'REQ-1.spec.ts'; self.path.write_text(self.source)
        self.node = {'id': 'REQ-1', 'description': 'Open must show Done; it must never show Wrong.',
                     'scenarios': [{'name': 'REQ-1: action', 'steps': [
                         {'keyword': 'WHEN', 'content': 'The visitor clicks “Open”.'},
                         {'keyword': 'THEN', 'content': 'The page shows “Done”.'}]}]}
        self.flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root / 'requirements')
        for key,value in {'tests_dir':self.directory, 'derived_tests_dir':self.directory,
                          'derived_as_specs':True,'derived_nodes':[self.node],
                          'requirement_nodes':{'REQ-1':self.node},'driver':object()}.items(): setattr(self.flow,key,value)
        self.flow.runner = SimpleNamespace(list_specs=Mock(return_value=(True,'')))
        self.flow.wound_down = Mock(return_value=False)
        self.flow.remaining = Mock(return_value=1000); self.flow.final_phase_reserve = Mock(return_value=0)
        self.flow.snapshot_protected = Mock(); self.flow.record_tests = Mock()
        self.flow.head = Mock(return_value='head'); self.flow.repair_source_index = Mock(return_value=SimpleNamespace(versions={}))
        self.flow.affected_regression_specs = Mock(return_value=[])
        self.review = {'verdict':'oracle_dispute', 'reason_code':'requirement_conflict',
                       'requirement_quote': self.node['description'],
                       'test_quote': "await h.expectTextsVisible(page, ['Wrong']);",
                       'evidence': 'Requirement explicitly excludes Wrong; this test expects Wrong after Open.', 'scenarios':[]}
        self.failed = RunSummary(total=2, results=[TestOutcome(self.title,False,'failed',1,file=self.path.name),
                            TestOutcome('REQ-1: valid [script]',False,'failed',1,file=self.path.name)])
        self.quarantined = RunSummary(total=2, results=[TestOutcome(self.title,False,'quarantined',0,file=self.path.name),
                            self.failed.results[1]])

    def test_independent_agreement_preserves_original_and_only_excludes_one_test(self):
        self.flow.text_turn = Mock(return_value=(True,json.dumps(self.review)))
        self.flow.run_specs = Mock(return_value=self.quarantined)
        with patch.dict('os.environ', {'OCTOS_ARC_DERIVED_SPEC_REPAIR':'0'}):
            observed = self.flow.review_failed_derived_spec_with_model('REQ-1',[self.path.name],self.failed)
        self.assertIs(observed,self.quarantined)
        self.assertEqual(self.flow.text_turn.call_count,2)
        self.assertEqual(self.flow.text_turn.call_args_list[0].args[0],self.flow.text_turn.call_args_list[1].args[0])
        self.assertEqual(self.path.read_text(),self.source)
        active = self.flow.uncontested_derived_results(observed)
        self.assertEqual((active.passed,active.total),(0,1))
        self.flow.audit_related_derived_specs = Mock(return_value=observed)
        self.flow.repair_rounds = 0
        self.assertFalse(self.flow.acceptance_loop('REQ-1',[self.path.name],time.time()+120, initial_summary=observed))
        report = json.loads((self.root/'.arc/derived-coverage.json').read_text())
        self.assertEqual(report['execution']['quarantined'],1)
        self.assertEqual(report['execution']['active_total'],1)

    def test_disagreement_does_not_skip_or_modify_any_test(self):
        self.flow.text_turn = Mock(side_effect=[(True,json.dumps(self.review)),
                           (True,json.dumps({'verdict':'app_error','evidence':'The valid implementation is missing.','scenarios':[]}))])
        self.flow.run_specs = Mock()
        self.assertIsNone(self.flow.review_failed_derived_spec_with_model('REQ-1',[self.path.name],self.failed))
        self.assertEqual(self.flow.generated_test_policy().quarantines(),{})
        self.assertEqual(self.path.read_text(),self.source)
        self.flow.run_specs.assert_not_called()

class RealQuarantineTests(unittest.TestCase):
    def test_real_playwright_skips_invalid_body_but_runs_valid_failure(self):
        import os
        install = os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT')
        if not install:self.skipTest('requires installed Playwright')
        root = Path(install)
        with tempfile.TemporaryDirectory(dir=root,prefix='quarantine-') as folder:
            base = Path(folder); directory = base/'.arc/derived-tests';directory.mkdir(parents=True)
            source = SOURCE.replace("test('valid', async () => { expect(1).toBe(1)", "test('valid', async () => { expect(1).toBe(3)")
            (directory/'A.spec.ts').write_text(source)
            policy = TestPolicy(directory,{},'helper-v1')
            policy.decide('A.spec.ts','wrong',source,'invalid','Confirmed test oracle error',[{},{}])
            runner = AcceptanceRunner(root,directory,base/'prepared',lambda *_:None,workers=1)
            runner.derived_policy = policy
            self.assertTrue(runner.list_specs(['A.spec.ts'])[0])
            summary = runner.run(['A.spec.ts'],'http://127.0.0.1:1',wall_timeout=30)
            self.assertEqual({r.title:r.status for r in summary.results},{'wrong':'quarantined','valid':'failed'})
            self.assertEqual((summary.passed,summary.total),(0,2))
            self.assertFalse(summary.all_passed)
            self.assertEqual((directory/'A.spec.ts').read_text(),source)
            source = source.replace('toBe(3)','toBe(1)')
            (directory/'A.spec.ts').write_text(source)
            # Regenerating the file invalidates the old decision, so wrong must fail again.
            summary = runner.run(['A.spec.ts'],'http://127.0.0.1:1',wall_timeout=30)
            self.assertEqual({r.title:r.status for r in summary.results},{'wrong':'failed','valid':'passed'})

class IncrementalGateTests(unittest.TestCase):
    def test_partial_scope_keeps_previous_pass_and_invalid_test_does_not_hide_valid_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); directory = root/'.arc/derived-tests';directory.mkdir(parents=True)
            (directory/'A.spec.ts').write_text(SOURCE)
            flow = Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
            flow.tests_dir=directory;flow.derived_tests_dir=directory;flow.derived_as_specs=True
            flow.spec_map={'A':['A.spec.ts'],'B':['B.spec.ts']};flow.test_verdict={'B':True}
            flow.record_tests=Mock();flow.write_derived_coverage=Mock();flow.derived_review_needed=Mock(return_value=True)
            flow.derived_spec_disputes={('A','wrong'):'Confirmed incorrect expectation'}
            summary=RunSummary(total=2,results=[TestOutcome('wrong',False,'quarantined',0,file='A.spec.ts'),
                                                TestOutcome('valid',False,'failed',1,file='A.spec.ts')])
            flow.record_full_suite(summary,{},scope=['A.spec.ts'])
            self.assertEqual(flow.test_verdict,{'A':False,'B':True})

    def test_known_generated_load_error_never_drives_app_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); directory=root/'.arc/derived-tests';directory.mkdir(parents=True)
            (directory/'A.spec.ts').write_text('BROKEN syntax')
            flow=Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
            flow.tests_dir=directory;flow.derived_tests_dir=directory;flow.derived_as_specs=True
            flow.runner=SimpleNamespace(list_specs=Mock(return_value=(False,'SyntaxError')))
            flow.snapshot_protected=Mock()
            flow.verify_derived_suite()
            self.assertFalse(flow.derived_suite_verified)
            self.assertEqual((directory/'A.spec.ts').read_text(),'BROKEN syntax')
            self.assertTrue(flow.generated_load_errors(['A.spec.ts']))
            self.assertFalse(flow.generated_load_errors(['B.spec.ts']))
            observed=flow.run_specs(['A.spec.ts'])
            self.assertTrue(observed.error.startswith('generated test load blocked:'))
            flow.audit_related_derived_specs=Mock(return_value=observed)
            flow.repair_source_index=Mock(return_value=SimpleNamespace(versions={}))
            flow.head=Mock(return_value='head');flow.node_repair_turn=Mock()
            self.assertIsNone(flow.acceptance_loop('A',['A.spec.ts'],time.time()+120,initial_summary=observed))
            flow.node_repair_turn.assert_not_called()
            (directory/'A.spec.ts').write_text('changed source')
            self.assertFalse(flow.generated_load_errors(['A.spec.ts']))

    def test_wave_failure_enters_node_repair_before_repeating_entire_suite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            flow=Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
            flow._wave_behavior_blocked=True
            flow.whole_app_codegen=Mock(return_value=True)
            flow.whole_app_first_suite=Mock(return_value=set())
            flow.whole_app_shared_repair=Mock(return_value=set())
            flow.test_verdict={};flow.whole_app_generated_ids=set();flow.whole_app_partial_ids={'A'}
            flow.driver=SimpleNamespace(end_scope=Mock());flow.node_cycle=Mock()
            flow.remaining=Mock(return_value=4000);flow.time_up=Mock(return_value=False)
            nodes=[{'id':'A'},{'id':'B'}]
            self.assertTrue(flow.whole_app_experiment({'id':'ROOT','children':nodes},nodes))
            self.assertEqual(flow.node_cycle.call_count,2)
            self.assertEqual([call.args[0]['id'] for call in flow.node_cycle.call_args_list], ['A', 'B'])
            flow.whole_app_first_suite.assert_called_once()
            flow.whole_app_shared_repair.assert_not_called()

class CheckpointQuarantineTests(unittest.TestCase):
    def test_invalid_only_file_does_not_interrupt_other_files_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);directory=root/'.arc/derived-tests';directory.mkdir(parents=True)
            flow=Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
            flow.tests_dir=directory;flow.derived_tests_dir=directory;flow.derived_as_specs=True
            flow.spec_map={'A':['A.spec.ts'],'B':['B.spec.ts']}
            flow.derived_spec_disputes={('A','wrong'):'Independently confirmed wrong assertion'}
            invalid=TestOutcome('wrong',False,'quarantined',0,file='A.spec.ts')
            bad=TestOutcome('valid',False,'failed',1,file='B.spec.ts',message='Expected visible Done, received Missing')
            good=TestOutcome('valid',True,'passed',1,file='B.spec.ts')
            first=RunSummary(total=2,results=[invalid,bad])
            last=RunSummary(total=2,passed=1,results=[invalid,good])
            flow.remaining=Mock(return_value=4000);flow.final_phase_reserve=Mock(return_value=0)
            flow.wound_down=Mock(return_value=False);flow.suite_repair_timeout=Mock(return_value=100)
            flow.suite_repair_turn=Mock(return_value=('tools',True,'applied'));flow.commit=Mock();flow.mark=Mock()
            flow.last_repair_changed=True;flow.app_repair_prompt=Mock(return_value='repair prompt')
            flow.repair_requirements=Mock(return_value='');flow.sources_text=Mock(return_value='')
            flow.corrections_text=Mock(return_value='');flow.derived_review_needed=Mock(return_value=False)
            flow.audit_related_derived_specs=Mock(side_effect=lambda specs,result:result)
            middle=RunSummary(total=2,results=[invalid,TestOutcome('valid',False,'failed',1,file='B.spec.ts',message='Expected visible Done, received Pending')])
            flow.run_specs=Mock(side_effect=[middle,last]);flow.test_verdict={'A':None,'B':False}
            with patch.dict('os.environ',{'OCTOS_ARC_CHECKPOINT_REPAIRS':'2'}):
                remains=flow.repair_regressions(4,['A.spec.ts','B.spec.ts'],flow.spec_map,{'B'},first,{'B':[bad]},1)
            self.assertFalse(remains)
            self.assertEqual(flow.suite_repair_turn.call_count,2)
            self.assertIsNone(flow.test_verdict['A'])
            self.assertTrue(flow.test_verdict['B'])
            self.assertIs(flow._checkpoint_repair_summary,last)
            for call in flow.suite_repair_turn.call_args_list:
                self.assertNotIn('wrong',call.args[2])
