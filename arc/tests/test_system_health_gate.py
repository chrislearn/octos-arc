"""A broken detail page must be caught before derived business tests are reviewed."""
import argparse
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from acceptance import AcceptanceRunner
from main import Flow
from runtime_diagnostics import browser_health


class HealthGateTests(unittest.TestCase):
    def test_all_missing_binding_names_reach_startup_repair(self):
        names = (['setWorkbook'] * 6 + ['setActiveSheetId'] * 3 +
                 ['setWorkbookRenameName', 'setWorkbookRenameError',
                  'setWorksheetRenameName', 'setWorksheetRenameError'])
        bindings = {'status': 'failed', 'total': len(names), 'diagnostics': [
            {'file': 'src/pages/EditorPage.jsx', 'line': index + 1, 'name': name}
            for index, name in enumerate(names)]}
        bindings['names'] = [{'name': name, 'count': names.count(name),
                              'file': 'src/pages/EditorPage.jsx', 'line': names.index(name) + 1}
                             for name in dict.fromkeys(names)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.runner = AcceptanceRunner(root, root, root / 'runner', lambda _message: None)
            flow.remaining = Mock(return_value=50)
            flow.app_source_digest = Mock(return_value='source-v1')
            flow.metric = Mock()
            def healthy_browser(_root, _base_url, destination, **_options):
                destination.mkdir(parents=True, exist_ok=True)
                return {'status': 'passed', 'observations': [], 'artifact_dir': str(destination)}

            with patch('main.browser_health', side_effect=healthy_browser), \
                    patch('main.frontend_binding_health', return_value=bindings):
                report = flow.check_browser_health(force=True)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(len(report['observations']), 1)
            message = report['observations'][0]['message']
            for name in set(names):
                self.assertIn(name, message)
            self.assertIn('13 references', message)
            self.assertLess(len(message), 1000)
            self.assertEqual(report['frontend_bindings']['diagnostics'], bindings['diagnostics'])

    def test_visible_detail_link_is_checked_without_design_route(self):
        playwright_root = Path(__file__).parents[1] / 'local-grader'
        if not (playwright_root / 'node_modules' / '@playwright' / 'test').exists():
            self.skipTest('Playwright is not installed')

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    body = b'<a href="/detail/seed">Open record</a>'
                else:
                    body = b'<main>Record</main><script>setWorkbook()</script>'
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report = browser_health(playwright_root,
                    f'http://127.0.0.1:{server.server_port}', Path(tmp),
                    paths=['/'], dynamic_patterns=[], timeout=25)
            if report['status'] == 'unknown' and any(
                    row['kind'] == 'browser_unavailable' for row in report['observations']):
                self.skipTest('Chromium is not available')
            self.assertEqual(report['status'], 'failed', report)
            self.assertTrue(any(row.get('path') == '/detail/seed' and row['kind'] == 'pageerror'
                                for row in report['observations']), report)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_confirmed_system_failure_is_distinct_from_unavailable_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            server = Mock()
            server.build.return_value = None
            server.start.return_value = None
            flow.app_server = Mock(return_value=server)
            flow.remaining = Mock(return_value=60)
            flow.repair_minimum = Mock(return_value=60)
            flow.metric = Mock()
            flow.rehearsal_browser_error = Mock(return_value='Browser health failed: ReferenceError')
            self.assertFalse(flow.rehearsal(restore_on_failure=False))
            self.assertTrue(flow._last_rehearsal_system_failure)
            flow.rehearsal_browser_error.return_value = 'Browser health unknown: Chromium unavailable'
            self.assertFalse(flow.rehearsal(restore_on_failure=False))
            self.assertFalse(flow._last_rehearsal_system_failure)
            flow.rehearsal_browser_error.return_value = None
            self.assertTrue(flow.rehearsal(restore_on_failure=False))
            self.assertFalse(flow._last_rehearsal_system_failure)


if __name__ == '__main__':
    unittest.main()
