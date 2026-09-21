import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from generation_checks import check_batch, contract_warnings


class GenerationChecksTests(TestCase):
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
