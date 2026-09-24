import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from llm_proxy import LlmProxy


class PendingCompletionTests(unittest.TestCase):
    def test_models_probe_closes_provider_circuit_without_a_completion(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
        proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(proxy.server.server_close)
        proxy._upstream_failures = 3
        proxy._provider_headers = {'Authorization': 'Bearer example'}
        with patch('llm_proxy.urllib.request.urlopen', return_value=Response()) as upstream:
            self.assertTrue(proxy.probe_provider())
        self.assertFalse(proxy.provider_unavailable)
        self.assertEqual(upstream.call_args.args[0].full_url, 'http://unused/v1/models')

    def test_should_report_upstream_pending_only_while_a_completion_is_in_flight(self):
        from concurrent.futures import Future
        proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(proxy.server.server_close)
        self.assertFalse(proxy.upstream_pending)
        proxy._inflight[('POST', '/chat/completions')] = Future()
        self.assertTrue(proxy.upstream_pending)
        proxy._inflight.clear()
        self.assertFalse(proxy.upstream_pending)

    def test_token_free_502_retries_once_then_counts_only_successful_request(self):
        class Response:
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return b'{"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}'
        proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(proxy.server.server_close)
        proxy.begin_turn(3)
        with patch('llm_proxy.urllib.request.urlopen', side_effect=[TimeoutError('temporary'), Response()]) as upstream:
            status, _, _ = proxy._request_upstream('POST', '/chat/completions', b'{}', {})
        self.assertEqual(status, 200)
        self.assertEqual(upstream.call_count, 2)
        self.assertEqual(proxy.turn_upstream_requests, 1)
        self.assertFalse(proxy.provider_unavailable)

    def test_missing_usage_reserves_tokens_for_the_cost_guard(self):
        proxy = LlmProxy('http://unused/v1', 'none')
        try:
            body = json.dumps({'model': 'm', 'messages': [{'role': 'user', 'content': 'x'}],
                               'max_tokens': 100}).encode()
            meta = proxy.request_meta(body)
            proxy._log(b'{"error":{"message":"timeout"}}', 600000, body,
                       len(body), 20, status=502, meta=meta)
            self.assertEqual(proxy.total_tokens, (len(body) + 2) // 3 + 100)
            self.assertEqual(proxy.estimated_tokens, proxy.total_tokens)
        finally:
            proxy.server.server_close()

    def test_absolute_budget_blocks_tool_requests_even_without_usage_log(self):
        class Response:
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"usage":{"prompt_tokens":8,"completion_tokens":3}}'
        with patch.dict('os.environ', {'OCTOS_ARC_MAX_TOTAL_TOKENS_ABS': '10'}):
            proxy = LlmProxy('http://unused/v1', 'none')
        try:
            with patch('llm_proxy.urllib.request.urlopen', return_value=Response()) as upstream:
                first = proxy._request_upstream('POST', '/chat/completions', b'{"messages":[]}', {})
                second = proxy._request_upstream('POST', '/chat/completions', b'{"messages":[{}]}', {})
                self.assertEqual(first[0], 200)
                self.assertEqual(second[0], 402)
                self.assertIn(b'local_token_budget_exhausted', second[1])
                self.assertEqual(proxy.total_tokens, 11)
                self.assertEqual(proxy.blocked_requests, 1)
                upstream.assert_called_once()
        finally:
            proxy.server.server_close()

    def test_pending_retry_shares_response_but_completed_requests_run_again(self):
        started, release, joined = threading.Event(), threading.Event(), threading.Event()
        payload = json.dumps({'usage': {'prompt_tokens': 2, 'completion_tokens': 1}}).encode()
        class Response:
            status = 200
            headers = {'Content-Type': 'application/json'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                started.set()
                if not release.wait(3): raise TimeoutError('test release missing')
                return payload
        with tempfile.TemporaryDirectory() as folder:
            proxy = LlmProxy('http://unused/v1', 'none', log_path=Path(folder) / 'usage.jsonl')
            args = ('POST', '/chat/completions', b'{"model":"generic","messages":[]}', {'Authorization': 'test'})
            try:
                with patch('llm_proxy.urllib.request.urlopen', return_value=Response()) as upstream:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        first = pool.submit(proxy._request_upstream, *args)
                        self.assertTrue(started.wait(2))
                        future = next(iter(proxy._inflight.values()))
                        original = future.result
                        def waiting(*a, **kw):
                            joined.set()
                            return original(*a, **kw)
                        with patch.object(future, 'result', side_effect=waiting):
                            second = pool.submit(proxy._request_upstream, *args)
                            self.assertTrue(joined.wait(2))
                            self.assertEqual(upstream.call_count, 1)
                            release.set()
                            self.assertEqual(first.result(2), second.result(2))
                    self.assertFalse(proxy._inflight)
                    self.assertEqual(proxy.total_requests, 1)
                    proxy._request_upstream(*args)
                    self.assertEqual(upstream.call_count, 2)
                    self.assertEqual(proxy.total_requests, 2)
            finally:
                release.set()
                proxy.server.server_close()

    def test_different_inputs_credentials_and_phases_remain_independent(self):
        for variant in ('body', 'credentials', 'phase'):
            with self.subTest(variant=variant):
                first_started, both_started, release = threading.Event(), threading.Event(), threading.Event()
                calls = []
                class Response:
                    status = 200
                    headers = {}
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def read(self):
                        calls.append(1)
                        first_started.set()
                        if len(calls) == 2: both_started.set()
                        release.wait(2)
                        return b'{}'
                proxy = LlmProxy('http://unused/v1', 'none')
                args = ['POST', '/chat/completions', b'{"messages":[]}', {'Authorization': 'first'}]
                try:
                    with patch('llm_proxy.urllib.request.urlopen', return_value=Response()):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            first = pool.submit(proxy._request_upstream, *args)
                            self.assertTrue(first_started.wait(1))
                            if variant == 'body': args[2] = b'{"messages":[{}]}'
                            elif variant == 'credentials': args[3] = {'Authorization': 'second'}
                            else: proxy.phase = 'repair'
                            second = pool.submit(proxy._request_upstream, *args)
                            try: self.assertTrue(both_started.wait(1))
                            finally: release.set()
                            first.result(2); second.result(2)
                    self.assertFalse(proxy._inflight)
                finally:
                    release.set()
                    proxy.server.server_close()

    def test_upstream_error_is_released_for_later_retry(self):
        proxy = LlmProxy('http://unused/v1', 'none')
        try:
            proxy.begin_turn(3)
            with patch('llm_proxy.urllib.request.urlopen', side_effect=TimeoutError('upstream timed out')) as upstream:
                for _ in range(2):
                    status, _, _ = proxy._request_upstream('POST', '/chat/completions', b'{}', {})
                    self.assertEqual(status, 502)
                    self.assertFalse(proxy._inflight)
                self.assertEqual(upstream.call_count, 4)  # one immediate retry per token-free 502
                self.assertEqual(proxy.turn_upstream_requests, 0)
                self.assertTrue(proxy.provider_unavailable)
        finally:
            proxy.server.server_close()

class TerminalAccountTests(unittest.TestCase):
    def test_quota_latches_across_turn_inputs_but_not_credentials(self):
        class Response:
            status = 429
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"error":{"type":"insufficient_quota"}}'
        proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(proxy.server.server_close)
        with patch('llm_proxy.urllib.request.urlopen', return_value=Response()) as upstream:
            proxy._request_upstream('POST', '/chat/completions', b'{}', {'Authorization': 'a'})
            proxy.phase = 'repair'
            proxy._request_upstream('POST', '/chat/completions', b'{"model":"other"}', {'authorization': 'a'})
            self.assertEqual(upstream.call_count, 1)
            self.assertEqual(proxy.total_requests, 1)
            self.assertEqual(proxy.terminal_blocked_requests, 1)
            proxy._request_upstream('POST', '/chat/completions', b'{}', {'Authorization': 'b'})
            self.assertEqual(upstream.call_count, 2)

    def test_rate_limits_and_model_permission_errors_do_not_latch(self):
        from llm_proxy import terminal_account_error
        for status, body in [(429, b'{"error":{"type":"rate_limit_exceeded"}}'),
                             (403, b'{"error":{"code":"model_not_allowed"}}'),
                             (429, b'not json'), (429, b'{"error":null}'),
                             (200, b'{"error":{"type":"insufficient_quota"}}')]:
            self.assertFalse(terminal_account_error(status, body))
        for status in (401, 402):
            self.assertTrue(terminal_account_error(status, b'account unavailable'))
