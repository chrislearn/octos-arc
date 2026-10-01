"""End-to-end reply/application recovery without paid model calls."""
import json
import unittest
from unittest.mock import Mock

from codegen import parse_context_request
from main import BUNDLE_DIR, app_design_blocks, quoted_paths
from source_index import SourceIndex
import test_diagnostic_repairs as flow_fixtures
import test_app_design as design_fixtures


def request(paths):
    return '<<<NEEDS_CONTEXT>>>\n' + json.dumps({'paths': paths, 'reason': 'read owner'}) + '\n<<<END NEEDS_CONTEXT>>>'


def file_block(path, text):
    return f'<<<FILE {path}>>>\n{text}\n<<<END FILE>>>'


def edit(path, old, new):
    return f'<<<EDIT {path}>>>\n<<<SEARCH>>>\n{old}\n<<<REPLACE>>>\n{new}\n<<<END EDIT>>>'


class RecoveryWorkflows(unittest.TestCase):
    def setUp(self):
        fixture = flow_fixtures.FlowRegression()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.flow, self.root = fixture.flow, fixture.root
        self.flow.use_structured_edits = Mock(return_value=False)

    def source(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def test_prose_request_then_missing_file_then_import_rejection_then_success(self):
        owner = 'frontend/src/model.js'
        self.source(owner, 'export const records = [];\n')
        page = 'frontend/src/View.jsx'
        replies = [
            'I need the current model.\n' + request([owner]),
            request(['frontend/src/NewView.jsx']),
            file_block(page, "import {missing} from './model.js';\nexport default missing;"),
            file_block(page, "import {records} from './model.js';\nexport default records;"),
        ]
        def respond(prompt, *args, **kwargs):
            index = len(self.flow.text_turn.call_args_list) - 1
            if index:
                self.assertIn('export const records', prompt)
                self.assertFalse((self.root / page).exists(), 'rejected replies must remain atomic')
            return True, replies[index]
        self.flow.text_turn = Mock(side_effect=respond)
        ok, reason = self.flow.codegen_turn('implement the view', 600, 'REQ-1 implement', request_budget=6)
        self.assertTrue(ok, reason)
        self.assertEqual(self.flow.text_turn.call_count, 4)
        self.assertEqual(self.flow.last_codegen_request_count, 4)
        self.assertIn('default records', (self.root / page).read_text())
        correction = self.flow.text_turn.call_args_list[2].args[0]
        self.assertIn('create it with FILE', correction)
        self.assertIn(owner, correction)

    def test_rejection_on_callers_retry_can_still_recover(self):
        owner = 'frontend/src/model.js'
        self.source(owner, 'export const rows = [];')
        page = 'frontend/src/Page.jsx'
        self.flow.text_turn = Mock(side_effect=[
            (True, file_block(page, "import {bad} from './model.js'; export default bad;")),
            (True, file_block(page, "import {rows} from './model.js'; export default rows;"))])
        self.assertTrue(self.flow.codegen_turn('implement', 600, 'REQ-1 implement (retry with model)')[0])
        self.assertIn('export const rows', self.flow.text_turn.call_args.args[0])

    def test_repeated_rejection_stops_without_write(self):
        self.flow.text_turn = Mock(return_value=(True, request(['frontend/src/missing.js'])))
        self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement')[0])
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertFalse((self.root / 'frontend/src/missing.js').exists())
        self.flow.save_rejected_reply.assert_called()

    def test_valid_repeated_source_read_stops_without_format_correction(self):
        paths = ['frontend/src/pages/Editor.jsx', 'backend/routes/workbooks.js']
        for path in paths:
            self.source(path, 'export const rows = [];\n')
        self.flow.text_turn = Mock(return_value=(True, request(paths)))
        ok, reason = self.flow.codegen_turn('implement row operations', 600, 'REQ-2-2-1 implement')
        self.assertFalse(ok)
        self.assertIn('unchanged evidence', reason)
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertEqual(self.flow.last_codegen_request_count, 2)
        self.assertEqual(self.flow.last_codegen_outcome, 'needs_context_repeated')
        self.assertEqual(self.flow.last_codegen_context_requested, set(paths))
        self.assertIn('export const rows', self.flow.text_turn.call_args.args[0])
        for path in paths:
            self.assertEqual((self.root / path).read_text(), 'export const rows = [];\n')

    def test_source_read_with_one_new_dependency_still_continues(self):
        for path in ['backend/a.js', 'backend/b.js']:
            self.source(path, 'export const rows = [];\n')
        self.flow.text_turn = Mock(side_effect=[
            (True, request(['backend/a.js'])),
            (True, request(['backend/a.js', 'backend/b.js'])),
            (True, file_block('backend/c.js', 'export const count = 1;'))])
        ok, reason = self.flow.codegen_turn('implement', 600, 'REQ-1 implement')
        self.assertTrue(ok, reason)
        self.assertEqual(self.flow.text_turn.call_count, 3)
        self.assertIn('backend/a.js', self.flow.text_turn.call_args.args[0])
        self.assertIn('backend/b.js', self.flow.text_turn.call_args.args[0])
        self.assertTrue((self.root / 'backend/c.js').exists())

    def test_repeated_read_after_export_correction_shares_original_evidence(self):
        self.source('frontend/src/model.js', 'export const rows = [];\n')
        self.flow.text_turn = Mock(side_effect=[
            (True, request(['frontend/src/model.js'])),
            (True, file_block('frontend/src/View.jsx', "import {missing} from './model.js'; export default missing;")),
            (True, request(['frontend/src/model.js']))])
        ok, reason = self.flow.codegen_turn('implement', 600, 'REQ-1 implement')
        self.assertFalse(ok)
        self.assertIn('unchanged evidence', reason)
        self.assertEqual(self.flow.text_turn.call_count, 3)
        self.assertEqual(self.flow.last_codegen_request_count, 3)
        self.assertEqual(self.flow.last_codegen_outcome, 'needs_context_repeated')
        self.assertFalse((self.root / 'frontend/src/View.jsx').exists())

    def test_request_cap_is_shared_by_reads_and_corrections(self):
        self.source('backend/model.js', 'module.exports = {};')
        self.flow.text_turn = Mock(side_effect=[
            (True, request(['backend/model.js'])),
            (True, request(['backend/new.js']))])
        self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement', request_budget=2)[0])
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertEqual(self.flow.last_codegen_request_count, 2)

    def test_deadline_and_global_budget_stop_correction(self):
        for seconds, wound_down in ((20, False), (600, True)):
            with self.subTest(seconds=seconds, wound_down=wound_down):
                self.flow.wound_down.return_value = wound_down
                self.flow.text_turn = Mock(return_value=(True, request(['backend/new.js'])))
                self.assertFalse(self.flow.codegen_turn('implement', seconds, 'REQ-1 implement')[0])
                self.flow.text_turn.assert_called_once()

    def test_zero_request_or_time_budget_sends_nothing(self):
        self.flow.text_turn = Mock()
        for timeout, requests in ((0, 10), (600, 0)):
            self.assertFalse(self.flow.codegen_turn('implement', timeout, 'REQ-1 implement', request_budget=requests)[0])
            self.assertEqual(self.flow.last_codegen_request_count, 0)
        self.flow.text_turn.assert_not_called()

    def test_inline_protocol_example_in_source_is_not_a_read_operation(self):
        path = 'backend/example.js'
        self.flow.text_turn = Mock(return_value=(True, file_block(path, 'const example = "<<<NEEDS_CONTEXT>>>";')))
        self.assertTrue(self.flow.codegen_turn('implement', 600, 'REQ-1 implement')[0])
        self.flow.text_turn.assert_called_once()
        self.assertTrue((self.root / path).is_file())

    def test_atomic_multi_file_local_edit_failure_then_fix(self):
        a, b = 'backend/a.js', 'backend/b.js'
        self.source(a, 'const value = 1;\n' + '// preserve\n' * 1400)
        self.source(b, 'const count = 1;\n')
        prompt = ''.join(f'--- {p} ---\n{(self.root / p).read_text()}\n' for p in (a, b))
        first = edit(a, 'const value = 1;', 'const value = 2;') + '\n' + edit(b, 'missing', 'const count = 2;')
        second = edit(a, 'const value = 1;', 'const value = 2;') + '\n' + edit(b, 'const count = 1;', 'const count = 2;')
        def respond(*args, **kwargs):
            self.assertIn('const value = 1;', (self.root / a).read_text())
            return True, first if self.flow.text_turn.call_count == 1 else second
        self.flow.text_turn = Mock(side_effect=respond)
        self.assertTrue(self.flow.codegen_turn(prompt, 600, 'wave implement')[0])
        self.assertIn('const value = 2;', (self.root / a).read_text())
        self.assertEqual((self.root / a).read_text().count('// preserve'), 1400)
        self.assertIn('const count = 2;', (self.root / b).read_text())

    def test_no_retry_after_a_partial_write(self):
        def generate(*args, **kwargs):
            self.flow.last_codegen_written = ['backend/a.js']
            self.flow.last_codegen_request_count = 1
            self.flow.last_codegen_outcome = 'export_contract'
            return False, 'bad export'
        self.flow._codegen_attempt = Mock(side_effect=generate)
        self.assertFalse(self.flow.codegen_turn('implement', 600, 'REQ-1 implement')[0])
        self.flow._codegen_attempt.assert_called_once()

    def test_atomic_scaffold_refusal_quotes_small_siblings_before_retry(self):
        helpers = {
            'frontend/build.mjs': 'frontend-build.mjs',
            'frontend/vite.config.mjs': 'vite.config.mjs',
            'frontend/src/shared/interactions.jsx': 'react-interactions.jsx',
        }
        for rel, asset in helpers.items():
            self.source(rel, (BUNDLE_DIR / 'blueprints' / asset).read_text())
        self.flow.generic_template_installed = True
        self.flow._atomic_codegen_response = True
        self.flow._whole_app_prompt_cap = 96000
        reply = (file_block('frontend/build.mjs', '// blind rewrite') + '\n'
                 + file_block('frontend/src/shared/interactions.jsx', '// blind rewrite') + '\n'
                 + file_block('frontend/src/pages/Editor.jsx', 'export default function Editor() {}'))

        def respond(prompt, *args, **kwargs):
            if self.flow.text_turn.call_count == 1:
                return True, reply
            for rel in helpers:
                self.assertIn(rel, quoted_paths(prompt))
            self.assertIn('Existing files allowed in this response', prompt)
            self.assertFalse((self.root / 'frontend/src/pages/Editor.jsx').exists())
            return True, file_block('frontend/src/pages/Editor.jsx', 'export default function Editor() { return null; }')

        self.flow.text_turn = Mock(side_effect=respond)
        ok, reason = self.flow.codegen_turn('implement', 600, 'whole application wave 1')
        self.assertTrue(ok, reason)
        self.assertEqual(self.flow.text_turn.call_count, 2)
        self.assertEqual((self.root / 'frontend/src/pages/Editor.jsx').read_text().strip(),
                         'export default function Editor() { return null; }')
        for rel, asset in helpers.items():
            self.assertEqual((self.root / rel).read_text(), (BUNDLE_DIR / 'blueprints' / asset).read_text())


class ContextContracts(unittest.TestCase):
    def test_surrounding_prose_is_tolerated_but_ambiguous_operations_are_not(self):
        block = request(['backend/a.js'])
        self.assertIsNotNone(parse_context_request('Read this first.\n' + block + '\nThen implement.'))
        for text in (block + block, block + file_block('backend/a.js', 'x'),
                     file_block('backend/a.js', block), request(['backend/../secret'])):
            self.assertIsNone(parse_context_request(text))

    def test_47_leaf_design_keeps_identity_and_commands_in_every_slice(self):
        design = {
            'data_model': {'Session': {'userId': 'same persistent User.id'}},
            'domain_contracts': [{'identity': 'shared identity owner', 'requirements': ['REQ-1']}],
            'contracts': [{'format': {'version': 2, 'required': ['id', 'items']}, 'requirements': ['REQ-1']}],
            'commands': [{'name': 'reject stale approval without mutation', 'requirements': ['REQ-2']}],
            'pages': [{'path': f'/page{i}', 'purpose': 'detail ' * 100, 'requirements': [f'REQ-{i}']} for i in range(47)]}
        for i in range(47):
            stable, _ = app_design_blocks(design, f'REQ-{i}', 6000)
            for value in ('same persistent User.id', 'shared identity owner', 'reject stale approval', '"version":2'):
                self.assertIn(value, stable)

    def test_contracts_grow_design_preference_but_never_bypass_input_limit(self):
        from tempfile import TemporaryDirectory
        design = {'data_model': {'Identity': {'rule': 'x' * 14000}}, 'pages': [{'path': '/'}]}
        stable, _ = app_design_blocks(design, 'REQ-1', 6000)
        self.assertIn('x' * 14000, stable)
        with TemporaryDirectory() as folder:
            flow = design_fixtures.PromptPlacementTests()._flow(folder)
            flow.app_design_doc = design
            prompt = flow.codegen_implement_prompt({'id': 'REQ-1'}, 'spec', context_limit=12000)
            self.assertIsNone(prompt, 'must refuse an over-budget prompt instead of dropping the identity contract')

    def test_large_active_route_keeps_exact_response_and_error_formats(self):
        contract = {'method': 'POST', 'path': '/api/items', 'requirements': ['REQ-47'],
                    'response': {'official_format': 'x' * 8000},
                    'errors': [{'status': 409, 'condition': 'stale version', 'kind': 'conflict'}]}
        design = {'data_model': {'Item': {'version': 'integer'}}, 'routes': [contract]}
        _, detail = app_design_blocks(design, 'REQ-47', 6000)
        self.assertIn('x' * 8000, detail)
        self.assertIn('"status":409', detail)

    def test_shared_layout_and_model_dependencies_are_required_without_all_pages(self):
        sources = {
            'frontend/src/App.jsx': "import Layout from './Layout'; import Page from './pages/Other';",
            'frontend/src/Layout.jsx': "import {identity} from './lib/identity';",
            'frontend/src/lib/identity.js': "import {schema} from './schema'; export const identity = schema;",
            'frontend/src/lib/schema.js': 'export const schema = {};',
            'frontend/src/pages/Other.jsx': 'export default 1;',
            'frontend/src/pages/Active.jsx': "import {identity} from '../lib/identity';"}
        selected = SourceIndex(sources).contract_context({'frontend/src/pages/Active.jsx'})
        self.assertIn('frontend/src/App.jsx', selected)
        self.assertIn('frontend/src/Layout.jsx', selected)
        self.assertIn('frontend/src/lib/schema.js', selected)
        self.assertNotIn('frontend/src/pages/Other.jsx', selected)

    def test_leaf_and_repair_prompts_both_include_composition_and_layout(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            flow = design_fixtures.PromptPlacementTests()._flow(folder)
            app = flow.output_dir / 'frontend/src/App.jsx'
            app.write_text("import Layout from './Layout'; export default Layout;")
            layout = app.with_name('Layout.jsx')
            layout.write_text('export default function Layout() { return null; }')
            prompt = flow.codegen_implement_prompt({'id': 'REQ-1'}, 'orders')
            required = {'frontend/src/App.jsx', 'frontend/src/Layout.jsx'}
            self.assertTrue(required <= quoted_paths(prompt))
            repair = flow._patched_repair_prompt('REQ-1', 'orders', 'Fix the failure\n' + flow.sources_text())
            self.assertIsNotNone(repair)
            self.assertTrue(required <= quoted_paths(repair))

    def test_explicit_requirement_id_selects_contract_without_spec_keyword_overlap(self):
        from tempfile import TemporaryDirectory
        for requirement_id in ('REQ-47', 'ITEM-A'):
            with self.subTest(requirement_id=requirement_id), TemporaryDirectory() as folder:
                flow = design_fixtures.PromptPlacementTests()._flow(folder)
                flow.app_design_doc = {
                    'data_model': {'Item': {'id': 'string'}}, 'notes': 'n' * 25000,
                    'pages': [{'path': '/work', 'requirements': [requirement_id],
                               'purpose': 'Irreducible business clause'}]}
                prompt = flow.codegen_implement_prompt({'id': requirement_id}, 'Click Confirm')
                self.assertIn('Irreducible business clause', prompt)
                wave = flow.codegen_implement_prompt(
                    {'id': 'application wave 1', 'active_requirement_ids': [requirement_id]}, 'Click Confirm')
                self.assertIn('Irreducible business clause', wave)
                repaired = flow._patched_repair_prompt(requirement_id, 'Click Confirm', flow.sources_text())
                self.assertIn('Irreducible business clause', repaired)
