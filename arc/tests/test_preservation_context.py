"""Shared edits receive original prior contracts before regression measurement."""
import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as m
from preservation_context import HEADER, INHERITED_HEADER, render_context, select_owners
from source_index import SourceIndex


class PreservationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.flow = f = m.Flow(argparse.Namespace(web_port=3000), self.root, self.root / 'requirements')
        f.tests_dir = self.root / 'tests'; f.tests_dir.mkdir()
        f.req_dir.mkdir(); (f.req_dir / 'requirements.yaml').write_text('original authority')
        f.requirement_nodes = {
            'register': {'id': 'register', 'description': 'Required error: Password requirements are not satisfied.'},
            'login': {'id': 'login', 'description': 'Login preserves active sessions.'},
            'recover': {'id': 'recover', 'description': 'Recover credentials; never alter unrelated accounts.',
                        'dependencies': ['register']},
            'future': {'id': 'future', 'description': 'Future feature must not be generated now.'},
        }
        f.spec_map = {key: [key + '.spec.ts'] for key in f.requirement_nodes}
        for name in f.spec_map:
            (f.tests_dir / (name + '.spec.ts')).write_text('test("' + name + '");')
        files = {'backend/server.js': "require('./routes/auth')",
                 'backend/routes/auth.js': "module.exports = app => { app.post('/api/register',()=>{}); };",
                 'frontend/src/Access.jsx': 'export default function Access(){return null}',
                 'frontend/src/App.jsx': "import Access from './Access.jsx'"}
        for name, text in files.items():
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        f.test_verdict = {'register': True, 'login': True}
        f.metric = Mock()

    def test_first_generation_includes_old_dependency_original_message(self):
        f = self.flow
        prompt = f.codegen_implement_prompt(f.requirement_nodes['recover'], 'Recovery form')
        self.assertIsNotNone(prompt, f.codegen_budget)
        self.assertIn(HEADER, prompt)
        self.assertIn('Password requirements are not satisfied', prompt)
        self.assertNotIn('Future feature must not be generated now', prompt)

    def test_dependency_id_in_description_is_not_mistaken_for_active_work(self):
        f = self.flow
        f.requirement_nodes = {'REQ-1': {'id': 'REQ-1', 'description': 'Old exact error text.'},
            'REQ-2': {'id': 'REQ-2', 'description': 'Reuse REQ-1, implement recovery.', 'dependencies': ['REQ-1']}}
        f.test_verdict = {'REQ-1': True}; f.spec_map = {}
        prompt = f.codegen_implement_prompt(f.requirement_nodes['REQ-2'], 'Recovery form')
        self.assertIn('Old exact error text.', prompt)

    def test_first_repair_without_regression_evidence_already_carries_old_contract(self):
        f = self.flow
        f.codegen_mode = Mock(return_value=False)
        f.turn = Mock(return_value=(True, 'no edit'))
        f.remaining = Mock(return_value=500); f.wound_down = Mock(return_value=False)
        f.spec_bodies = Mock(return_value='Recovery form')
        f.node_repair_turn('recover', 'recovery fails', 90, 'recover repair', lambda: 'Repair recovery')
        self.assertIn('Password requirements are not satisfied', f.turn.call_args.args[0])
        self.assertEqual(f.turn.call_args.args[0].count(HEADER), 1)

    def test_prior_red_owner_remains_in_context(self):
        f = self.flow
        f.proven_behavior = {'register'}; f.test_verdict['register'] = False
        self.assertIn('Password requirements are not satisfied', f.preservation_context(['recover']).text)

    def test_existing_context_is_rebuilt_when_shared_ownership_changes(self):
        f = self.flow
        prompt = f.with_preservation_context('Repair recovery', ['recover'])
        f.requirement_source_targets = Mock(return_value={'login': {'frontend/src/Access.jsx'}})
        updated = f.with_preservation_context(prompt, ['recover'], 'frontend/src/Access.jsx')
        self.assertEqual(updated.count(HEADER), 1)
        self.assertIn('Login preserves active sessions.', updated)
        self.assertIn('Password requirements are not satisfied', updated)

    def test_omitted_contract_forces_tool_mode_without_patched_prompt_bypass(self):
        f = self.flow
        f.sources_text = Mock(return_value='current sources')
        f.spec_bodies = Mock(return_value='Recovery form')
        f._patched_repair_prompt = Mock(return_value='unsafe text-only fallback')
        with patch.dict(os.environ, {'OCTOS_ARC_PRESERVATION_CHARS': '10'}):
            self.assertIsNone(f.codegen_repair_prompt('recover', 'Repair recovery', 'recovery fails'))
            f._patched_repair_prompt.assert_not_called()
            prompt = f.with_preservation_context('Repair recovery', ['recover'])
        self.assertIn('Contracts not quoted whole: register', prompt)
        self.assertIn(str(f.req_dir / 'requirements.yaml'), prompt)
        self.assertNotIn('Description: Required error', prompt)

    def test_active_and_future_nodes_never_become_preservation_obligations(self):
        f = self.flow
        f.requirement_nodes['recover']['dependencies'] += ['future']
        f.proven_behavior.add('recover')
        context = f.preservation_context(['recover'])
        self.assertEqual(context.owners, ('register',))

    def test_large_spec_cannot_bypass_omitted_contract_check_via_requote(self):
        f = self.flow
        f.spec_bodies = Mock(return_value='Recovery form' * 20000)
        f._patched_repair_prompt = Mock(return_value='unsafe text-only fallback')
        with patch.dict(os.environ, {'OCTOS_ARC_PRESERVATION_CHARS': '10'}):
            self.assertIsNone(f.codegen_repair_prompt('recover', 'Repair recovery', 'failure'))
        f._patched_repair_prompt.assert_not_called()
        self.assertEqual(f.codegen_repair_unavailable_reason, 'preservation_contracts_need_tool_reads')

    def test_source_overlap_covers_non_dependency_owner_and_ignores_hubs(self):
        nodes = self.flow.requirement_nodes
        index = SourceIndex({'frontend/src/App.jsx': "import X from './Access.jsx'",
                             'frontend/src/Access.jsx': "import X from './shared/Auth.js'",
                             'frontend/src/shared/Auth.js': 'export const X=1;'})
        targets = {'register': {'frontend/src/Access.jsx'}, 'login': {'frontend/src/Access.jsx'}}
        self.assertEqual(select_owners(nodes, ['future'], {'register', 'login'}, targets,
            ['frontend/src/App.jsx'], index), ())
        self.assertEqual(select_owners(nodes, ['future'], {'register', 'login'}, targets,
            ['frontend/src/shared/Auth.js'], index), ('login', 'register'))

    def test_folder_dependency_cycles_are_bounded_and_expand_only_measured_leaves(self):
        nodes = self.flow.requirement_nodes
        nodes['register']['dependencies'] = ['recover']
        nodes['recover']['dependencies'] = ['identity']
        self.assertEqual(select_owners(nodes, ['recover'], {'register'}, {}, [], SourceIndex({}),
                                      {'identity': ['register', 'future']}), ('register',))

    def test_description_is_never_cut_at_a_clause_boundary(self):
        nodes = {'A': {'description': 'first clause; ' + 'x' * 3000 + '; final required message'}}
        context = render_context(nodes, ['A'], '/original/requirements.yaml', 500)
        self.assertEqual(context.omitted, ('A',))
        self.assertNotIn('first clause', context.text)
        self.assertIn('/original/requirements.yaml', context.text)

    def test_first_node_inherits_parent_contract_without_activating_siblings(self):
        f = self.flow
        f.test_verdict = {}
        f.original_requirement_tree = {'id': 'product', 'description': 'Keep anonymous entry points on the home page.',
            'children': [{'id': 'identity', 'description': 'Recovery uses the same account identity.',
                'children': [f.requirement_nodes['recover'], f.requirement_nodes['future']]}]}
        context = f.preservation_context(['recover'])
        self.assertEqual(context.owners, ())
        self.assertEqual(context.inherited, ('product', 'identity'))
        prompt = f.codegen_implement_prompt(f.requirement_nodes['recover'], 'Recovery form')
        self.assertIn(INHERITED_HEADER, prompt)
        self.assertIn('Keep anonymous entry points on the home page.', prompt)
        self.assertNotIn('Future feature must not be generated now.', prompt)

    def test_parent_overflow_cannot_enter_text_repair_without_any_prior_pass(self):
        f = self.flow
        f.test_verdict = {}
        f.original_requirement_tree = {'id': 'product', 'description': 'Required parent policy ' * 1000,
                                      'children': [f.requirement_nodes['recover']]}
        f.spec_bodies = Mock(return_value='Recovery form')
        f._patched_repair_prompt = Mock(return_value='unsafe fallback')
        with patch.dict(os.environ, {'OCTOS_ARC_PRESERVATION_CHARS': '500'}):
            self.assertIsNone(f.codegen_repair_prompt('recover', 'Repair', 'failure'))
            context = f.preservation_context(['recover'])
        f._patched_repair_prompt.assert_not_called()
        self.assertEqual(context.omitted, ('product',))
        self.assertNotIn('Description: Required parent policy', context.text)

    def test_parent_and_prior_blocks_are_rebuilt_together_without_duplicates(self):
        f = self.flow
        f.original_requirement_tree = {'id': 'product', 'description': 'Original parent policy.',
                                      'children': [f.requirement_nodes['recover']]}
        prompt = f.with_preservation_context('Repair', ['recover'])
        f.original_requirement_tree['description'] = 'Current original parent policy.'
        rebuilt = f.with_preservation_context(prompt, ['recover'])
        self.assertEqual(rebuilt.count(INHERITED_HEADER), 1)
        self.assertEqual(rebuilt.count(HEADER), 1)
        self.assertIn('Current original parent policy.', rebuilt)
        self.assertNotIn('Description: Original parent policy.', rebuilt)

    def test_failing_react_route_renderer_is_quoted_before_the_first_repair(self):
        f = self.flow
        m.write_codegen_manifests(self.root)
        page = self.root / 'frontend/src/pages/UI.jsx'
        page.parent.mkdir(parents=True); page.write_text('export default function UI(){return <main>Start</main>}')
        (self.root / 'frontend/src/App.jsx').write_text("import Landing from './pages/UI.jsx';\n"
            'export default function App(){return <Routes>\n<Route path="/" element={<Landing />} />\n</Routes>}')
        prompt = f.codegen_implement_prompt(f.requirement_nodes['recover'], 'Recovery form',
                                           evidence='Page URL at failure: http://127.0.0.1:3000/')
        self.assertIn('frontend/src/pages/UI.jsx', m.quoted_paths(prompt))
        self.assertIn('frontend/src/pages/UI.jsx', f.codegen_budget['required_source_paths'])
        self.assertNotIn('frontend/src/pages/Future.jsx', m.quoted_paths(prompt))


if __name__ == '__main__':
    unittest.main()
