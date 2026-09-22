import importlib.util
import io
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import main as m
from codegen import FORMAT_INSTRUCTIONS
from llm_proxy import LlmProxy, collect_codegen_stream, compact_repeated_reads
from reply_quality import StreamRepetitionGuard
import test_whole_app_v5 as fixtures

spec = importlib.util.spec_from_file_location('edit_hook', Path(m.__file__).parent / 'hooks/deny_protected.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class EditProtocolTests(TestCase):
    def setUp(self):
        fixtures.WholeAppTests.setUp(self)
        self.flow.llm_proxy = SimpleNamespace(extra_drop_tools=set())

    def source(self, text):
        p = self.root / 'frontend/src/App.jsx'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_file_only_instruction_is_unambiguous(self):
        self.assertNotIn('<<<EDIT', FORMAT_INSTRUCTIONS)
        self.assertNotIn('<<<EDIT', m.CODEGEN_SYSTEM)

    def test_large_quoted_source_and_repairs_route_to_tools(self):
        p = self.source('a' * 13000)
        prompt = '--- frontend/src/App.jsx ---\n' + p.read_text() + '\n'
        self.assertTrue(self.flow.use_structured_edits(prompt, 'wave implement'))
        self.assertFalse(self.flow.use_structured_edits('', 'suite repair'))
        self.assertTrue(self.flow.use_structured_edits(prompt, 'suite repair'))
        self.assertFalse(self.flow.use_structured_edits('', 'wave implement'))
        self.assertFalse(self.flow.use_structured_edits(prompt, 'application design'))
        with patch.dict('os.environ', {'OCTOS_ARC_STRUCTURED_EDITS': '0'}):
            self.assertFalse(self.flow.use_structured_edits(prompt, 'wave implement'))
        p.write_text('short source')
        self.assertFalse(self.flow.use_structured_edits(prompt, 'wave implement'))

    def test_tools_preserve_evidence_strip_sources_and_record_partial_writes(self):
        p = self.source('const before = 1;\n' * 1000)
        self.flow.llm_proxy = SimpleNamespace(extra_drop_tools={'original'})
        self.flow.metric = Mock()
        prompt = '--- frontend/src/App.jsx ---\n' + p.read_text() + '\nAcceptance: keep the button.'
        observed = []
        def run(value, *a, **kw):
            observed.append(value)
            self.assertIn('diff_edit', self.flow.llm_proxy.extra_drop_tools)
            self.assertIn('glob', self.flow.llm_proxy.extra_drop_tools)
            p.write_text('const after = 2;')
            return False, 'timeout'
        self.flow.turn = run
        ok, _ = self.flow.codegen_turn(prompt, 90, 'wave implement')
        self.assertFalse(ok)
        self.assertEqual(self.flow.last_codegen_written, ['frontend/src/App.jsx'])
        self.assertEqual(self.flow.last_codegen_outcome, 'tool_incomplete')
        self.assertNotIn('const before', observed[0])
        self.assertIn('Acceptance: keep the button.', observed[0])
        self.assertIn('do not search, list or read other acceptance files', observed[0])
        self.assertEqual(self.flow.llm_proxy.extra_drop_tools, {'original'})

    def test_tool_configuration_restored_on_failure(self):
        self.source('a' * 13000)
        self.flow.llm_proxy = SimpleNamespace(extra_drop_tools={'original'})
        self.flow.turn = Mock(side_effect=RuntimeError('failure'))
        with self.assertRaises(RuntimeError):
            self.flow.structured_edit_turn('', 90, 'repair')
        self.assertEqual(self.flow.llm_proxy.extra_drop_tools, {'original'})
        self.assertFalse(self.flow.llm_proxy.compact_reads)

    def test_localized_small_source_is_not_discarded(self):
        p = self.source('const current = 1;')
        self.flow.turn = Mock(return_value=(True, 'done'))
        self.flow.structured_edit_turn('--- frontend/src/App.jsx ---\n' + p.read_text() + '\n', 90, 'repair')
        self.assertIn(p.read_text(), self.flow.turn.call_args.args[0])

    def test_large_quoted_context_file_does_not_override_known_small_target(self):
        p = self.source('a' * 13000)
        target = p.parent / 'Small.jsx'
        target.write_text('export const Small = () => null;')
        prompt = '--- frontend/src/App.jsx ---\n' + p.read_text() + '\n--- frontend/src/Small.jsx ---\n' + target.read_text() + '\n'
        self.flow.bind_edit_scope(prompt, '', {'frontend/src/Small.jsx'})
        self.assertFalse(self.flow.use_structured_edits(prompt, 'suite repair'))

    def test_retained_context_prioritizes_bound_scope_before_alphabetical_files(self):
        other = self.source('/* unrelated */' + 'a' * 10000)
        target = other.parent / 'ZTarget.jsx'
        target.write_text('/* target */' + 'z' * 10000)
        prompt = ('--- frontend/src/App.jsx ---\n' + other.read_text() + '\n'
                  '--- frontend/src/ZTarget.jsx ---\n' + target.read_text() + '\n'
                  'Acceptance evidence: keep the required link semantics.')
        self.flow.bind_edit_scope(prompt, '', {'frontend/src/ZTarget.jsx'})
        # Memory changes the prompt hash: capture ownership before appending it.
        self.flow.repair_memory_context = Mock(return_value='\nPrevious observation\n')
        self.flow.turn = Mock(return_value=(True, 'done'))
        self.flow.structured_edit_turn(prompt, 90, 'repair')
        sent = self.flow.turn.call_args.args[0]
        self.assertIn(target.read_text(), sent)
        self.assertNotIn(other.read_text(), sent)
        self.assertIn('Acceptance evidence: keep the required link semantics.', sent)
        self.assertIn('Previous observation', sent)

    def test_structured_repairs_check_partial_writes_but_not_unchanged_turns(self):
        for ok in (True, False):
            with self.subTest(ok=ok):
                p = self.source('const before = 1;')
                self.flow.generation_batch_check = Mock()
                def edit(*args, **kwargs):
                    p.write_text('const after = ;')
                    return ok, 'done' if ok else 'timeout'
                self.flow.turn = edit
                self.flow.structured_edit_turn('', 90, 'repair')
                self.flow.generation_batch_check.assert_called_once_with('repair')
                self.flow.generation_batch_check.reset_mock()
                self.flow.turn = Mock(return_value=(ok, 'no changes'))
                self.flow.structured_edit_turn('', 90, 'repair')
                self.flow.generation_batch_check.assert_not_called()

    def test_local_request_cap_is_incomplete_not_success_or_run_exhaustion(self):
        f = self.flow
        proxy = SimpleNamespace(mode='none', extra_drop_tools=set(), no_tools=False,
                                turn_budget=8, turn_requests=9, begin_turn=Mock())
        f.llm_proxy = proxy
        def run(*args):
            proxy.hard_budget_exhausted = True
            return True, 'local terminal response'
        f.driver = SimpleNamespace(run=run)
        f.metric = Mock()
        f.restore_protected = Mock(return_value=[])
        ok, text = f.turn('repair', 30, 'node repair')
        self.assertFalse(ok)
        self.assertIn('local_turn_budget_exhausted', text)
        self.assertFalse(getattr(f, 'local_budget_exhausted', False))
        f.restore_protected.assert_called_once()
        self.assertFalse(f.metric.call_args.kwargs['ok'])

    def test_suite_does_not_bypass_hard_cap_or_start_one_second_fallback(self):
        for reason, spent in [('local_turn_budget_exhausted', 20), ('timeout', 299)]:
            with self.subTest(reason=reason):
                f = self.flow
                now = [0]
                f.compact_tool_repair_prompt = Mock(return_value='tool prompt')
                f.suite_repair_prompt = Mock(return_value='repair prompt')
                f.turn = Mock()
                f.last_codegen_written = []
                f.last_codegen_refused = set()
                def generate(*args, **kwargs):
                    now[0] = spent
                    return False, reason
                f.codegen_turn = generate
                with patch.object(m.time, 'monotonic', side_effect=lambda: now[0]):
                    mode, _ = f.suite_repair_turn('repair', ['A'], 'failure', 300, tool_prompt='tools')
                self.assertEqual(mode, 'unapplied')
                f.turn.assert_not_called()

    def test_hook_exact_noop_ambiguous_and_current_excerpt(self):
        p = self.source('alpha current value\nsecond line\nalpha current value\n')
        args = dict(path=str(p), old_string='second line', new_string='new line')
        self.assertIsNone(hook.check_edit(args, str(self.root)))
        for old in ('second line', 'alpha current value', 'missing anchor', ''):
            args.update(old_string=old, new_string=old if old == 'second line' else 'replacement')
            self.assertIsNotNone(hook.check_edit(args, str(self.root)))
        args.update(old_string='missing anchor', new_string='new')
        self.assertIn('alpha current value', hook.check_edit(args, str(self.root)))
        self.assertEqual(p.read_text(), 'alpha current value\nsecond line\nalpha current value\n')

    def test_hook_allows_only_unique_crlf_equivalent_not_guessed_indent(self):
        p = self.source('')
        p.write_bytes(b'alpha\r\n  beta\r\ngamma\r\n')
        args = dict(filePath=str(p), oldString='alpha\n  beta', newString='next')
        self.assertIsNone(hook.check_edit(args, str(self.root)))
        args['oldString'] = 'alpha\nbeta'
        self.assertIsNotNone(hook.check_edit(args, str(self.root)))

    def test_hook_does_not_read_external_target_for_error_context(self):
        p = self.root / 'outside.txt'
        p.write_text('private external data')
        app = self.root / 'app'
        app.mkdir()
        reason = hook.check_edit(dict(path=str(p), old_string='missing', new_string='new'), str(app))
        self.assertIn('outside', reason)
        self.assertNotIn('private external data', reason)


class StreamingTests(TestCase):
    def test_admission_cap_counts_upstream_attempts_even_without_new_kernel_request(self):
        proxy = LlmProxy('http://127.0.0.1:1/v1', 'none')
        try:
            proxy.begin_turn(1)
            # Model-route fallback can call upstream again without going through
            # the HTTP handler. It must share the same admission allowance.
            proxy.turn_upstream_requests = 1
            with patch('llm_proxy.open_upstream') as upstream:
                status, body, _ = proxy._request_upstream('POST', '/chat/completions',
                    b'{"model":"fallback","messages":[]}', {})
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)['arc_local_response'])
            upstream.assert_not_called()
            self.assertTrue(proxy.hard_budget_exhausted)
        finally:
            proxy.server.server_close()

    def test_read_compaction_preserves_latest_ranges_and_edit_evidence(self):
        messages = []
        def pair(i, name, args, content):
            messages.extend([{'role': 'assistant', 'tool_calls': [{'id': str(i), 'function': {
                'name': name, 'arguments': json.dumps(args)}}]},
                {'role': 'tool', 'tool_call_id': str(i), 'content': content}])
        pair(1, 'read_file', {'path': 'a.js'}, 'old source' * 1000)
        pair(1, 'edit_file', {'path': 'a.js', 'old_string': 'old', 'new_string': 'new'}, 'edit succeeded' * 100)
        pair(3, 'read_file', {'path': 'a.js', 'start_line': 4}, 'range source' * 20)
        pair(4, 'read_file', {'path': 'a.js'}, 'new source' * 1000)
        body = json.dumps({'messages': messages}).encode()
        compact = compact_repeated_reads(body)
        out = json.loads(compact)['messages']
        self.assertIn('Earlier read omitted', out[1]['content'])
        self.assertEqual(out[3:], messages[3:])
        self.assertLess(len(compact), len(body) * .6)
        self.assertEqual(compact_repeated_reads(compact), compact)
        self.assertEqual(compact_repeated_reads(b'bad json'), b'bad json')

    def stream(self, chunks, finish='stop', usage=None):
        records = [dict(choices=[dict(index=0, delta={'content': c}, finish_reason=None)]) for c in chunks]
        records.append(dict(choices=[dict(index=0, delta={}, finish_reason=finish)]))
        if usage:
            records.append(dict(choices=[], usage=usage))
        return io.BytesIO(b''.join(b'data: ' + json.dumps(r).encode() + b'\n\n' for r in records) + b'data: [DONE]\n')

    def test_complete_response_keeps_actual_usage(self):
        payload, stop = collect_codegen_stream(self.stream(['abc', 'def'], usage={'prompt_tokens': 12, 'completion_tokens': 3}))
        response = json.loads(payload)
        self.assertIsNone(stop)
        self.assertEqual(response['choices'][0]['message']['content'], 'abcdef')
        self.assertEqual(response['usage']['completion_tokens'], 3)

    def test_repeated_envelopes_abort_before_remaining_stream(self):
        block = '<<<FILE frontend/a.js>>>\n' + 'x' * 900 + '\n<<<END FILE>>>\n'
        stream = self.stream([block] * 20, usage={'completion_tokens': 999})
        payload, reason = collect_codegen_stream(stream)
        response = json.loads(payload)
        self.assertEqual(reason, 'repeated_operation_cycle')
        self.assertEqual(response['choices'][0]['finish_reason'], 'length')
        self.assertNotIn('usage', response)
        self.assertLess(stream.tell(), len(stream.getvalue()))

    def test_incomplete_stream_is_never_success(self):
        payload, reason = collect_codegen_stream(self.stream(['partial'], finish=None))
        self.assertEqual(reason, 'incomplete_stream')
        self.assertEqual(json.loads(payload)['choices'][0]['finish_reason'], 'length')

    def test_normal_repeated_ui_lines_are_not_degenerate(self):
        text = '\n'.join(f'<button data-id="{i}">Save</button>' for i in range(500))
        self.assertIsNone(StreamRepetitionGuard().check(text))
        self.assertIsNone(StreamRepetitionGuard().check('short line\n' * 50))

    def test_identical_unfinished_suffix_is_stopped(self):
        self.assertEqual(StreamRepetitionGuard().check(('long repeat ' + 'x' * 800) * 9), 'periodic_text_suffix')

    def test_proxy_requests_stream_retains_partial_and_logs_missing_usage(self):
        import tempfile
        block = '<<<FILE frontend/a.js>>>\n' + 'x' * 900 + '\n<<<END FILE>>>\n'
        response = self.stream([block] * 20)
        response.status = 200
        response.headers = {'Content-Type': 'text/event-stream'}
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'usage.jsonl'
            proxy = LlmProxy('http://127.0.0.1:1/v1', 'none', log).start()
            try:
                proxy.no_tools = True
                proxy.phase, proxy.label = 'implement', 'wave 1'
                proxy.begin_turn(1)
                with patch('llm_proxy.open_upstream', return_value=response) as upstream:
                    status, payload, _ = proxy._request_upstream('POST', '/chat/completions',
                        json.dumps({'model': 'example', 'messages': [], 'stream': False}).encode(), {})
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(upstream.call_args.args[0].data)['stream'])
                self.assertIn('<<<FILE', proxy.take_truncated_reply('wave 1'))
                record = json.loads(log.read_text())
                self.assertEqual(record['stream_guard'], 'repeated_operation_cycle')
                self.assertTrue(record['no_usage'])
                self.assertEqual(json.loads(payload)['choices'][0]['finish_reason'], 'length')
            finally:
                proxy.stop()

    def test_deadline_aborts_without_claiming_completion(self):
        payload, stop = collect_codegen_stream(self.stream(['hello']), deadline=0)
        self.assertEqual(stop, 'turn_deadline')
        self.assertEqual(json.loads(payload)['choices'][0]['finish_reason'], 'length')

    def test_tool_ids_can_be_reused_in_later_completions_not_same_batch(self):
        proxy = LlmProxy('http://127.0.0.1:1/v1', 'none').start()
        try:
            directory = Path(proxy.enable_edit_preflight())
            def call(value):
                return {'id': 'reused', 'function': {'name': 'edit_file', 'arguments': json.dumps({'new_string': value})}}
            def payload(calls):
                return json.dumps({'choices': [{'message': {'tool_calls': calls}}]}).encode()
            proxy.retain_edit_arguments(payload([call('first')]))
            proxy.retain_edit_arguments(payload([call('second')]))
            self.assertEqual(json.loads(next(directory.glob('*.json')).read_text())['arguments']['new_string'], 'second')
            proxy.retain_edit_arguments(payload([call('first'), call('second')]))
            self.assertIn('error', json.loads(next(directory.glob('*.json')).read_text()))
        finally:
            proxy.stop()

    def test_real_http_stream_request_has_updated_content_length(self):
        received = []
        stream = self.stream(['code'], usage={'prompt_tokens': 2, 'completion_tokens': 1}).getvalue()
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(body)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(stream)))
                self.end_headers()
                self.wfile.write(stream)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        proxy = LlmProxy(f'http://127.0.0.1:{server.server_port}/v1', 'none').start()
        try:
            proxy.no_tools, proxy.phase = True, 'implement'
            req = urllib.request.Request(proxy.base_url + '/chat/completions',
                data=json.dumps({'model': 'local', 'messages': [], 'stream': False}).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5) as response:
                result = json.load(response)
            self.assertTrue(received[0]['stream'])
            self.assertEqual(result['choices'][0]['message']['content'], 'code')
        finally:
            proxy.stop()
            server.shutdown()
            server.server_close()


class KernelHookIntegrationTests(TestCase):
    setUp = EditProtocolTests.setUp
    source = EditProtocolTests.source
    def test_real_kernel_large_edit_hook_receives_complete_arguments(self):
        binary = Path(m.__file__).parent / 'bin/octos'
        if not binary.is_file():
            self.skipTest('local octos binary required (fake provider only, no paid calls)')
        p = self.source('const oldValue = 1;\n' * 100)
        old, new = p.read_text(), 'const newValue = 2;\n'
        operations = [
            ('read_file', {'path': str(p)}),
            ('edit_file', {'path': str(p), 'old_string': 'not present\n' * 100, 'new_string': new}),
            ('edit_file', {'path': str(p), 'old_string': old, 'new_string': new}),
        ]
        received = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                index = len(received)
                received.append(body)
                message = {'role': 'assistant', 'content': 'done' if index >= len(operations) else ''}
                finish = 'stop'
                if index < len(operations):
                    name, args = operations[index]
                    message['tool_calls'] = [{'id': f'call_{index}', 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}]
                    finish = 'tool_calls'
                response = json.dumps({'id': f'completion_{index}', 'object': 'chat.completion',
                    'model': 'local-test', 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        proxy = LlmProxy(f'http://127.0.0.1:{server.server_port}/v1', 'none').start()
        driver = None
        try:
            sidecar = proxy.enable_edit_preflight()
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'local-test-key', 'OPENAI_BASE_URL': proxy.base_url,
                    'MODEL': 'local-test', 'OCTOS_MODEL': 'local-test', 'OCTOS_PROVIDER': 'custom',
                    'OCTOS_ARC_EDIT_ARGUMENTS_DIR': sidecar, 'OCTOS_ARC_SAFE_EDIT': '1'}):
                config = self.root / 'config'
                data = self.root / 'data'
                env = m.build_octos_env(config, [self.flow.tests_dir])
                hooks = m.protected_hooks([self.flow.tests_dir])
                m.write_profile_defaults(data, config, hooks)
                driver = m.OctosDriver(str(binary), self.root, env, data, 8, self.root / 'events.jsonl')
                driver.hooks = hooks
                ok, text = driver.run('Make the requested edit.', 30)
            self.assertTrue(ok, text)
            self.assertEqual(p.read_text(), new)
            all_messages = json.dumps([r['messages'] for r in received])
            self.assertIn('Edit refused: old_string matched 0', all_messages)
            self.assertIn('Current source excerpt', all_messages)
            self.assertNotIn('kernel truncated hook arguments', all_messages)
            # Even a provider that keeps requesting tools cannot exceed the cap.
            received.clear()
            proxy.begin_turn(1)
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'local-test-key'}):
                _, capped_text = driver.run('Read current source and continue working.', 30)
            self.assertEqual(len(received), 1)
            self.assertTrue(proxy.hard_budget_exhausted)
            self.assertIn('local_turn_budget_exhausted', capped_text)
            proxy.begin_turn(1)
            self.assertFalse(proxy.hard_budget_exhausted)
        finally:
            if driver:
                driver.close()
            proxy.stop()
            server.shutdown()
            server.server_close()
