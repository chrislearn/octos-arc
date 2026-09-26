"""Regression checks for failures observed in the stopped v11.1 local run."""
import argparse
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

from acceptance import RunSummary, TestOutcome
from llm_proxy import reject_unoffered_tool_calls
from main import Flow
from scenario_review import proposal_problems, validate_proposal, semantic_contracts, semantic_contract_evidence, review_targets
from scenario_tests import Fixtures, compile_leaf


class TestOracleBoundaries(unittest.TestCase):
    def test_unprovisioned_team_maintainer_never_gets_anonymous_reach_or_owner_case(self):
        node = {'id': 'REQ-team', 'name': 'Members', 'description': 'Team membership.',
                'scenarios': [{'name': 'REQ-team: Scenario 1', 'steps': [
                    {'keyword': 'GIVEN', 'content': 'A team maintainer opens an organization team.'},
                    {'keyword': 'WHEN', 'content': 'The maintainer clicks “Members”.'},
                    {'keyword': 'THEN', 'content': 'The roster is displayed.'}]}]}
        fixtures = Fixtures(account='alice-dev', password='Valid-password-123!')
        self.assertNotIn("test('", compile_leaf(node, fixtures).source)
        target = review_targets([node], fixtures, include_all=True)[0]
        proposal = {'confidence': .9, 'signed_in': True, 'steps': [
            {'op': 'click', 'target': 'Members'}, {'op': 'expect_visible', 'target': 'Members'}]}
        self.assertTrue(any('unverified GIVEN actor' in item for item in
                            proposal_problems(proposal, target, fixtures)))

    def test_semantic_outcome_does_not_disappear_when_case_keeps_only_entry(self):
        steps = ['THEN: The visitor can immediately sign in with the new account and enter the workspace.']
        self.assertEqual([row['kind'] for row in semantic_contracts(steps)], ['new_account_sign_in'])
        title = 'REQ: registration [case 1] [model]'
        weak = f"test('{title}', async ({{page}}) => {{ await h.clickNamed(page, 'Create account'); await h.expectTextsVisible(page, ['Sign in']); }});"
        self.assertFalse(semantic_contract_evidence(weak, title, 'new_account_sign_in'))
        strong = (f"test('{title}', async ({{page}}) => {{ await h.fillField(page, 'Username', 'user-abcdef'); "
                  "await h.clickNamed(page, 'Create account'); await h.signIn(page, 'user-abcdef', 'Derived-pass-abcdef!'); "
                  "await h.expectIdentity(page, 'user-abcdef', true); }});")
        self.assertTrue(semantic_contract_evidence(strong, title, 'new_account_sign_in'))

    def test_new_account_sign_in_requires_registration_in_same_case(self):
        fixtures = Fixtures(account='alice-dev', password='Valid-password-123!')
        target = {'title': 'A: Scenario 1', 'description': 'Create an account then sign in.',
                  'steps': ['THEN: The new account can sign in.'],
                  'allowed': ['Create account', 'Username', 'Sign in'], 'controls': ['Create account'],
                  'seeds': [], 'required_actions': [], 'required_then_literal': ''}
        proposal = {'confidence': .9, 'steps': [{'op': 'sign_in', 'target': '$NEW_USERNAME',
                                                 'value': '$NEW_PASSWORD'},
                                                {'op': 'expect_visible', 'target': 'Sign in'}]}
        self.assertTrue(any('before this case registered' in p for p in proposal_problems(proposal, target, fixtures)))

    def test_unknown_email_needs_rejection_after_reset_to_prove_no_account(self):
        steps = ['THEN: An unknown email does not modify any account.']
        self.assertEqual([row['kind'] for row in semantic_contracts(steps)],
                         ['unknown_email_recovery', 'unknown_email_no_account'])
        title = 'REQ: recovery [case 1] [model]'
        weak = (f"test('{title}', async ({{page}}) => {{ "
                "await h.fillField(page, 'Email', 'unknown-abcdef@example.test'); "
                "await h.clickNamed(page, 'Send reset link'); "
                "await h.expectTextsVisible(page, ['123456']); });")
        self.assertTrue(semantic_contract_evidence(weak, title, 'unknown_email_recovery'))
        self.assertFalse(semantic_contract_evidence(weak, title, 'unknown_email_no_account'))
        strong = weak.replace("});", "await h.clickNamed(page, 'Reset password'); "
                              "await h.expectSignInRejected(page, 'unknown-abcdef@example.test', "
                              "'Derived-pass-abcdef!'); });")
        self.assertTrue(semantic_contract_evidence(strong, title, 'unknown_email_no_account'))

    def test_cancel_branch_keeps_identity_without_confirmed_signout_oracle(self):
        fixtures = Fixtures(account='alice-dev', password='Valid-password-123!')
        target = {'id': 'S1', 'node_id': 'A', 'title': 'A: Scenario 1',
                  'description': 'Only “Confirm sign out” invalidates the session; “Cancel” retains it.',
                  'steps': ['THEN: After confirming, display “Sign in”; if the user cancels, the session remains valid.'],
                  'allowed': ['Sign out', 'Confirm sign out', 'Cancel', 'Sign in', 'alice-dev'],
                  'controls': ['Sign out', 'Confirm sign out', 'Cancel'],
                  'required_then_literal': 'Sign in'}
        steps = [{'op': 'click', 'target': 'Sign out'}, {'op': 'click', 'target': 'Cancel'},
                 {'op': 'expect_visible', 'target': 'alice-dev'}]
        proposal = {'id': 'S1', 'signed_in': True, 'confidence': .9, 'steps': steps}
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        self.assertIn('h.expectIdentity', validate_proposal(proposal, target, fixtures))
        confirmed = {**proposal, 'steps': [{'op': 'click', 'target': 'Sign out'},
                                          {'op': 'click', 'target': 'Confirm sign out'},
                                          {'op': 'expect_visible', 'target': 'alice-dev'}]}
        self.assertTrue(proposal_problems(confirmed, target, fixtures))

    def review_flow(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        flow = Flow(argparse.Namespace(web_port=3000), root, root)
        tests = root / 'tests'; tests.mkdir()
        source = ("test('A: Scenario 1 [reach] Members', async ({ page }) => {\n"
                  "  await h.openHome(page);\n  await h.expectReachable(page, 'Members');\n});\n")
        (tests / 'A.spec.ts').write_text(source)
        flow.tests_dir = flow.derived_tests_dir = tests
        flow.derived_as_specs = True
        node = {'id': 'A', 'name': 'A', 'description': 'The signed-in Owner opens the team Members page.',
                'scenarios': [{'name': 'A: Scenario 1', 'steps': [
                    {'keyword': 'GIVEN', 'content': 'A signed-in Owner starts on the home page.'},
                    {'keyword': 'WHEN', 'content': 'The Owner opens “Members”.'},
                    {'keyword': 'THEN', 'content': 'The team member list is displayed.'}]}]}
        flow.requirement_nodes = {'A': node}
        flow.derived_nodes = [node]
        flow.requirement_tree = node
        flow.driver = object()
        flow.runner = Mock()
        flow.runner.list_specs.return_value = (True, [])
        flow.suite_is_measured = Mock(return_value=True)
        flow.review_budget_spent = Mock(return_value=False)
        flow.remaining = Mock(return_value=5000)
        flow.final_phase_reserve = Mock(return_value=0)
        flow.wound_down = Mock(return_value=False)
        flow.snapshot_protected = Mock()
        flow.flag_derived_spec_dispute = Mock()
        flow.metric = Mock()
        row = TestOutcome(title='A: Scenario 1 [reach] Members', ok=False, status='failed',
                          duration_ms=41000, file='A.spec.ts',
                          message='Required control or text "Members" is not reachable within 3 navigation clicks')
        return flow, source, RunSummary(results=[row], total=1, passed=0)

    def test_depth_exhaustion_is_unresolved_before_any_app_repair_call(self):
        flow, source, summary = self.review_flow()
        flow.oracle_review_turn = Mock(side_effect=AssertionError('a crawl limit needs no model opinion'))
        self.assertIsNone(flow.review_failed_derived_spec_with_model('A', ['A.spec.ts'], summary))
        self.assertTrue((flow.tests_dir.parent / 'test-control' / 'test-policy.json').exists())
        self.assertEqual((flow.tests_dir / 'A.spec.ts').read_text(), source)
        flow.flag_derived_spec_dispute.assert_called_once()

    def test_ungrounded_spec_error_cannot_apply_a_replacement(self):
        flow, source, summary = self.review_flow()
        summary.results[0].message = 'expect failed after wrong action'
        reply = json.dumps({'verdict': 'spec_error', 'evidence': 'The test omitted a sign-in action before Members.',
                            'scenarios': []})
        flow.oracle_review_turn = Mock(return_value=(True, reply))
        flow.run_specs = Mock(side_effect=AssertionError('unreviewed replacement must not run'))
        self.assertIsNone(flow.review_failed_derived_spec_with_model('A', ['A.spec.ts'], summary))
        self.assertEqual(flow.oracle_review_turn.call_count, 2)  # one format-only retry
        self.assertEqual((flow.tests_dir / 'A.spec.ts').read_text(), source)
        flow.flag_derived_spec_dispute.assert_not_called()


class TestExecutionBoundaries(unittest.TestCase):
    def test_unoffered_read_call_is_removed_but_offered_edit_survives(self):
        request = {'tools': [{'type': 'function', 'function': {'name': 'edit_file'}}]}
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
            'tool_calls': [
                {'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}},
                {'id': 'edit', 'type': 'function', 'function': {'name': 'edit_file', 'arguments': '{}'}}]}}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 2, 'total_tokens': 7}}
        payload, refused = reject_unoffered_tool_calls(json.dumps(request).encode(), json.dumps(response).encode())
        result = json.loads(payload)
        self.assertEqual(refused, ['read_file'])
        self.assertEqual([c['function']['name'] for c in result['choices'][0]['message']['tool_calls']], ['edit_file'])
        self.assertEqual(result['usage'], response['usage'])
        only_read = json.loads(json.dumps(response)); only_read['choices'][0]['message']['tool_calls'] = response['choices'][0]['message']['tool_calls'][:1]
        payload, _ = reject_unoffered_tool_calls(json.dumps(request).encode(), json.dumps(only_read).encode())
        self.assertEqual(json.loads(payload)['choices'][0]['finish_reason'], 'stop')
        self.assertNotIn('tool_calls', json.loads(payload)['choices'][0]['message'])

    def test_tool_choice_none_and_legacy_call_are_enforced(self):
        request = {'tools': [{'type': 'function', 'function': {'name': 'read_file'}}],
                   'tool_choice': 'none'}
        response = {'choices': [{'finish_reason': 'function_call', 'message': {
            'role': 'assistant', 'content': [{'type': 'text', 'text': 'ignored'}],
            'function_call': {'name': 'read_file', 'arguments': '{}'}}}]}
        payload, refused = reject_unoffered_tool_calls(json.dumps(request).encode(), json.dumps(response).encode())
        result = json.loads(payload)['choices'][0]
        self.assertEqual(refused, ['read_file'])
        self.assertEqual(result['finish_reason'], 'stop')
        self.assertNotIn('function_call', result['message'])

    def test_dependencies_do_not_gate_generation_and_repair_budget_is_shared(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        flow = Flow(argparse.Namespace(web_port=3000), root, root)
        flow.pending_dependencies = Mock(side_effect=[['A'], []])
        flow.metric = Mock(); flow.mark = Mock()
        flow.test_verdict = {'A': False}
        self.assertTrue(flow.admit_node({'id': 'B'}))
        self.assertNotIn('B', flow.test_verdict)
        flow.metric.assert_any_call('implementation_dependency_unverified', node_id='B',
                                    dependencies=['A'], decision='admitted')
        self.assertTrue(flow.admit_node({'id': 'C'}))
        proxy = Mock(turn_upstream_requests=8, hard_budget_exhausted=False)
        flow.llm_proxy = proxy
        flow.codegen_mode = Mock(return_value=True)
        flow.codegen_repair_prompt = Mock(return_value='compact')
        flow.codegen_turn = Mock(return_value=(True, ''))
        flow.last_codegen_written = []
        flow.last_codegen_refused = set()
        flow.last_codegen_degenerated = True
        flow.last_codegen_outcome = 'unchanged'
        flow.remaining = Mock(return_value=5000)
        flow.wound_down = Mock(return_value=False)
        flow.compact_tool_repair_prompt = Mock(side_effect=lambda p, f: p)
        flow.repair_tool_turn = Mock(return_value=(True, 'done'))
        flow.pending_corrections = []
        flow.node_repair_turn('B', 'failure', 100, 'B repair', lambda: 'prompt')
        self.assertEqual(flow.codegen_turn.call_args.kwargs['request_budget'], 12)
        self.assertEqual(flow.repair_tool_turn.call_args.kwargs['request_budget'], 4)

    def test_protocol_retry_spends_only_remaining_round_allowance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            proxy = Mock(turn_upstream_requests=0, hard_budget_exhausted=False)
            flow.llm_proxy = proxy
            flow.codegen_mode = Mock(return_value=True)
            flow.codegen_repair_prompt = Mock(return_value='compact')
            flow.remaining = Mock(return_value=5000)
            flow.wound_down = Mock(return_value=False)
            flow.compact_tool_repair_prompt = Mock(side_effect=lambda p, f: p)
            flow.repair_tool_turn = Mock(return_value=(True, 'tool fallback'))
            flow.pending_corrections = []
            allowances = []

            def codegen(_prompt, _left, _label, **kwargs):
                allowances.append(kwargs['request_budget'])
                proxy.turn_upstream_requests = min(8, kwargs['request_budget'])
                flow.last_codegen_written = []
                flow.last_codegen_refused = set()
                flow.last_codegen_degenerated = False
                flow.last_codegen_outcome = 'no_blocks'
                return False, 'codegen reply contained no complete blocks'

            flow.codegen_turn = codegen
            flow.node_repair_turn('B', 'failure', 100, 'B repair', lambda: 'prompt')
            self.assertEqual(allowances, [12, 4])
            flow.repair_tool_turn.assert_not_called()


class TestBrowserHelperRegression(unittest.TestCase):
    def test_rejected_login_does_not_count_as_a_session(self):
        install = os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT')
        if not install:
            self.skipTest('requires installed Playwright and Chromium')
        from acceptance import AcceptanceRunner
        body = ("<!doctype html><html><body><main><a href='/sign-in'>Sign in</a>"
                "<form><input aria-label='Username or email'><input type='password' aria-label='Password'>"
                "<button type='submit'>Sign in</button></form></main><script>"
                "document.querySelector('form').onsubmit=e=>{e.preventDefault();"
                "const fields=document.querySelectorAll('input');"
                "if(fields[0].value==='alice-dev'&&fields[1].value==='right-password')"
                "document.querySelector('main').innerHTML='<h1>Workspace</h1>';}"
                "</script></body></html>").encode()
        reset_body = ("<!doctype html><html><body><main><a href='/sign-in'>Sign in</a>"
                      "<form><input type='password' aria-label='New password'>"
                      "<button type='submit'>Reset password</button></form></main></body></html>").encode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                page_body = reset_body if self.path == '/reset' else body
                self.send_response(200); self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(page_body))); self.end_headers(); self.wfile.write(page_body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=install, prefix='negative-login-') as folder:
                root = Path(folder); tests = root / 'tests'; tests.mkdir()
                helper = Path(__file__).resolve().parents[1] / 'blueprints' / 'derived-helpers.ts'
                (tests / 'helpers.ts').write_text(helper.read_text())
                (tests / 'A.spec.ts').write_text(
                    "import {test,expect} from '@playwright/test'; import * as h from './helpers';\n"
                    "test('login rejection', async ({page}) => { await h.openHome(page); "
                    "await page.goto(new URL('/reset', page.url()).toString()); "
                    "await h.expectSignInRejected(page, 'unknown-abcdef@example.test', 'right-password'); "
                    "await h.signIn(page, 'alice-dev', 'right-password'); "
                    "await expect(page.getByRole('heading', {name:'Workspace'})).toBeVisible(); });\n")
                runner = AcceptanceRunner(Path(install), tests, root / 'prepared', lambda *_: None, workers=1)
                result = runner.run(['A.spec.ts'], f'http://127.0.0.1:{server.server_address[1]}', wall_timeout=35)
                self.assertTrue(result.all_passed, (result.error, [(r.title, r.message[:350]) for r in result.results]))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_delayed_spa_route_does_not_fill_old_similarly_named_field(self):
        install = os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT')
        if not install:
            self.skipTest('requires installed Playwright and Chromium')
        from acceptance import AcceptanceRunner
        body = ("<!doctype html><html><body><main><label>Username or email"
                "<input id='old'></label><a href='/register' id='entry'>Create an account</a></main>"
                "<script>document.getElementById('entry').onclick=e=>{e.preventDefault();"
                "history.pushState({},'', '/register');setTimeout(()=>{"
                "document.querySelector('main').innerHTML='<label>Username<input id=new></label>'"
                "},120)}</script></body></html>").encode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200); self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                self.send_response(200); self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=install, prefix='spa-field-') as folder:
                root = Path(folder); tests = root / 'tests'; tests.mkdir()
                helper = Path(__file__).resolve().parents[1] / 'blueprints' / 'derived-helpers.ts'
                (tests / 'helpers.ts').write_text(helper.read_text())
                (tests / 'A.spec.ts').write_text(
                    "import {test,expect} from '@playwright/test'; import * as h from './helpers';\n"
                    "test('route field', async ({page}) => { await h.openHome(page); "
                    "await h.clickNamed(page, 'Create an account'); "
                    "await h.fillField(page, 'Username', 'new-user'); "
                    "await expect(page.locator('#new')).toHaveValue('new-user'); "
                    "await expect(page.locator('#old')).toHaveCount(0); });\n")
                runner = AcceptanceRunner(Path(install), tests, root / 'prepared', lambda *_: None, workers=1)
                result = runner.run(['A.spec.ts'], f'http://127.0.0.1:{server.server_address[1]}', wall_timeout=35)
                self.assertTrue(result.all_passed, (result.error, [(r.title, r.message[:350]) for r in result.results]))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
