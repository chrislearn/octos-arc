"""Regressions from v11.1 captured failures; no model/network generation."""
import argparse
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from acceptance import RunSummary, TestOutcome
from llm_proxy import LlmProxy
from main import Flow, app_design_errors, parse_app_design_reply
from requirement_order import dependency_ids
from scenario_review import compile_reply, proposal_problems, review_targets
from scenario_tests import Fixtures, spec_header, write_suite


def leaf(nid='A', description='', dependencies=()):
    return {'id': nid, 'name': nid, 'type': 'ATOMIC', 'description': description,
            'dependencies': list(dependencies), 'scenarios': [{'name': nid + ': Scenario 1', 'steps': [
                {'keyword': 'GIVEN', 'content': 'A visitor starts at home.'},
                {'keyword': 'WHEN', 'content': 'The user performs the requested workflow.'},
                {'keyword': 'THEN', 'content': 'The required outcome is visible.'}]}]}


def target(description='', allowed=(), seeds=()):
    return {'id': 'S1', 'node_id': 'A', 'title': 'A: Scenario 1', 'name': 'A', 'description': description,
            'allowed': list(allowed), 'seeds': list(seeds), 'controls': list(allowed)}


def proposal(steps):
    return {'id': 'S1', 'confidence': 0.9, 'signed_in': False, 'steps': steps}


class ProxyFailureBranches(unittest.TestCase):
    def test_real_context_rejection_returns_400_without_a_logging_exception_or_provider_call(self):
        proxy = object.__new__(LlmProxy)
        proxy.model_contexts = {'small': 30}
        body = json.dumps({'model': 'small', 'max_tokens': 100, 'messages': [{'role': 'user', 'content': 'x' * 100}]}).encode()
        with patch('llm_proxy.open_upstream') as upstream:
            status, payload, headers = proxy._request_upstream('POST', '/chat/completions', body, {})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(payload)['error']['code'], 'local_context_limit')
        upstream.assert_not_called()

    def test_extension_works_without_a_mock_nonexistent_logger(self):
        proxy = object.__new__(LlmProxy)
        proxy.turn_budget = 8; proxy.turn_extension_limit = 12
        proxy.turn_budget_extended = False; proxy.turn_upstream_requests = 6
        proxy.turn_progress = Mock(return_value=False)
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 8)
        proxy.turn_progress.return_value = True
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 12)
        proxy.turn_extension_limit = 20
        proxy.maybe_extend_turn(); self.assertEqual(proxy.turn_budget, 12)

    def test_closed_diagnostic_stream_does_not_abort_extension(self):
        proxy = object.__new__(LlmProxy)
        with patch('builtins.print', side_effect=OSError('closed')):
            proxy.diagnostic('a safe operational notice')


class OracleSemantics(unittest.TestCase):
    def setUp(self):
        self.fixtures = Fixtures(account='alice-dev', email='alice@example.test', password='Original-pass-123!')
        self.auth = target(allowed=['Username or email', 'Password', 'Sign in', 'Sign out', 'alice-dev', 'Original-pass-123!'], seeds=['alice-dev'])

    def test_authenticated_identity_is_evidence_but_input_echo_is_not(self):
        steps = [{'op': 'fill', 'target': 'Username or email', 'value': 'alice-dev'},
                 {'op': 'fill', 'target': 'Password', 'value': 'Original-pass-123!'},
                 {'op': 'click', 'target': 'Sign in'}, {'op': 'expect_visible', 'target': 'alice-dev'}]
        self.assertEqual(proposal_problems(proposal(steps), self.auth, self.fixtures), [])
        sources, dropped = compile_reply(json.dumps({'scenarios': [proposal(steps)]}), [self.auth], self.fixtures)
        self.assertFalse(dropped)
        self.assertIn("h.expectIdentity(page, 'alice-dev', true)", sources['A'][0])
        self.assertTrue(proposal_problems(proposal([steps[0], steps[-1]]), self.auth, self.fixtures))

    def test_logout_hides_identity_without_deleting_seed(self):
        steps = [{'op': 'click', 'target': 'Sign out'}, {'op': 'expect_absent', 'target': 'alice-dev'}]
        self.assertEqual(proposal_problems({**proposal(steps), 'signed_in':True}, self.auth, self.fixtures), [])
        bad = [{'op': 'open', 'target': 'home'}, {'op': 'expect_absent', 'target': 'alice-dev'}]
        self.assertTrue(proposal_problems(proposal(bad), self.auth, self.fixtures))

    def test_public_code_before_entry_is_allowed_but_private_password_is_not(self):
        t = target('After reset, the page displays the fixed verification-code text “123456”.',
                   ['Send reset link', '123456', 'Verification code', 'Reset password', 'Password updated', 'Password'])
        steps = [{'op': 'click', 'target': 'Send reset link'}, {'op': 'expect_visible', 'target': '123456'},
                 {'op': 'fill', 'target': 'Verification code', 'value': '123456'},
                 {'op': 'click', 'target': 'Reset password'}, {'op': 'expect_visible', 'target': 'Password updated'}]
        self.assertFalse(proposal_problems(proposal(steps), t, self.fixtures))
        steps[2] = {'op': 'fill', 'target': 'Password', 'value': '123456'}
        self.assertTrue(proposal_problems(proposal(steps), t, self.fixtures))

    def test_sign_in_link_after_confirmed_logout_is_state_evidence(self):
        t = target('Only “Confirm sign out” invalidates the session. After confirming, the page displays the “Sign in” link.',
                   ['Sign in', 'Sign out', 'Confirm sign out'])
        steps = [{'op': 'click', 'target': 'Sign in'}, {'op': 'click', 'target': 'Sign out'},
                 {'op': 'click', 'target': 'Confirm sign out'}, {'op': 'expect_visible', 'target': 'Sign in'}]
        sources, dropped = compile_reply(json.dumps({'scenarios': [proposal(steps)]}), [t], self.fixtures)
        self.assertFalse(dropped)
        self.assertIn("h.expectRole(page, 'link', 'Sign in')", sources['A'][0])
        self.assertTrue(proposal_problems(proposal(steps[:2] + steps[3:]), t, self.fixtures))
        self.assertTrue(proposal_problems(proposal(steps[:1] + steps[3:]), t, self.fixtures))
        t['description'] = 'The login form has a “Sign in” button.'
        self.assertTrue(proposal_problems(proposal(steps), t, self.fixtures))

    def test_nonpublic_code_echo_remains_rejected(self):
        t = target('A code is supplied out of band.', ['Verification code', '123456', 'Verify'])
        p = proposal([{'op': 'fill', 'target': 'Verification code', 'value': '123456'},
                      {'op': 'click', 'target': 'Verify'}, {'op': 'expect_visible', 'target': '123456'}])
        self.assertTrue(proposal_problems(p, t, self.fixtures))
        t['description']='The page must not display the verification code “123456”.'
        self.assertTrue(proposal_problems(p, t, self.fixtures))

    def test_dependency_literal_is_grounded_in_explicit_dependency_only(self):
        login = leaf('login', 'Failed login displays “Invalid credentials”.')
        reset = leaf('reset', 'A form has “Reset password”.', ['login'])
        unrelated = leaf('unrelated', 'Failed export displays “Export failed”.')
        targets = review_targets([login, reset, unrelated], self.fixtures, include_all=True)
        t = next(t for t in targets if t['node_id'] == 'reset')
        self.assertEqual(t['dependency_literals']['Invalid credentials'], ['login'])
        self.assertNotIn('Export failed', t['dependency_literals'])
        p = proposal([{'op': 'click', 'target': 'Reset password'}, {'op': 'expect_visible', 'target': 'Invalid credentials'}])
        self.assertFalse(proposal_problems(p, t, self.fixtures))

    def test_cases_compile_independently_without_silently_dropping_a_branch(self):
        t = target(allowed=['Save', 'Done'])
        steps = [{'op': 'click', 'target': 'Save'}, {'op': 'expect_visible', 'target': 'Done'}]
        p = {'id': 'S1', 'cases': [proposal(steps), proposal(steps)]}
        sources, dropped = compile_reply(json.dumps({'scenarios': [p]}), [t], Fixtures())
        self.assertFalse(dropped); self.assertEqual(len(sources['A']), 2)
        self.assertIn('[case 1] [model]', sources['A'][0]); self.assertIn('[case 2] [model]', sources['A'][1])
        p['cases'][1]['steps'] = [{'op': 'click', 'target': 'Unknown'}]
        sources, dropped = compile_reply(json.dumps({'scenarios': [p]}), [t], Fixtures())
        self.assertEqual(sources, {}); self.assertTrue(dropped)

    def test_long_case_still_obeys_step_cap(self):
        t = target(allowed=['Save', 'Done'])
        p = {'id': 'S1', 'cases': [proposal([{'op': 'click', 'target': 'Save'}] * 20 + [{'op': 'expect_visible', 'target': 'Done'}])]}
        sources, dropped = compile_reply(json.dumps({'scenarios': [p]}), [t], Fixtures())
        self.assertFalse(sources); self.assertIn('at most 20', dropped[0])

    def test_validator_dispute_retains_unresolved_evidence_without_skip_or_pass(self):
        t = target('The page displays the fixed verification code “123456”.')
        p = {'id': 'S1', 'validator_dispute': {'requirement_quote': t['description'], 'reason': 'Code is explicitly public'}}
        sources, dropped, retryable = compile_reply(json.dumps({'scenarios': [p]}), [t], Fixtures(), with_retryable=True)
        self.assertEqual(sources, {}); self.assertIn('unresolved, not quarantined', dropped[0]); self.assertFalse(retryable)


class FlowRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.flow = Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.metric = Mock(); self.flow.save_rejected_reply = Mock(); self.flow.remember_repair = Mock()
        self.flow.generation_batch_check = Mock(); self.flow.remaining = Mock(return_value=4000)
        self.flow.wound_down = Mock(return_value=False)

    def test_invalid_design_has_exact_schema_path_and_preserves_raw_object(self):
        invalid = {'pages': [{'path': '/'}], 'modules': [{'path': 'frontend/src/App.jsx', 'owns': 'routing'}]}
        self.assertIsNone(parse_app_design_reply(json.dumps(invalid)))
        self.assertEqual(parse_app_design_reply(json.dumps(invalid), validate=False), invalid)
        self.assertEqual(app_design_errors(invalid)[0]['path'], '/modules/0/owns')
        self.assertIsNone(parse_app_design_reply(json.dumps({'pages': [{'path': '/'}], 'modules': [4]})))

    def test_schema_retry_uses_original_fields_and_full_module_schema(self):
        f = self.flow; f.codegen_mode = Mock(return_value=True); f.evolution = False
        invalid = {'pages': [{'path': '/signup'}], 'modules': [{'path': 'frontend/src/App.jsx', 'owns': 'routing'}]}
        valid = {**invalid, 'modules': [{'path': 'frontend/src/App.jsx', 'owns': ['routing']}]}
        f.text_turn = Mock(side_effect=[(True, json.dumps(invalid)), (True, json.dumps(valid))])
        nodes = [leaf(str(i)) for i in range(3)]
        self.assertEqual(f.app_design({'id': 'root', 'type': 'FOLDER', 'children': nodes}, nodes), valid)
        retry = f.text_turn.call_args.args[0]
        self.assertIn('/modules/0/owns', retry); self.assertIn('PREVIOUS OBJECT', retry)
        self.assertIn('Each module is', retry); self.assertIn('/signup', retry)

    def test_atomic_wave_refusal_keeps_both_ends_of_api_contract(self):
        f = self.flow
        (self.root/'backend/routes').mkdir(parents=True); (self.root/'frontend/src').mkdir(parents=True)
        backend = self.root/'backend/routes/auth.js'; frontend = self.root/'frontend/src/auth.js'
        backend.write_text('old backend'); frontend.write_text('old frontend')
        f.text_turn = Mock(return_value=(True, '<<<FILE backend/routes/auth.js>>>\nnew backend\n<<<END FILE>>>\n<<<FILE frontend/src/auth.js>>>\nnew frontend\n<<<END FILE>>>'))
        f.use_structured_edits = Mock(return_value=False)
        f._atomic_codegen_response = True
        prompt = '--- frontend/src/auth.js ---\nold frontend\n'
        ok, reason = f.codegen_turn(prompt, 60, 'wave implement')
        self.assertFalse(ok); self.assertIn('Atomic response not applied', reason)
        self.assertEqual(backend.read_text(), 'old backend'); self.assertEqual(frontend.read_text(), 'old frontend')
        self.assertEqual(f.last_codegen_written, [])
        self.assertEqual(f.last_codegen_application['refused'], ['backend/routes/auth.js'])

    def test_partial_write_never_retries_the_stale_quotation(self):
        f = self.flow
        def generated(*args, **kwargs):
            f.last_codegen_written = ['frontend/src/App.jsx']
            return False, 'Incomplete FILE/EDIT output: complete blocks were applied'
        f.codegen_turn = Mock(side_effect=generated)
        f.whole_app_generation_turn('old quotation', 600, 'wave implement', spec_chars=100)
        f.codegen_turn.assert_called_once()
        self.assertTrue(any('Rebuild the next prompt' in p for p in f.pending_corrections))
        self.assertFalse(f._atomic_codegen_response)

    def test_folder_unknown_and_self_dependencies_match_sorting_semantics(self):
        a, b = leaf('A'), leaf('B')
        c = leaf('C', dependencies=['folder', 'C', 'unknown'])
        tree = {'id': 'root', 'type': 'FOLDER', 'children': [{'id': 'folder', 'type': 'FOLDER', 'children': [a, b]}, c]}
        self.assertEqual(dependency_ids(tree, c), ['A', 'B'])
        self.flow._dependency_tree = tree
        self.flow.test_verdict = {'A': True, 'B': False}
        self.assertEqual(self.flow.pending_dependencies(c), ['B'])
        self.flow.test_verdict['B'] = True
        self.assertFalse(self.flow.pending_dependencies(c))

    def test_incomplete_prerequisite_blocks_wave_but_not_independent_leaf(self):
        f = self.flow; a = leaf('A'); b = leaf('B', dependencies=['A']); c = leaf('C')
        f._dependency_tree = {'id': 'root', 'type': 'FOLDER', 'children': [a,b,c]}
        f.whole_app_deferred_ids = {'A'}; f.whole_app_generated_ids = {'A'}
        for verdict in (False, None, True):
            f.test_verdict = {'A': verdict}
            self.assertEqual(f.pending_dependencies(b, wave=True), ['A'])
        self.assertFalse(f.pending_dependencies(c, wave=True))
        f.whole_app_deferred_ids.clear()
        self.assertFalse(f.pending_dependencies(b, wave=True))

    def test_missing_negative_contract_cannot_be_hidden_by_positive_scenario_coverage(self):
        f = self.flow; node = leaf(description='Success displays “Password updated”. Incorrect input displays “Invalid credentials”.')
        directory = self.root/'.arc/derived-tests'; directory.mkdir(parents=True)
        f.derived_nodes = [node]; f.derived_tests_dir = directory; f.derived_as_specs = True
        f._derived_scenario_targets = [target(allowed=['Save', 'Password updated', 'Invalid credentials'])]
        source = "test('A: Scenario 1 [model]', async ({page}) => {\n await h.clickNamed(page, 'Save');\n await h.expectTextsVisible(page, ['Password updated']);\n});\n"
        (directory/'A.spec.ts').write_text(source)
        coverage = f.derived_scenario_coverage('A')
        self.assertEqual(coverage['covered'], 1)
        self.assertEqual(coverage['missing_contract_outcomes'], 1)
        self.assertTrue(f.derived_review_needed('A'))
        (directory/'A.spec.ts').write_text(source + source.replace('Scenario 1 [model]', 'Scenario 1 [case 2] [model]').replace('Password updated', 'Invalid credentials'))
        self.assertFalse(f.derived_review_needed('A'))

    def test_mechanical_wrong_precondition_can_be_quarantined_with_spec_edits_disabled(self):
        f = self.flow; directory = self.root/'.arc/derived-tests'; directory.mkdir(parents=True)
        title = 'A: Scenario 1 [reach] Create an account'
        source = ("import { test } from '@playwright/test';\n"
                  f"test('{title}', async ({{page}}) => {{\n"
                  "await h.signIn(page, 'alice-dev', 'Original-pass-123!');\n"
                  "await h.expectReachable(page, 'Create an account');\n});\n")
        (directory/'A.spec.ts').write_text(source)
        description = 'Only an unauthenticated visitor can open Create an account.'
        node = leaf(description=description)
        f.tests_dir = f.derived_tests_dir = directory; f.derived_as_specs = True
        f.derived_nodes = [node]; f.requirement_nodes = {'A':node}; f.driver = object()
        f.runner = Mock(); f.snapshot_protected = Mock(); f.final_phase_reserve = Mock(return_value=0)
        failed = RunSummary(total=1, results=[TestOutcome(title,False,'failed',1,file='A.spec.ts')])
        observed = RunSummary(total=1, results=[TestOutcome(title,False,'quarantined',0,file='A.spec.ts')])
        review = {'verdict':'oracle_dispute', 'reason_code':'requirement_conflict', 'requirement_quote':description,
                  'test_quote':"await h.signIn(page, 'alice-dev', 'Original-pass-123!');",
                  'evidence':'Test authenticates the visitor before the entry that requires an unauthenticated visitor.'}
        f.text_turn = Mock(return_value=(True,json.dumps(review))); f.run_specs = Mock(return_value=observed)
        f.write_derived_coverage = Mock()
        with patch.dict(os.environ, {'OCTOS_ARC_DERIVED_SPEC_REPAIR':'0'}):
            result = f.review_failed_derived_spec_with_model('A',['A.spec.ts'],failed)
        self.assertIs(result, observed); self.assertEqual(f.text_turn.call_count, 2)
        self.assertEqual((directory/'A.spec.ts').read_text(),source)
        self.assertEqual(set(f.generated_test_policy().quarantines()), {'A.spec.ts'})
        self.assertFalse(result.all_passed)

    def test_missing_import_in_complete_atomic_response_is_not_written(self):
        f = self.flow; f._atomic_codegen_response = True
        f.use_structured_edits = Mock(return_value=False)
        f.text_turn = Mock(return_value=(True, "<<<FILE frontend/src/App.jsx>>>\nimport Page from './Missing.jsx';\nexport default Page;\n<<<END FILE>>>"))
        ok, reason = f.codegen_turn('new application',60,'wave implement')
        self.assertFalse(ok); self.assertIn('missing',reason)
        self.assertFalse((self.root/'frontend/src/App.jsx').exists())

    def test_dependency_waiting_queue_resumes_if_independent_work_repairs_precondition(self):
        f = self.flow; nodes = [leaf('A'),leaf('B',dependencies=['A']),leaf('C')]
        tree = {'id':'root','type':'FOLDER','children':nodes}
        f.final_phase_due = Mock(return_value=False); f.time_up = Mock(return_value=False)
        f.prepare_derived_spec_batch = Mock(); f.regression_checkpoint = Mock()
        f.driver = Mock(); f.mark = Mock(); f.batch_codegen = Mock(return_value=False)
        f.llm_proxy = None; f.spec_map = {}; f._unresolved_startup_error = ''
        visited = []
        def run(node,*args,**kwargs):
            visited.append(node['id'])
            if node['id']=='A': f.test_verdict['A'] = False
            elif node['id']=='C': f.test_verdict['A'] = True; f.test_verdict['C'] = True
            else: f.test_verdict['B'] = True
        f.node_cycle = Mock(side_effect=run)
        with patch.dict(os.environ, {'OCTOS_ARC_SIBLING_BATCH_SIZE':'1'}):
            f.implement_sequential(tree,nodes,set())
        self.assertEqual(visited,['A','C','B'])


    def test_absent_error_message_does_not_cover_required_display(self):
        f = self.flow; node = leaf(description='Failure displays “Invalid credentials”.')
        directory = self.root/'.arc/derived-tests'; directory.mkdir(parents=True)
        f.derived_nodes=[node]; f.derived_tests_dir=directory; f.derived_as_specs=True
        f._derived_scenario_targets=[target(allowed=['Save','Invalid credentials'])]
        (directory/'A.spec.ts').write_text("test('A: Scenario 1 [model]',async ({page})=>{\nawait h.clickNamed(page,'Save');\nawait h.expectAbsent(page,'Invalid credentials');\n});\n")
        self.assertEqual(f.derived_scenario_coverage('A')['missing_contract_outcomes'],1)

    def test_cycles_allow_joint_construction_but_external_failed_edges_still_block(self):
        f = self.flow
        nodes=[leaf('A',dependencies=['B','C']),leaf('B',dependencies=['A']),leaf('C')]
        f._dependency_tree={'id':'root','type':'FOLDER','children':nodes}
        f.test_verdict={'C':False}
        self.assertEqual(f.pending_dependencies(nodes[0]),['C'])
        self.assertEqual(f.pending_dependencies(nodes[1]),['C'])
        f.test_verdict['C']=True
        self.assertEqual(f.pending_dependencies(nodes[1]),[])
        self.assertNotIn('A',f.test_verdict)  # Construction permission is not a passing verdict.

    def test_structured_implement_budget_and_controls_restore_even_after_failure(self):
        from types import SimpleNamespace
        f=self.flow
        f.llm_proxy=SimpleNamespace(extra_drop_tools=set(),tool_max_tokens=0,compact_reads=False,bounded_edits=False)
        captured=[]
        def turn(prompt,timeout,label,**kwargs):
            captured.append(kwargs['request_budget'])
            self.assertTrue(f.llm_proxy.bounded_edits)
            self.assertIn('no shell is available',prompt)
            if f.llm_proxy.turn_progress is not None:
                directory=self.root/'.arc/design'; directory.mkdir(parents=True,exist_ok=True)
                (directory/'A.json').write_text('{}')
                self.assertFalse(f.llm_proxy.turn_progress())
            return False,'bounded tool turn ended'
        f.turn=Mock(side_effect=turn)
        f.structured_edit_turn('active implementation',60,'A implement')
        self.assertEqual(captured,[8])
        self.assertFalse(f.llm_proxy.bounded_edits); self.assertFalse(f.llm_proxy.compact_reads)
        with patch.dict(os.environ,{'OCTOS_ARC_IMPLEMENT_REQUESTS':'5'}):
            f.structured_edit_turn('active implementation',60,'A implement')
        self.assertEqual(captured,[8,5])
        f.turn=Mock(side_effect=RuntimeError('model failure'))
        with self.assertRaises(RuntimeError): f.structured_edit_turn('active implementation',60,'A implement')
        self.assertFalse(f.llm_proxy.bounded_edits); self.assertEqual(f.llm_proxy.extra_drop_tools,set())


    def test_dependency_graph_cache_invalidates_when_folder_membership_changes(self):
        import requirement_order
        f=self.flow; a,b,c=leaf('A'),leaf('B'),leaf('C',dependencies=['folder'])
        folder={'id':'folder','type':'FOLDER','children':[a]}; other={'id':'other','type':'FOLDER','children':[b]}
        f._dependency_tree={'id':'root','type':'FOLDER','children':[folder,other,c]}
        f.test_verdict={'A':True,'B':False}
        with patch('requirement_order.dependency_graph',wraps=requirement_order.dependency_graph) as build:
            self.assertEqual(f.pending_dependencies(c),[])
            self.assertEqual(f.pending_dependencies(c),[])
            self.assertEqual(build.call_count,1)
            folder['children']=[b]; other['children']=[a]
            self.assertEqual(f.pending_dependencies(c),['B'])
            self.assertEqual(build.call_count,2)

    def test_waiting_event_is_blocked_not_an_application_failure(self):
        from arcbench_agent_runtime.events import EventClient
        from types import SimpleNamespace
        path=self.root/'events.jsonl'
        events=EventClient(SimpleNamespace(runner_events_path=path))
        writer=Mock(); events.set_requirement_state_writer(writer)
        events.mark_implementation_waiting('A','waiting for B')
        self.assertEqual(json.loads(path.read_text())['status'],'blocked')
        writer.assert_not_called()



class RealIdentityHelper(unittest.TestCase):
    def test_browser_identity_assertion_rejects_an_input_echo_and_detects_logout(self):
        install = os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT')
        if not install: self.skipTest('requires installed Playwright and Chromium')
        from acceptance import AcceptanceRunner
        with tempfile.TemporaryDirectory(dir=install, prefix='identity-regression-') as folder:
            root = Path(folder); tests = root/'tests'; tests.mkdir()
            helper = Path(__file__).resolve().parents[1]/'blueprints/derived-helpers.ts'
            (tests/'helpers.ts').write_text(helper.read_text())
            (tests/'A.spec.ts').write_text("""import {test,expect} from '@playwright/test';
import * as h from './helpers';
test('input echo', async ({page})=>{await page.setContent('<input value="alice-dev">'); await h.expectIdentity(page,'alice-dev',true);});
test('actual identity and logout', async ({page})=>{await page.setContent('<button>alice-dev</button>'); await h.expectIdentity(page,'alice-dev',true); await page.setContent('<input value="alice-dev">'); await h.expectIdentity(page,'alice-dev',false);});
""")
            runner = AcceptanceRunner(Path(install), tests, root/'prepared', lambda *_:None, workers=1)
            self.assertTrue(runner.list_specs(['A.spec.ts'])[0])
            result = runner.run(['A.spec.ts'], 'http://127.0.0.1:1', wall_timeout=40)
            self.assertEqual({r.title:r.status for r in result.results}, {'input echo':'failed','actual identity and logout':'passed'})

    def test_independent_cases_reset_server_state_and_each_execute(self):
        install=os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT')
        if not install: self.skipTest('requires installed Playwright and Chromium')
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from acceptance import AcceptanceRunner
        counter={'value':0,'resets':0}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                body=b"<button onclick=run('Done1')>Save1</button><button onclick=run('Done2')>Save2</button><p id=output></p><script>async function run(v){const r=await fetch('/increment?'+v,{method:'POST'});document.getElementById('output').textContent=await r.text()}</script>"
                self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                if self.path.startswith('/increment?'):
                    counter['value']+=1
                    body=(self.path.split('?',1)[1] if counter['value']==1 else 'Leaked state').encode()
                else:
                    counter['value']=0; counter['resets']+=1; body=b'{}'
                self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            t=target(allowed=['Save1','Save2','Done1','Done2'])
            cases=[proposal([{'op':'click','target':'Save'+str(i)},{'op':'expect_visible','target':'Done'+str(i)}]) for i in (1,2)]
            scripts,dropped=compile_reply(json.dumps({'scenarios':[{'id':'S1','cases':cases}]}),[t],Fixtures())
            self.assertFalse(dropped)
            with tempfile.TemporaryDirectory(dir=install,prefix='case-isolation-') as folder:
                root=Path(folder); tests=root/'tests'; tests.mkdir()
                helper=Path(__file__).resolve().parents[1]/'blueprints/derived-helpers.ts'
                (tests/'helpers.ts').write_text(helper.read_text())
                (tests/'A.spec.ts').write_text(spec_header('A')+'\n\n'.join(scripts['A']))
                runner=AcceptanceRunner(Path(install),tests,root/'prepared',lambda *_:None,workers=1)
                result=runner.run(['A.spec.ts'],f'http://127.0.0.1:{server.server_address[1]}',wall_timeout=40)
                self.assertTrue(result.all_passed,(result.error,[(r.title,r.message) for r in result.results]))
                self.assertEqual(result.total,2); self.assertEqual(counter['resets'],2)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
