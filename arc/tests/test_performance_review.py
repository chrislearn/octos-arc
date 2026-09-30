"""Regression evidence for the v15 performance review; no model requests."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from llm_proxy import (LlmProxy, enforce_turn_budget, force_write_decision,
                       prompt_fingerprint, request_fingerprints)


class ForwardedContextTests(unittest.TestCase):
    def body(self):
        return {'model': 'local-fixture', 'messages': [{'role': 'user', 'content': 'private source'}],
                'tools': [{'type': 'function', 'function': {'name': name, 'parameters': {'type': 'object'}}}
                          for name in ('list_dir', 'read_file', 'edit_file')]}

    def test_budget_guidance_keeps_identical_schema_before_and_after_write(self):
        initial = self.body()
        limited = json.loads(force_write_decision(json.dumps(initial).encode(), 10, 12, 200))
        written = copy.deepcopy(initial)
        written['messages'].append({'role': 'assistant', 'tool_calls': [{'id': '1', 'function': {
            'name': 'edit_file', 'arguments': '{}'}}]})
        after = json.loads(force_write_decision(json.dumps(written).encode(), 11, 12, 201))
        exhausted = json.loads(enforce_turn_budget(json.dumps(after).encode(), 12, 12))
        for request in (limited, after, exhausted):
            self.assertEqual(request['tools'], initial['tools'])
        self.assertEqual(limited['messages'][:-1], initial['messages'])

    def test_schema_arguments_multimodal_content_and_order_are_fingerprinted(self):
        original = self.body()
        baseline = prompt_fingerprint(json.dumps(original).encode(), '')[0]
        for kind in ('schema', 'arguments', 'image', 'order'):
            changed = copy.deepcopy(original)
            if kind == 'schema': changed['tools'][0]['function']['parameters']['required'] = ['path']
            elif kind == 'arguments': changed['messages'][0]['tool_calls'] = [{'function': {'name': 'read_file', 'arguments': '{"path":"a.js"}'}}]
            elif kind == 'image': changed['messages'][0]['content'] = [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA'}}]
            else: changed['tools'].reverse()
            with self.subTest(kind=kind):
                self.assertNotEqual(baseline, prompt_fingerprint(json.dumps(changed).encode(), '')[0])

    def test_wire_hash_is_final_and_structural_hash_ignores_json_key_order(self):
        body = self.body()
        body['stream'] = True  # the stream guard changes this after request_received
        raw = json.dumps(body).encode()
        reordered = json.dumps(body, sort_keys=True, indent=2).encode()
        first, second = request_fingerprints(raw), request_fingerprints(reordered)
        self.assertEqual(first['wire_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(first['wire_sha256'], second['wire_sha256'])
        self.assertEqual(first['request_structure_sha256'], second['request_structure_sha256'])
        proxy = object.__new__(LlmProxy)
        proxy._lock = threading.Lock()
        proxy.phase, proxy.mode, proxy.no_tools, proxy.turn_serial = 'repair', 'low', True, 2
        meta = proxy.request_meta(raw)
        self.assertEqual(meta['wire_sha256'], first['wire_sha256'])
        self.assertNotIn('private source', json.dumps(meta))
        self.assertEqual(request_fingerprints(b'not json'), {})


class HelperClosureTests(unittest.TestCase):
    def test_alias_transitive_dependencies_and_initialization_survive(self):
        helper = ("import { expect } from '@playwright/test';\n"
                  "import './registration';\nexport { expect };\n"
                  "const value = 'yes';\nfunction leaf() { return value; }\n"
                  "const fixture = register();\nfunction register() { return leaf(); }\n"
                  "function used() { return leaf(); }\nexport { used as alias };\n"
                  "function unused() { return 'no'; }\n")
        result = main.trim_helper_to_references(helper, {'alias', 'expect'})
        for text in ("import './registration'", 'export { expect }', 'used as alias',
                     'function leaf', 'const value', 'const fixture', 'function register'):
            self.assertIn(text, result)
        self.assertNotIn('function unused', result)

    def test_top_level_side_effect_after_unused_declaration_is_retained(self):
        helper = "function unused() {}\nsetup();\nfunction setup() {}\nexport function used() {}\n"
        result = main.trim_helper_to_references(helper, {'used'})
        self.assertIn('setup();', result)
        self.assertIn('function setup', result)
        self.assertNotIn('function unused', result)

    def test_eager_property_access_and_assignments_cannot_be_discarded(self):
        helper = ("const state = setup.value;\nconst changed = state = 1;\n"
                  "const fixture = (() => setup())();\nconst fixture2 = function() { setup(); }();\n"
                  "export function used() {}\n")
        result = main.trim_helper_to_references(helper, {'used'})
        self.assertIn('const state', result)
        self.assertIn('const changed', result)
        self.assertIn('const fixture =', result)
        self.assertIn('const fixture2 =', result)

    def test_unknown_bindings_and_exports_conservatively_fall_back(self):
        for helper in ("const a = 1, b = 2;\nexport function used() { return b; }\n",
                       "const a = 1\nconst b = 2\nexport function used() { return b; }\n",
                       "function unused(): {x: number} { return {x: 1}; }\nexport function used() {}\n",
                       "function unused() { return `${`${1}`}`; }\nexport function used() {}\n",
                       "export * from './other';\nexport function used() {}\n",
                       "export const { a } = cfg;\nexport function used() {}\n"):
            self.assertEqual(main.trim_helper_to_references(helper, {'used'}), helper)

    def test_strings_comments_and_regex_do_not_create_declarations(self):
        helper = ("export function used() { return /[{};]/.test(`text ; }`); }\n"
                  "// export function misleading() {}\nexport function unused() {}\n")
        result = main.trim_helper_to_references(helper, {'used'})
        self.assertIn('/[{};]/', result)
        self.assertNotIn('function unused', result)


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flow = main.Flow(argparse.Namespace(web_port=3000), self.root, self.root)
        self.flow.codegen_ports_clause = lambda: ''
        self.flow.codegen_reasoning = lambda _: None
        main.write_codegen_manifests(self.root)
        self.sources = {
            'backend/server.js': 'const entry = true;',
            'frontend/src/App.jsx': "import Orders from './Orders'; import Other from './Other';",
            'frontend/src/Orders.jsx': "import {value} from './model.mjs'; export default value;",
            'frontend/src/model.mjs': 'export const value = 1;',
            'frontend/src/Other.jsx': 'export default 2;',
        }
        for path, source in self.sources.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
        self.node = {'id': 'REQ-1', 'description': 'Orders'}

    def test_known_target_gets_dependencies_unknown_target_keeps_broad_context(self):
        known = self.flow.codegen_implement_prompt(self.node, 'orders')
        quoted = main.quoted_paths(known)
        self.assertIn('frontend/src/model.mjs', quoted)
        self.assertIn('frontend/src/App.jsx', quoted)
        self.assertNotIn('frontend/src/Other.jsx', quoted)
        self.assertIn('frontend/src/Other.jsx', known)  # available through NEEDS_CONTEXT
        unknown = self.flow.codegen_implement_prompt(self.node, 'unknown feature')
        self.assertIn('frontend/src/Other.jsx', main.quoted_paths(unknown))

    def test_only_active_and_shared_contract_owners_expand_context(self):
        self.flow.app_design_doc = {'domain_contracts': [
            {'requirements': ['REQ-1'], 'owner': 'frontend/src/Orders.jsx'},
            {'requirements': ['REQ-2'], 'owner': 'frontend/src/Other.jsx'}]}
        required = self.flow.required_source_context('', sources=self.sources, requirement_ids=['REQ-1'])
        self.assertIn('frontend/src/Orders.jsx', required)
        self.assertIn('frontend/src/model.mjs', required)
        self.assertNotIn('frontend/src/Other.jsx', required)

    def test_presentation_weights_freeze_but_source_content_is_current(self):
        run = Mock(return_value=SimpleNamespace(returncode=0, stdout='frontend/src/Orders.jsx\n'))
        self.flow.runtime = SimpleNamespace(git=SimpleNamespace(run=run))
        first = self.flow.source_change_counts()
        run.return_value.stdout = 'frontend/src/Other.jsx\n' * 20
        self.assertEqual(first, self.flow.source_change_counts())
        run.assert_called_once()
        (self.root / 'frontend/src/model.mjs').write_text('export const value = 3;')
        self.assertIn('export const value = 3;', self.flow.codegen_implement_prompt(self.node, 'orders'))

    def test_repair_and_implementation_share_prefix_and_preserve_caller_protocols(self):
        self.flow.requirement_nodes = {'REQ-1': self.node}
        self.flow.spec_bodies = lambda _: 'orders'
        implementation = self.flow.codegen_implement_prompt(self.node, 'orders')
        caller = 'Diagnosis: stale UI. Keep the draft on failure. TEST_DISPUTE stays allowed.\n' + self.flow.sources_text()
        repair = self.flow.codegen_repair_prompt('REQ-1', caller, 'stale UI')
        common = os.path.commonprefix([implementation, repair])
        self.assertIn('export const value = 1;', common)
        self.assertIn('Keep the draft on failure', repair)
        self.assertIn('TEST_DISPUTE', repair)

    def test_dynamic_route_note_follows_the_shared_design_and_sources(self):
        self.flow.generic_template_installed = True
        self.flow.app_design_doc = {'data_model': {'Order': {'id': 'string'}}}
        with patch.object(main, 'route_table_note', side_effect=['route version A\n', 'route version B\n']):
            a = self.flow.codegen_implement_prompt(self.node, 'orders')
            b = self.flow.codegen_implement_prompt(self.node, 'orders')
        common = os.path.commonprefix([a, b])
        self.assertIn('Application design', common)
        self.assertIn('export const value = 1;', common)
        self.assertLess(a.index('--- backend/server.js ---'), a.index('route version A'))


if __name__ == '__main__':
    unittest.main()
