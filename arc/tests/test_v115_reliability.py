"""No provider calls: trust boundaries, context versions and terminal accounting."""
import argparse
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from acceptance import RunSummary, TestOutcome, summarize_report
from context_ledger import compact_context, read_records
from derived_case_review import assertion_after_action
from domain_contracts import contract_manifest, official_status, source_contract_advisories
from main import Flow, app_design_errors
from llm_proxy import LlmProxy
from runtime_diagnostics import application_failures, diagnose


class ContextTests(unittest.TestCase):
    def body(self, operations):
        messages=[]
        for i,(name,args,content) in enumerate(operations):
            messages += [{'role':'assistant','tool_calls':[{'id':str(i),'function':{'name':name,'arguments':json.dumps(args)}}]},
                         {'role':'tool','tool_call_id':str(i),'content':content}]
        return json.dumps({'messages':messages}).encode()

    def test_identical_reads_compact_and_keep_tool_pairs(self):
        body=self.body([('read_file',{'path':'a'},'source '*100)]*2)
        data=json.loads(compact_context(body))
        self.assertIn('Earlier read omitted',data['messages'][1]['content'])
        self.assertEqual([m.get('tool_call_id') for m in data['messages'] if m['role']=='tool'],['0','1'])
        self.assertEqual(data['messages'][-1]['content'],'source '*100)
        self.assertEqual(compact_context(compact_context(body)),compact_context(body))

    def test_aba_and_failed_edit_versions_are_not_conflated(self):
        for operations in [[('read_file',{'path':'a'},v*300) for v in ['A','B','A']],
                           [('read_file',{'path':'a'},'A'*300),('edit_file',{'path':'a'},'Tool call refused: stale anchor'),('read_file',{'path':'a'},'A'*300)]]:
            body=self.body(operations)
            self.assertEqual(compact_context(body),body)

    def test_original_reads_are_recoverable_and_stopped_proxy_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            proxy=LlmProxy('http://127.0.0.1:1/v1','none',Path(directory)/'usage.jsonl').start()
            try:
                body=self.body([('read_file',{'path':'a'},'source '*100)]*2)
                self.assertTrue(proxy.retain_read_evidence(body))
                files=list((Path(directory)/'context-reads').glob('*.txt'))
                self.assertEqual(len(files),1); self.assertEqual(files[0].read_text(),'source '*100)
                proxy._stopped=True
                with patch('llm_proxy.open_upstream') as provider:
                    status,_,_=proxy._request_upstream('POST','/chat/completions',b'{}',{})
                self.assertEqual(status,503); provider.assert_not_called()
            finally: proxy.stop()

    def test_numbered_pagination_preserves_uncovered_rows(self):
        first='\n'.join(f'{n}│ '+str(n)*80 for n in range(1,5))
        tail='\n'.join(f'{n}│ '+str(n)*80 for n in range(3,5))
        body=self.body([('read_file',{'path':'a','start_line':1},first),('read_file',{'path':'a','start_line':3},tail)])
        self.assertEqual(compact_context(body),body)
        body=self.body([('read_file',{'path':'a','start_line':3},tail),('read_file',{'path':'a','start_line':1},first)])
        self.assertIn('Earlier read omitted',json.loads(compact_context(body))['messages'][1]['content'])
        changed=first.replace('4│ 444','4│ new')
        body=self.body([('read_file',{'path':'a'},first),('read_file',{'path':'a','start_line':1},changed)])
        self.assertEqual([r['epoch'] for r in read_records(json.loads(body)['messages'])],[0,1])


class TrustTests(unittest.TestCase):
    def test_system_fault_survives_untrusted_case_filter(self):
        flow=Flow.__new__(Flow); flow.derived_as_specs=True; flow.derived_case_reviews={}; flow.derived_spec_disputes={}
        flow.trusted_derived_case=Mock(return_value=False)
        summary=RunSummary(total=1,passed=0,results=[TestOutcome(title='wrong assertion',ok=False,status='failed',duration_ms=1,message='wrong',file='A.spec.ts')],
                           runtime_observations=[{'kind':'pageerror','confirmed':True,'message':'app crashed'}])
        filtered=flow.uncontested_derived_results(summary)
        self.assertEqual(filtered.total,0)
        self.assertEqual(application_failures(filtered),['app crashed'])
        self.assertFalse(filtered.all_passed)

    def test_expected_http_is_not_automatically_a_system_failure(self):
        summary=RunSummary(total=1,passed=1,runtime_observations=[{'kind':'http_response','status':403,'confirmed':False}])
        self.assertTrue(summary.all_passed)
        self.assertEqual(diagnose(summary)[0]['owner'],'unknown')
        summary.runtime_observations=[{'kind':'browser_unavailable','confirmed':False}]
        self.assertEqual(diagnose(summary)[0]['owner'],'environment')

    def test_passing_spec_attachment_cannot_claim_independent_confirmation(self):
        attachment=base64.b64encode(json.dumps([{'kind':'pageerror','confirmed':True,'message':'crash'}]).encode()).decode()
        report={'suites':[{'file':'A.spec.ts','specs':[{'title':'happy','id':'one','tests':[{'status':'expected','results':[
            {'status':'passed','attachments':[{'name':'arc-runtime-observations','body':attachment}]}]}]}]}]}
        summary=summarize_report(report)
        self.assertEqual(summary.passed,1); self.assertFalse(summary.runtime_observations[0]['confirmed'])
        self.assertFalse(summary.all_passed)
        self.assertFalse(Flow.suite_is_measured(summary,["A.spec.ts"]))

    def test_setup_only_does_not_earn_behavior_credit(self):
        quote="await h.expectCell(page, 'A1', '7');"
        case="await test.step('setup: cell_type', async () => { await h.cellType(page, 'A1', '7'); });\n"+quote
        self.assertFalse(assertion_after_action(case,quote))
        self.assertTrue(assertion_after_action(case.replace('setup:','action:'),quote))
        self.assertFalse(assertion_after_action("await h.watchResponse(page, '/api/x', 'GET');\n"+quote,quote))

    def test_http_exception_needs_original_evidence(self):
        case={'status':404,'source':{'requirement_id':'R','quote':'Use HTTP 404 to hide private resources.'}}
        self.assertFalse(official_status(case,{'R':'Use HTTP 403.'}))
        self.assertTrue(official_status(case,{'R':case['source']['quote']}))
        self.assertFalse(official_status(case,{}))

    def test_shared_contract_and_static_split_store_are_advisory(self):
        tree={'id':'R','description':'Save and reload a document.'}
        design={'data_model':{'documents':{'id':'string'}}}
        row=contract_manifest(tree,design)
        self.assertEqual(row['status'],'proposed_unverified'); self.assertTrue(row['gaps'])
        self.assertTrue(app_design_errors({**design,'domain_contracts':{'entity':'documents'}}))
        advisories=source_contract_advisories({'backend/routes/a.js':"const {store} = require('../store')",'backend/routes/b.js':"const {store} = require('../lib/store')"})
        self.assertEqual(advisories[0]['status'],'suspected')

    def test_domain_review_cannot_drop_requirement_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            flow=Flow(argparse.Namespace(web_port=3000),Path(directory),Path(directory))
            flow.remaining=Mock(return_value=4000); flow.wound_down=Mock(return_value=False)
            design={'data_model':{'docs':{'id':'string'}},'routes':[{'method':'GET','path':'/docs','requirements':['R']}],
                    'commands':[{'name':'save','requirements':['R'],'preconditions':[],'effects':['save'],
                                 'rejected_effects':['unchanged'],'state_transitions':[],'permissions':[],'persistence':['reload']} ]}
            flow.text_turn=Mock(return_value=(True,json.dumps({'data_model':{'docs':{'id':'string'}}})))
            self.assertEqual(flow.review_domain_design({'id':'R','description':'Save documents.'},design),design)
            report=json.loads((Path(directory)/'.arc/design/domain-review.json').read_text())
            self.assertEqual(report['status'],'unverified')
            flow.text_turn=Mock(return_value=(True,json.dumps(design)))
            self.assertEqual(flow.review_domain_design({'id':'R','description':'Save documents.'},design),design)
            self.assertEqual(json.loads((Path(directory)/'.arc/design/domain-review.json').read_text())['status'],'reviewed_unverified')

    def test_domain_review_compacts_design_before_skipping_large_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            flow=Flow(argparse.Namespace(web_port=3000),Path(directory),Path(directory))
            flow.remaining=Mock(return_value=4000); flow.wound_down=Mock(return_value=False)
            flow.codegen_context_chars=Mock(return_value=5000)
            design={'data_model':{'docs':{'id':'string'}},
                    'routes':[{'method':'GET','path':'/docs','requirements':['R']}],
                    'commands':[{'name':'save','requirements':['R'],'preconditions':[],
                                 'effects':['save'],'rejected_effects':['unchanged'],
                                 'state_transitions':[],'permissions':[],'persistence':['reload']}],
                    'notes':'Do not alter route ownership. ' * 150}
            reviewed={key:design[key] for key in ('data_model','commands')}
            flow.text_turn=Mock(return_value=(True,json.dumps({'data_model':design['data_model']})))
            self.assertEqual(flow.review_domain_design({'id':'R','description':'Save documents.'},design),design)
            report=json.loads((Path(directory)/'.arc/design/domain-review.json').read_text())
            self.assertEqual(report['status'],'unverified')
            flow.text_turn=Mock(return_value=(True,json.dumps(reviewed)))
            result=flow.review_domain_design({'id':'R','description':'Save documents.'},design)
            self.assertEqual(result,design)
            prompt=flow.text_turn.call_args.args[0]
            self.assertIn('PROPOSED DOMAIN CONTRACT:',prompt)
            self.assertIn('Save documents.',prompt)
            self.assertNotIn(design['notes'],prompt)
            report=json.loads((Path(directory)/'.arc/design/domain-review.json').read_text())
            self.assertEqual(report['status'],'reviewed_unverified')
            self.assertEqual(report['scope'],'domain_fields')

    def test_explicit_parent_grid_role_is_checked_for_its_leaf(self):
        tree={'id':'ROOT','description':'Application', 'children':[
            {'id':'R-1','description':'The active worksheet grid uses the ARIA grid role named Worksheet grid.',
             'children':[{'id':'R-1-1','description':'Open a workbook.'}]},
            {'id':'R-2','description':'Export data.'}]}
        sources={'frontend/src/Editor.jsx':'export default function Editor(){return <table><td>A1</td></table>}' }
        self.assertIn('grid role',Flow.required_grid_role_gap(tree,['R-1-1'],sources))
        self.assertIsNone(Flow.required_grid_role_gap(tree,['R-2'],sources))
        sources['frontend/src/Editor.jsx']='export default function Editor(){return <table role="grid" aria-label="Worksheet grid"/>}'
        self.assertIsNone(Flow.required_grid_role_gap(tree,['R-1-1'],sources))
        sources['frontend/src/Editor.jsx']='export default function Editor(){return <table role={gridRole}/> }'
        self.assertIsNone(Flow.required_grid_role_gap(tree,['R-1-1'],sources))
        sources={'frontend/src/Editor.jsx':'import Grid from "./Grid"; export default () => <Grid/>',
                 'frontend/src/Grid.jsx':'export default () => <table><td>A1</td></table>'}
        self.assertIn('grid role',Flow.required_grid_role_gap(tree,['R-1-1'],sources))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            editor=root/'frontend/src/Editor.jsx'; editor.parent.mkdir(parents=True)
            editor.write_text('export default function Editor(){return <table><td>A1</td></table>}')
            flow=Flow(argparse.Namespace(web_port=3000),root,root)
            flow.requirement_tree=tree
            flow.whole_app_generated_ids={'R-1-1'}
            flow.last_codegen_written=['frontend/src/Editor.jsx']
            flow.whole_app_wave_design_items=Mock(return_value={'routes':[],'pages':[]})
            self.assertTrue(any('grid role' in gap for gap in flow.whole_app_wave_gaps(['R-2'])))

    def test_final_generated_repair_uses_correct_node_and_retests_new_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'A.spec.ts').write_text("test('A: approved', async () => {});\n")
            (root/'backend').mkdir(); source=root/'backend/server.js'; source.write_text('broken')
            flow=Flow(argparse.Namespace(web_port=3000),root,root)
            flow.tests_dir=root; flow.derived_as_specs=True; flow.runner=SimpleNamespace(timeout_ms=1000)
            flow.remaining=Mock(return_value=2000); flow.wound_down=Mock(return_value=False)
            flow.final_measurement_reserve=Mock(return_value=100); flow.final_retry_admission=Mock(return_value=200)
            flow.trusted_derived_case=Mock(return_value=True); flow.record_full_suite=Mock()
            flow.derived_review_needed=Mock(side_effect=lambda node_id: node_id == 'B')
            flow.derived_has_runnable_cases=Mock(side_effect=lambda node_id: node_id == 'A')
            flow.test_verdict={'A':False,'B':True}
            bad=RunSummary(total=1,passed=0,results=[TestOutcome('A: approved',False,'failed',1,file='A.spec.ts')])
            good=RunSummary(total=1,passed=1,results=[TestOutcome('A: approved',True,'passed',1,file='A.spec.ts')])
            flow.run_specs=Mock(side_effect=[bad,good])
            def repair(node,specs,deadline,**kwargs):
                self.assertEqual(node,'A'); self.assertTrue(flow._in_final_repair)
                source.write_text('fixed'); return True
            flow.acceptance_loop=Mock(side_effect=repair)
            flow.final_acceptance_passes()
            self.assertEqual(flow.run_specs.call_count,2); self.assertIsNone(flow.test_verdict['B'])
            self.assertFalse(flow._in_final_repair)
            self.assertIs(flow.record_full_suite.call_args.args[0],good)

    def test_terminal_snapshot_preserves_unverified_and_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            flow=Flow(argparse.Namespace(web_port=3000),Path(directory),Path(directory))
            flow.test_verdict={'A':True,'B':None}
            flow.llm_proxy=Mock(_inflight_ids={'pending':'request-1'})
            flow.write_terminal_state('interrupted_by_user')
            result=json.loads((Path(directory)/'.arc/terminal-state.json').read_text())
            self.assertEqual(result['test_verdict'],{'A':True,'B':None})
            self.assertEqual(result['pending_requests'],['request-1'])
            self.assertEqual(result['pending_usage_status'],'unknown'); self.assertFalse(result['automatic_restart'])

if __name__=='__main__': unittest.main()
