"""Provider boundary regressions: intended off/medium must not become GLM max."""
import json
import os
import unittest
import urllib.request
from unittest.mock import MagicMock, patch
from llm_proxy import LlmProxy, cap_reasoning_effort, inject_reasoning, route_request, usage_record

class GlmFlashReasoningTests(unittest.TestCase):
    def test_gateway_reasoning_usage_is_retained_for_json_and_streaming(self):
        event = {'choices': [], 'usage': {'prompt_tokens': 16, 'completion_tokens': 52,
                 'reasoning_tokens': 50, 'total_tokens': 68}}
        payload = json.dumps(event).encode()
        for body in (payload, b'data: '+payload+b'\n\ndata: [DONE]\n\n'):
            row = usage_record(body, 2400, 'none')
            self.assertEqual(row['reasoning_tokens'], 50)
            self.assertEqual(row['total_tokens'], 68)
        event['usage']['completion_tokens_details'] = {'reasoning_tokens': 49}
        self.assertEqual(usage_record(json.dumps(event).encode(), 1, 'low')['reasoning_tokens'], 49)

    def test_absent_reasoning_breakdown_remains_unknown(self):
        payload = json.dumps({'usage': {'prompt_tokens': 16, 'completion_tokens': 1, 'total_tokens': 17}}).encode()
        self.assertNotIn('reasoning_tokens', usage_record(payload, 1, 'low'))

    def test_off_and_unsupported_medium_use_low_for_all_supported_model_names(self):
        for model in ('glm-5.3-flash', 'provider/glm-5.3-flash', 'glm-5.3-flash-2026-08-27'):
            for mode in ('none', 'off', 'disabled', 'medium', 'low'):
                for old in (None, 'medium', 'none'):
                    with self.subTest(model=model, mode=mode, old=old):
                        data = {'model': model, 'messages': [], 'reasoning_effort': old,
                                'thinking': {'type': 'disabled', 'clear_thinking': False}, 'enable_thinking': False}
                        wire = json.loads(inject_reasoning(json.dumps(data).encode(), mode, force=True))
                        self.assertEqual(wire['reasoning_effort'], 'low')
                        self.assertEqual(wire['thinking'], {'type': 'enabled', 'clear_thinking': False})
                        self.assertNotIn('enable_thinking', wire)

    def test_medium_ceiling_uses_supported_low_after_explicit_route_parameters(self):
        for effort in ('none', 'medium', 'high', 'xhigh', 'max', 'ultra'):
            data = {'model': 'glm-5.3-flash', 'messages': [], 'reasoning_effort': effort}
            wire = json.loads(cap_reasoning_effort(json.dumps(data).encode()))
            self.assertEqual(wire['reasoning_effort'], 'low')
        for mode in ('none', 'low', 'medium'):
            with patch.dict(os.environ, {'OCTOS_ARC_IMPLEMENT_REASONING': mode}, clear=True):
                routed = route_request(json.dumps({'model': 'base', 'messages': []}).encode(),
                                       [{'model': 'glm-5.3-flash', 'phases': ['implement']}],
                                       'implement', mode, 'feature implement')
                self.assertEqual(json.loads(routed)['reasoning_effort'], 'low')

    def test_passthrough_and_unrelated_models_keep_existing_semantics(self):
        body = json.dumps({'model': 'glm-5.3-flash', 'messages': [], 'reasoning_effort': 'max'}).encode()
        self.assertEqual(inject_reasoning(body, 'passthrough'), body)
        self.assertEqual(json.loads(inject_reasoning(body, 'low'))['reasoning_effort'], 'max')
        qwen = json.loads(inject_reasoning(body.replace(b'glm-5.3-flash', b'qwen3.7-plus'), 'none'))
        self.assertFalse(qwen['enable_thinking'])
        self.assertNotIn('reasoning_effort', qwen)
        self.assertEqual(json.loads(cap_reasoning_effort(body.replace(b'glm-5.3-flash', b'qwen3.7-plus')))['reasoning_effort'], 'medium')

    def test_actual_http_generation_and_repair_wire_never_uses_provider_default_max(self):
        for phase, mode in (('implement', 'none'), ('repair', 'medium')):
            with self.subTest(phase=phase), patch.dict(os.environ, {}, clear=True):
                proxy = LlmProxy('http://127.0.0.1:1/v1', mode).start()
                try:
                    proxy.phase, proxy.label = phase, 'feature '+phase
                    proxy.begin_turn(8)
                    upstream = MagicMock()
                    upstream.status = 200
                    upstream.headers = {'Content-Type': 'application/json'}
                    upstream.__enter__.return_value = upstream
                    upstream.read.return_value = json.dumps({'choices': [{'finish_reason': 'stop', 'message':
                        {'role': 'assistant', 'content': 'done'}}], 'usage':
                        {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
                    with patch('llm_proxy.open_upstream', return_value=upstream) as send:
                        body = json.dumps({'model': 'glm-5.3-flash', 'messages': [],
                            'reasoning_effort': 'medium', 'thinking': {'type': 'disabled'}}).encode()
                        req = urllib.request.Request(proxy.base_url+'/chat/completions', data=body,
                            headers={'Content-Type': 'application/json'})
                        with urllib.request.urlopen(req, timeout=8) as response:
                            self.assertEqual(response.status, 200)
                        wire = json.loads(send.call_args.args[0].data)
                        self.assertEqual(wire['reasoning_effort'], 'low')
                        self.assertEqual(wire['thinking']['type'], 'enabled')
                finally:
                    proxy.stop()

if __name__ == '__main__': unittest.main()
