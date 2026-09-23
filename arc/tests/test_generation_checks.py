import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from generation_checks import check_batch, contract_warnings


class GenerationChecksTests(TestCase):
    def bundled_sources(self):
        blueprints = Path(__file__).resolve().parents[1] / 'blueprints'
        return {
            'backend/lib/collection.js': (blueprints / 'collection.js').read_text(),
            'frontend/src/shared/request.js': (blueprints / 'frontend-request.js').read_text(),
        }

    def test_transaction_replacement_and_empty_react_action_are_reported(self):
        sources = self.bundled_sources()
        sources['backend/routes/people.js'] = (
            'people.transact(items => { const ids = new Set([1]); '
            'return items.filter(row => !ids.has(row.id)); });')
        sources['frontend/src/People.jsx'] = (
            'export default function People() { return <button onClick={() => {}}>Remove</button>; }')
        warnings = contract_warnings(sources, ['backend/routes/people.js', 'frontend/src/People.jsx'])
        self.assertEqual({w.split(' ')[0] for w in warnings},
                         {'TRANSACT_RETURN', 'EMPTY_HANDLER'})
        self.assertEqual(contract_warnings(sources, ['frontend/src/shared/request.js']), [])

    def test_dialog_close_save_requires_interaction_probe(self):
        sources = {'frontend/src/Editor.jsx': (
            'export function Editor() { return <Dialog.Root open={open} '
            'onOpenChange={(next) => { if (!next) saveAndClose(); }}>Edit</Dialog.Root>; }')}
        warnings = contract_warnings(sources, ['frontend/src/Editor.jsx'])
        self.assertTrue(any('DIALOG_CLOSE_SAVE' in warning for warning in warnings))
        sources['frontend/src/Editor.jsx'] = (
            'export function Editor() { return <Dialog.Root open={open} '
            'onOpenChange={setOpen}>Edit</Dialog.Root>; }')
        self.assertFalse(any('DIALOG_CLOSE_SAVE' in warning for warning in
                             contract_warnings(sources, ['frontend/src/Editor.jsx'])))

    def test_native_interactive_nesting_warns_without_rejecting_component_composition(self):
        sources = {'frontend/src/Form.jsx': (
            '<label htmlFor="phone">Phone <input id="phone" />'
            '<button type="button">Send code</button></label>'
            '<button>Card <button>Delete</button></button>')}
        warnings = contract_warnings(sources, ['frontend/src/Form.jsx'])
        self.assertEqual({w.split(' ')[0] for w in warnings}, {'LABEL_BUTTON', 'NESTED_BUTTON'})
        sources['frontend/src/Form.jsx'] = (
            '<label htmlFor="phone">Phone</label><input id="phone" />'
            '<button type="button">Send code</button>')
        self.assertEqual(contract_warnings(sources, ['frontend/src/Form.jsx']), [])

    def test_react_effect_and_parsed_response_contract_are_checked(self):
        sources = self.bundled_sources()
        sources['frontend/src/View.jsx'] = (
            "import {requestJson} from './shared/request';\n"
            "useEffect(async () => { const response = await requestJson('/api/items'); "
            'if (response.ok) setItems(await response.json()); }, []);')
        warnings = contract_warnings(sources, ['frontend/src/View.jsx'])
        self.assertTrue(any('ASYNC_EFFECT' in w for w in warnings))
        self.assertTrue(any('REQUEST_JSON' in w for w in warnings))
        sources['frontend/src/useData.js'] = 'useLayoutEffect(async function () { await load(); }, []);'
        self.assertTrue(any('ASYNC_EFFECT' in w for w in contract_warnings(
            sources, ['frontend/src/useData.js'])))
        sources['frontend/src/shared/request.js'] = 'export async function requestJson() { return fetch("/x"); }'
        warnings = contract_warnings(sources, ['frontend/src/View.jsx'])
        self.assertFalse(any('REQUEST_JSON' in w or 'REQUEST_ENVELOPE' in w for w in warnings))

    def test_response_domain_ok_is_advisory_and_legitimate_transaction_result_is_quiet(self):
        sources = self.bundled_sources()
        sources['frontend/src/View.jsx'] = (
            "const reply = await requestJson('/api/action'); if (reply.ok) show(reply.value);")
        sources['backend/routes/people.js'] = (
            'people.transact(items => { items.splice(0, 1); return items.length; });')
        warnings = contract_warnings(sources, ['frontend/src/View.jsx', 'backend/routes/people.js'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('REQUEST_ENVELOPE', warnings[0])

    def test_empty_owner_on_creation_with_scoped_reads_is_reported(self):
        sources = {'backend/routes/orders.js': (
            "app.post('/api/orders', (req, res) => { const user = getCurrentUser(req); "
            "orders.create({userId: ''}); }); "
            "app.get('/api/orders', (req, res) => { const user = getCurrentUser(req); "
            "return orders.all().filter(order => order.userId === user.id); });")}
        warnings = contract_warnings(sources, ['backend/routes/orders.js'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('OWNER_SCOPE', warnings[0])
        sources['backend/routes/orders.js'] = sources['backend/routes/orders.js'].replace("userId: ''", 'userId: user.id')
        self.assertEqual(contract_warnings(sources, ['backend/routes/orders.js']), [])

    def test_nested_react_router_layout_requires_outlet(self):
        sources = {
            'frontend/src/App.jsx': (
                "import Layout from './Layout.jsx';\n"
                '<Routes><Route element={<Layout />}><Route path="/" element={<Home />} /></Route></Routes>'),
            'frontend/src/Layout.jsx': 'export default function Layout(){return <main>Home</main>}',
        }
        warnings = contract_warnings(sources, ['frontend/src/App.jsx'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('ROUTE_OUTLET', warnings[0])
        sources['frontend/src/Layout.jsx'] = 'export default function Layout(){return <main><Outlet /></main>}'
        self.assertEqual(contract_warnings(sources, ['frontend/src/App.jsx']), [])

    def test_duplicate_collection_owners_are_advisory_and_change_scoped(self):
        sources = {
            'backend/routes/a.js': "collection('records', {initial: []})",
            'backend/routes/b.js': "collection('records', {initial: items})",
            'backend/routes/c.js': "collection('other', {initial: []})",
        }
        warnings = contract_warnings(sources, ['backend/routes/a.js'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('DATA_OWNER', warnings[0])
        self.assertIn('backend/routes/b.js', warnings[0])
        self.assertEqual(contract_warnings(sources, ['backend/routes/c.js']), [])

    def test_storage_writer_dependency_prompts_behavior_check_not_rewrite(self):
        sources = {'frontend/src/state.js': "export function save(x) {localStorage.setItem('x', x)}",
                   'frontend/src/Layout.jsx': "import {get} from './state'; export default function Layout(){return <p>{get()}</p>}"}
        warnings = contract_warnings(sources, ['frontend/src/state.js'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('REACTIVE_STATE', warnings[0])
        self.assertIn('without reload', warnings[0])
        self.assertIn('may already handle', warnings[0])
        sources['frontend/src/Layout.jsx'] += '\nuseSyncExternalStore(subscribe, getSnapshot);'
        self.assertEqual(contract_warnings(sources, ['frontend/src/state.js']), [])

    def test_storage_alone_is_not_an_error_and_warnings_are_bounded(self):
        sources = {'frontend/cache.js': "localStorage.setItem('x', 'y');"}
        self.assertEqual(contract_warnings(sources, sources), [])
        for i in range(20):
            sources[f'frontend/View{i}.jsx'] = "localStorage.setItem('x', 'y');"
        warnings = contract_warnings(sources, sources)
        self.assertEqual(len(warnings), 6)
        self.assertTrue(all(len(w) <= 900 for w in warnings))
        result = check_batch(self.root, [], sources=sources)
        self.assertFalse(result['errors'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for part in ('frontend', 'backend'):
            (self.root / part).mkdir()
            (self.root / part / 'package.json').write_text('{}')

    def test_backend_syntax_failure_is_exact_evidence(self):
        (self.root / 'backend/server.js').write_text('const = ;')
        with patch('generation_checks._bounded_run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='SyntaxError: invalid')):
            result = check_batch(self.root, ['backend/server.js'])
        self.assertIn('SyntaxError', result['errors'][0])

    def test_missing_dependencies_are_deferred_not_installed_or_failed(self):
        (self.root / 'frontend/package.json').write_text(json.dumps({'scripts': {'build': 'vite build'}, 'dependencies': {'vite': '1'}}))
        with patch('generation_checks._bounded_run') as run:
            result = check_batch(self.root, ['frontend/App.jsx'])
        run.assert_not_called()
        self.assertFalse(result['errors'])
        self.assertTrue(result['deferred'])

    def test_explicit_missing_relative_code_import_is_an_early_error(self):
        path = 'frontend/src/components/layout/Header.jsx'
        source = "import {requestJson} from '../shared/request.js';\nexport default function Header() {}"
        sources = {path: source, 'frontend/src/shared/request.js': 'export const requestJson = () => null;'}
        result = check_batch(self.root, [path], sources=sources)
        self.assertTrue(any('missing frontend/src/components/shared/request.js' in e
                            for e in result['errors']))
        self.assertFalse(any('IMPORT_PATH' in w for w in result['warnings']))
        sources[path] = source.replace('../shared/', '../../shared/')
        result = check_batch(self.root, [path], sources=sources)
        self.assertFalse(result['errors'])
        sources[path] = "import styles from './card.css?inline';"
        self.assertFalse(check_batch(self.root, [path], sources=sources)['errors'])

    def test_dependency_free_build_runs_once_without_install(self):
        (self.root / 'frontend/package.json').write_text(json.dumps({'scripts': {'build': 'node build.js'}}))
        with patch('generation_checks._bounded_run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            result = check_batch(self.root, ['frontend/App.jsx'])
        self.assertEqual(run.call_args.args[0], ['npm', 'run', 'build'])
        self.assertEqual(result['checked'], ['frontend build'])

    def test_timeout_is_not_misrepresented_as_code_failure(self):
        (self.root / 'backend/server.js').write_text('')
        with patch('generation_checks._bounded_run', side_effect=subprocess.TimeoutExpired('node', 1)):
            result = check_batch(self.root, ['backend/server.js'])
        self.assertFalse(result['errors'])
        self.assertTrue(result['deferred'])

    def test_invalid_scripts_shape_is_a_manifest_error(self):
        (self.root / 'frontend/package.json').write_text('{"scripts": []}')
        result = check_batch(self.root, ['frontend/package.json'])
        self.assertIn('scripts must be an object', result['errors'][0])

    def test_real_process_timeout_is_bounded(self):
        from generation_checks import _bounded_run
        import sys
        import time
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            _bounded_run([sys.executable, '-c', 'import time; time.sleep(20)'], self.root, 0.05)
        self.assertLess(time.monotonic() - started, 3)
