"""Captured run regressions; real control flow with no provider/model calls."""
import argparse
import io
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml
from github_test_setup import github_setup_features
from frozen_setup import (frozen_setup_dependencies,
                          missing_setup, setup_generation_order)
from llm_proxy import LlmProxy
from main import Flow
from requirement_order import topo_order
from test_codegen_recovery import request
import test_diagnostic_repairs as flow_fixtures
import test_target_quoting as quoting_fixtures

ROOT = Path(__file__).resolve().parents[1]


class ContextRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixture = flow_fixtures.FlowRegression()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow, self.root = fixture.flow, fixture.root
        self.path = 'backend/model.js'
        (self.root / 'backend').mkdir()
        (self.root / self.path).write_text('module.exports = {};')
        self.flow.use_structured_edits = Mock(return_value=False)
        self.flow.llm_proxy = SimpleNamespace(turn_upstream_requests=1)
        self.flow.text_turn = Mock(return_value=(True, request([self.path])))
        def edit(*args, **kwargs):
            (self.root / self.path).write_text('module.exports = {ready:true};')
            self.flow.last_codegen_written = [self.path]
            self.flow.last_codegen_outcome = 'applied'
            return True, ''
        self.flow.structured_edit_turn = Mock(side_effect=edit)

    def test_repeated_read_switches_once_to_edit_with_remaining_request_allowance(self):
        ok, reason = self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=3)
        self.assertTrue(ok, reason)
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.flow.structured_edit_turn.assert_called_once()
        call = self.flow.structured_edit_turn.call_args
        self.assertEqual(call.kwargs['request_budget'], 1)
        self.assertLessEqual(call.args[1], 240)
        self.assertIn('module.exports = {};', call.args[0])
        self.assertEqual(self.flow.last_codegen_request_count, 3)
        self.assertEqual(self.flow.last_codegen_context_requested, set())

    def test_exhausted_allowance_does_not_start_tools(self):
        self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=2)[0])
        self.flow.structured_edit_turn.assert_not_called()

    def test_zero_tool_request_setting_does_not_start_tools(self):
        with patch.dict('os.environ', {'OCTOS_ARC_EDIT_REQUESTS': '0'}):
            self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=3)[0])
        self.flow.structured_edit_turn.assert_not_called()

    def test_disabled_tools_or_missing_proxy_preserve_bounded_stop(self):
        for proxy, enabled in ((None, '1'), (self.flow.llm_proxy, '0')):
            with self.subTest(proxy=proxy, enabled=enabled), patch.dict('os.environ', {'OCTOS_ARC_STRUCTURED_EDITS': enabled}):
                self.flow.llm_proxy = proxy
                self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=3)[0])
                self.flow.structured_edit_turn.assert_not_called()

    def test_partial_write_never_replays_generation_or_starts_context_tools(self):
        def partial(*args, **kwargs):
            self.flow.last_codegen_outcome = 'needs_context_repeated'
            self.flow.last_codegen_written = [self.path]
            self.flow.last_codegen_request_count = 1
            return False, 'source already changed'
        self.flow._codegen_attempt = Mock(side_effect=partial)
        self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=3)[0])
        self.flow._codegen_attempt.assert_called_once()
        self.flow.structured_edit_turn.assert_not_called()


class ResolvedRefusalTests(unittest.TestCase):
    def test_node_does_not_reimplement_a_successfully_corrected_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            quoting_fixtures._app(root, {'frontend/src/index.html': '<main>old</main>'})
            flow = quoting_fixtures.RefusalRetryTests()._flow(root)
            flow.codegen_implement_prompt = Mock(return_value='implementation prompt')
            def corrected(*args, **kwargs):
                flow.refused_paths.add('frontend/src/index.html')
                flow.last_codegen_refused = set()
                flow.last_codegen_written = ['frontend/src/index.html']
                flow.last_codegen_outcome = 'applied'
                (root / 'frontend/src/index.html').write_text('<main>corrected</main>')
                return True, 'corrected reply applied'
            flow.codegen_turn.side_effect = corrected
            Flow.node_cycle(flow, {'id': 'REQ-9', 'description': 'orders'}, [], 1, 1)
            flow.codegen_turn.assert_called_once()
            flow.acceptance_loop.assert_called_once()
            self.assertEqual((root / 'frontend/src/index.html').read_text(), '<main>corrected</main>')


class FrozenSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / 'derived-tests/hackathon--github'
        self.tree = yaml.safe_load((ROOT / 'tasks/hackathon--github/requirements.yaml').read_text())
        self.setup = frozen_setup_dependencies(self.directory, self.tree)

    def test_org_and_team_entry_closure_includes_search_and_overview(self):
        for owner in ('REQ-2-1-1', 'REQ-2-2-1'):
            self.assertLessEqual({'REQ-3-1', 'REQ-3-3'}, self.setup[owner])
        self.assertIn('REQ-2-1-1', self.setup['REQ-2-2-1'])
        self.assertIn('REQ-2-1-2', self.setup['REQ-2-2-1'])

    def test_declared_pr_dependency_and_helper_preparation_cycle_both_wait_for_code(self):
        self.assertIn('REQ-6-2-3', self.setup['REQ-6-3-1'])
        self.assertIn('REQ-6-3-1', self.setup['REQ-6-2-3'])
        missing = missing_setup('REQ-6-3-1', self.setup, set(self.setup) - {'REQ-6-2-3'})
        self.assertEqual(missing, {'REQ-6-2-3'})

    def test_actual_transitive_helper_source_is_followed(self):
        helpers = 'export async function organization(p) { await custom(p); }\nexport async function custom(p) { await repo(p); }\nexport async function repo(p) { await home(p); }'
        self.assertLessEqual({'REQ-3-1', 'REQ-3-3'}, github_setup_features('await h.organization(page);', helpers))

    def test_generation_reaches_both_members_of_preparation_cycle_before_org(self):
        ordered, cycles = setup_generation_order(self.tree, self.setup)
        ids = [node['id'] for node in ordered]
        self.assertEqual(set(ids), {node['id'] for node in topo_order(self.tree)})
        self.assertEqual(len(ids), len(set(ids)))
        for owner in ('REQ-2-1-1', 'REQ-2-2-1'):
            self.assertLess(ids.index('REQ-3-1'), ids.index(owner))
            self.assertLess(ids.index('REQ-3-3'), ids.index(owner))
        self.assertTrue(any({'REQ-3-1', 'REQ-3-3'} <= set(cycle) for cycle in cycles))

    def test_missing_setup_closure_does_not_wait_on_its_own_cycle_member(self):
        setup = {'A': {'B'}, 'B': {'A', 'C'}}
        self.assertEqual(missing_setup('A', setup, {'B'}), {'C'})
        self.assertEqual(missing_setup('A', setup, {'B', 'C'}), set())

    def test_unknown_setup_is_rejected_and_empty_setup_preserves_order(self):
        with self.assertRaises(ValueError):
            setup_generation_order(self.tree, {'REQ-2-1-1': {'UNKNOWN'}})
        self.assertEqual(setup_generation_order(self.tree, {})[0], topo_order(self.tree))

    def test_runtime_coordinator_uses_setup_order_for_verified_github_suite(self):
        import test_embedded_suites as suite_fixtures
        fixture = suite_fixtures.EmbeddedSuiteTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        import shutil
        shutil.rmtree(fixture.directory)
        shutil.copytree(self.directory, fixture.directory)
        fixture.tree = self.tree
        flow, _ = fixture._run_trusted_source_flow(suite_name='hackathon--github')
        expected = [node['id'] for node in setup_generation_order(self.tree, self.setup)[0]]
        self.assertEqual([call.args[0] for call in flow.acceptance_loop.call_args_list], expected)
        self.assertEqual(flow._frozen_setup_dependencies, self.setup)

    def test_setup_comes_from_command_metadata_without_helper_or_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            tree = {'id':'ROOT','children':[{'id':'A'},{'id':'B'}]}
            (directory/'case-plan.json').write_text(json.dumps([
                {'node_id':'A','phase':'node','setup_requires':['B'],'requires':['A']},
                {'node_id':'B','phase':'node','setup_requires':[],'requires':['B']},
            ]))
            self.assertEqual(frozen_setup_dependencies(directory, tree), {'A': {'B'}, 'B': set()})
            (directory/'case-plan.json').write_text('[{"node_id":"A","phase":"node","requires":["A"]}]')
            self.assertEqual(frozen_setup_dependencies(directory, tree), {})

    def test_acceptance_waits_without_browser_or_repair_then_resumes_once(self):
        with tempfile.TemporaryDirectory() as folder:
            flow = Flow(argparse.Namespace(web_port=3000), Path(folder), Path(folder))
            flow.runner = Mock()
            flow.metric = Mock()
            flow.run_specs = Mock(side_effect=AssertionError('entry is not ready'))
            flow._frozen_setup_dependencies = {'A': {'B'}, 'B': {'A'}}
            flow.spec_map = {'A': ['A.spec.ts']}
            flow.implementation_evidence = {'A': {'status': 'implemented_unverified'}}
            self.assertIsNone(flow.acceptance_loop('A', ['A.spec.ts'], time.time() + 60))
            flow.run_specs.assert_not_called()
            self.assertEqual(flow._pending_frozen_acceptance, {'A'})
            flow.test_verdict['A'] = None
            flow.implementation_evidence['B'] = {'status': 'implemented_unverified'}
            flow.remaining = Mock(return_value=600)
            flow.wound_down = Mock(return_value=False)
            flow.acceptance_loop = Mock(return_value=False)
            flow.resume_frozen_acceptance([{'id': 'A'}, {'id': 'B'}])
            flow.acceptance_loop.assert_called_once()
            self.assertIs(flow.test_verdict['A'], False)
            flow.resume_frozen_acceptance([{'id': 'A'}])
            flow.acceptance_loop.assert_called_once()


class ProxyTransportTests(unittest.TestCase):
    def send(self, *, error=None, status=400, usage=None, single=False, expired=False):
        proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(proxy.server.server_close)
        proxy.begin_turn(3)
        proxy.single_attempt = single
        if expired:
            proxy.turn_deadline = time.monotonic() + 1
        payload = {'error': error or {'type': 'proxy_error', 'message': 'upstream: unexpected EOF'}}
        if usage is not None:
            payload['usage'] = usage
        failure = urllib.error.HTTPError('http://unused', status, 'Bad request', {}, io.BytesIO(json.dumps(payload).encode()))
        response = Mock(status=200, headers={})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b'{"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}'
        with patch('llm_proxy.open_upstream', side_effect=[failure, response]) as upstream, patch('llm_proxy.time.sleep'):
            result = proxy._request_upstream('POST', '/chat/completions', b'{"messages":[]}', {})
        return proxy, result, upstream.call_count

    def test_wrapped_eof_gets_one_retry_and_preserves_unknown_usage_reservation(self):
        proxy, result, calls = self.send()
        self.assertEqual(result[0], 200)
        self.assertEqual(calls, 2)
        self.assertGreater(proxy.estimated_tokens, 0)
        self.assertFalse(proxy.provider_unavailable)

    def test_ordinary_bad_requests_and_ambiguous_proxy_errors_are_not_retried(self):
        for error in ({'code': 'invalid_request_error', 'message': 'unexpected EOF'},
                      {'type': 'proxy_error', 'message': 'unsupported model'},
                      {'code': 'local_context_limit', 'message': 'context too long'}):
            with self.subTest(error=error):
                _, result, calls = self.send(error=error)
                self.assertEqual(result[0], 400)
                self.assertEqual(calls, 1)

    def test_single_attempt_deadline_and_reported_usage_prevent_retry(self):
        for options in ({'single': True}, {'expired': True}, {'usage': {'prompt_tokens': 1, 'completion_tokens': 2}}):
            with self.subTest(options=options):
                _, result, calls = self.send(**options)
                self.assertEqual(result[0], 400)
                self.assertEqual(calls, 1)


if __name__ == '__main__':
    unittest.main()
