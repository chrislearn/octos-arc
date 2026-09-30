"""Real local layered gates/discovery/rollback, without provider calls.

Review replies are fixed fixtures. This verifies orchestration and execution,
not the semantic quality or latency of an actual model review.
"""
import argparse
import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from acceptance import AcceptanceRunner
from layered_tests import ApplicationSnapshot, GateBlocked, LayeredTests, digest
from main import Flow


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run_fixture(playwright_root, evidence):
    coordinator_path = Path(__file__).resolve().parents[1] / 'layered_tests.py'
    coordinator_sha = digest(coordinator_path.read_bytes())
    with tempfile.TemporaryDirectory(prefix='arc-layered-runtime-') as tmp, tempfile.TemporaryDirectory(
            prefix='.arc-layered-playwright-', dir=playwright_root) as work:
        parent = Path(tmp)
        output, requirements = parent / 'app', parent / 'task'
        output.mkdir(); requirements.mkdir()
        nodes = [{'id': f'REQ-{i}', 'type': 'ATOMIC', 'description': f'The home page has a button named “Open {i}”.',
                  'scenarios': [], 'dependencies': []} for i in (1, 2, 3)]
        tree = {'id': 'ROOT', 'description': 'Each visible item can be opened.', 'children': nodes}
        (requirements / 'requirements.yaml').write_text(json.dumps(tree))
        for folder in ('backend', 'frontend/src'):
            (output / folder).mkdir(parents=True)
        (output / 'frontend/package.json').write_text(json.dumps({'name': 'layered-fixture',
            'scripts': {'build': 'node build.cjs'}}))
        (output / 'frontend/build.cjs').write_text("const f=require('fs');f.rmSync('dist',{recursive:true,force:true});f.cpSync('src','dist',{recursive:true});")
        (output / 'backend/package.json').write_text(json.dumps({'name': 'layered-fixture-backend',
            'scripts': {'start': 'node server.cjs'}}))
        (output / 'backend/server.cjs').write_text("""const http=require('http'),f=require('fs'),p=require('path');
http.createServer((req,res)=>{
 if(req.method==='GET' && req.url==='/health'){res.writeHead(200);res.end('healthy');return;}
 if(req.method!=='GET'){res.writeHead(404);res.end('unsupported');return;}
 res.writeHead(200,{'Content-Type':'text/html'});res.end(f.readFileSync(p.join(__dirname,'../frontend/dist/index.html')));
}).listen(Number(process.env.PORT),'127.0.0.1');
""")
        html = output / 'frontend/src/index.html'
        def page(count, broken=False):
            buttons = ''.join(f'<button onclick="document.querySelector(\'output\').textContent=\'{i}\'">Open {i}</button>'
                              for i in range(1, count + 1) if not (broken and i == 1))
            return f'<!doctype html><html><body><h1>Authoritative fixture</h1>{buttons}<output>0</output></body></html>'
        html.write_text(page(0))
        subprocess.run(['git', 'init', '-q'], cwd=output, check=True)
        subprocess.run(['git', 'add', '.'], cwd=output, check=True)
        subprocess.run(['git', '-c', 'user.name=ARC fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'fixture'], cwd=output, check=True)
        flow = Flow(argparse.Namespace(web_port=free_port()), output, requirements)
        flow.smoke_port = free_port()
        flow.runtime = SimpleNamespace(git=SimpleNamespace(run=lambda args, check=False: subprocess.run(
            ['git', *args], cwd=output, check=check, capture_output=True, text=True)))
        flow.requirement_tree = tree
        flow.requirement_nodes = {n['id']: n for n in nodes}
        flow.app_design_doc = {'data_model': {'items': {'id': 'string'}}, 'pages': [
            {'path': '/', 'purpose': 'Home', 'requirements': [n['id'] for n in nodes]}], 'obligations': []}
        flow.tests_dir = output / 'official-tests'
        flow.tests_dir.mkdir()
        flow.derived_as_specs = False
        flow.spec_map = {'REQ-1': ['nested.spec.ts'], 'REQ-2': [], 'REQ-3': [], None: []}
        # Discovery must handle nested suites, dynamic titles, double quotes and siblings.
        (flow.tests_dir / 'nested.spec.ts').write_text('''import {test,expect} from '@playwright/test';
test.describe("official suite", () => {
 for (const i of [1,2]) {
  test(`open ${i}`, async ({page}) => {
   await page.goto('/'); await page.getByRole('button',{name:`Open ${i}`,exact:true}).click();
   await expect(page.locator('output')).toHaveText(String(i));
  });
 }
 test("unapproved sibling must never run", async () => { throw new Error('outside frozen selection'); });
});
''')
        flow.runner = AcceptanceRunner(playwright_root, flow.tests_dir, Path(work), lambda *_: None, workers=1, timeout_ms=2500)
        metrics = []
        flow.metric = lambda kind, **fields: metrics.append({'kind': kind, **fields})
        flow.commit = Mock()
        flow.remaining = lambda: 10000
        flow.time_up = lambda: False
        flow.wound_down = lambda: False
        flow.final_measurement_reserve = lambda: 30
        flow.node_start_budget_available = lambda *a, **kw: True
        flow.admit_node = lambda node: True
        flow.start_background_specs = Mock()
        flow.poll_background_specs = Mock()
        flow.driver = None
        flow.repair_rounds = 0
        flow.derived_review_needed = lambda key: False
        def audit(prompt, *args, **kwargs):
            for node in nodes:
                if node['description'] in prompt:
                    index = node['id'][-1]
                    return True, json.dumps({'status': 'approved_basic', 'requirement_quote': node['description'],
                        'test_quote': f"await h.expectRole(page, 'button', 'Open {index}');", 'reason': 'Grounded entry fixture'})
            raise AssertionError('unexpected fixture review input')
        flow.text_turn = audit
        layer = flow.layered = LayeredTests(flow, nodes)
        layer.prepare()
        called = []
        def implement(node, ordered, index, total):
            called.append(node['id'])
            html.write_text(page(index, broken=index == 2))
            flow.implementation_evidence[node['id']] = {'status': 'implemented_unverified'}
        flow.node_cycle = implement
        try:
            layer.implement(tree, nodes, set())
            raise AssertionError('regressed baseline advanced to the next node')
        except GateBlocked as exc:
            if 'REQ-2' not in str(exc):
                evidence.mkdir(parents=True, exist_ok=True)
                (evidence / 'blocked-measurement.json').write_text(json.dumps({
                    'error': str(exc), 'health': getattr(flow, '_last_browser_health', {}), 'metrics': metrics}, indent=2))
            assert 'REQ-2' in str(exc), str(exc)
        assert called == ['REQ-1', 'REQ-2'], called
        assert html.read_text() == page(1), 'unsafe edit did not restore the last basic-passing application'
        assert not layer.state.data['nodes']['REQ-2']['code_done']
        assert not layer.state.data['nodes']['REQ-3']['code_done']
        assert layer.deliver_blocked('REQ-2: stopped by basic regression'), 'safe partial application did not rehearse'
        blocked = flow.run_specs(['nested.spec.ts'])
        assert blocked.error and 'no frozen' in blocked.error, blocked
        # Finish nodes under the same mandatory gates, then discover immutable official cases.
        for i in (2, 3):
            html.write_text(page(i))
            layer.gate(f'REQ-{i}')
        layer.state.data.pop('termination', None)
        layer.state.data.pop('termination_reason', None)
        cases, error = flow.runner.discover_cases(['nested.spec.ts'])
        assert not error and len(cases) == 3, (error, cases)
        source = (flow.tests_dir / 'nested.spec.ts').read_bytes()
        layer.state.data['phase'] = 'business'
        protected = layer.run_basic()
        assert layer.complete(protected, layer.basic_specs()) and protected.all_passed, protected
        for case in cases[:2]:
            key = layer.state.identity('REQ-1', case['title'])
            layer.state.data['cases'][key] = {**case, 'id': key, 'node_id': 'REQ-1', 'scenario': case['title'],
                'status': 'pending', 'dependencies': {'nested.spec.ts': digest(source)}}
        measured_runs = []
        run_specs = flow.run_specs
        def count_run(specs, **kwargs):
            measured_runs.append(specs)
            return run_specs(specs, **kwargs)
        flow.run_specs = count_run
        layer.execute_business()
        assert len(measured_runs) == 1, 'the ready business cases did not share one execution cycle'
        flow.run_specs = run_specs
        assert all(row['status'] == 'passed' for row in layer.state.data['cases'].values()), layer.state.data['cases']
        assert (flow.tests_dir / 'nested.spec.ts').read_bytes() == source, 'the official source was modified'
        # A broken backend update must be statically rejected and fully restored.
        before = ApplicationSnapshot(flow)
        (output / 'backend/server.cjs').write_text('const broken = ;')
        rejected = layer.run_basic()
        assert rejected.error and 'syntax' in rejected.error, rejected
        before.restore()
        restored = layer.run_basic()
        assert layer.complete(restored, layer.basic_specs()) and restored.all_passed, restored
        result = {'basic_next_node_blocked': True, 'previous_basics_regression_restored': True,
            'business_blocked_before_all_nodes': True, 'official_discovered': len(cases),
            'selected_business_passed': len(layer.state.data['cases']), 'unapproved_sibling_excluded': True,
            'official_source_unchanged': True, 'invalid_backend_static_rejected': True,
            'rollback_basic_and_health_passed': True, 'initial_snapshot_published': True,
            'partial_application_rehearsed': True, 'business_execution_cycles': len(measured_runs),
            'review_quality_and_provider_latency_tested': False,
            'coordinator_sha256': coordinator_sha}
        assert coordinator_sha == digest(coordinator_path.read_bytes()), 'coordinator changed during integration measurement'
        evidence.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output / '.arc/acceptance-evidence', evidence / 'acceptance', dirs_exist_ok=True)
        shutil.copytree(output / '.arc/browser-health', evidence / 'browser-health', dirs_exist_ok=True)
        shutil.copy2(layer.state.path, evidence / 'layered-control.json')
        (evidence / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n')
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        layer.close()
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--playwright-root', required=True)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    print(json.dumps(run_fixture(Path(args.playwright_root).resolve(), Path(args.evidence).resolve()), indent=2))


if __name__ == '__main__':
    main()
