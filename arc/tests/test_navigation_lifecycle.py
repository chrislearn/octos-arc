"""Public scaffold contracts; deterministic async checks, separate from business specs."""
import os
import argparse
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import main as m
from generic_template import install_generic_template
from web_stack import stack_note


class NavigationContractTests(unittest.TestCase):
    def test_fresh_react_installs_read_scope_and_advertises_only_its_known_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_generic_template(root, m.BUNDLE_DIR, 3000, [], react=True)
            m.write_codegen_manifests(root)
            helper = root / 'frontend/src/shared/request-scope.js'
            self.assertEqual(helper.read_bytes(), (m.BUNDLE_DIR / 'blueprints/frontend-request-scope.js').read_bytes())
            self.assertIn('createRequestScope()', stack_note(root))
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            prompt = flow.codegen_implement_prompt({'id': 'READ', 'description': 'Show a record'}, 'public example')
            self.assertIn('createRequestScope()', prompt)
            self.assertIn('same-owner background refresh', prompt)
            self.assertIn('createRequestScope()', flow.sources_text())
            helper.write_text('export const custom = true;')
            self.assertNotIn('createRequestScope()', stack_note(root))
            # Installing a template never silently overwrites an evolved app.
            install_generic_template(root, m.BUNDLE_DIR, 3000, [])
            self.assertEqual(helper.read_text(), 'export const custom = true;')

    def test_actual_codegen_and_repair_paths_receive_lifecycle_guidance(self):
        for prompt in (m.CODEGEN_PROMPT, m.REPAIR_PROMPT, m.DERIVED_REPAIR_PROMPT):
            self.assertIn('finally', prompt)
            self.assertIn('logout', prompt)
        self.assertIn('same-owner background refresh', m.CODEGEN_PROMPT)
        self.assertNotIn('No two visible controls with the same role and name', m.CODEGEN_PROMPT)
        self.assertIn('scope conflict', m.REPAIR_PROMPT)
        self.assertIn('not a universal requirement', m.FINAL_CHECK_PROMPT)
        for constant, filename in [('UI_CONTRACT_CORE', 'ui-contract-core.md'),
                                   ('UI_CONTRACT_SESSION', 'ui-contract-session.md')]:
            self.assertEqual(getattr(m, constant).strip(),
                             (m.BUNDLE_DIR / 'prompts' / filename).read_text().strip())
        # Other shipped templates have different wrappers; preserve the same
        # new paragraph in both engines without replacing their placeholders.
        for constant, filename, prefix in [
            ('CODEGEN_PROMPT', 'codegen-prompt.md', 'Navigation/session:'),
            ('REPAIR_PROMPT', 'repair.md', 'For missing controls after navigation,'),
            ('FINAL_CHECK_PROMPT', 'final-check.md', '4. For flows affected by async')]:
            paragraph = next(line for line in getattr(m, constant).splitlines() if line.startswith(prefix))
            self.assertIn(paragraph, (m.BUNDLE_DIR / 'prompts' / filename).read_text())

    @unittest.skipUnless(shutil.which('node'), 'Node.js required')
    def test_read_scope_rejects_stale_success_failure_and_finally(self):
        result = subprocess.run(['node', str(Path(__file__).parent / 'fixtures/request-scope.mjs'),
                                 str(m.BUNDLE_DIR / 'blueprints/frontend-request-scope.js')],
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required')
    def test_read_scope_checks_reject_unguarded_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / 'broken.js'
            source = (m.BUNDLE_DIR / 'blueprints/frontend-request-scope.js').read_text()
            helper.write_text(source.replace('active === controller && !controller.signal.aborted', 'true'))
            result = subprocess.run(['node', str(Path(__file__).parent / 'fixtures/request-scope.mjs'), str(helper)],
                                    text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('stale catch/finally must not clear the latest pending state', result.stderr)


@unittest.skipUnless(os.environ.get('ARC_TEST_NPM_INTEGRATION') and
                     os.environ.get('ARC_TEST_PLAYWRIGHT_ROOT') and shutil.which('npm'),
                     'Set ARC_TEST_NPM_INTEGRATION=1 and ARC_TEST_PLAYWRIGHT_ROOT for real browser checks')
class NavigationBrowserTests(unittest.TestCase):
    def test_scaffold_navigation_and_controlled_read_order(self):
        import functools
        import http.server
        import threading

        fixtures = Path(__file__).parent / 'fixtures'
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_generic_template(root, m.BUNDLE_DIR, 3000, [], react=True)
            frontend = root / 'frontend'
            shutil.copy2(fixtures / 'navigation-lifecycle.jsx', frontend / 'src/App.jsx')
            for command in (['npm', 'ci', '--no-audit', '--no-fund'], ['npm', 'run', 'build']):
                result = subprocess.run(command, cwd=frontend, text=True, capture_output=True, timeout=240)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            handler = functools.partial(QuietHandler, directory=str(frontend / 'dist'))
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = dict(os.environ, NODE_PATH=str(Path(os.environ['ARC_TEST_PLAYWRIGHT_ROOT']) / 'node_modules'))
                result = subprocess.run(['node', str(fixtures / 'navigation-lifecycle.cjs'),
                                         str(server.server_port)], env=env, text=True, capture_output=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(result.stdout.strip())
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
