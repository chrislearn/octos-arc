"""Behavioral calibration of v11.7 orchestration, contracts and test oracles."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from codegen import parse_context_request
from main import Flow
from quality_control import context_evidence, review_evidence, export_contracts, repair_allowance, recovery_budget, preserves_design, helper_evidence_hash, blocked_design_owners, valid_json_schema
from scenario_review import generated_values, transition_contract, compile_reply, grounded_behavior_test
from scenario_tests import Fixtures
from llm_proxy import force_write_decision, model_routes, route_request, cap_reasoning_effort, turn_reasoning_for_model


class QualityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_context_aliases_do_not_accept_mixed_writes_or_path_escape(self):
        for marker in ('NEEDS_CONTEXT', 'NEEDS CONTEXT'):
            text = f'<<<{marker}>>>\n' + json.dumps({'paths': ['backend/lib/a.js'], 'reason': 'read owner'}) + f'\n<<<END {marker}>>>'
            self.assertEqual(parse_context_request(text)['paths'], ['backend/lib/a.js'])
            self.assertIsNone(parse_context_request(text + '\n<<<FILE backend/server.js>>>\nx\n<<<END FILE>>>'))
            self.assertIsNone(parse_context_request(text.replace('backend/lib/a.js', 'backend/../secret')))

    def test_context_reads_versions_and_refuses_repeat_and_symlink(self):
        (self.root / 'backend').mkdir()
        file = self.root / 'backend/a.js'
        file.write_text('original')
        request = {'paths': ['backend/a.js']}
        evidence, versions = context_evidence(self.root, request, {'backend/a.js'}, {})
        self.assertIn('original', evidence)
        with self.assertRaisesRegex(ValueError, 'unchanged'):
            context_evidence(self.root, request, {'backend/a.js'}, versions)
        file.write_text('updated')
        self.assertIn('updated', context_evidence(self.root, request, {'backend/a.js'}, versions)[0])
        link = self.root / 'backend/out.js'
        link.symlink_to(Path(__file__).resolve())
        with self.assertRaisesRegex(ValueError, 'non-source'):
            context_evidence(self.root, {'paths': ['backend/out.js']}, {'backend/out.js'}, {})

    def test_three_dependency_reads_continue_same_generation_and_budget_bounds(self):
        from test_diagnostic_repairs import FlowRegression
        case = FlowRegression()
        case.setUp()
        self.addCleanup(case.doCleanups)
        flow = case.flow
        flow.use_structured_edits = Mock(return_value=False)
        replies = []
        for name in ('a', 'b', 'c'):
            path = case.root / f'backend/{name}.js'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'export const {name} = 1;')
            replies.append((True, '<<<NEEDS_CONTEXT>>>\n' + json.dumps({'paths': [f'backend/{name}.js'], 'reason': 'dependency'}) + '\n<<<END NEEDS_CONTEXT>>>'))
        flow.text_turn = Mock(side_effect=replies + [(True, '<<<NO CHANGE>>>')])
        ok, _ = flow.codegen_turn('implement', 600, 'test implement')
        self.assertTrue(ok)
        self.assertEqual(flow.text_turn.call_count, 4)
        final = flow.text_turn.call_args.args[0]
        for name in ('a', 'b', 'c'):
            self.assertIn(f'export const {name} = 1;', final)
        flow.text_turn = Mock(side_effect=replies)
        ok, _ = flow.codegen_turn('implement', 600, 'test implement', request_budget=1)
        self.assertFalse(ok)
        flow.text_turn.assert_called_once()

    def test_helper_review_includes_tail_and_transitive_local_import(self):
        (self.root / 'helpers.ts').write_text("import {check} from './oracle';\n" + '// context\n' * 1500 + 'export function last() {check();}')
        (self.root / 'oracle.ts').write_text('export function check() { throw new Error("oracle"); }')
        text = review_evidence(self.root)
        self.assertIn('export function last()', text)
        self.assertIn('throw new Error("oracle")', text)

    def test_contract_export_preserves_unresolved_requirements(self):
        tree = {'id': 'A', 'description': 'Must preserve zero, false and empty strings.'}
        export_contracts(self.root, tree, None, 'design_recovery_blocked')
        obligations = json.loads((self.root / 'design/obligations.json').read_text())
        self.assertIn('zero, false', obligations[0]['text'])
        self.assertEqual(obligations[0]['status'], 'awaiting_behavior_evidence')

    def test_measured_progress_extends_three_default_repairs_to_five(self):
        import time
        from acceptance import RunSummary, TestOutcome
        flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        flow.runner = object()
        flow.repair_rounds, flow.repair_rounds_explicit = 3, False
        flow.head = Mock(return_value='best')
        flow.commit = Mock()
        flow.record_tests = Mock()
        flow.remaining = Mock(return_value=9000)
        flow.wound_down = Mock(return_value=False)
        flow.node_repair_turn = Mock(return_value=True)
        flow.suite_is_measured = Mock(return_value=True)
        counts = [0, 1, 2, 3, 4, 6]
        flow.run_specs = Mock(side_effect=[RunSummary(passed=count, total=6, results=[
            TestOutcome(f'case-{i}', i < count, 'passed' if i < count else 'failed', 1,
                        file='A.spec.ts', message='' if i < count else 'Expected visible business result')
            for i in range(6)]) for count in counts])
        self.assertTrue(flow.acceptance_loop('A', ['A.spec.ts'], time.time() + 2000))
        self.assertEqual(flow.node_repair_turn.call_count, 5)
        self.assertIn('5/5', flow.node_repair_turn.call_args.args[3])

    def test_input_state_oracle_is_admitted_through_compile_and_semantic_gate(self):
        target = {'id':'S1','node_id':'A','title':'A: Edit quantity','description':'Edit quantity and save. The value persists after reload.',
                  'steps':['WHEN: edit quantity and Save', 'THEN: the changed quantity persists after reload'],
                  'allowed':['Quantity','Save','7'], 'seeds':[]}
        proposal = {'id':'S1','confidence':.99,'steps':[
            {'op':'fill','target':'Quantity','value':'7','phase':'action'},
            {'op':'click','target':'Save','phase':'action'},
            {'op':'expect_input_value','target':'Quantity','value':'7','phase':'assertion'},
            {'op':'reload','phase':'action'},
            {'op':'expect_input_value','target':'Quantity','value':'7','phase':'assertion'}]}
        sources, errors = compile_reply(json.dumps({'scenarios':[proposal]}), [target], Fixtures())
        self.assertTrue(sources, errors)
        self.assertTrue(grounded_behavior_test(sources['A'][0], 'A: Edit quantity [model]', target))
        proposal['steps'] = proposal['steps'][:2] + [proposal['steps'][-1]]
        sources, errors = compile_reply(json.dumps({'scenarios':[proposal]}), [target], Fixtures())
        self.assertFalse(sources, 'missing promised reload must stay rejected')

    def test_generic_format_operations_compile_and_invalid_data_is_rejected(self):
        target = {'id': 'S1', 'node_id': 'A', 'title': 'A: format', 'description': '', 'steps': [],
                  'allowed': ['Import', 'Done', 'Export'], 'seeds': [], 'api_contracts': []}
        proposal = {'id': 'S1', 'confidence': .99, 'signed_in': False, 'steps': [
            {'op':'upload_fixture','target':'Import','filename':'sample.json','mime':'application/json','content':'{"active":false,"amount":0}'},
            {'op':'expect_download','target':'Export','value':'.json','exact_json':{'active':False,'amount':0},
             'schema':{'type':'object','required':['active'],'properties':{'active':{'type':'boolean'}}}}]}
        sources, errors = compile_reply(json.dumps({'scenarios':[proposal]}), [target], Fixtures())
        self.assertTrue(sources, errors)
        self.assertIn('application/json', sources['A'][0])
        self.assertIn('"active": false', sources['A'][0])
        proposal['steps'][0]['filename'] = '../escape.json'
        sources, errors = compile_reply(json.dumps({'scenarios':[proposal]}), [target], Fixtures())
        self.assertFalse(sources)
        self.assertTrue(any('filename' in message for message in errors))

    def test_positive_budget_requires_progress_and_honors_zero(self):
        self.assertEqual(repair_allowance(3, 5, False), 3)
        self.assertEqual(repair_allowance(3, 5, True), 5)
        self.assertEqual(repair_allowance(0, 0, True), 0)

    def test_read_only_workflow_does_not_inherit_description_update(self):
        contract = transition_contract({'title': 'View saved order',
            'description': 'Edit the order and save changed values.',
            'steps': ['WHEN: follows the visible controls', 'THEN: shows saved values']})
        self.assertEqual(contract['kind'], '')

    def test_typed_test_data_preserves_empty_zero_and_false(self):
        self.assertEqual(generated_values({'test_data': {
            '$DATA_EMPTY': {'type': 'string', 'value': ''},
            '$DATA_ZERO': {'type': 'number', 'value': 0},
            '$DATA_FALSE': {'type': 'boolean', 'value': False}}}),
            {'$DATA_EMPTY': '', '$DATA_ZERO': '0', '$DATA_FALSE': 'false'})
        with self.assertRaises(ValueError):
            generated_values({'test_data': {'$DATA_X': {'type': 'number', 'value': float('nan')}}})

    def test_snapshot_requires_fresh_read_and_compiles_as_state_comparison(self):
        target = {'id': 'S1', 'node_id': 'A', 'title': 'A: observe state', 'description': '',
                  'steps': [], 'allowed': ['Refresh'], 'seeds': [],
                  'api_contracts': [{'method': 'GET', 'path': '/api/orders'}]}
        steps = [{'op': 'watch_response', 'target': '/api/orders', 'method': 'GET'},
                 {'op': 'reload'}, {'op': 'snapshot_response', 'target': '/api/orders', 'key': 'before'},
                 {'op': 'watch_response', 'target': '/api/orders', 'method': 'GET'}, {'op': 'reload'},
                 {'op': 'expect_response_unchanged', 'target': '/api/orders', 'key': 'before'}]
        proposal = {'id': 'S1', 'title': target['title'], 'confidence': .99, 'signed_in': False, 'steps': steps}
        sources, errors = compile_reply(json.dumps({'scenarios': [proposal]}), [target], Fixtures())
        self.assertTrue(sources, errors)
        self.assertIn('expectResponseUnchanged', sources['A'][0])
        proposal['steps'] = steps[:3] + steps[4:]
        sources, errors = compile_reply(json.dumps({'scenarios': [proposal]}), [target], Fixtures())
        self.assertFalse(sources)
        self.assertTrue(errors)

    def test_recovery_budget_renews_local_allowance_and_restores_even_after_exception(self):
        from types import SimpleNamespace
        flow = SimpleNamespace(derived_review_requests=60, derived_llm_seconds=3600,
                               derived_preflight_deadline=123, derived_preflight_start_tokens=20,
                               llm_proxy=SimpleNamespace(total_tokens=999), metric=Mock())
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            with recovery_budget(flow):
                self.assertEqual(flow.derived_review_requests, 0)
                self.assertEqual(flow.derived_preflight_start_tokens, 999)
                self.assertTrue(flow._in_final_repair)
                flow.derived_review_requests += 2
                raise RuntimeError('interrupted')
        self.assertEqual(flow.derived_review_requests, 62)
        self.assertEqual(flow.derived_preflight_deadline, 123)
        self.assertEqual(flow.derived_preflight_start_tokens, 20)
        self.assertFalse(hasattr(flow, '_in_final_repair'))

    def test_recovery_cannot_overwrite_shared_contract_and_missing_owners_stay_blocked(self):
        shared = {'data_model': {'accounts': {'id': 'string'}}, 'routes': [{'method': 'GET', 'path': '/api/a'}]}
        self.assertFalse(preserves_design(shared, {**shared, 'data_model': {'accounts': {'id': 'number'}}}))
        self.assertTrue(preserves_design(shared, {**shared, 'commands': [{'name': 'create'}]}))
        self.assertEqual(blocked_design_owners({}, shared, {'A', 'B'}, True), {'A', 'B'})

    def test_transitive_helper_change_invalidates_review_hash(self):
        (self.root / 'helpers.ts').write_text("export {check} from './oracle';")
        (self.root / 'oracle.ts').write_text('export const check = 1;')
        before = helper_evidence_hash(self.root)
        (self.root / 'oracle.ts').write_text('export const check = 2;')
        self.assertNotEqual(helper_evidence_hash(self.root), before)

    def test_schema_never_ignores_unsupported_keywords(self):
        self.assertTrue(valid_json_schema({'type': 'object', 'required': ['active'],
                                          'properties': {'active': {'type': 'boolean'}}, 'additionalProperties': False}))
        self.assertFalse(valid_json_schema({'type': 'string', 'minLength': 3}))
        self.assertFalse(valid_json_schema({'type': 'array', 'items': {'format': 'date'}}))

    def test_targeted_read_tools_remain_available_near_write_deadline(self):
        body = json.dumps({'messages': [{'role': 'user', 'content': 'fix state'}],
                           'tools': [{'type': 'function', 'function': {'name': n}} for n in ('read_file', 'grep', 'write_file', 'glob')]}).encode()
        data = json.loads(force_write_decision(body, 18, 24, 900))
        names = {x['function']['name'] for x in data['tools']}
        self.assertEqual(names, {'read_file', 'grep', 'write_file'})

    def test_approval_must_map_supplied_obligations_and_requirement_hash_changes(self):
        from derived_case_review import validate_review, requirement_text
        outcome = 'Saved quantity survives reload unchanged.'
        assertion = "await h.expectInputValue(page, 'Quantity', '7');"
        row = {'status':'unreviewed','outcome':outcome,
               'case':"await h.clickNamed(page, 'Save');\n"+assertion,
               'obligations':[{'id':'O1'}]}
        verdict = {'status':'approved_behavior', 'requirement_quote':outcome,'test_quote':assertion,
                   'reason':'The persisted control value is verified after saving.'}
        self.assertFalse(validate_review(row, verdict))
        verdict['obligation_ids'] = ['unknown']
        self.assertFalse(validate_review(row, verdict))
        verdict['obligation_ids'] = ['O1']
        self.assertTrue(validate_review(row, verdict))
        target = {'description':outcome,'obligations':[{'id':'O1','branch':'success'}]}
        old = requirement_text(target)
        target['obligations'][0]['branch'] = 'rejection'
        self.assertNotEqual(old, requirement_text(target))

    def test_low_default_and_explicit_medium_ceiling(self):
        for label in ('application design', 'shared domain contract review', 'A repair', 'whole application implement'):
            self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', label, {}), 'low')
        self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', 'derived scenario review', {}), 'none')
        self.assertEqual(turn_reasoning_for_model('glm-5.3-flash', 'derived scenario review', {}), 'low')
        self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', 'derived scenario review (retry)', {}), 'low')
        self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', 'derived scenario review',
                                                  {'OCTOS_ARC_SCENARIO_PROPOSAL_NO_THINK': '0'}), 'low')
        for label in ('application design (format retry)', 'A implement (tiny)', 'protocol retry', 'small patch'):
            self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', label, {}), 'low')
        for mode in ('high', 'xhigh', 'max', 'ultra'):
            data = json.loads(cap_reasoning_effort(json.dumps({'reasoning_effort': mode, 'reasoning': {'effort': mode}}).encode()))
            self.assertEqual(data['reasoning_effort'], 'medium')
            self.assertEqual(data['reasoning']['effort'], 'medium')
        for mode in ('low', 'medium'):
            body = json.dumps({'reasoning_effort': mode}).encode()
            self.assertEqual(cap_reasoning_effort(body), body)
        self.assertEqual(turn_reasoning_for_model('qwen3.7-plus', 'application design',
                                                  {'OCTOS_ARC_REASONING': 'medium'}), 'medium')

    def test_wire_effort_ceiling_applies_to_routed_request_and_model_fallback(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        import urllib.request
        from llm_proxy import LlmProxy
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append(data)
                missing = data.get('model') == 'missing-model'
                payload = ({'error': {'code':'model_not_found','message':'model missing-model not found'}} if missing else
                           {'choices':[{'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
                body = json.dumps(payload).encode()
                self.send_response(404 if missing else 200); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        proxy = None
        try:
            with patch.dict(os.environ, {'OCTOS_ARC_MODEL_ROUTES':'[]'}):
                proxy = LlmProxy(f'http://127.0.0.1:{server.server_address[1]}/v1', 'high').start()
            proxy.routes = [{'model':'missing-model','parameters':{'reasoning_effort':'high'}}]
            body = json.dumps({'model':'base','messages':[{'role':'user','content':'test'}], 'reasoning_effort':'high'}).encode()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(proxy.base_url + '/chat/completions', data=body,
                             headers={'Content-Type':'application/json'}), timeout=10) as response:
                self.assertEqual(response.status,200)
            self.assertEqual(len(seen),2)
            self.assertEqual([row['reasoning_effort'] for row in seen], ['medium','medium'])
            self.assertEqual([row['model'] for row in seen], ['missing-model','base'])
        finally:
            if proxy: proxy.stop()
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_scenario_proposal_only_disables_thinking_on_actual_qwen_wire(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        import urllib.request
        from llm_proxy import LlmProxy
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                payload = {'choices': [{'message': {'role': 'assistant', 'content': 'ok'},
                                         'finish_reason': 'stop'}],
                           'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
                body = json.dumps(payload).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        proxy = None
        try:
            with patch.dict(os.environ, {'OCTOS_ARC_MODEL_ROUTES': '[]'}, clear=True):
                proxy = LlmProxy(f'http://127.0.0.1:{server.server_address[1]}/v1', 'low').start()
                proxy.routes = [{'model': 'qwen3.7-plus', 'phases': ['implement']}]
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for label in ('derived scenario review', 'derived scenario review (retry)',
                              'derived case independent review', 'whole application implement'):
                    proxy.label = label
                    body = json.dumps({'model': 'base', 'messages': [{'role': 'user', 'content': 'test'}]}).encode()
                    with opener.open(urllib.request.Request(proxy.base_url + '/chat/completions', data=body,
                                     headers={'Content-Type': 'application/json'}), timeout=10) as response:
                        self.assertEqual(response.status, 200)
            self.assertEqual(len(seen), 4)
            self.assertEqual([row['enable_thinking'] for row in seen], [False, True, True, True])
            self.assertNotIn('reasoning_effort', seen[0])
            self.assertEqual([row['reasoning_effort'] for row in seen[1:]], ['low'] * 3)
        finally:
            if proxy: proxy.stop()
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_verified_route_thinking_budget_does_not_mix_effort(self):
        rules = model_routes(json.dumps([{'model': 'qwen3.7-plus', 'parameters': {'thinking_budget': 16000}}]))
        body = route_request(json.dumps({'model': 'old', 'messages': [], 'reasoning_effort': 'high'}).encode(), rules, 'implement')
        data = json.loads(body)
        self.assertEqual(data['thinking_budget'], 16000)
        self.assertNotIn('reasoning_effort', data)
        with self.assertRaises(ValueError):
            model_routes(json.dumps([{'model': 'qwen3.7-plus', 'parameters': {'thinking_budget': 16000, 'reasoning_effort': 'high'}}]))


if __name__ == '__main__':
    unittest.main()


class BrowserOracleCalibration(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT'), 'requires Playwright and Chromium')
    def test_business_oracles_reject_corrupted_values_partial_writes_and_false_empty(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from acceptance import AcceptanceRunner
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                if self.path.startswith('/api/state'):
                    changed = 'corrupt' in self.path and self.headers.get('X-After') == '1'
                    body = json.dumps({'order': {'status': 'closed' if changed else 'open'}, 'stock': 9 if changed else 10}).encode()
                    mime, status = 'application/json', 200
                elif self.path.startswith('/api/private'):
                    good = 'session=issued-token' in self.headers.get('Cookie', '') and 'broken' not in self.path
                    body = json.dumps({'items': ['known-record']} if good else {'error': 'unauthorized'}).encode()
                    mime, status = 'application/json', 200 if good else 401
                elif self.path.startswith('/api/matrix'):
                    bad = 'broken' in self.path
                    body = json.dumps({'list': ['private'] if bad else [], 'detail': 403, 'search': [], 'count': 0}).encode()
                    mime, status = 'application/json', 200
                elif self.path.startswith('/api/approval'):
                    body = json.dumps({'version': 2, 'approved': 'broken' in self.path}).encode()
                    mime, status = 'application/json', 200
                else:
                    body = b"<label>Quantity<input value='0'></label><p>expected</p><button>Save</button>"
                    mime, status = 'text/html', 200
                self.send_response(status); self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                self.send_response(200); self.send_header('Set-Cookie', 'session=issued-token; HttpOnly; Path=/')
                self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b'{"signedIn":true}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        install = Path(os.environ['OCTOS_TEST_PLAYWRIGHT_ROOT'])
        try:
            with tempfile.TemporaryDirectory(dir=install, prefix='v117-oracles-') as folder:
                root = Path(folder); suite = root / 'tests'; suite.mkdir()
                (suite / 'helpers.ts').write_text((Path(__file__).resolve().parents[1] / 'blueprints/derived-helpers.ts').read_text())
                source = "import {test,expect} from '@playwright/test'; import * as h from './helpers';\n"
                source += "test.use({actionTimeout:1500}); test.beforeEach(async({page})=>{await page.goto(process.env.E2E_BASE_URL!);});\n"
                for bad in (False, True):
                    mode = 'bad' if bad else 'good'
                    source += f"test('input-{mode}',async({{page}})=>{{await h.expectInputValue(page,'Quantity','{'expected' if bad else '0'}');}});\n"
                    route = '/api/state?corrupt' if bad else '/api/state'
                    source += f"test('atomic-{mode}',async({{page}})=>{{await h.watchResponse(page,'/api/state','GET'); await page.evaluate(async()=>{{await fetch('{route}')}}); await h.snapshotResponse(page,'/api/state','before'); await h.watchResponse(page,'/api/state','GET'); await page.evaluate(async()=>{{await fetch('{route}',{{headers:{{'X-After':'1'}}}})}}); await h.expectResponseUnchanged(page,'/api/state','before');}});\n"
                    route = '/api/private?broken' if bad else '/api/private'
                    source += f"test('session-{mode}',async({{page}})=>{{await page.evaluate(async()=>{{await fetch('/login',{{method:'POST'}})}}); await h.watchResponse(page,'/api/private','GET'); await page.evaluate(async()=>{{await fetch('{route}')}}); await h.expectResponse(page,'/api/private',200,{{items:['known-record']}});}});\n"
                for endpoint, expected in (('matrix', {'list': [], 'detail': 403, 'search': [], 'count': 0}),
                                           ('approval', {'version': 2, 'approved': False})):
                    for bad in (False, True):
                        mode = 'bad' if bad else 'good'
                        route = '/api/' + endpoint
                        url = route + ('?broken' if bad else '')
                        contract = json.dumps({'exact_json': expected})
                        source += f"test('{endpoint}-{mode}',async({{page}})=>{{await h.watchResponse(page,'{route}','GET'); await page.evaluate(async()=>{{await fetch('{url}')}}); await h.expectResponse(page,'{route}',200,{{}},{contract});}});\n"
                schema = json.dumps({'type':'object','required':['enabled','amount'],'properties':{'enabled':{'type':'boolean'},'amount':{'type':'integer'}},'additionalProperties':False})
                source += f"test('schema-good',()=>{{h.assertJsonContract({{enabled:false,amount:0}},{schema});}});\n"
                source += f"test('schema-bad',()=>{{h.assertJsonContract({{enabled:'false',amount:0}},{schema});}});\n"
                (suite / 'A.spec.ts').write_text(source)
                runner = AcceptanceRunner(install, suite, root / 'prepared', lambda *_: None, workers=1)
                result = runner.run(['A.spec.ts'], f'http://127.0.0.1:{server.server_address[1]}', wall_timeout=65)
                self.assertFalse(result.error, result.error)
                self.assertEqual(result.total, 12, [(r.title, r.message[:300]) for r in result.results])
                self.assertEqual({r.title for r in result.results if r.ok}, {'input-good', 'atomic-good', 'session-good', 'matrix-good', 'approval-good', 'schema-good'})
                for row in result.results:
                    if row.title.endswith('-bad'):
                        self.assertRegex(row.message, 'expect|Expected|HTTP response')
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
