"""Offline real-browser regressions. No model/provider calls. Keep evidence outside bundle."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance import AcceptanceRunner
from runtime_diagnostics import browser_health, application_failures

class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path.startswith('/api/private'):
            self.send_response(403); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(b'{"error":"forbidden"}'); return
        pages = {'/blank': '<div id="root"></div>', '/crash': '<script>throw new Error("fixture runtime crash")</script>',
                 '/event': '<h1>Visible content</h1><script>throw new Error("fixture action fault")</script>'}
        text = pages.get(self.path, '<h1>Ready</h1><button onclick="fetch(\'/api/private\')">Read private</button>')
        self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
        self.wfile.write(('<html><body>'+text+'</body></html>').encode())


def main():
    p=argparse.ArgumentParser(); p.add_argument('--playwright-root', required=True); p.add_argument('--evidence',required=True)
    args=p.parse_args(); root=Path(args.playwright_root).resolve(); evidence=Path(args.evidence).resolve(); evidence.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture); threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        checks={}
        for route, expected in [('/', 'passed'),('/blank','failed'),('/crash','failed')]:
            report=browser_health(root,base,evidence/('health-'+(route.strip('/') or 'home')),paths=[route])
            assert report['status']==expected, report
            checks[route]=report['status']
        with tempfile.TemporaryDirectory(prefix='v115-spec-') as tmp:
            specs=Path(tmp)
            shutil.copyfile(Path(__file__).resolve().parents[1]/'blueprints/derived-helpers.ts',specs/'helpers.ts')
            (specs/'runtime.spec.ts').write_text('''import {test, expect} from '@playwright/test';
import * as h from './helpers';
test('passing assertion still retains runtime error', async ({page}) => {
  await page.goto('/event'); await expect(page.getByRole('heading')).toHaveText('Visible content');
});
test('expected permission rejection is business evidence', async ({page}) => {
  await page.goto('/'); await h.watchResponse(page, '/api/private', 'GET');
  await page.getByRole('button').click(); await h.expectResponse(page, '/api/private', 403, {error:'forbidden'});
});
test('mutation wrong status must fail', async ({page}) => {
  await page.goto('/'); await h.watchResponse(page, '/api/private', 'GET');
  await page.getByRole('button').click(); await h.expectResponse(page, '/api/private', 200);
});
''')
            with tempfile.TemporaryDirectory(prefix='.v115-run-',dir=root) as work:
                runner=AcceptanceRunner(root,specs,Path(work),print,timeout_ms=2500,workers=1)
                runner.artifact_dir=evidence/'acceptance'
                summary=runner.run(['runtime.spec.ts'],base,wall_timeout=40)
                assert summary.total==3 and summary.passed==2, repr(summary)
                assert any(e['kind']=='pageerror' and e['test_title']=='passing assertion still retains runtime error' for e in summary.runtime_observations), summary.runtime_observations
                assert any(e['kind']=='http_response' and e['status']==403 for e in summary.runtime_observations), summary.runtime_observations
                assert not application_failures(summary), 'unconfirmed spec observations must not self-certify'
                assert any(Path(d).joinpath('report.json').exists() for d in summary.artifact_dirs)
                checks['acceptance']={'passed':summary.passed,'total':summary.total,'expected_mutation_failure':1,'runtime_events':len(summary.runtime_observations)}
        (evidence/'result.json').write_text(json.dumps(checks,indent=2)); print(json.dumps(checks))
    finally: server.shutdown(); server.server_close()
if __name__=='__main__': main()
