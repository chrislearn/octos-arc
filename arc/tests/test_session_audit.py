"""Session failure-driven regression: delivery, diagnostics and phase controls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import unittest
from unittest.mock import Mock, patch

import main
from acceptance import AcceptanceRunner
from flow_policy import is_test_infrastructure_error, measurement_seconds, reasoning_for_phase
from generation_checks import placeholder_overwrites
from llm_proxy import LlmProxy
from repair_control import startup_recovery_deadline, seconds_available
from web_checks import autoload_invocations, route_transition_errors


class SessionAudit(unittest.TestCase):
    def test_generation_off_default_explicit_override_and_legacy_scope(self):
        labels=['REQ-1 implement','REQ-1 implement (structured edits)',
                'REQ-1 implement (context 1)','whole application wave 1','skeleton']
        for label in labels:
            for base in ['none','low','medium','high','auto']:
                self.assertEqual(reasoning_for_phase(label,base,{}),'none')
            self.assertEqual(reasoning_for_phase(label,'low',{'OCTOS_ARC_IMPLEMENT_REASONING':'medium'}),'medium')
            self.assertEqual(reasoning_for_phase(label,'medium',{'OCTOS_ARC_IMPLEMENT_REASONING':''}),'none')
            self.assertEqual(reasoning_for_phase(label,'low',{'OCTOS_ARC_IMPLEMENT_REASONING_ALL':'0'}),'low')
        for label in ['node repair','source rewrite','startup recovery']:
            self.assertEqual(reasoning_for_phase(label,'none',{}),'medium')
            self.assertEqual(reasoning_for_phase(label,'low',{'OCTOS_ARC_REPAIR_REASONING':'none'}),'medium')
        self.assertEqual(reasoning_for_phase('application design','low',{}),'low')

    def test_default_wire_generation_off_and_repair_on_after_routes_and_stall(self):
        for label,phase,expected in [('REQ-1 implement','implement',False),
                ('REQ-1 implement (context 1)','implement',False),
                ('REQ-1 implement (structured edits)','implement',False),
                ('source rewrite','repair',True),('startup recovery','repair',True)]:
            with self.subTest(label=label), patch.dict(os.environ,{},clear=True):
                proxy=LlmProxy('http://127.0.0.1:1/v1','none')
                proxy.label=label;proxy.phase=phase;proxy.no_action_count=1
                proxy.routes=[{'phases':[phase],'model':'qwen3.7-plus',
                               'parameters':{'enable_thinking':not expected}}]
                proxy.begin_turn(3)
                response=json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]}).encode()
                with patch.object(proxy,'_request_upstream',return_value=(200,response,{'Content-Type':'application/json'})) as send:
                    proxy.start()
                    try:
                        request=urllib.request.Request(proxy.base_url+'/chat/completions',method='POST',
                            data=json.dumps({'model':'qwen3.7-plus','messages':[]}).encode(),headers={'Content-Type':'application/json'})
                        urllib.request.urlopen(request,timeout=5).read()
                        wire=json.loads(send.call_args.args[2])
                        self.assertIs(wire['enable_thinking'],expected)
                        if expected:self.assertEqual(wire['reasoning_effort'],'medium')
                        else:self.assertNotIn('reasoning_effort',wire)
                    finally:proxy.stop()

    def test_generation_off_and_every_repair_on_despite_suffix_and_recovery(self):
        env={'OCTOS_ARC_IMPLEMENT_REASONING_ALL':'1', 'OCTOS_ARC_IMPLEMENT_REASONING':'none',
             'OCTOS_ARC_REPAIR_REASONING':'medium'}
        for label in ['REQ-1 implement', 'REQ-1 implement (structured edits)', 'wave 1 context continuation', 'skeleton']:
            self.assertEqual(reasoning_for_phase(label,'medium',env),'none')
        for label in ['REQ-1 repair (structured edits)', 'whole application startup repair', 'source rewrite', 'provider recovery']:
            self.assertEqual(reasoning_for_phase(label,'none',env),'medium')
        self.assertEqual(reasoning_for_phase('app design','medium',env),'medium')
        self.assertEqual(reasoning_for_phase('node repair','none',{}),'medium')

    def test_actual_proxy_wire_enforces_generation_and_repair_modes_after_routes(self):
        for phase,label,expected in [('implement','wave 1 context continuation',False),('repair','startup repair (tools)',True)]:
            with self.subTest(phase=phase), patch.dict(os.environ, {'OCTOS_ARC_IMPLEMENT_REASONING_ALL':'1',
                    'OCTOS_ARC_IMPLEMENT_REASONING':'none','OCTOS_ARC_REPAIR_REASONING':'medium'}):
                proxy=LlmProxy('http://127.0.0.1:1/v1','none')
                proxy.phase=phase; proxy.label=label
                proxy.routes=[{'phase':phase,'model':'qwen3.7-plus','parameters':{'enable_thinking':False}}]
                proxy.begin_turn(3)
                response=json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]}).encode()
                with patch.object(proxy,'_request_upstream',return_value=(200,response,{'Content-Type':'application/json'})) as send:
                    proxy.start()
                    try:
                        request=urllib.request.Request(proxy.base_url+'/chat/completions',method='POST',
                            data=json.dumps({'model':'qwen3.7-plus','messages':[]}).encode(),headers={'Content-Type':'application/json'})
                        urllib.request.urlopen(request,timeout=5).read()
                        wire=json.loads(send.call_args.args[2])
                        self.assertIs(wire['enable_thinking'],expected)
                        if expected: self.assertEqual(wire['reasoning_effort'],'medium')
                    finally: proxy.stop()

    def test_case_timeout_budget_counts_sixteen_double_quoted_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'pivot.spec.ts').write_text('test.setTimeout(60_000);\n'+'\n'.join('test("case '+str(i)+'", async () => {});' for i in range(16)))
            self.assertGreater(measurement_seconds(root,['pivot.spec.ts']),960)
        for error in ['playwright run exceeded 900s','Playwright collected 0 tests','acceptance time budget exhausted']:
            self.assertTrue(is_test_infrastructure_error(error))
        self.assertFalse(is_test_infrastructure_error('frontend/src/App.jsx:3 SyntaxError'))

    def test_large_full_suite_default_admits_sufficient_budget_and_respects_explicit_cap(self):
        for cap,left,admitted in [(None,10000,True),('900',10000,False),(None,800,False)]:
            with self.subTest(cap=cap,left=left), tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
                os.environ.pop('OCTOS_ARC_FULL_SUITE_SECONDS_CAP',None)
                if cap is not None: os.environ['OCTOS_ARC_FULL_SUITE_SECONDS_CAP']=cap
                root=Path(folder);tests=root/'tests';tests.mkdir()
                (tests/'a.spec.ts').write_text('test.setTimeout(60_000);\n'+'\n'.join('test("case '+str(i)+'", async () => {});' for i in range(16)))
                (tests/'b.spec.ts').write_text('test("other", async () => {});')
                flow=main.Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
                flow.tests_dir=tests;flow.runner=Mock(timeout_ms=10000);flow.metric=Mock()
                flow.test_verdict={'A':False,'B':False};flow.spec_map={'A':['a.spec.ts'],'B':['b.spec.ts']}
                flow.remaining=lambda:left;flow.time_up=lambda:False;flow.wound_down=lambda:False
                flow.final_workers=lambda:1;flow.final_measurement_reserve=lambda:120
                flow.final_acceptance=Mock(side_effect=lambda:setattr(flow,'final_suite_green',True))
                flow.final_acceptance_passes()
                self.assertEqual(flow.final_acceptance.call_count,int(admitted))

    def test_harness_timeout_cannot_start_whole_app_startup_repair(self):
        flow=object.__new__(main.Flow);flow.metric=Mock();flow.whole_app_generation_turn=Mock()
        self.assertFalse(flow.whole_app_startup_repair('playwright run exceeded 900s'))
        flow.whole_app_generation_turn.assert_not_called()

    def test_startup_repair_cannot_delete_unrelated_selection_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'backend').mkdir();(root/'frontend/src').mkdir(parents=True)
            entry=root/'backend/server.js';page=root/'frontend/src/Editor.jsx'
            entry.write_text('module.exports = broken;');page.write_text('function select(){ saveSelection(); }')
            flow=main.Flow(argparse.Namespace(web_port=3000),root,root/'requirements')
            flow.metric=Mock()
            def bad(*args,**kwargs):
                entry.write_text('module.exports = {};');page.write_text('function select(){}');return True
            flow._whole_app_startup_repair=Mock(side_effect=bad)
            self.assertFalse(flow.whole_app_startup_repair('backend/server.js:3 SyntaxError'))
            self.assertEqual(entry.read_text(),'module.exports = broken;')
            self.assertIn('saveSelection',page.read_text())
            self.assertFalse(flow.last_turn_changed)

    def test_startup_recovery_does_not_reset_exhausted_node_budget(self):
        class Flow:
            _startup_recovery_deadline=time.monotonic()-1
            _node_deadline=None
            def remaining(self): return 10000
            @startup_recovery_deadline
            def recover(self): raise AssertionError('must not get new budget')
        f=Flow();self.assertFalse(f.recover());self.assertIsNone(f._node_deadline)
        f._startup_recovery_deadline=time.monotonic()+20
        @startup_recovery_deadline
        def budget(flow): return seconds_available(flow)
        self.assertLessEqual(budget(f),20);self.assertIsNone(f._node_deadline)

    def test_only_atomic_import_and_export_preserving_jsx_migration_is_allowed(self):
        old={'frontend/src/A.js':'export default function A() {}', 'frontend/src/App.jsx':"import A from './A.js'; export default A;"}
        proposal={'frontend/src/A.js':'// migrated', 'frontend/src/A.jsx':'export default function A() { return <p>A</p>; }',
                  'frontend/src/App.jsx':"import A from './A.jsx'; export default A;"}
        self.assertEqual(placeholder_overwrites(old,proposal),[])
        for missing in ['frontend/src/App.jsx','frontend/src/A.jsx']:
            bad={k:v for k,v in proposal.items() if k!=missing}
            self.assertTrue(placeholder_overwrites(old,bad))
        bad={**proposal,'frontend/src/A.jsx':'export const different=1'}
        self.assertTrue(placeholder_overwrites(old,bad))

    def test_root_autoloader_calls_and_runtime_lost_or_duplicate_routes_are_rejected(self):
        sources={'backend/routes/workbooks.js':"module.exports = app => require('./cells')(app);",'backend/routes/cells.js':'module.exports = app => {}'}
        self.assertEqual(autoload_invocations(sources),{('backend/routes/workbooks.js','backend/routes/cells.js')})
        before={'routes':[{'method':'GET','path':'/api/workbooks/:id'}],'conflicts':[]}
        self.assertTrue(route_transition_errors(before,{'routes':[],'conflicts':[]}))
        self.assertTrue(route_transition_errors(before,{**before,'conflicts':[{'kind':'duplicate','method':'GET','path':'/api/workbooks/:other'}]}))
        self.assertEqual(route_transition_errors(before,{**before,'routes':before['routes']+[{'method':'POST','path':'/api/workbooks'}]}),[])
        self.assertTrue(route_transition_errors(before,None))

    def test_fixture_closure_includes_inbound_grants_without_partial_text_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); doc={'repositories':[{'name':'wanted','owner':'alice'},{'name':'unused','body':'x'*1000}],
                'accounts':[{'username':'alice'},{'username':'writer'}], 'grants':[{'repository':'wanted','account':'writer','role':'Write'}]}
            (root/'fixtures.json').write_text(json.dumps(doc))
            flow=Mock();flow.tests_dir=root;flow.output_dir=root;flow.frozen_suite={'name':'reviewed'}
            with patch.dict(os.environ,{'OCTOS_ARC_FIXTURE_CONTEXT_CHARS':'350'}):
                text=main.fixture_context(flow,'Open wanted')
            self.assertIn('writer',text);self.assertIn('Write',text);self.assertNotIn('unused',text)
            with patch.dict(os.environ,{'OCTOS_ARC_FIXTURE_CONTEXT_CHARS':'50'}):
                text=main.fixture_context(flow,'Open wanted')
            self.assertNotIn('INCOMPLETE',text)
            closure=json.loads(text[text.index('\n{')+1:])
            self.assertEqual(len(closure['grants']),1);self.assertEqual(len(closure['accounts']),2)
            flow.metric.assert_called_once()
            self.assertTrue(flow.metric.call_args.kwargs['complete'])
            self.assertTrue(flow.metric.call_args.kwargs['over_inline_preference'])
            self.assertEqual(json.loads((root/'fixtures.json').read_text()),doc)

    def test_isolated_timeout_cannot_lose_error_when_completed_results_exist(self):
        from acceptance import RunSummary, TestOutcome
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            flow=object.__new__(main.Flow);flow.tests_dir=Path(folder);flow.smoke_port=1
            flow.remaining=lambda:1000;flow.metric=Mock()
            partial=RunSummary(passed=1,total=1,results=[TestOutcome('completed',True,'passed',1,file='a.spec.ts')],
                               error='playwright run exceeded 60s',partial=True,error_kind='test_wall_timeout')
            runner=Mock();runner.timeout_ms=10000;runner.run.return_value=partial
            server=Mock();server.tail.return_value=''
            observed=flow.run_isolated(runner,['a.spec.ts','b.spec.ts'],server,Mock(),1)
            self.assertEqual(observed.error,partial.error);self.assertTrue(observed.partial)
            self.assertEqual(observed.passed,1);self.assertFalse(observed.all_passed)
            self.assertFalse(main.Flow.suite_is_measured(observed,['a.spec.ts']))
            runner.run.assert_called_once()

    def test_final_handoff_no_model_calls_and_no_overwrite_even_events_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'backend').mkdir(); (root/'backend/server.js').write_text('retained application')
            events=Mock();events.mark_run_completed.side_effect=RuntimeError('event service down')
            with patch('main.open_upstream',create=True,side_effect=AssertionError('no model')):
                self.assertEqual(main.finish_partial_delivery(root,'provider unavailable',events=events,startable=False,verdicts={'A':False}),0)
            self.assertEqual((root/'backend/server.js').read_text(),'retained application')
            data=json.loads((root/'.arc/delivery-state.json').read_text())
            self.assertEqual(data['test_verdict'],{'A':False});self.assertFalse(data['startable']);self.assertEqual(data['model_calls_during_handoff'],0)
            events.mark_run_failed.assert_not_called()

    def test_internal_system_exit_and_configuration_failure_always_handoff(self):
        with tempfile.TemporaryDirectory() as folder, patch('sys.argv',['main.py','--output-dir',folder]):
            for error in [SystemExit(0),SystemExit(),SystemExit(1),SystemExit([]),RuntimeError('all model requests failed')]:
                with self.subTest(error=type(error).__name__), patch('main.coordinated_main',side_effect=error):
                    self.assertEqual(main.main(),0)
            self.assertTrue((Path(folder)/'backend/server.js').is_file())

    def test_help_exit_is_intentional_and_does_not_create_a_submission(self):
        with patch('sys.argv',['main.py','--help']), patch('main.coordinated_main',side_effect=SystemExit(0)), \
                patch('main.finish_partial_delivery') as deliver:
            self.assertEqual(main.main(),0)
        deliver.assert_not_called()

    def test_setup_failure_preserves_explicit_output_for_both_cli_forms_and_writes_completion(self):
        for joined in [False, True]:
            with self.subTest(joined=joined), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)/'explicit';(root/'backend').mkdir(parents=True)
                (root/'backend/server.js').write_text('existing application')
                argv=['main.py']+(['--output-dir='+str(root)] if joined else ['--output-dir',str(root)])
                with patch('sys.argv',argv), patch.dict(os.environ,{'ARCBENCH_TEMPLATE_DIR':str(Path(folder)/'other')}), \
                        patch('main.coordinated_main',side_effect=RuntimeError('setup failed')):
                    self.assertEqual(main.main(),0)
                self.assertEqual((root/'backend/server.js').read_text(),'existing application')
                events=[json.loads(s) for s in (root/'.arc/runner-events.jsonl').read_text().splitlines()]
                self.assertEqual(events[-1]['state'],'completed')
                self.assertFalse((Path(folder)/'other/.arc/delivery-state.json').exists())

    def test_real_setup_sigterm_and_repeated_signal_handoff_but_user_sigint_stays_cancelled(self):
        import select,signal,sys
        script='''
import main,sys,time
sys.argv=['main.py','--output-dir='+sys.argv[1]]
def setup():
    print('READY',flush=True)
    time.sleep(60)
main.coordinated_main=setup
deliver=main.finish_partial_delivery
def handoff(*args,**kwargs):
    print('HANDOFF',flush=True)
    time.sleep(.3)
    return deliver(*args,**kwargs)
main.finish_partial_delivery=handoff
sys.exit(main.main())
'''
        for sig in [signal.SIGTERM,signal.SIGINT]:
            with self.subTest(signal=sig), tempfile.TemporaryDirectory() as folder:
                env={k:v for k,v in os.environ.items() if not k.startswith(('OCTOS_','ARCBENCH_'))}
                env['PYTHONPATH']=str(Path(main.__file__).parent)
                proc=subprocess.Popen([sys.executable,'-c',script,folder],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                try:
                    self.assertTrue(select.select([proc.stdout],[],[],30)[0])
                    self.assertEqual(proc.stdout.readline().strip(),'READY')
                    proc.send_signal(sig)
                    if sig==signal.SIGTERM:
                        self.assertTrue(select.select([proc.stdout],[],[],30)[0])
                        self.assertEqual(proc.stdout.readline().strip(),'HANDOFF')
                        proc.send_signal(sig)  # second signal during finalization
                    stdout,stderr=proc.communicate(timeout=30)
                    self.assertEqual(proc.returncode,0 if sig==signal.SIGTERM else 130,stderr)
                    if sig==signal.SIGTERM:
                        self.assertTrue((Path(folder)/'backend/server.js').is_file())
                        events=[json.loads(s) for s in (Path(folder)/'.arc/runner-events.jsonl').read_text().splitlines()]
                        self.assertEqual(events[-1]['state'],'completed')
                    else:self.assertFalse((Path(folder)/'.arc/delivery-state.json').exists())
                finally:
                    if proc.poll() is None:proc.kill();proc.wait()
                    proc.stdout.close();proc.stderr.close()

    def test_completion_service_system_exit_does_not_abort_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);events=Mock()
            events.mark_run_completed.side_effect=SystemExit(1)
            self.assertEqual(main.finish_partial_delivery(root,'provider failed',events=events),0)
            self.assertTrue((root/'backend/server.js').is_file())
            self.assertEqual(json.loads((root/'.arc/terminal-state.json').read_text())['state'],'completed_with_issues')

    def test_artifact_and_state_writer_system_exit_cannot_abort_retained_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'backend').mkdir();entry=root/'backend/server.js'
            entry.write_text('retained application');events=Mock()
            with patch('main.write_codegen_manifests',side_effect=SystemExit(1)), \
                    patch.object(Path,'write_text',side_effect=SystemExit(1)):
                self.assertEqual(main.finish_partial_delivery(root,'internal failures',events=events),0)
            self.assertEqual(entry.read_text(),'retained application')
            events.mark_run_completed.assert_called_once()

    def test_closed_stdout_and_stderr_do_not_change_process_handoff_to_exit_120(self):
        import sys
        with tempfile.TemporaryDirectory() as folder:
            env={k:v for k,v in os.environ.items() if not k.startswith(('OCTOS_','ARCBENCH_'))}
            proc=subprocess.Popen([sys.executable,str(Path(main.__file__)), '--output-dir',folder,
                '--web-port','invalid'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            try:
                proc.stdout.close();proc.stderr.close()
                self.assertEqual(proc.wait(timeout=30),0)
                self.assertTrue((Path(folder)/'backend/server.js').is_file())
                self.assertEqual(json.loads((Path(folder)/'.arc/terminal-state.json').read_text())['state'],'completed_with_issues')
            finally:
                if proc.poll() is None: proc.kill();proc.wait()

    def test_cleanup_failures_cannot_skip_driver_proxy_browser_or_owned_reaping(self):
        with tempfile.TemporaryDirectory() as folder:
            flow=object.__new__(main.Flow);flow.output_dir=Path(folder)
            flow.layered=Mock();flow.layered.close.side_effect=OSError('pipeline failed')
            flow.driver=Mock();flow.driver.close.side_effect=SystemExit(1)
            flow.cleanup_playwright=Mock(side_effect=OSError('browser cleanup failed'))
            flow.stop_llm_proxy=Mock();flow.discard_runtime_store=Mock()
            with patch('main.reap_workspace_processes',return_value=0) as reap:
                flow.postflight()
                reap.assert_called_once_with(flow.output_dir,main.log)
            flow.driver.close.assert_called_once();flow.cleanup_playwright.assert_called_once()
            flow.stop_llm_proxy.assert_called_once();flow.discard_runtime_store.assert_not_called()

    @unittest.skipUnless(os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT'),'real Playwright required')
    def test_real_wall_timeout_retains_completed_case_and_full_scope_unknown(self):
        pw=Path(os.environ['OCTOS_TEST_PLAYWRIGHT_ROOT'])
        with tempfile.TemporaryDirectory() as folder:
            tests=Path(folder)/'tests';tests.mkdir();(tests/'partial.spec.ts').write_text("import { test, expect } from '@playwright/test';\ntest('completed failure', async () => { expect(1).toBe(2); });\ntest('unfinished case', async () => { await new Promise(r=>setTimeout(r,20000)); });")
            # Work must sit beneath node_modules for ordinary module resolution.
            work=pw/('audit-partial-'+str(os.getpid()))
            try:
                runner=AcceptanceRunner(pw,tests,work,lambda _:None,timeout_ms=30000)
                summary=runner.run(['partial.spec.ts'],'http://127.0.0.1:1',wall_timeout=4,workers=1)
                self.assertTrue(summary.partial);self.assertEqual(summary.error_kind,'test_wall_timeout')
                self.assertEqual(summary.expected_total,2);self.assertGreaterEqual(summary.total,1)
                self.assertEqual(summary.results[0].title,'completed failure');self.assertFalse(summary.results[0].ok)
                self.assertFalse(summary.all_passed);self.assertIn('toBe',summary.results[0].message)
                self.assertTrue((work/'partial-report.json').is_file())
            finally:
                import shutil;shutil.rmtree(work,ignore_errors=True)
