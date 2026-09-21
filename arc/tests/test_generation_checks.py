import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from generation_checks import check_batch


class GenerationChecksTests(TestCase):
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
