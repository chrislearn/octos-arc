import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import main as m
from llm_proxy import LlmProxy, cap_output_tokens, open_upstream, usage_record
from acceptance import page_snapshot
from web_stack import REACT_CONTRACT
import test_whole_app_v5 as whole_tests


class KeepFullRecoveryTests(TestCase):
    setUp = whole_tests.WholeAppTests.setUp

    def test_single_failed_leaf_does_not_abandon_later_groups(self):
        f = self.flow
        f.codegen_implement_prompt = Mock(return_value='prompt')
        def generate(*args, **kwargs):
            ok = f.codegen_turn.call_count > 1
            f.last_codegen_written = ['frontend/a.js'] if ok else []
            return ok, 'files' if ok else 'output_truncated'
        f.codegen_turn = Mock(side_effect=generate)
        with patch.dict('os.environ', {'OCTOS_ARC_WHOLE_APP_WAVE_NODES': '1'}):
            self.assertTrue(f.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(f.codegen_turn.call_count, 3)
        self.assertEqual(f.whole_app_generated_ids, {'B', 'C'})
        self.assertEqual(f.whole_app_deferred_ids, {'A'})
        self.assertEqual(f.test_verdict, {})

    def test_partial_group_is_split_and_each_leaf_is_completed(self):
        f = self.flow
        f.codegen_implement_prompt = Mock(return_value='prompt')
        def generate(*args, **kwargs):
            f.last_codegen_written = ['frontend/a.js']
            return f.codegen_turn.call_count > 1, 'incomplete_blocks'
        f.codegen_turn = Mock(side_effect=generate)
        with patch.dict('os.environ', {'OCTOS_ARC_WHOLE_APP_WAVE_NODES': '2'}):
            self.assertTrue(f.whole_app_waves(self.tree, self.nodes))
        self.assertEqual(f.codegen_turn.call_count, 4)
        self.assertEqual(f.whole_app_partial_ids, set())
        self.assertEqual(f.whole_app_generated_ids, {'A', 'B', 'C'})
        self.assertEqual(f.test_verdict, {})

    def test_per_node_prompt_preserves_scenarios_and_dependencies(self):
        node = {'id': 'B', 'description': 'Assign a default category', 'dependencies': ['A'],
                'scenarios': [{'steps': [{'keyword': 'WHEN', 'content': 'User chooses a category'},
                                         {'keyword': 'THEN', 'content': 'Unselected options remain absent'}]}]}
        prompt = self.flow.codegen_implement_prompt(node, 'test example')
        self.assertIn('WHEN User chooses a category', prompt)
        self.assertIn('THEN Unselected options remain absent', prompt)
        self.assertIn('Depends on: A', prompt)

    def test_shared_layout_and_required_gesture_contracts_are_domain_neutral(self):
        self.assertIn('reuse one layout', m.APP_DESIGN_PROMPT)
        self.assertIn('Router Outlet', REACT_CONTRACT)
        self.assertIn('required', REACT_CONTRACT)
        self.assertNotIn('REQ-2.4', REACT_CONTRACT)

    def test_short_codegen_admission_respects_explicit_user_floor(self):
        f = self.flow
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(f.repair_minimum(), 60)
            f.repair_durations['codegen'] = [100]
            self.assertAlmostEqual(f.repair_minimum(), 110)
            f.codegen_mode.return_value = False
            self.assertEqual(f.repair_minimum(), 300)
        f.codegen_mode.return_value = True
        with patch.dict('os.environ', {'OCTOS_MIN_REPAIR_SECONDS': '300'}):
            self.assertEqual(f.repair_minimum(), 300)

    def test_partial_node_repair_is_tested_before_tool_fallback(self):
        f = self.flow
        f.codegen_repair_prompt = Mock(return_value='prompt')
        def generate(*args, **kwargs):
            f.last_codegen_written = ['frontend/a.js']
            f.last_codegen_refused = set()
            return False, 'incomplete_blocks'
        f.codegen_turn = Mock(side_effect=generate)
        f.turn = Mock()
        self.assertTrue(f.node_repair_turn('A', 'failed', 100, 'repair', lambda: 'prompt'))
        f.codegen_turn.assert_called_once()
        f.turn.assert_not_called()

    def test_partial_suite_repair_is_tested_before_tool_fallback(self):
        f = self.flow
        f.suite_repair_prompt = Mock(return_value='prompt')
        def generate(*args, **kwargs):
            f.last_codegen_written = ['frontend/a.js']
            f.last_codegen_refused = set()
            return False, 'incomplete_blocks'
        f.codegen_turn = Mock(side_effect=generate)
        f.turn = Mock()
        self.assertEqual(f.suite_repair_turn('repair', ['A'], 'failed', 100, tool_prompt='tools')[0], 'codegen')
        f.turn.assert_not_called()

    def test_output_ceiling_preserves_smaller_route_limits_and_other_fields(self):
        for field in ['max_tokens', 'max_completion_tokens']:
            body = json.dumps({'messages': [], field: 32768, 'model': 'custom'}).encode()
            capped = json.loads(cap_output_tokens(body, 8192))
            self.assertEqual(capped[field], 8192)
            self.assertEqual(capped['model'], 'custom')
            capped[field] = 4000
            self.assertEqual(json.loads(cap_output_tokens(json.dumps(capped).encode(), 8192))[field], 4000)
        self.assertEqual(cap_output_tokens(b'invalid', 8192), b'invalid')

    def test_recovery_cap_also_constrains_wave_planner(self):
        f = self.flow
        f.codegen_degenerated = True
        with patch.dict('os.environ', {'OCTOS_ARC_DEGENERATE_MAX_TOKENS': '8192',
                                       'OCTOS_ARC_CODEGEN_OUTPUT_TOKENS': '32768'}):
            self.assertEqual(f.generation_output_budget(), 8192)

    def test_recovery_reasoning_is_opt_in_and_settings_are_restored(self):
        f = self.flow
        proxy = SimpleNamespace(mode='none', no_tools=False, system_override=None, codegen_max_tokens=123)
        f.llm_proxy = proxy
        f.driver = SimpleNamespace(without_tools=lambda: nullcontext())
        f.codegen_reasoning = Mock(return_value='none')
        f.codegen_degenerated = True
        observed = []
        def turn(*args, **kwargs):
            observed.append((f.base_reasoning_mode, proxy.codegen_max_tokens))
            return True, 'reply'
        f.turn = Mock(side_effect=turn)
        with patch.dict('os.environ', {'OCTOS_ARC_RECOVERY_REASONING': 'none',
                                       'OCTOS_ARC_DEGENERATE_MAX_TOKENS': '8192'}):
            f.text_turn('prompt', 30, 'A repair')
        with patch.dict('os.environ', {'OCTOS_ARC_RECOVERY_REASONING': 'low',
                                       'OCTOS_ARC_DEGENERATE_MAX_TOKENS': '8192'}):
            f.text_turn('prompt', 30, 'A repair')
            f.text_turn('prompt', 30, 'application design')
        self.assertEqual(observed, [('none', 8192), ('low', 8192), ('none', 8192)])
        self.assertEqual(f.base_reasoning_mode, 'none')
        self.assertEqual(proxy.codegen_max_tokens, 123)
        self.assertFalse(proxy.no_tools)

    def test_repeated_suffix_applies_one_valid_cycle_but_requires_verification(self):
        f = self.flow
        (self.root / 'frontend').mkdir()
        path = self.root / 'frontend/a.js'
        old, new = 'a' * 400, 'b' * 400
        path.write_text(old + '\n')
        block = f'<<<EDIT frontend/a.js>>>\n<<<SEARCH>>>\n{old}\n<<<REPLACE>>>\n{new}\n<<<END EDIT>>>\n'
        f.text_turn = Mock(return_value=(True, block * 5))
        ok, _ = f.codegen_turn(f'--- frontend/a.js ---\n{old}\n', 30, 'A implement')
        self.assertFalse(ok)
        self.assertEqual(path.read_text(), new + '\n')
        self.assertTrue(f.codegen_degenerated)
        self.assertEqual(f.last_codegen_outcome, 'incomplete_blocks')
        self.assertEqual(f.test_verdict, {})

    def test_snapshot_clipping_keeps_active_dialog_after_large_background(self):
        background = '- generic [aria-hidden]:\n' + '  - button "Background item"\n' * 500
        surface = '- dialog "Editor":\n  - textbox "Title" [active]\n  - button "Save"\n'
        context = '# Page snapshot\n\n```yaml\n' + background + surface + '```\n'
        snapshot = page_snapshot(context, max_chars=4000)
        self.assertLessEqual(len(snapshot), 4000)
        self.assertIn('textbox "Title" [active]', snapshot)
        self.assertIn('button "Save"', snapshot)
        self.assertNotIn('Background item', snapshot)

    def test_usage_records_actual_finish_reason_without_response_content(self):
        data = {'usage': {'completion_tokens': 8000}, 'choices': [
            {'finish_reason': 'length', 'message': {'content': 'private source code'}}]}
        for payload in [json.dumps(data).encode(), ('data: ' + json.dumps(data) + '\n\ndata: [DONE]\n').encode()]:
            record = usage_record(payload, 10, 'none')
            self.assertEqual(record['finish_reasons'], ['length'])
            self.assertNotIn('private source code', str(record))

    def test_real_proxy_wire_enforces_ceiling_after_routing_only_for_codegen(self):
        import urllib.request
        proxy = LlmProxy('http://127.0.0.1:1/v1', 'none', trim=False).start()
        self.addCleanup(proxy.stop)
        payload = b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
        proxy._request_upstream = Mock(return_value=(200, payload, {}))
        proxy.codegen_max_tokens = 8192
        body = json.dumps({'model': 'original', 'messages': [], 'max_tokens': 4096}).encode()
        for codegen, parameters, expected in [
                (True, {'max_tokens': 16000}, 8192),
                (True, {'max_completion_tokens': 4000}, 4000),
                (False, {'max_tokens': 16000}, 16000)]:
            proxy.no_tools = codegen
            proxy.routes = [{'model': 'routed', 'parameters': parameters}]
            request = urllib.request.Request(proxy.base_url + '/chat/completions', data=body)
            with open_upstream(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
            sent = json.loads(proxy._request_upstream.call_args.args[2])
            self.assertEqual(sent.get('max_completion_tokens', sent.get('max_tokens')), expected)
            self.assertEqual(sent['model'], 'routed')

    def test_anchor_retry_requotes_only_failed_targets_without_partial_apply(self):
        f = self.flow
        (self.root / 'frontend').mkdir()
        for name in ['a', 'b']:
            (self.root / f'frontend/{name}.js').write_text('old\n')
        def edit(name, search):
            return (f'<<<EDIT frontend/{name}.js>>>\n<<<SEARCH>>>\n{search}\n'
                    '<<<REPLACE>>>\nnew\n<<<END EDIT>>>\n')
        f.text_turn = Mock(return_value=(True, edit('a', 'old') + edit('b', 'missing')))
        ok, reason = f.codegen_turn('--- frontend/a.js ---\nold\n--- frontend/b.js ---\nold\n', 30, 'repair')
        self.assertFalse(ok)
        self.assertIn('frontend/b.js', reason)
        self.assertEqual(f.last_codegen_refused, {'frontend/b.js'})
        self.assertEqual((self.root / 'frontend/a.js').read_text(), 'old\n')
        self.assertEqual(f.last_codegen_written, [])

    def test_suite_refused_targets_outrank_broad_historical_diff(self):
        f = self.flow
        f.requirement_nodes = {node['id']: node for node in self.nodes}
        f.changed_files_since = Mock(return_value={'frontend/old-change.js'})
        f.refused_paths = {'frontend/actual-target.js'}
        f.codegen_implement_prompt = Mock(return_value='--- frontend/actual-target.js ---\nsource\n')
        self.assertIsNotNone(f.suite_repair_prompt(['A'], 'failure'))
        self.assertEqual(f.codegen_implement_prompt.call_args.kwargs['must_include'],
                         {'frontend/actual-target.js'})

    def test_suite_specs_share_helpers_once_without_losing_nodes(self):
        f = self.flow
        self.nodes[0]['scenarios'] = [{'steps': [{'keyword': 'THEN', 'content': 'Preserve optional user choices'}]}]
        f.requirement_nodes = {node['id']: node for node in self.nodes}
        f.changed_files_since = Mock(return_value=set())
        f.codegen_implement_prompt = Mock(return_value='prompt')
        self.assertEqual(f.suite_repair_prompt(['A', 'B', 'C'], 'failure'), 'prompt')
        specs = f.codegen_implement_prompt.call_args.args[1]
        self.assertEqual(specs.count('--- helpers.ts ---'), 1)
        for node in self.nodes:
            self.assertIn(f"--- {node['id']}.spec.ts ---", specs)
        self.assertEqual(f.suite_spec_chars, len(specs))
        self.assertIn('THEN Preserve optional user choices', f.codegen_implement_prompt.call_args.args[0]['description'])

    def test_suite_spec_budget_does_not_slice_a_test_or_its_helpers(self):
        f = self.flow
        f.requirement_nodes = {node['id']: node for node in self.nodes}
        f.changed_files_since = Mock(return_value=set())
        one = f.batch_spec_bodies(['A'])
        f.codegen_context_chars = Mock(return_value=int(len(one) / 0.45) + 1)
        f.codegen_implement_prompt = Mock(return_value='prompt')
        self.assertEqual(f.suite_repair_prompt(['A', 'B'], 'failure'), 'prompt')
        self.assertEqual(f.codegen_implement_prompt.call_args.args[1], one)
        self.assertIn('specs not shown: B', f.codegen_implement_prompt.call_args.args[0]['description'])
