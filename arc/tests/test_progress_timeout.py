import io
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import urlopen

from progress_timeout import ProgressDeadline
from llm_proxy import collect_codegen_stream


def event(content=None, reasoning=None):
    return b'data: ' + json.dumps({'choices': [{'delta': {'content': content, 'reasoning_content': reasoning}}]}).encode() + b'\n\n'


class ProgressTests(unittest.TestCase):
    def test_progress_extends_but_hard_cap_wins(self):
        now = [0]
        lease = ProgressDeadline(100, extension=25, idle=20, clock=lambda: now[0])
        now[0] = 95
        lease.progress()
        self.assertEqual(lease.remaining(), 20)
        now[0] = 110
        lease.progress()
        self.assertEqual(lease.remaining(), 15)
        now[0] = 126
        lease.progress()
        self.assertEqual(lease.remaining(), 0)

    def test_no_progress_and_close_cannot_extend(self):
        now = [0]
        lease = ProgressDeadline(100, clock=lambda: now[0])
        now[0] = 101
        lease.progress()
        self.assertEqual(lease.remaining(), 0)
        other = ProgressDeadline(100, clock=lambda: now[0])
        lease.close()
        lease.progress()
        self.assertIsNone(other.last)
        self.assertEqual(lease.remaining(), 0)

    def test_content_and_reasoning_count_but_heartbeats_do_not(self):
        for raw, expected in [(event('abc'), True), (event(reasoning='thinking'), True),
                              (event('  '), False), (b': heartbeat\n\n', False),
                              (b'data: {"usage":{"completion_tokens":1}}\n', False)]:
            lease = ProgressDeadline(100)
            collect_codegen_stream(io.BytesIO(raw), lease=lease)
            self.assertEqual(lease.last is not None, expected)

    def test_heartbeat_cannot_hide_idle_or_first_output_timeout(self):
        for initial, expected, elapsed in [(event('hello'), 'stream_idle_timeout', 121),
                                            (b': ping\n', 'stream_first_output_timeout', 301)]:
            now = [0]
            def lines():
                yield initial
                now[0] = elapsed
                yield b': ping\n'
            with patch('llm_proxy.time.monotonic', side_effect=lambda: now[0]):
                payload, reason = collect_codegen_stream(lines(), deadline=1000)
            self.assertEqual(reason, expected)
            self.assertEqual(json.loads(payload)['choices'][0]['finish_reason'], 'length')

    def test_real_silent_socket_is_interrupted_without_waiting_for_next_line(self):
        release = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(event('partial'))
                self.wfile.flush()
                release.wait(5)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            started = time.monotonic()
            with urlopen(f'http://127.0.0.1:{server.server_port}', timeout=5) as response:
                payload, reason = collect_codegen_stream(response, lease=ProgressDeadline(.3, extension=0))
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(reason, 'turn_deadline')
            self.assertEqual(json.loads(payload)['choices'][0]['message']['content'], 'partial')
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            worker.join()

    def test_stdio_waiter_observes_upstream_progress_beyond_original_timeout(self):
        from types import SimpleNamespace
        from octos_stdio import OctosStdioSession
        now = [0]
        lease = ProgressDeadline(10, extension=5, idle=3, clock=lambda: now[0])
        session = object.__new__(OctosStdioSession)
        session.progress_deadline = lease
        session.session_id = 'session'
        session.proc = SimpleNamespace(poll=lambda: None)
        session.on_event = lambda *args: None
        session._send = lambda *args, **kwargs: None
        class Notifications:
            calls = 0
            def get(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    now[0] = 9
                    lease.progress()
                    now[0] = 11
                    return {'method': 'server/heartbeat'}
                return {'method': 'turn/completed', 'params': {'turn_id': 'test-turn'}}
        session._notifications = Notifications()
        with patch('octos_stdio.uuid.uuid4', return_value='test-turn'), patch('octos_stdio.time.monotonic', side_effect=lambda: now[0]):
            self.assertEqual(session.run_turn('hi', timeout=10), (True, ''))
        self.assertEqual(session._notifications.calls, 2)

    def test_real_active_stream_finishes_after_original_timeout(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                for i in range(6):
                    self.wfile.write(event(str(i)))
                    self.wfile.flush()
                    time.sleep(.1)
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                self.wfile.flush()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}', timeout=5) as response:
                payload, reason = collect_codegen_stream(response, lease=ProgressDeadline(.3, extension=1))
            self.assertIsNone(reason)
            self.assertEqual(json.loads(payload)['choices'][0]['message']['content'], '012345')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_timed_out_persistent_session_is_closed(self):
        from unittest.mock import Mock
        from main import OctosDriver
        driver = object.__new__(OctosDriver)
        session = Mock()
        session.run_turn.return_value = (False, 'octos turn timed out')
        driver._get_session = Mock(return_value=session)
        driver.close = Mock()
        self.assertFalse(driver._run_stdio('hi', 10)[0])
        driver.close.assert_called_once()
