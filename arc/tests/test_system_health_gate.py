"""A broken detail page must be caught before derived business tests are reviewed."""
import argparse
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acceptance import AcceptanceRunner
from main import Flow
from runtime_diagnostics import browser_health, diagnose


class HealthGateTests(unittest.TestCase):
    def test_module_load_failure_shows_startup_fallback_and_fails_health(self):
        playwright_root = Path(__file__).parents[1] / 'local-grader'
        if not (playwright_root / 'node_modules' / '@playwright' / 'test').exists():
            self.skipTest('Playwright is not installed')
        html = (Path(__file__).parents[1] / 'blueprints/react-index.html').read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    body = html
                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    body = b'module missing'
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
                    f'http://127.0.0.1:{server.server_port}', Path(tmp), paths=['/'], timeout=25)
            if report['status'] == 'unknown' and any(
                    row['kind'] == 'browser_unavailable' for row in report['observations']):
                self.skipTest('Chromium is not available')
            self.assertEqual(report['status'], 'failed', report)
            self.assertTrue(any(row['kind'] == 'runtime_fallback' and row['confirmed']
                                for row in report['observations']), report)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_visible_fallback_is_a_confirmed_app_failure(self):
        playwright_root = Path(__file__).parents[1] / 'local-grader'
        if not (playwright_root / 'node_modules' / '@playwright' / 'test').exists():
            self.skipTest('Playwright is not installed')

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<main data-arc-runtime-error="true" role="alert"><h1>Could not display</h1><button>Reload</button></main>'
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
                    f'http://127.0.0.1:{server.server_port}', Path(tmp), paths=['/'], timeout=25)
            if report['status'] == 'unknown' and any(
                    row['kind'] == 'browser_unavailable' for row in report['observations']):
                self.skipTest('Chromium is not available')
            self.assertEqual(report['status'], 'failed', report)
            issues = diagnose(SimpleNamespace(runtime_observations=report['observations']))
            self.assertTrue(any(row['kind'] == 'runtime_fallback' and row['owner'] == 'app'
                                and row['state'] == 'confirmed' for row in issues), report)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_server_exit_overrides_unknown_browser_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            proc = subprocess.Popen(['true'])
            proc.wait(timeout=2)
            server = SimpleNamespace(proc=proc, tail=lambda: 'backend exited')
            self.assertIn('Server crash during rehearsal', flow.rehearsal_server_error(server))

    def test_rehearsal_measurement_exception_stops_server_and_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            server = Mock()
            server.build.return_value = None
            server.start.return_value = None
            flow.app_server = Mock(return_value=server)
            flow.rehearsal_browser_error = Mock(side_effect=RuntimeError('collector crashed'))
            self.assertTrue(flow.measure_rehearsal_server().startswith('Browser health unknown:'))
            server.stop.assert_called_once()
            server.build.side_effect = RuntimeError('build crashed')
            self.assertTrue(flow.measure_rehearsal_server().startswith('Rehearsal measurement unknown:'))
            self.assertEqual(server.stop.call_count, 2)
            server.proc = subprocess.Popen(['true'])
            server.proc.wait(timeout=2)
            server.tail.return_value = 'backend exited'
            self.assertTrue(flow.measure_rehearsal_server().startswith('Server crash during rehearsal'))
            server.proc = None
            server.build.side_effect = None
            flow.rehearsal_browser_error.side_effect = None
            flow.rehearsal_browser_error.return_value = None
            server.stop.side_effect = OSError('cleanup crashed')
            self.assertTrue(flow.measure_rehearsal_server().startswith('Browser health unknown: server cleanup failed:'))

    def test_measurement_exception_neither_repairs_nor_rolls_back_valid_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.measure_rehearsal_server = Mock(return_value='Rehearsal measurement unknown: OSError')
            flow.turn = Mock()
            flow.restore_startable_commit = Mock()
            self.assertFalse(flow.rehearsal())
            self.assertTrue(flow._last_rehearsal_measurement_unavailable)
            flow.turn.assert_not_called()
            flow.restore_startable_commit.assert_not_called()
            flow.last_startable_sha = 'good1234'
            flow.head = Mock(return_value='current9')
            flow.restore_app = Mock()
            self.assertFalse(Flow.restore_startable_commit(flow))
            flow.restore_app.assert_not_called()

    def test_requirements_setup_exception_writes_minimal_failed_terminal_state(self):
        import json
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module.shutil, 'copytree', side_effect=OSError('copy failed')), \
                    patch.object(module, 'Flow') as constructor, \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            constructor.assert_not_called()
            row = json.loads((output / '.arc/terminal-state.json').read_text())
            self.assertEqual(row['state'], 'failed')
            self.assertIn('requirements setup', row['reason'])

    def test_unwritable_output_setup_exits_without_starting_flow(self):
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            output.write_text('occupied by a file')
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module, 'Flow') as constructor, \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            constructor.assert_not_called()

    def test_signal_setup_exception_writes_minimal_failed_terminal_state(self):
        import json
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            fake_flow = Mock()
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module, 'Flow', return_value=fake_flow), \
                    patch('signal.signal', side_effect=ValueError('not main thread')), \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            fake_flow.run.assert_not_called()
            row = json.loads((output / '.arc/terminal-state.json').read_text())
            self.assertEqual(row['state'], 'failed')
            self.assertIn('signal setup', row['reason'])

    def test_fatal_flow_exception_records_failure_and_runs_cleanup(self):
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            fake_flow = Mock()
            fake_flow.run.side_effect = RuntimeError('fatal')
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module, 'Flow', return_value=fake_flow), \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            fake_flow.events.mark_run_failed.assert_called_once()
            fake_flow.write_terminal_state.assert_called_once_with('failed')
            fake_flow.postflight.assert_called_once()

    def test_flow_init_exception_writes_minimal_failed_terminal_state(self):
        import json
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module, 'Flow', side_effect=RuntimeError('init failed')), \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            row = json.loads((output / '.arc/terminal-state.json').read_text())
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['pending_usage_status'], 'unknown')

    def test_fatal_flow_and_terminal_writer_exceptions_still_leave_failure_record(self):
        import json
        import main as module
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'requirements'
            req.mkdir()
            output = Path(tmp) / 'output'
            fake_flow = Mock()
            fake_flow.run.side_effect = RuntimeError('fatal')
            fake_flow.write_terminal_state.side_effect = OSError('writer failed')
            fake_flow.postflight.side_effect = OSError('cleanup failed')
            with patch('sys.argv', ['main.py', str(req), '--output-dir', str(output)]), \
                    patch.object(module, 'Flow', return_value=fake_flow), \
                    patch.dict('os.environ', {'OCTOS_ARC_ENGINE': 'python'}):
                self.assertEqual(module.main(), 1)
            row = json.loads((output / '.arc/terminal-state.json').read_text())
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['pending_usage_status'], 'unknown')

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
