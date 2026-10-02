"""Run the actual date recipes against correct and deliberately wrong clients."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from acceptance import AcceptanceRunner
from embedded_sheet_cases import register
from embedded_sheet_contract_gap_cases import register as register_gaps


class SheetDateOracleTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT'),'requires local Playwright and Chromium')
    def test_non_iso_sort_rejects_lexical_comparison_without_overclaiming_iso_filter_coverage(self):
        arc=Path(__file__).resolve().parents[1]
        html=(arc/'tests/fixtures/sheet-date-oracle.html').read_bytes()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(html)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            bodies={}
            wanted=('audit regression: Ascending uses chronological order',
                    'audit regression: Descending uses chronological order', 'condition Before')
            def collect(node,title,body,**kw):
                prefix=next((p for p in wanted if title.startswith(p)),None)
                if prefix:bodies[prefix]=body
            register(collect)
            register_gaps(collect)
            self.assertEqual(set(bodies),set(wanted))
            install=Path(os.environ['OCTOS_TEST_PLAYWRIGHT_ROOT'])
            with tempfile.TemporaryDirectory(dir=install,prefix='sheet-date-oracle-') as folder:
                root=Path(folder);suite=root/'tests';suite.mkdir()
                (suite/'helpers.ts').write_bytes((arc/'derived-tests/hackathon--sheet/helpers.ts').read_bytes())
                address=f'http://127.0.0.1:{server.server_port}'
                source="import {test,expect} from './helpers'; import * as h from './helpers';\n"
                expected={}
                for prefix,body in bodies.items():
                    is_filter=prefix=='condition Before'
                    for mode in ('chronological','lexical') if is_filter else ('chronological','lexical','noop'):
                        # ISO date-only strings have the same chronological and
                        # lexical order. This filter witness cannot prove types.
                        title=prefix+' '+mode;expected[title]=mode=='chronological' or is_filter
                        source+=f'test({json.dumps(title)},async({{page,context,browser}})=>{{await context.addCookies([{{name:"oracle",value:{json.dumps(mode)},url:{json.dumps(address)}}}]);\n'+body+'\n});\n'
                (suite/'oracle.spec.ts').write_text(source)
                runner=AcceptanceRunner(install,suite,root/'prepared',lambda *_:None,timeout_ms=7000,workers=1)
                summary=runner.run(['oracle.spec.ts'],address,wall_timeout=60,workers=1)
                self.assertIsNone(summary.error)
                self.assertEqual(summary.total,len(expected))
                self.assertEqual({r.title:r.ok for r in summary.results},expected,
                                 {r.title:r.message for r in summary.results if not r.ok})
                for row in summary.results:
                    if not row.ok:
                        self.assertIn('Expected:',row.message)
                        self.assertIn('Received:',row.message)
                # Preserve structured evidence when an explicit proof directory
                # is requested; ordinary unit runs stay in their temporary dir.
                if proof:=os.environ.get('OCTOS_SHEET_DATE_PROOF'):
                    path=Path(proof);path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text(json.dumps([{'title':r.title,'ok':r.ok,'message':r.message} for r in summary.results],ensure_ascii=False,indent=2)+'\n')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
