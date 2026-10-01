"""Calibrate save-failure witness across API architectures and broken rollback."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from acceptance import AcceptanceRunner
from embedded_repair_cases import register

HTML = r'''<!doctype html><html><body><div id="app"></div><script>
const app=document.getElementById('app');
const mode=document.cookie.split('; ').find(s=>s.startsWith('oracle='))?.split('=')[1]||'cells-good';
if(location.pathname==='/') {
 app.innerHTML='<button id="new">New blank workbook</button>';
 document.getElementById('new').onclick=()=>{
  app.innerHTML='<button id="create">Create</button>';
  document.getElementById('create').onclick=async()=>{await fetch('/initialize',{method:'POST'});location.href='/workbooks/main';};
 };
} else {
 let saved='';
 app.innerHTML='<button role="tab" aria-selected="true">Sheet1</button><div role="grid" aria-label="Worksheet grid"><div id="cell" role="gridcell" aria-label="A1" aria-selected="true" style="width:100px;height:24px;border:1px solid"></div></div><input id="formula" aria-label="Formula bar"><div id="errors"></div>';
 const cell=document.getElementById('cell'),formula=document.getElementById('formula'),errors=document.getElementById('errors');
 fetch('/data').then(r=>r.json()).then(data=>{saved=data.value;cell.textContent=saved;formula.value=saved;});
 formula.onkeydown=async event=>{
  if(event.key!=='Enter')return;
  const value=formula.value;const whole=mode.startsWith('workbook');
  const body=whole?{worksheets:[{cells:{A1:value}}]}:{cells:{A1:value}};
  if(mode.endsWith('bad'))cell.textContent=value;
  try {
   let response;
   for(let i=0;i<(mode.includes('retry')?3:1);i++){
    response=await fetch(whole?'/save-record':'/cell-write',{method:whole?'PUT':'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(response.ok)break;
   }
   const result=await response.json();if(!response.ok)throw Error(result.error);
   saved=value;cell.textContent=value;formula.value=value;errors.innerHTML='';
  } catch(error) {
   errors.innerHTML='';const alert=document.createElement('p');alert.setAttribute('role','alert');alert.textContent=mode.includes('generic')?'Could not store changes':error.message;errors.append(alert);
   if(!mode.endsWith('bad')){cell.textContent=saved;formula.value=saved;}
  }
 };
}
</script></body></html>'''

class SaveFailureOracleTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OCTOS_TEST_PLAYWRIGHT_ROOT'), 'requires local Playwright and Chromium')
    def test_write_injection_covers_cell_and_workbook_apis_and_rejects_false_ui_success(self):
        values={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def identity(self):return self.headers.get('Cookie','').split('oracle=')[-1].split(';')[0]
            def send(self,data,mime='application/json'):
                body=data if isinstance(data,bytes) else json.dumps(data).encode()
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_GET(self):
                if self.path=='/data':self.send({'value':values.get(self.identity(),'')})
                else:self.send(HTML.encode(),'text/html')
            def do_POST(self):values[self.identity()]='';self.send({})
            def write(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cells=body.get('cells') or body['worksheets'][0]['cells']
                values[self.identity()]=cells['A1'];self.send({})
            do_PATCH=write
            do_PUT=write
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            bodies=[]
            register(lambda node,title,body,**kw:bodies.append(body) if title.startswith('failed cell save') else None)
            self.assertEqual(len(bodies),1)
            install=Path(os.environ['OCTOS_TEST_PLAYWRIGHT_ROOT'])
            with tempfile.TemporaryDirectory(dir=install,prefix='save-failure-oracle-') as folder:
                root=Path(folder);suite=root/'tests';suite.mkdir()
                (suite/'helpers.ts').write_text((Path(__file__).resolve().parents[1]/'derived-tests/hackathon--sheet/helpers.ts').read_text())
                source="import {test,expect} from './helpers'; import * as h from './helpers';\n"
                address=f'http://127.0.0.1:{server.server_port}'
                modes=('cells-good','workbook-good','cells-retry-good','workbook-retry-good',
                       'cells-generic-good','workbook-generic-good','cells-bad','workbook-bad')
                for mode in modes:
                    source+=f"test('{mode}',async({{page,context,browser}})=>{{ await context.addCookies([{{name:'oracle',value:'{mode}',url:'{address}'}}]);\n"+bodies[0]+"\n});\n"
                (suite/'oracle.spec.ts').write_text(source)
                runner=AcceptanceRunner(install,suite,root/'prepared',lambda *_:None,workers=1)
                summary=runner.run(['oracle.spec.ts'],address,wall_timeout=100,workers=1)
                self.assertIsNone(summary.error)
                self.assertEqual(summary.total,len(modes))
                self.assertEqual({r.title:r.ok for r in summary.results},{mode:mode.endswith('good') for mode in modes},
                                 {r.title:r.message for r in summary.results if not r.ok})
                for row in summary.results:
                    if row.title.endswith('bad'):self.assertIn('original',row.message)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
