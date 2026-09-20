import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as m
from llm_proxy import LlmProxy


class PartialGenerationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.flow = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.proxy = LlmProxy('http://unused/v1', 'none')
        self.addCleanup(self.proxy.server.server_close)
        self.proxy.begin_turn(3)
        self.flow.llm_proxy = self.proxy
        self.flow.text_turn = Mock(return_value=(False, 'output_truncated: max_tokens'))

    def capture(self, text, **meta):
        self.proxy.capture_truncated_reply(json.dumps({'choices': [
            {'finish_reason': 'length', 'message': {'content': text}}
        ]}).encode(), {'label': 'test', 'turn_serial': self.proxy.turn_serial, **meta})

    def test_terminated_file_saved_but_unfinished_tail_not_written_and_turn_not_successful(self):
        self.capture('<<<FILE backend/one.js>>>\nmodule.exports = 1;\n<<<END FILE>>>\n'
                     '<<<FILE backend/two.js>>>\nmodule.exports = ')
        ok, _ = self.flow.codegen_turn('sources', 30, 'test')
        self.assertFalse(ok)
        self.assertTrue((self.root / 'backend/one.js').exists())
        self.assertFalse((self.root / 'backend/two.js').exists())
        self.assertEqual(self.flow.last_codegen_outcome, 'incomplete_blocks')

    def test_truncated_bare_format_is_never_inferred_complete_at_eof(self):
        self.capture('FILE backend/one.js\nmodule.exports = 1;')
        self.assertFalse(self.flow.codegen_turn('sources', 30, 'test')[0])
        self.assertFalse((self.root / 'backend/one.js').exists())

    def test_existing_unquoted_file_is_still_guarded(self):
        (self.root / 'backend').mkdir()
        path = self.root / 'backend/one.js'
        path.write_text('module.exports = 0;')
        self.capture('<<<FILE backend/one.js>>>\nmodule.exports = 1;\n<<<END FILE>>>')
        self.assertFalse(self.flow.codegen_turn('sources', 30, 'test')[0])
        self.assertEqual(path.read_text(), 'module.exports = 0;')

    def test_late_response_from_previous_turn_cannot_be_recovered(self):
        serial = self.proxy.turn_serial
        self.proxy.begin_turn(3)
        self.capture('late text', turn_serial=serial)
        self.assertIsNone(self.proxy.take_truncated_reply('test'))
        self.capture('current text')
        self.assertIsNone(self.proxy.take_truncated_reply('different-label'))
        self.assertEqual(self.proxy.take_truncated_reply('test'), 'current text')
        self.assertIsNone(self.proxy.take_truncated_reply('test'))

    def test_completed_bare_reply_uses_same_write_guards_without_a_second_request(self):
        self.flow.text_turn.return_value = (True, 'FILE backend/new.js\nmodule.exports = 1;')
        self.assertTrue(self.flow.codegen_turn('sources', 30, 'test')[0])
        self.flow.text_turn.assert_called_once()
        self.assertTrue((self.root / 'backend/new.js').exists())
        self.flow.text_turn.return_value = (True, 'FILE backend/new.js\nmodule.exports = 2;')
        self.assertFalse(self.flow.codegen_turn('not quoted', 30, 'test')[0])
        self.assertEqual((self.root / 'backend/new.js').read_text(), 'module.exports = 1;\n')

    def test_wire_length_reply_is_captured_only_in_toolless_turns(self):
        self.proxy.no_tools = True
        self.proxy.label = 'test'
        class Response:
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}'
        with patch('llm_proxy.urllib.request.urlopen', return_value=Response()):
            self.proxy._request_upstream('POST', '/chat/completions', b'{"messages":[]}', {})
            self.assertEqual(self.proxy.take_truncated_reply('test'), 'partial')
            self.proxy.no_tools = False
            self.proxy._request_upstream('POST', '/chat/completions', b'{"messages":[]}', {})
            self.assertIsNone(self.proxy.take_truncated_reply('test'))
